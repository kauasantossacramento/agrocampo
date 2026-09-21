"""Silvinha: monta o contexto da loja e conversa com o Gemini.

A assistente só sabe o que está no banco: catálogo publicado, cidades
atendidas, horário e contato. Nada de inventar prazo ou produto — a
instrução é explícita e o catálogo vai no prompt, filtrado pelo que o
cliente perguntou, para caber na janela e no custo.
"""
import re
from decimal import Decimal

from django.conf import settings
from django.db.models import Q

from apps.catalog.models import Produto
from apps.core.models import SiteConfig
from apps.shipping.models import Cidade

from . import gemini
from .models import ConversaAssistente

MAX_HISTORICO = 8         # mensagens anteriores que vão para o modelo
MAX_PRODUTOS = 8          # produtos por resposta no contexto
LIMITE_POR_HORA = 40      # perguntas por sessão/hora — segura custo e abuso
PALAVRAS_IGNORADAS = {
    "de", "da", "do", "para", "pra", "com", "sem", "uma", "um", "que", "qual",
    "tem", "vocês", "voces", "você", "voce", "the", "meu", "minha", "por",
    "como", "quanto", "custa", "preço", "preco", "valor", "onde", "quero",
}


def _palavras(texto: str) -> list[str]:
    termos = re.findall(r"[a-zà-ú0-9]{3,}", texto.lower())
    return [t for t in termos if t not in PALAVRAS_IGNORADAS][:6]


def produtos_relacionados(pergunta: str, produto_atual=None):
    """Produtos publicados que batem com as palavras da pergunta."""
    palavras = _palavras(pergunta)
    qs = Produto.objects.vitrine().select_related("categoria", "marca")
    if palavras:
        filtro = Q()
        for p in palavras:
            filtro |= (
                Q(nome__icontains=p) | Q(resumo__icontains=p)
                | Q(categoria__nome__icontains=p) | Q(marca__nome__icontains=p)
                | Q(especies__nome__icontains=p)
            )
        encontrados = list(qs.filter(filtro).distinct().order_by("-vendas")[:MAX_PRODUTOS])
    else:
        encontrados = []
    if not encontrados:
        # sem match, manda os mais vendidos: ela precisa de algo para sugerir
        encontrados = list(qs.order_by("-vendas", "-destaque")[:MAX_PRODUTOS])
    if produto_atual and produto_atual not in encontrados:
        encontrados.insert(0, produto_atual)
    return encontrados[:MAX_PRODUTOS + 1]


def _linha_produto(p: Produto) -> str:
    preco = p.preco_atual
    partes = [f"- {p.nome} — R$ {preco:.2f}".replace(".", ",")]
    if p.promocao_vigente:
        partes.append("(em promoção)")
    if p.linha:
        partes.append(f"[linha {p.get_linha_display()}]")
    if p.tem_variacoes:
        tamanhos = ", ".join(str(v) for v in p.variacoes_disponiveis[:6])
        partes.append(f"tamanhos: {tamanhos}")
    if p.permite_assinatura:
        partes.append(f"assinatura por R$ {p.preco_assinatura:.2f}".replace(".", ","))
    partes.append("· em estoque" if p.em_estoque else "· SEM estoque")
    if settings.SITE_URL:
        partes.append(f"· link: {settings.SITE_URL}{p.get_absolute_url()}")
    if p.resumo:
        partes.append(f"\n  {p.resumo[:160]}")
    return " ".join(partes)


def montar_instrucoes(pergunta: str, produto_atual=None) -> str:
    config = SiteConfig.load()
    nome = config.assistente_nome or "Silvinha"

    blocos = [
        f"Você é {nome}, atendente virtual da loja {config.nome_loja} "
        "(ração, saúde animal, aves, insumos rurais). Fale em português do Brasil, "
        "de forma calorosa e curta — no máximo 3 parágrafos curtos, sem markdown "
        "pesado (negrito simples com * é ok, nada de tabelas ou títulos).",
        "REGRAS: só cite produtos, preços, cidades e prazos que estejam neste "
        "contexto. Se não souber, diga que não tem essa informação e ofereça o "
        "WhatsApp da loja. Nunca invente estoque, preço ou prazo. Não dê "
        "diagnóstico veterinário: para sintomas, oriente a procurar um veterinário. "
        "Quando indicar um produto, inclua o link dele.",
    ]

    contato = []
    if config.whatsapp:
        contato.append(f"WhatsApp da loja: {config.whatsapp}")
    if config.telefone:
        contato.append(f"telefone: {config.telefone}")
    if config.horario_atendimento:
        contato.append(f"horário: {config.horario_atendimento}")
    if config.endereco:
        contato.append(f"endereço: {config.endereco}, {config.cidade_uf}")
    if contato:
        blocos.append("CONTATO — " + " · ".join(contato))

    cidades = list(Cidade.objects.atendidas().prefetch_related("localidades"))
    if cidades:
        linhas = []
        for c in cidades:
            texto = f"- {c.nome}/{c.uf}: frete R$ {c.frete:.2f}".replace(".", ",")
            texto += f", entrega {c.dias_legivel}"
            if c.horario_a_partir_de or config.entrega_a_partir_de:
                h = c.horario_a_partir_de or config.entrega_a_partir_de
                texto += f", a partir das {h:%H:%M}"
            ilhas = [l.nome for l in c.localidades.all() if l.ativo]
            if ilhas:
                texto += f". Localidades com acréscimo: {', '.join(ilhas[:8])}"
            if c.observacao:
                texto += f". {c.observacao}"
            linhas.append(texto)
        blocos.append("ENTREGA (cidades atendidas):\n" + "\n".join(linhas))
        if config.frete_gratis_acima_de:
            blocos.append(
                f"Frete grátis em compras acima de R$ {config.frete_gratis_acima_de:.2f}".replace(".", ",")
            )
    else:
        blocos.append(
            "ENTREGA: a lista de cidades ainda não foi cadastrada. Diga que a loja "
            "confirma a entrega pelo WhatsApp."
        )
    if config.aviso_entrega:
        blocos.append(f"AVISO DE ENTREGA: {config.aviso_entrega}")

    produtos = produtos_relacionados(pergunta, produto_atual)
    if produto_atual:
        blocos.append(
            f"O CLIENTE ESTÁ NA PÁGINA DO PRODUTO: {produto_atual.nome}. "
            f"Descrição: {(produto_atual.descricao or produto_atual.resumo or '')[:600]}"
        )
    if produtos:
        blocos.append("PRODUTOS RELEVANTES:\n" + "\n".join(_linha_produto(p) for p in produtos))

    if config.assistente_instrucoes:
        blocos.append("ORIENTAÇÕES DO LOJISTA:\n" + config.assistente_instrucoes)

    return "\n\n".join(blocos)


def responder(*, sessao: str, pergunta: str, historico: list[dict],
              produto=None, usuario=None) -> dict:
    """Ponto único da view. Devolve {"texto": ..., "ok": bool}."""
    config = SiteConfig.load()
    registro = ConversaAssistente(
        sessao=sessao, usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
        produto=produto, pergunta=pergunta, modelo=config.gemini_modelo,
    )

    # fallback honesto quando não há chave: ainda ajuda com o WhatsApp
    if not config.gemini_api_key:
        texto = _resposta_sem_ia(config)
        registro.resposta, registro.falhou, registro.erro = texto, True, "Sem chave do Gemini."
        registro.save()
        return {"texto": texto, "ok": False}

    instrucoes = montar_instrucoes(pergunta, produto)
    mensagens = [m for m in historico[-MAX_HISTORICO:] if m.get("texto")]
    mensagens.append({"papel": "usuario", "texto": pergunta})

    try:
        texto = gemini.gerar_resposta(
            chave=config.gemini_api_key,
            modelo=config.gemini_modelo or "gemini-2.5-flash",
            instrucoes=instrucoes,
            historico=mensagens,
        )
        registro.resposta = texto
        ok = True
    except gemini.GeminiErro as exc:
        texto = _resposta_sem_ia(config, indisponivel=True)
        registro.resposta, registro.falhou, registro.erro = texto, True, str(exc)[:300]
        ok = False

    registro.save()
    return {"texto": texto, "ok": ok}


def _resposta_sem_ia(config, indisponivel=False) -> str:
    nome = config.assistente_nome or "Silvinha"
    inicio = (
        f"Desculpa, estou com dificuldade para responder agora."
        if indisponivel
        else f"Oi! Eu sou a {nome}, mas ainda estou aprendendo."
    )
    if config.whatsapp:
        return f"{inicio} Fale direto com a loja pelo WhatsApp {config.whatsapp} que a equipe te atende rapidinho."
    return f"{inicio} Use a busca do site ou fale com a loja pela página de contato."
