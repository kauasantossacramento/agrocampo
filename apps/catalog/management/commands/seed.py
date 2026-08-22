"""Popula a loja com um catálogo realista para desenvolvimento e demonstração.

    python manage.py seed
    python manage.py seed --limpar   # apaga e recria o conteúdo de exemplo

Reaproveita as imagens do mockup em `media/seed/`.
"""
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.blog.models import CategoriaPost, Post
from apps.catalog.models import Categoria, Especie, Marca, Produto, ProdutoImagem
from apps.core.models import Banner, Diferencial, Pagina, SiteConfig
from apps.payments.models import ProvedorPagamento

SEED_DIR = Path(settings.MEDIA_ROOT) / "seed"

CATEGORIAS = [
    ("Ração & Alimentação", "racao", ["Cães", "Gatos", "Extrusados", "Farinhadas"]),
    ("Aves & Pássaros", "ave", ["Sementes", "Misturas", "Alimentação manual", "Gaiolas"]),
    ("Rural & Fazenda", "rural", ["Sal mineral", "Cercas e currais", "Ferramentas"]),
    ("Saúde Animal", "saude", ["Vermífugos", "Suplementos", "Antiparasitários", "Desinfetantes"]),
    ("Acessórios", "acessorio", ["Comedouros", "Bebedouros", "Higiene", "Brinquedos"]),
    ("Casa e Jardim", "jardim", ["Sementes de horta", "Adubos"]),
]

# A ordem manda na home: cão e gato vêm primeiro porque são o que mais
# gente procura numa loja de ração. Antes eles ficavam depois de 20 pássaros
# e nunca apareciam na vitrine.
ESPECIES = [
    ("Cão", "pet", "🐕"), ("Gato", "pet", "🐈"),
    ("Peixe", "pet", "🐠"), ("Roedor", "pet", "🐹"),
    ("Canário", "passeriforme", "🐤"), ("Calopsita", "psitacideo", "🦜"),
    ("Coleiro", "passeriforme", "🐦"), ("Periquito", "psitacideo", "🦜"),
    ("Curió", "passeriforme", "🐦"), ("Papagaio", "psitacideo", "🦜"),
    ("Bovino", "rural", "🐄"), ("Galinha", "rural", "🐓"),
    ("Equino", "rural", "🐴"), ("Suíno", "rural", "🐖"),
    ("Azulão", "passeriforme", "🐦"), ("Cardeal", "passeriforme", "🐦"),
    ("Sabiá", "passeriforme", "🐦"), ("Mandarim", "passeriforme", "🐤"),
    ("Caboclinho", "passeriforme", "🐦"), ("Patativa", "passeriforme", "🐦"),
    ("Bigodinho", "passeriforme", "🐦"), ("Trinca-ferro", "passeriforme", "🐦"),
    ("Pintassilgo", "passeriforme", "🐤"), ("Bicudo", "passeriforme", "🐦"),
    ("Agapornis", "psitacideo", "🦜"), ("Arara", "psitacideo", "🦜"),
    ("Ring Neck", "psitacideo", "🦜"), ("Rosella", "psitacideo", "🦜"),
]

MARCAS = [
    "Golden Fórmula", "Special Dog", "Alcon", "Nutrópica", "Biotron",
    "Christino", "Megazoo", "Suplex", "Premier Pet", "Guabi",
    "Total Alimentos", "Nekton", "Zoetis", "Vetnil", "Ourofino",
]

# (nome, categoria, marca, preço, promo, estoque, assinável, destaque, lançamento, imagem, resumo)
PRODUTOS = [
    ("Ração Golden Fórmula Adulto Raças Médias e Grandes 15kg", "Ração & Alimentação", "Golden Fórmula",
     "289.90", "259.90", 23, True, True, False, "pasted-1785783061543-0.png",
     "Carne de frango de verdade como primeiro ingrediente. Rende cerca de 45 dias."),
    ("Ração Special Dog Puppy 10,1kg", "Ração & Alimentação", "Special Dog",
     "149.90", None, 40, True, True, False, None,
     "Para filhotes em fase de crescimento, com DHA para o desenvolvimento cognitivo."),
    ("Mistura de Sementes Alcon Aves 1kg", "Aves & Pássaros", "Alcon",
     "34.90", "27.90", 85, True, True, False, "pasted-1785783136452-0.png",
     "Mistura balanceada de sementes selecionadas para pássaros silvestres."),
    ("Sal Mineral Bovino Fósforo 30 · 25kg", "Rural & Fazenda", "Ourofino",
     "119.90", None, 12, True, True, False, "pasted-1785783167342-0.png",
     "Suplementação mineral completa para bovinos de corte e leite a pasto."),
    ("Comedouro Automático Pet Duplo Inox", "Acessórios", "Premier Pet",
     "79.90", "64.90", 30, False, True, True, "pasted-1785783190822-0.png",
     "Reservatório duplo em inox, ideal para quem passa o dia fora."),
    ("Suplemento Vitamínico Aviário Suplex 100ml", "Saúde Animal", "Suplex",
     "28.50", None, 4, True, False, False, None,
     "Complexo vitamínico para aves em muda de penas e reprodução."),
    ("Areia Higiênica Gato Limpo 4kg", "Acessórios", "Premier Pet",
     "39.90", None, 0, True, False, False, None,
     "Alta absorção e controle de odor por até 7 dias."),
    ("Cerca Elétrica Rural Kit Completo", "Rural & Fazenda", "Christino",
     "349.90", None, 8, False, True, False, None,
     "Kit com eletrificador, isoladores e fio para até 5 km de cerca."),
    ("Farinhada Nutrópica Premium 500g", "Aves & Pássaros", "Nutrópica",
     "42.90", None, 55, True, False, True, None,
     "Farinhada úmida enriquecida, ideal para o período de cria."),
    ("Vermífugo Bovino Injetável 500ml", "Saúde Animal", "Zoetis",
     "189.90", "159.90", 15, False, False, False, None,
     "Amplo espectro contra endo e ectoparasitas do rebanho."),
    ("Ração Extrusada Premier Gato Castrado 7,5kg", "Ração & Alimentação", "Premier Pet",
     "219.90", None, 26, True, True, False, None,
     "Controle de peso e saúde urinária para gatos castrados."),
    ("Bebedouro Automático para Aves 2L", "Acessórios", "Megazoo",
     "36.90", None, 48, False, False, True, None,
     "Sistema antigotejamento, fácil de higienizar."),
    ("Núcleo Mineral Equino 20kg", "Rural & Fazenda", "Guabi",
     "249.90", None, 9, True, False, False, None,
     "Formulação específica para cavalos em atividade moderada a intensa."),
    ("Ninho de Madeira para Calopsita", "Aves & Pássaros", "Christino",
     "58.90", None, 22, False, False, False, None,
     "Madeira tratada, com tampa removível para inspeção dos filhotes."),
    ("Desinfetante Concentrado para Canil 5L", "Saúde Animal", "Vetnil",
     "94.90", "79.90", 18, True, False, False, None,
     "Bactericida, fungicida e viruscida — diluição de 1:100."),
    ("Osso de Siba Natural (pacote com 5)", "Aves & Pássaros", "Nutrópica",
     "18.90", None, 120, False, False, False, None,
     "Fonte natural de cálcio para a formação da casca do ovo e do bico."),
]

DIFERENCIAIS = [
    ("Frete para toda zona rural", "Entregamos onde outros não chegam", "caminhao"),
    ("Pix aprovado na hora", "5% de desconto à vista", "raio"),
    ("Assinatura com 10% OFF", "Nunca falta o essencial", "refresh"),
    ("Compra 100% garantida", "Ambiente seguro e criptografado", "escudo"),
]

PAGINAS = [
    ("Quem somos", 1, "<mark>Texto de exemplo — substitua pela história real da loja.</mark> "
     "Descreva aqui quando a AgroCampo começou, quem toca o negócio e o que "
     "diferencia o atendimento de vocês."),
    ("Entregas e prazos", 2, "Entregamos em toda a região, inclusive na zona rural. "
     "Pedidos aprovados até as 14h saem no mesmo dia. Para endereços rurais, "
     "combinamos o ponto de entrega por WhatsApp antes de sair."),
    ("Trocas e devoluções", 3, "Você tem 7 dias corridos para desistir da compra, conforme "
     "o Código de Defesa do Consumidor. Produtos lacrados podem ser trocados em até 30 dias. "
     "Rações abertas só são aceitas em caso de defeito comprovado."),
    ("Central de atendimento", 4, "Fale com a gente por WhatsApp, telefone ou e-mail. "
     "Atendemos de segunda a sexta, das 8h às 18h, e aos sábados das 8h às 12h."),
    ("Política de privacidade", 5, "Seus dados são usados apenas para processar pedidos e "
     "melhorar sua experiência. Não vendemos nem compartilhamos suas informações. "
     "Os dados de cartão são tokenizados pela Stone e nunca ficam armazenados na loja."),
]

POSTS = [
    ("Retenção de ovo em aves: como identificar e agir", "Saúde",
     "A retenção de ovo é uma emergência silenciosa. Saiba reconhecer os sinais e o que fazer nas primeiras horas.",
     "A retenção de ovo acontece quando a fêmea não consegue expelir o ovo formado. "
     "É mais comum em fêmeas jovens, em dietas pobres em cálcio ou em ambientes frios.\n\n"
     "<h3>Sinais de alerta</h3><p>Ave arrepiada no fundo da gaiola, respiração ofegante, "
     "abdômen dilatado e esforço visível sem resultado.</p>"
     "<h3>O que fazer</h3><p>Aqueça o ambiente para cerca de 30 °C, ofereça cálcio líquido e "
     "procure um veterinário. Nunca tente retirar o ovo manualmente — o risco de ruptura é alto.</p>"),
    ("Verminose bovina: o calendário que realmente funciona", "Manejo",
     "Vermifugar na hora errada custa caro. Veja como montar o calendário estratégico para o seu rebanho.",
     "<p>O controle estratégico substitui a vermifugação por calendário fixo pela vermifugação "
     "no momento de maior carga parasitária — normalmente no início e no fim da seca.</p>"
     "<h3>Três aplicações estratégicas</h3><p>Maio, julho e setembro concentram o resultado na "
     "maior parte do Brasil central. Ajuste conforme o histórico da sua região.</p>"),
    ("Como escolher a ração certa para o seu cão", "Nutrição",
     "Porte, idade e nível de atividade mudam completamente a necessidade nutricional. Um guia direto ao ponto.",
     "<p>O primeiro ingrediente da lista deve ser proteína animal nomeada — 'carne de frango', "
     "não 'farinha de origem animal'.</p>"
     "<h3>Porte importa</h3><p>Raças grandes precisam de grânulos maiores e de suporte articular; "
     "raças pequenas precisam de mais energia por grama.</p>"),
]


class Command(BaseCommand):
    help = "Popula a loja com dados de exemplo (catálogo, banners, blog e páginas)."

    def add_arguments(self, parser):
        parser.add_argument("--limpar", action="store_true", help="Apaga o conteúdo antes de recriar.")
        parser.add_argument("--com-sem-imagem", action="store_true",
                            help="Cria também os produtos de exemplo que não têm foto.")

    @transaction.atomic
    def handle(self, *args, **opcoes):
        if opcoes["limpar"]:
            self.stdout.write("Limpando conteúdo existente...")
            Produto.objects.all().delete()
            Categoria.objects.all().delete()
            Marca.objects.all().delete()
            Especie.objects.all().delete()
            Post.objects.all().delete()
            Banner.objects.all().delete()

        self._config()
        self._provedor()
        categorias = self._categorias()
        marcas = self._marcas()
        especies = self._especies()
        self._produtos(categorias, marcas, especies, opcoes)
        self._entrega()
        self._banners()
        self._diferenciais()
        self._paginas()
        self._blog()

        self.stdout.write(self.style.SUCCESS("\nCatálogo populado com sucesso."))
        self.stdout.write("Crie um operador com: python manage.py createsuperuser")

    # ------------------------------------------------------------------
    def _entrega(self):
        """Cria só a cidade sede.

        Valença/BA é a única informação de entrega que veio do lojista, e por
        isso a cidade nasce **desativada**: com frete 0,00 e ativa, a loja
        estaria anunciando entrega grátis — um preço que ninguém combinou.
        O lojista define o valor e liga a cidade no painel.
        """
        from apps.shipping.models import Cidade

        cidade, criada = Cidade.objects.get_or_create(
            nome="Valença", uf="BA",
            defaults={
                "sede": True,
                "frete": Decimal("0.00"),
                "prazo_dias": 0,
                "ativo": False,
                "observacao": "",
            },
        )
        if criada:
            # o console do Windows usa cp1252: seta e travessao quebram aqui
            self.stdout.write(
                "  1 cidade (Valenca/BA) DESATIVADA - defina o frete e ative em "
                "Painel > Entrega > Cidades atendidas"
            )

    # ------------------------------------------------------------------
    def _config(self):
        config = SiteConfig.load()
        config.nome_loja = "Veterinária AgroCampo"
        config.ano_fundacao = 2012          # conforme o CNPJ
        # Contato NAO e semeado de proposito. O telefone que estava aqui era
        # o do site que serviu de referencia (Terra dos Passaros) — publicar
        # isso mandaria cliente da AgroCampo para um terceiro.
        # O lojista preenche em: Admin > Configuracao da loja.
        config.save()
        self.stdout.write("  configuração da loja")

    def _provedor(self):
        provedor, criado = ProvedorPagamento.objects.get_or_create(
            nome="Stone",
            defaults={
                "driver": ProvedorPagamento.Driver.SIMULADO,
                "ambiente": ProvedorPagamento.Ambiente.SANDBOX,
                "padrao": True,
                "ativo": True,
                "stone_pix_chave": "contato@agrocampo.com.br",
            },
        )
        # bootstrap opcional a partir do .env
        bootstrap = getattr(settings, "STONE_BOOTSTRAP", {})
        if criado and bootstrap.get("api_key"):
            provedor.driver = ProvedorPagamento.Driver.STONE
            provedor.ambiente = bootstrap.get("environment", "sandbox")
            provedor.stone_client_id = bootstrap.get("client_id", "")
            provedor.stone_client_secret = bootstrap.get("client_secret", "")
            provedor.stone_api_key = bootstrap.get("api_key", "")
            provedor.stone_merchant_id = bootstrap.get("merchant_id", "")
            provedor.stone_affiliation_code = bootstrap.get("affiliation_code", "")
            provedor.stone_webhook_secret = bootstrap.get("webhook_secret", "")
            provedor.stone_pix_chave = bootstrap.get("pix_key", "") or provedor.stone_pix_chave
            provedor.save()
        self.stdout.write(f"  provedor de pagamento ({provedor.get_driver_display()})")

    def _categorias(self):
        mapa = {}
        for ordem, (nome, icone, filhas) in enumerate(CATEGORIAS):
            pai, criado = Categoria.objects.get_or_create(
                nome=nome,
                pai=None,
                defaults={"icone": icone, "ordem": ordem, "destaque_home": True},
            )
            # `defaults` só vale na criação; sem isto, uma categoria antiga
            # ficaria com o emoji de antes da troca para SVG.
            if not criado and pai.icone != icone:
                pai.icone = icone
                pai.save(update_fields=["icone"])
            mapa[nome] = pai
            for i, filha in enumerate(filhas):
                Categoria.objects.get_or_create(
                    nome=filha, pai=pai, defaults={"ordem": i, "exibir_no_menu": True}
                )
        self.stdout.write(f"  {Categoria.objects.count()} categorias")
        return mapa

    def _marcas(self):
        mapa = {}
        for ordem, nome in enumerate(MARCAS):
            marca, _ = Marca.objects.get_or_create(nome=nome, defaults={"ordem": ordem})
            mapa[nome] = marca
        self.stdout.write(f"  {len(mapa)} marcas")
        return mapa

    def _especies(self):
        mapa = {}
        for ordem, (nome, grupo, icone) in enumerate(ESPECIES):
            especie, criada = Especie.objects.get_or_create(
                nome=nome,
                defaults={"grupo": grupo, "icone": icone, "ordem": ordem,
                          "destaque_home": ordem < 24},
            )
            if not criada:
                # a ordem mudou: sem isso, quem já rodou o seed ficaria com
                # cão e gato fora da vitrine para sempre
                especie.ordem = ordem
                especie.destaque_home = ordem < 24
                especie.save(update_fields=["ordem", "destaque_home"])
            mapa[nome] = especie
        self.stdout.write(f"  {len(mapa)} espécies")
        return mapa

    def _produtos(self, categorias, marcas, especies, opcoes=None):
        opcoes = opcoes or {}
        vinculos = {
            "Ração & Alimentação": ["Cão", "Gato"],
            "Aves & Pássaros": ["Canário", "Calopsita", "Coleiro", "Curió", "Periquito"],
            "Rural & Fazenda": ["Bovino", "Equino", "Suíno"],
            "Saúde Animal": ["Cão", "Bovino", "Canário"],
            "Acessórios": ["Cão", "Gato", "Calopsita"],
        }
        for i, dados in enumerate(PRODUTOS, start=1):
            (nome, cat, marca, preco, promo, estoque, assinavel,
             destaque, lancamento, imagem, resumo) = dados

            # produto sem foto nao entra no catalogo: vitrine com placeholder
            # vazio passa impressao de loja abandonada. O lojista cadastra os
            # dele com foto propria pelo painel.
            if not imagem or not (SEED_DIR / imagem).exists():
                if not opcoes.get("com_sem_imagem"):
                    continue

            produto, criado = Produto.objects.get_or_create(
                sku=f"AGC-{i:04d}",
                defaults={
                    "nome": nome,
                    "categoria": categorias[cat],
                    "marca": marcas.get(marca),
                    "resumo": resumo,
                    "descricao": resumo,
                    "beneficios": "\n".join(
                        [
                            "Produto original, com nota fiscal",
                            "Armazenado em local seco e climatizado",
                            "Entrega em toda a região, inclusive zona rural",
                        ]
                    ),
                    "preco": Decimal(preco),
                    "preco_promocional": Decimal(promo) if promo else None,
                    "promocao_ate": timezone.now() + timedelta(days=3 + i) if promo else None,
                    "estoque": estoque,
                    "estoque_minimo": 5,
                    "permite_assinatura": assinavel,
                    "desconto_assinatura_proprio": None,  # segue o percentual global
                    "destaque": destaque,
                    "lancamento": lancamento,
                },
            )
            if not criado:
                continue

            produto.especies.set(
                [especies[e] for e in vinculos.get(cat, []) if e in especies]
            )

            if imagem:
                caminho = SEED_DIR / imagem
                if caminho.exists():
                    with caminho.open("rb") as arquivo:
                        ProdutoImagem.objects.create(
                            produto=produto,
                            imagem=File(arquivo, name=imagem),
                            legenda=nome,
                        )
        self.stdout.write(f"  {Produto.objects.count()} produtos")

    def _banners(self):
        dados = [
            ("Tudo para o campo e para quem você ama cuidar.",
             "Ração, suplementos e equipamentos rurais com entrega rápida — e assinatura recorrente para nunca faltar o essencial.",
             "Frete facilitado para zona rural", "/catalogo/"),
            ("Assine e economize 10% em toda entrega.",
             "Escolha a frequência, receba em casa e pause quando quiser. Sem multa, sem fidelidade.",
             "Assinatura AgroCampo", "/catalogo/?assinatura=1"),
            ("Assinatura, entrega e atendimento de gente que entende do campo.",
             "Produtos de marcas conhecidas, com quem sabe indicar o que serve para cada animal.",
             "Nossa loja", "/pagina/quem-somos/"),
        ]
        for ordem, (titulo, subtitulo, selo, link) in enumerate(dados):
            Banner.objects.get_or_create(
                titulo=titulo,
                defaults={"subtitulo": subtitulo, "selo": selo, "link": link, "ordem": ordem},
            )
        self.stdout.write(f"  {Banner.objects.count()} banners")

    def _diferenciais(self):
        for ordem, (titulo, descricao, icone) in enumerate(DIFERENCIAIS):
            Diferencial.objects.get_or_create(
                titulo=titulo, defaults={"descricao": descricao, "icone": icone, "ordem": ordem}
            )
        self.stdout.write(f"  {Diferencial.objects.count()} diferenciais")

    def _paginas(self):
        for nome, ordem, conteudo in PAGINAS:
            Pagina.objects.get_or_create(
                nome=nome,
                defaults={"ordem_rodape": ordem, "conteudo": f"<p>{conteudo}</p>"},
            )
        self.stdout.write(f"  {Pagina.objects.count()} páginas institucionais")

    def _blog(self):
        cores = {"Saúde": "#D62B20", "Manejo": "#2F9E44", "Nutrição": "#E2A100"}
        for titulo, categoria, resumo, conteudo in POSTS:
            cat, _ = CategoriaPost.objects.get_or_create(
                nome=categoria, defaults={"cor": cores.get(categoria, "#D62B20")}
            )
            Post.objects.get_or_create(
                titulo=titulo,
                defaults={"categoria": cat, "resumo": resumo, "conteudo": conteudo,
                          "tempo_leitura": 5, "destaque": True},
            )
        self.stdout.write(f"  {Post.objects.count()} posts do blog")
