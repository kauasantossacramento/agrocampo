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
LINK_PRODUTO = re.compile(r"https?://[^\s)]*/produto/([\w-]+)/?")
URL_QUALQUER = re.compile(r"https?://[^\s)\]]+")
# o modelo às vezes escreve [Nome](codigo) ou [Nome](url) em markdown
LINK_MD = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
ACAO_COMPRAR = re.compile(r"\[\[\s*COMPRAR\s+codigo=([\w-]+)\s+qtd=(\d+)(?:\s+assinar=(\d+))?\s*\]\]", re.I)
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
    """Produtos publicados que batem com a pergunta, os mais aderentes primeiro.

    Usa a mesma busca do site (sinônimos, plural, sem acento, começo de
    palavra): antes a Silvinha tinha uma busca própria, mais crua, e numa
    pergunta sobre "ração para cachorro filhote" recebia ração de galinha —
    "ração" sozinha casava com tudo. Agora cada palavra vale um ponto, e
    vence quem casa com mais palavras; palavra que não acha produto nenhum
    ("entrega", "Valença") simplesmente não pontua.
    """
    from django.db.models import Case, IntegerField, Value, When

    from apps.catalog.views import _condicao_de_busca, _palavras_da_busca

    qs = Produto.objects.vitrine().select_related("categoria", "marca")
    palavras = [p for p in _palavras_da_busca(pergunta) if p not in PALAVRAS_IGNORADAS][:8]
    encontrados = []
    if palavras:
        pontos = Value(0)
        for palavra in palavras:
            pontos = pontos + Case(
                When(_condicao_de_busca(palavra), then=Value(1)),
                default=Value(0), output_field=IntegerField(),
            )
        encontrados = list(
            qs.annotate(_pontos=pontos).filter(_pontos__gt=0)
            .order_by("-_pontos", "-prioridade_busca", "-vendas")[:MAX_PRODUTOS]
        )
    if not encontrados:
        # sem match, manda os mais vendidos: ela precisa de algo para sugerir
        encontrados = list(qs.order_by("-vendas", "-destaque")[:MAX_PRODUTOS])
    if produto_atual and produto_atual not in encontrados:
        encontrados.insert(0, produto_atual)
    return encontrados[:MAX_PRODUTOS + 1]


def _texto_limpo(texto: str, limite: int) -> str:
    """Descrição sem HTML nem espaço sobrando, cortada no fim de uma frase."""
    import html

    texto = html.unescape(re.sub(r"<[^>]+>", " ", texto or ""))
    texto = " ".join(texto.split())
    if len(texto) <= limite:
        return texto
    corte = texto.rfind(". ", 0, limite)
    return texto[: corte + 1 if corte > limite * 0.6 else limite].rstrip() + " …"


def _detalhe_produto(p: Produto) -> str:
    """A ficha que a Silvinha usa para responder sobre um produto: a linha de
    sempre mais as observações do cadastro (descrição, benefícios,
    composição) e para quais animais ele é."""
    partes = [_linha_produto(p)]
    animais = ", ".join(e.nome for e in p.especies.all()[:6])
    if animais:
        partes.append(f"  Para: {animais}.")
    if p.marca_id:
        partes.append(f"  Marca: {p.marca.nome}.")
    if p.descricao:
        partes.append("  Observações do cadastro: " + _texto_limpo(p.descricao, 900))
    if p.beneficios:
        partes.append("  Benefícios: " + _texto_limpo(p.beneficios, 300))
    if p.composicao:
        partes.append("  Composição: " + _texto_limpo(p.composicao, 300))
    return "\n".join(partes)


def catalogo_resumido() -> str:
    """Uma linha por produto à venda, para ela saber o que a loja tem.

    Sem a descrição (seriam ~60 mil tokens por pergunta); a descrição vai só
    dos produtos ligados à conversa. Guardado 5 minutos.
    """
    from django.core.cache import cache

    texto = cache.get("assistente:catalogo")
    if texto is not None:
        return texto
    linhas = []
    for p in (Produto.objects.vitrine().select_related("categoria", "linha")
              .prefetch_related("especies").order_by("categoria__nome", "nome")):
        animais = "/".join(e.nome for e in p.especies.all()[:3]) or "—"
        preco = f"R$ {p.preco_atual:.2f}".replace(".", ",")
        estoque = "" if p.em_estoque else " · SEM estoque"
        linha = f" · {p.linha_nome}" if p.linha_id else ""
        linhas.append(f"- {p.nome} · {preco} · {animais}{linha}{estoque} · codigo: {p.slug}")
    texto = "\n".join(linhas)
    cache.set("assistente:catalogo", texto, 300)
    return texto


def _linha_produto(p: Produto) -> str:
    preco = p.preco_atual
    partes = [f"- {p.nome} — R$ {preco:.2f}".replace(".", ",")]
    if p.promocao_vigente:
        partes.append("(em promoção)")
    if p.linha_id:
        partes.append(f"[linha {p.linha_nome}]")
    if p.tem_variacoes:
        tamanhos = ", ".join(str(v) for v in p.variacoes_disponiveis[:6])
        partes.append(f"tamanhos: {tamanhos}")
    if p.permite_assinatura:
        partes.append(f"assinatura por R$ {p.preco_assinatura:.2f}".replace(".", ","))
    partes.append("· em estoque" if p.em_estoque else "· SEM estoque")
    if settings.SITE_URL:
        partes.append(f"· link: {settings.SITE_URL}{p.get_absolute_url()}")
    partes.append(f"· codigo: {p.slug}")
    if p.resumo:
        partes.append(f"\n  {p.resumo[:160]}")
    return " ".join(partes)


def montar_instrucoes(pergunta: str, produto_atual=None, historico=None) -> str:
    config = SiteConfig.load()
    nome = config.assistente_nome or "Silvinha"

    blocos = [
        f"Você é {nome}, atendente virtual da {config.nome_loja}"
        + (f", em {config.cidade_uf}" if config.cidade_uf else "")
        + ": uma loja agropecuária e pet que vende ração, saúde animal, "
        "acessórios e insumos para o campo, com entrega na cidade e na zona "
        "rural. Fale em português do Brasil, como uma atendente de balcão "
        "experiente: simpática, direta e prática. No máximo 3 frases curtas por "
        "parágrafo e 2 parágrafos, sem markdown pesado (negrito simples com * é "
        "ok, nada de tabelas ou títulos).",
        # Medido em 04/11/2026: a cada "Oi" ela se apresentava de novo e
        # improvisava frases fora de lugar ("como posso te dar uma historinha
        # hoje?"). A apresentação já está no balão de boas-vindas.
        "CONVERSA: você JÁ se apresentou na primeira mensagem da conversa — não "
        "repita seu nome nem dê boas-vindas de novo. Se o cliente só cumprimentar, "
        "responda em uma frase e pergunte qual animal ele tem ou o que está "
        "procurando. Responda exatamente o que foi perguntado. Nada de "
        "expressões infantis, trocadilhos ou frases de efeito; nada de emojis "
        "em excesso (no máximo um, e só se couber).",
        "REGRAS: só cite produtos, preços, cidades e prazos que estejam neste "
        "contexto. Se não souber, diga que não tem essa informação e ofereça o "
        "WhatsApp da loja. Nunca invente estoque, preço ou prazo. Não dê "
        "diagnóstico veterinário: para sintomas, oriente a procurar um veterinário. "
        "Quando indicar um produto, diga na frase o nome e o preço dele e escreva "
        "o link completo (começando com http), sem markdown de link — o site "
        "transforma o link num cartão com foto. Nunca diga \"qual das opções\" "
        "sem ter dito antes quais são.",
        "COMPRA PELO CHAT: você consegue iniciar a compra. Quando o cliente disser "
        "que quer comprar/levar/pedir um produto específico que está neste contexto, "
        "confirme o produto e a quantidade (pergunte a quantidade se ele não disse) e, "
        "assim que estiver claro, termine a resposta com uma linha exatamente neste "
        "formato, usando o codigo do produto: [[COMPRAR codigo=<codigo> qtd=<numero>]]. "
        "Só use essa linha para produtos em estoque listados aqui. Não invente códigos. "
        "Se o cliente quiser ASSINAR (receber de novo a cada 30, 60 ou 90 dias) um produto "
        "marcado como 'assinatura', acrescente assinar=<dias> na mesma linha. "
        "Diga em uma frase que o botão de compra vai aparecer na conversa.",
    ]

    # o que a loja é e como ela vende: sem isto a assistente falava de uma
    # loja genérica e não sabia oferecer assinatura, Pix ou as linhas da casa
    from apps.catalog.models import Categoria, Especie, LinhaProduto

    categorias = list(Categoria.objects.publicados().values_list("nome", flat=True)[:12])
    if categorias:
        blocos.append("CATEGORIAS DA LOJA: " + ", ".join(categorias) + ".")
    animais = list(Especie.objects.navegaveis().values_list("nome", flat=True)[:16])
    if animais:
        blocos.append("ANIMAIS ATENDIDOS: " + ", ".join(animais) + ".")
    linhas = list(LinhaProduto.objects.filter(ativo=True).values_list("nome", flat=True))
    if linhas:
        blocos.append(
            "LINHAS DE PRODUTO (qualidade, da mais alta para a de entrada, na ordem "
            "do cadastro): " + ", ".join(linhas) + ". Use para orientar quem pede "
            "indicação por faixa de preço ou qualidade."
        )
    vantagens = []
    if config.desconto_pix:
        vantagens.append(f"{config.desconto_pix}% de desconto pagando no Pix")
    if getattr(config, "assinatura_visivel", True):
        vantagens.append(
            "assinatura: o cliente recebe o mesmo produto de novo a cada 30, 60 ou "
            "90 dias, sem precisar pedir, e pode cancelar quando quiser"
        )
    vantagens.append("entrega também na zona rural")
    blocos.append("COMO A LOJA VENDE: " + "; ".join(vantagens) + ".")

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

    # a busca olha também as últimas falas do cliente: "e esse serve para
    # filhote?" não cita o produto, mas a mensagem anterior citou
    anteriores = [m.get("texto", "") for m in (historico or [])[-4:] if m.get("papel") == "usuario"]
    produtos = produtos_relacionados(" ".join(anteriores[-2:] + [pergunta]), produto_atual)
    if produto_atual:
        blocos.append(
            f"O CLIENTE ESTÁ NA PÁGINA DO PRODUTO: {produto_atual.nome}. "
            f"Descrição: {(produto_atual.descricao or produto_atual.resumo or '')[:600]}"
        )
    catalogo = catalogo_resumido()
    if catalogo:
        blocos.append(
            "CATÁLOGO COMPLETO DA LOJA (uma linha por produto à venda; use para saber "
            "o que existe, sugerir alternativas e responder 'vocês têm…?'):\n" + catalogo
        )
    if produtos:
        blocos.append(
            "PRODUTOS LIGADOS À PERGUNTA, COM AS OBSERVAÇÕES DO CADASTRO — responda sobre "
            "cada produto de acordo com essas observações (indicação, idade, porte, modo de "
            "uso, cuidados). Se a resposta não estiver nas observações, diga que não tem essa "
            "informação e ofereça o WhatsApp da loja; nunca invente:\n"
            + "\n\n".join(_detalhe_produto(p) for p in produtos)
        )

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

    instrucoes = montar_instrucoes(pergunta, produto, historico)
    mensagens = [m for m in historico[-MAX_HISTORICO:] if m.get("texto")]
    mensagens.append({"papel": "usuario", "texto": pergunta})

    acao = None
    try:
        texto = gemini.gerar_resposta(
            chave=config.gemini_api_key,
            modelo=config.gemini_modelo or "gemini-3.6-flash",
            instrucoes=instrucoes,
            historico=mensagens,
        )
        texto, acao = extrair_acao(texto)
        registro.resposta = texto
        ok = True
    except gemini.GeminiErro as exc:
        texto = _resposta_sem_ia(config, indisponivel=True)
        registro.resposta, registro.falhou, registro.erro = texto, True, str(exc)[:300]
        ok = False

    registro.save()
    resposta = {"texto": texto, "ok": ok}
    if ok:
        resposta["texto"], resposta["produtos"] = produtos_citados(texto)
    if acao:
        resposta["acao"] = acao
    return resposta


def produtos_citados(texto: str):
    """Produtos cujo link aparece na resposta viram cartões com foto.

    O link cru sai do texto (o cartão já leva lá) e uma linha que era só
    "- Nome: link" some junto, para não sobrar uma lista de dois-pontos.
    """
    slugs = []
    # markdown [Nome](codigo) / [Nome](url): guarda o código e deixa só o nome
    def _md(m):
        alvo = m.group(2)
        slug = (LINK_PRODUTO.search(alvo).group(1) if LINK_PRODUTO.search(alvo)
                else alvo.strip("/").split("/")[-1])
        if re.fullmatch(r"[\w-]+", slug) and slug not in slugs:
            slugs.append(slug)
        return m.group(1)
    texto = LINK_MD.sub(_md, texto or "")
    # qualquer URL cujo último trecho seja um código de produto (o modelo às
    # vezes troca o domínio): o cartão leva ao endereço certo
    for url in URL_QUALQUER.findall(texto):
        slug = url.rstrip("/").split("/")[-1]
        if re.fullmatch(r"[\w-]+", slug) and slug not in slugs:
            slugs.append(slug)
    if not slugs:
        return texto, []
    encontrados = {p.slug: p for p in Produto.objects.vitrine().filter(slug__in=slugs).prefetch_related("imagens")}
    slugs = [s for s in slugs if s in encontrados]
    if not slugs:
        return texto, []
    cartoes = []
    for slug in slugs:
        p = encontrados.get(slug)
        if not p:
            continue
        foto = p.foto_principal
        cartoes.append({
            "slug": p.slug, "nome": p.nome, "url": p.get_absolute_url(),
            "preco": f"R$ {p.preco_atual:.2f}".replace(".", ","),
            "a_partir": p.tem_variacoes, "foto": foto.url if foto else "",
            "em_estoque": p.em_estoque,
        })
    if not cartoes:
        return texto, []
    def _tira(m):
        return "" if m.group(0).rstrip("/").split("/")[-1] in encontrados else m.group(0)
    limpo = URL_QUALQUER.sub(_tira, texto)
    linhas = []
    for linha in limpo.splitlines():
        # "- Ração Golden: " (sobrou só o rótulo) ou "Confira nos links:" sem links
        if re.fullmatch(r"\s*[-•*]?\s*[^:]{0,80}:\s*", linha):
            continue
        if re.search(r"\b(links?|neste link|nestes links)\b", linha, re.I) and ":" in linha and not re.search(r"https?://", linha):
            continue
        linhas.append(linha.rstrip())
    limpo = re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()
    return limpo or texto, cartoes


def extrair_acao(texto: str):
    """Tira a marca [[COMPRAR ...]] do texto e devolve a ação estruturada.

    A IA só *propõe*; quem confirma é o cliente, num botão. Produto que não
    existe, sem estoque ou despublicado vira ação nenhuma.
    """
    m = ACAO_COMPRAR.search(texto or "")
    if not m:
        return texto, None
    limpo = ACAO_COMPRAR.sub("", texto).strip()
    produto = Produto.objects.vitrine().filter(slug=m.group(1)).first()
    if not produto or not produto.em_estoque:
        return limpo, None
    qtd = max(1, min(int(m.group(2)), 50))
    assinar = int(m.group(3)) if m.group(3) else 0
    if assinar not in (30, 60, 90) or not produto.permite_assinatura or not SiteConfig.load().assinatura_visivel:
        assinar = 0
    foto = produto.foto_principal
    return limpo, {
        "tipo": "comprar",
        "assinar": assinar,
        "produto": {
            "slug": produto.slug, "nome": produto.nome,
            "preco": f"R$ {produto.preco_atual:.2f}".replace(".", ","),
            "foto": foto.url if foto else "",
            "tem_variacoes": produto.tem_variacoes,
            "variacoes": [
                {"id": v.id, "rotulo": v.rotulo, "preco": f"R$ {v.preco_atual:.2f}".replace(".", ",")}
                for v in produto.variacoes_disponiveis if v.em_estoque
            ] if produto.tem_variacoes else [],
        },
        "quantidade": qtd,
    }


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
