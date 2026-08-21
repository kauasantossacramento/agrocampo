"""Busca fotos de licença livre no Wikimedia Commons para espécies e produtos.

    python manage.py baixar_imagens                 # espécies sem foto
    python manage.py baixar_imagens --produtos      # também tenta os produtos
    python manage.py baixar_imagens --refazer       # substitui as já existentes

Só aceita licenças que permitem reuso (domínio público e Creative Commons).
O crédito volta gravado em `Especie.credito_imagem` e é exibido no site —
CC-BY exige atribuição.
"""
import io
import time

import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageOps

from apps.catalog.models import Especie, Produto, ProdutoImagem

API = "https://commons.wikimedia.org/w/api.php"
UA = "AgroCampo/1.0 (loja veterinaria; contato@agrocampo.com.br)"

# licencas que permitem reuso comercial com atribuicao
LICENCAS_OK = (
    "cc0", "cc-zero", "public domain", "pd-", "cc by", "cc-by",
    "cc by-sa", "cc-by-sa", "attribution",
)
LICENCAS_PROIBIDAS = ("nc", "nd", "fair use", "non-free")

# O Commons devolve muito material que nao serve de retrato: ovos, cranios,
# peles de museu, mapas de distribuicao, ilustracoes antigas, selos. Esta
# lista e o que separa "foto do bicho" de "prancha cientifica".
TITULO_PROIBIDO = (
    "egg", "eggs", "ei ", "oolog", "nest", "nido",
    "skull", "skeleton", "specimen", "taxidermy",
    "museum", "mhnt", "naturalis", "collection",
    "map", "distribution", "range", "chart", "diagram",
    "stamp", "coin", "logo", "sign", "banner",
    "illustration", "drawing", "plate", "lithograph", "engraving",
    "keulemans", "gould", "1800", "1900", "sketch", "painting",
    "feather", "pena", "cage", "gaiola", "aviary interior",
)

# Nome cientifico exibido no site. Separado do termo de busca porque o que
# funciona no Commons ("Labrador Retriever dog") nao e um binomio valido.
NOME_CIENTIFICO = {
    "Canário": "Sicalis flaveola", "Coleiro": "Sporophila caerulescens",
    "Curió": "Sporophila angolensis", "Trinca-ferro": "Saltator similis",
    "Pintassilgo": "Spinus magellanicus", "Bicudo": "Sporophila maximiliani",
    "Azulão": "Cyanoloxia brissonii", "Cardeal": "Paroaria coronata",
    "Sabiá": "Turdus rufiventris", "Mandarim": "Taeniopygia guttata",
    "Caboclinho": "Sporophila bouvreuil", "Patativa": "Sporophila plumbea",
    "Bigodinho": "Sporophila lineola", "Calopsita": "Nymphicus hollandicus",
    "Periquito": "Melopsittacus undulatus", "Papagaio": "Amazona aestiva",
    "Agapornis": "Agapornis roseicollis", "Arara": "Ara ararauna",
    "Ring Neck": "Psittacula krameri", "Rosella": "Platycercus eximius",
    "Cão": "Canis lupus familiaris", "Gato": "Felis catus",
    "Peixe": "Carassius auratus", "Roedor": "Mesocricetus auratus",
    "Bovino": "Bos indicus", "Equino": "Equus caballus",
    "Suíno": "Sus scrofa domesticus", "Galinha": "Gallus gallus domesticus",
}

# nome da especie -> termo de busca (nome cientifico da o melhor resultado)
BUSCA_ESPECIES = {
    "Canário": "Sicalis flaveola",
    "Canário da Terra": "Sicalis flaveola",
    "Coleiro": "Sporophila caerulescens",
    "Curió": "Sporophila angolensis",
    "Trinca-ferro": "Saltator similis green-winged saltator",
    "Pintassilgo": "Spinus magellanicus",
    "Bicudo": "Sporophila maximiliani",
    "Azulão": "Cyanoloxia brissonii",
    "Cardeal": "Paroaria coronata",
    "Sabiá": "Turdus rufiventris rufous-bellied thrush",
    "Mandarim": "Taeniopygia guttata",
    "Caboclinho": "Sporophila bouvreuil",
    "Patativa": "Sporophila plumbea",
    "Bigodinho": "Sporophila lineola",
    "Calopsita": "Nymphicus hollandicus",
    "Periquito": "Melopsittacus undulatus",
    "Papagaio": "Amazona aestiva",
    "Agapornis": "Agapornis roseicollis",
    "Arara": "Ara ararauna",
    "Ring Neck": "Psittacula krameri",
    "Rosella": "Platycercus eximius",
    "Cão": "Labrador Retriever dog",
    "Gato": "Domestic cat portrait",
    "Peixe": "Carassius auratus aquarium",
    "Roedor": "Syrian hamster Mesocricetus auratus",
    "Bovino": "Zebu cattle Bos indicus",
    "Equino": "Horse portrait",
    "Suíno": "Domestic pig piglet farm",
    "Galinha": "Gallus gallus domesticus hen",
}

# produtos genericos (commodities) que uma foto genérica representa de fato.
# Itens de marca ficam de fora: usar foto aleatória neles seria enganoso.
BUSCA_PRODUTOS = {
    "Osso de Siba Natural": "Cuttlebone",
    "Ninho de Madeira": "Nest box bird wooden",
    "Bebedouro Automático para Aves": "Bird drinker waterer",
    "Sal Mineral": "Salt lick mineral",
    "Cerca Elétrica Rural": "Electric fence pasture",
    "Farinhada": "Bird food mixture",
    "Areia Higiênica": "Cat litter",
}


class Command(BaseCommand):
    help = "Baixa imagens de licença livre do Wikimedia Commons."

    def add_arguments(self, parser):
        parser.add_argument("--produtos", action="store_true",
                            help="Também tenta preencher produtos genéricos.")
        parser.add_argument("--refazer", action="store_true",
                            help="Substitui imagens já existentes.")
        parser.add_argument("--limite", type=int, default=0,
                            help="Processa no máximo N itens (0 = todos).")

    # ------------------------------------------------------------------
    def handle(self, *args, **opcoes):
        self.sessao = requests.Session()
        self.sessao.headers.update({"User-Agent": UA})

        self._especies(opcoes)
        if opcoes["produtos"]:
            self._produtos(opcoes)

    # ------------------------------------------------------------------
    def _especies(self, opcoes):
        qs = Especie.objects.all()
        if not opcoes["refazer"]:
            qs = qs.filter(imagem="")
        if opcoes["limite"]:
            qs = qs[: opcoes["limite"]]

        self.stdout.write(self.style.MIGRATE_HEADING(f"Espécies ({qs.count()})"))
        for especie in qs:
            termo = BUSCA_ESPECIES.get(especie.nome)
            if not termo:
                self.stdout.write(f"  - {especie.nome}: sem termo de busca mapeado")
                continue

            achado = self._buscar(termo)
            if not achado:
                self.stdout.write(self.style.WARNING(f"  ! {especie.nome}: nada com licença livre"))
                continue

            conteudo = self._baixar_quadrado(achado["url"], 640)
            if not conteudo:
                self.stdout.write(self.style.WARNING(f"  ! {especie.nome}: falha ao baixar"))
                continue

            especie.imagem.save(f"{especie.slug}.jpg", ContentFile(conteudo), save=False)
            especie.credito_imagem = achado["credito"][:250]
            especie.nome_cientifico = NOME_CIENTIFICO.get(especie.nome, "")
            especie.save()
            self.stdout.write(self.style.SUCCESS(f"  ok {especie.nome} — {achado['licenca']}"))
            time.sleep(0.4)  # cortesia com a API

    def _produtos(self, opcoes):
        qs = Produto.objects.all()
        if not opcoes["refazer"]:
            qs = qs.filter(imagens__isnull=True)

        self.stdout.write(self.style.MIGRATE_HEADING("Produtos genéricos"))
        for produto in qs:
            termo = next(
                (t for chave, t in BUSCA_PRODUTOS.items() if chave.lower() in produto.nome.lower()),
                None,
            )
            if not termo:
                continue

            achado = self._buscar(termo)
            if not achado:
                continue
            conteudo = self._baixar_quadrado(achado["url"], 800)
            if not conteudo:
                continue

            imagem = ProdutoImagem(produto=produto, legenda=achado["credito"][:140])
            imagem.imagem.save(f"{produto.slug}.jpg", ContentFile(conteudo), save=True)
            self.stdout.write(self.style.SUCCESS(f"  ok {produto.nome[:46]} — {achado['licenca']}"))
            time.sleep(0.4)

    # ------------------------------------------------------------------
    def _buscar(self, termo):
        """Primeira imagem do Commons com licença que permite reuso."""
        try:
            resposta = self.sessao.get(API, timeout=25, params={
                "action": "query", "format": "json",
                "prop": "imageinfo", "iiprop": "url|extmetadata|size",
                "iiurlwidth": "1024",
                "generator": "search", "gsrsearch": f"filetype:bitmap {termo}",
                "gsrnamespace": "6", "gsrlimit": "12",
            })
            paginas = resposta.json().get("query", {}).get("pages", {})
        except Exception:
            return None

        # palavras que o titulo precisa conter para o arquivo ser do bicho certo
        chaves = [t.lower() for t in termo.split() if len(t) > 3]

        candidatos = []
        for pagina in sorted(paginas.values(), key=lambda p: p.get("index", 99)):
            titulo = pagina.get("title", "")
            baixo_titulo = titulo.lower()
            info = (pagina.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata", {})
            licenca = (meta.get("LicenseShortName", {}).get("value", "") or "").strip()
            baixa = licenca.lower()

            if any(p in baixa for p in LICENCAS_PROIBIDAS):
                continue
            if not any(ok in baixa for ok in LICENCAS_OK):
                continue
            if any(ruim in baixo_titulo for ruim in TITULO_PROIBIDO):
                continue

            largura, altura = info.get("width", 0), info.get("height", 0)
            if largura < 600 or altura < 400:
                continue
            proporcao = largura / altura if altura else 0
            if not 0.7 <= proporcao <= 2.2:      # descarta panoramicas e tiras
                continue

            # o titulo precisa mencionar a especie procurada
            acertos = sum(1 for c in chaves if c in baixo_titulo)
            if chaves and not acertos:
                continue

            autor = self._limpar_html(meta.get("Artist", {}).get("value", "")) or "Wikimedia Commons"
            candidatos.append((
                acertos, largura,
                {
                    "url": info.get("thumburl") or info.get("url"),
                    "licenca": licenca,
                    "titulo": titulo,
                    "credito": f"{autor} · {licenca} · Wikimedia Commons",
                },
            ))

        if not candidatos:
            return None
        # mais mencoes ao nome da especie primeiro; empate desempata por resolucao
        candidatos.sort(key=lambda c: (c[0], c[1]), reverse=True)
        return candidatos[0][2]

    @staticmethod
    def _limpar_html(texto):
        import re

        return re.sub(r"<[^>]+>", "", texto or "").strip()[:120]

    @staticmethod
    def _monocromatica(imagem):
        """Detecta foto P&B — quase sempre material historico de arquivo."""
        amostra = imagem.convert("RGB").resize((48, 48))
        pixels = list(amostra.getdata())
        diferencas = [max(p) - min(p) for p in pixels]
        return sum(diferencas) / len(diferencas) < 12

    def _baixar_quadrado(self, url, lado):
        """Baixa, corta no centro em quadrado e devolve JPEG otimizado."""
        try:
            resposta = self.sessao.get(url, timeout=40)
            resposta.raise_for_status()
            imagem = Image.open(io.BytesIO(resposta.content))
            imagem = ImageOps.exif_transpose(imagem).convert("RGB")
            if self._monocromatica(imagem):
                return None
            imagem = ImageOps.fit(imagem, (lado, lado), Image.LANCZOS, centering=(0.5, 0.4))
            saida = io.BytesIO()
            imagem.save(saida, "JPEG", quality=82, optimize=True)
            return saida.getvalue()
        except Exception:
            return None
