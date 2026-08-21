"""Telas nativas de conteúdo do painel.

Cada seção descreve um model, o formulário e as colunas da listagem. As
views são genéricas — assim banners, categorias, marcas, espécies, cupons e
páginas ganham a mesma tela, sem sete arquivos quase iguais.

O admin do Django deixa de aparecer para o lojista: fica só para o analista,
via `/admin/`.
"""
from dataclasses import dataclass, field
from typing import Callable

from django import forms

from apps.catalog.models import Categoria, Especie, Marca
from apps.core.models import Banner, Diferencial, Pagina
from apps.orders.models import Cupom

from .forms import CLASSE, _EstilizadoMixin


# ══════════════════════════════════════════════════════════ formulários
class BannerForm(_EstilizadoMixin, forms.ModelForm):
    class Meta:
        model = Banner
        fields = ("selo", "titulo", "subtitulo", "imagem", "cor_fundo",
                  "texto_botao", "link", "posicao", "ordem", "publicado")
        widgets = {
            "subtitulo": forms.Textarea(attrs={"rows": 2}),
            "cor_fundo": forms.TextInput(attrs={"type": "color"}),
            "link": forms.TextInput(attrs={"placeholder": "/catalogo/"}),
        }


class DiferencialForm(_EstilizadoMixin, forms.ModelForm):
    ICONES = [
        ("caminhao", "Caminhão (entrega)"), ("raio", "Raio (rapidez)"),
        ("refresh", "Ciclo (assinatura)"), ("escudo", "Escudo (segurança)"),
        ("medalha", "Medalha (qualidade)"), ("folha", "Folha (natural)"),
        ("relogio", "Relógio (prazo)"), ("cartao", "Cartão (pagamento)"),
    ]
    icone = forms.ChoiceField(choices=ICONES, label="Ícone")

    class Meta:
        model = Diferencial
        fields = ("titulo", "descricao", "icone", "ordem", "publicado")


class PaginaForm(_EstilizadoMixin, forms.ModelForm):
    class Meta:
        model = Pagina
        fields = ("nome", "resumo", "conteudo", "ordem_rodape", "publicado")
        widgets = {
            "conteudo": forms.Textarea(attrs={"rows": 12}),
            "resumo": forms.TextInput(attrs={"placeholder": "Uma linha de resumo"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ordem_rodape"].help_text = "0 esconde do rodapé."
        self.fields["conteudo"].help_text = "Aceita HTML simples (<p>, <b>, <ul>)."


class CategoriaForm(_EstilizadoMixin, forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ("nome", "pai", "icone", "descricao", "imagem",
                  "ordem", "exibir_no_menu", "destaque_home", "publicado")
        widgets = {"descricao": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pai"].empty_label = "Categoria principal"
        # uma categoria não pode ser filha de si mesma nem das próprias filhas
        if self.instance.pk:
            descendentes = self.instance.ramo_ids
            self.fields["pai"].queryset = Categoria.objects.exclude(pk__in=descendentes)


class MarcaForm(_EstilizadoMixin, forms.ModelForm):
    class Meta:
        model = Marca
        fields = ("nome", "logo", "descricao", "site", "destaque", "ordem", "publicado")
        widgets = {"descricao": forms.Textarea(attrs={"rows": 2})}


class EspecieForm(_EstilizadoMixin, forms.ModelForm):
    class Meta:
        model = Especie
        fields = ("nome", "grupo", "nome_cientifico", "imagem", "credito_imagem",
                  "descricao", "ordem", "destaque_home", "publicado")
        widgets = {"descricao": forms.Textarea(attrs={"rows": 2})}


class CupomForm(_EstilizadoMixin, forms.ModelForm):
    class Meta:
        model = Cupom
        fields = ("codigo", "descricao", "tipo", "valor", "valor_minimo",
                  "usos_maximos", "valido_de", "valido_ate", "ativo")
        widgets = {
            "codigo": forms.TextInput(attrs={"placeholder": "BEMVINDO10", "autocapitalize": "characters"}),
            "valor": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
            "valor_minimo": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
            "valido_de": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "valido_ate": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in ("valido_de", "valido_ate"):
            self.fields[campo].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["usos_maximos"].help_text = "0 = ilimitado."


# ══════════════════════════════════════════════════════════ registro
@dataclass
class Secao:
    slug: str
    titulo: str
    singular: str
    model: type
    form: type
    colunas: list           # [(rótulo, callable(obj) -> str|bool)]
    # campo com default tem que vir depois dos obrigatórios
    artigo: str = "Novo"    # "Novo banner" x "Nova marca"
    icone: str = "i-config"
    descricao: str = ""
    ordenacao: tuple = ("id",)
    busca: tuple = ()
    relacionados: tuple = field(default_factory=tuple)

    def queryset(self):
        qs = self.model.objects.all()
        if self.relacionados:
            qs = qs.select_related(*self.relacionados)
        return qs.order_by(*self.ordenacao)


def _sim_nao(valor):
    return bool(valor)


SECOES: dict[str, Secao] = {
    "banners": Secao(
        slug="banners", titulo="Banners da home", singular="banner",
        model=Banner, form=BannerForm, icone="i-imagem",
        descricao="Os quadros do carrossel principal — texto, imagem e botão.",
        ordenacao=("ordem", "-criado_em"),
        busca=("titulo", "subtitulo"),
        colunas=[
            ("Título", lambda o: o.titulo),
            ("Selo", lambda o: o.selo or "—"),
            ("Posição", lambda o: o.get_posicao_display()),
            ("Imagem", lambda o: _sim_nao(o.imagem)),
            ("Ordem", lambda o: o.ordem),
            ("No ar", lambda o: o.publicado),
        ],
    ),
    "diferenciais": Secao(
        slug="diferenciais", artigo="Nova", titulo="Faixa de garantias", singular="garantia",
        model=Diferencial, form=DiferencialForm, icone="i-escudo",
        descricao="A faixa logo abaixo do banner. Apagar todas esconde a faixa.",
        ordenacao=("ordem",),
        busca=("titulo", "descricao"),
        colunas=[
            ("Título", lambda o: o.titulo),
            ("Descrição", lambda o: o.descricao or "—"),
            ("Ordem", lambda o: o.ordem),
            ("No ar", lambda o: o.publicado),
        ],
    ),
    "paginas": Secao(
        slug="paginas", artigo="Nova", titulo="Páginas institucionais", singular="página",
        model=Pagina, form=PaginaForm, icone="i-info",
        descricao="Quem somos, trocas, entregas, privacidade — o que sai no rodapé.",
        ordenacao=("ordem_rodape", "nome"),
        busca=("nome", "conteudo"),
        colunas=[
            ("Página", lambda o: o.nome),
            ("Ordem no rodapé", lambda o: o.ordem_rodape or "escondida"),
            ("No ar", lambda o: o.publicado),
        ],
    ),
    "categorias": Secao(
        slug="categorias", artigo="Nova", titulo="Categorias", singular="categoria",
        model=Categoria, form=CategoriaForm, icone="i-estoque",
        descricao="A árvore do menu e dos atalhos da home.",
        ordenacao=("ordem", "nome"),
        busca=("nome",),
        relacionados=("pai",),
        colunas=[
            ("Categoria", lambda o: o.nome),
            ("Dentro de", lambda o: o.pai.nome if o.pai else "— principal —"),
            ("Produtos", lambda o: o.produtos.count()),
            ("No menu", lambda o: o.exibir_no_menu),
            ("Na home", lambda o: o.destaque_home),
            ("No ar", lambda o: o.publicado),
        ],
    ),
    "marcas": Secao(
        slug="marcas", artigo="Nova", titulo="Marcas", singular="marca",
        model=Marca, form=MarcaForm, icone="i-medalha",
        descricao="As marcas que a loja trabalha, exibidas na vitrine de marcas.",
        ordenacao=("ordem", "nome"),
        busca=("nome",),
        colunas=[
            ("Marca", lambda o: o.nome),
            ("Logo", lambda o: _sim_nao(o.logo)),
            ("Produtos", lambda o: o.produtos.count()),
            ("Na vitrine", lambda o: o.destaque),
            ("No ar", lambda o: o.publicado),
        ],
    ),
    "especies": Secao(
        slug="especies", artigo="Nova", titulo="Espécies", singular="espécie",
        model=Especie, form=EspecieForm, icone="i-folha",
        descricao="Navegação por animal: canário, calopsita, bovino, cão…",
        ordenacao=("grupo", "ordem", "nome"),
        busca=("nome", "nome_cientifico"),
        colunas=[
            ("Espécie", lambda o: o.nome),
            ("Grupo", lambda o: o.get_grupo_display()),
            ("Foto", lambda o: _sim_nao(o.imagem)),
            ("Na home", lambda o: o.destaque_home),
            ("No ar", lambda o: o.publicado),
        ],
    ),
    "cupons": Secao(
        slug="cupons", titulo="Cupons de desconto", singular="cupom",
        model=Cupom, form=CupomForm, icone="i-cartao",
        descricao="Códigos que o cliente digita no carrinho.",
        ordenacao=("-criado_em",),
        busca=("codigo", "descricao"),
        colunas=[
            ("Código", lambda o: o.codigo),
            ("Desconto", lambda o: (f"{o.valor:.0f}%" if o.tipo == "percentual"
                                    else f"R$ {o.valor:.2f}")),
            ("Mínimo", lambda o: f"R$ {o.valor_minimo:.2f}"),
            ("Usos", lambda o: f"{o.usos}/{o.usos_maximos or '∞'}"),
            ("Vigente", lambda o: o.vigente()),
        ],
    ),
}
