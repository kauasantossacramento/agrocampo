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
from apps.shipping.models import DIAS_SEMANA, Cidade, Localidade, RegraEntrega

from .forms import CLASSE, _EstilizadoMixin


# ══════════════════════════════════════════════════════════ formulários
class BannerForm(_EstilizadoMixin, forms.ModelForm):
    class Meta:
        model = Banner
        fields = ("posicao", "selo", "titulo", "subtitulo", "imagem", "video",
                  "cor_fundo", "texto_botao", "link", "produtos", "ordem", "publicado")
        widgets = {
            "subtitulo": forms.Textarea(attrs={"rows": 2}),
            "cor_fundo": forms.TextInput(attrs={"type": "color"}),
            "link": forms.TextInput(attrs={"placeholder": "/catalogo/"}),
            "produtos": forms.SelectMultiple(attrs={"size": 10}),
        }

    def __init__(self, *args, **kwargs):
        from apps.catalog.models import Produto

        super().__init__(*args, **kwargs)
        self.fields["produtos"].queryset = (
            Produto.objects.filter(publicado=True).order_by("nome")
        )
        self.fields["produtos"].help_text = (
            "Segure Ctrl (ou toque em vários no celular) para escolher mais de um. "
            "Na faixa de produtos vira uma foto por produto; na apresentação, "
            "o primeiro define para onde o slide leva quando não há link."
        )
        self.fields["posicao"].help_text = (
            "“Apresentação” é o bloco de vídeo/foto no topo da home — é o que "
            "o cliente vê primeiro no celular."
        )
        self.fields["imagem"].help_text = (
            "Na apresentação com vídeo, esta imagem é o quadro que aparece "
            "enquanto o vídeo carrega."
        )

    def clean(self):
        dados = super().clean()
        posicao = dados.get("posicao")

        if posicao == Banner.Posicao.APRESENTACAO:
            # sem mídia o slide sairia como um retângulo preto
            tem_midia = dados.get("video") or dados.get("imagem") or self.instance.tem_midia
            if not tem_midia:
                self.add_error(
                    "imagem",
                    "A apresentação precisa de um vídeo ou de uma foto para exibir.",
                )

        if posicao == Banner.Posicao.PRODUTOS and not (
            dados.get("produtos") or self.instance.pk
        ):
            self.add_error("produtos", "Escolha ao menos um produto para a faixa.")

        return dados


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


class CidadeForm(_EstilizadoMixin, forms.ModelForm):
    """Dias da semana como caixinhas — ninguém deveria digitar "0,2,4"."""

    dias = forms.MultipleChoiceField(
        choices=DIAS_SEMANA,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Entrega nestes dias",
        help_text="Nenhum marcado = de segunda a sexta.",
    )

    class Meta:
        model = Cidade
        fields = ("nome", "uf", "sede", "frete", "frete_gratis_acima_de",
                  "horario_a_partir_de", "prazo_dias", "observacao", "ordem", "ativo")
        widgets = {
            "uf": forms.TextInput(attrs={"maxlength": 2, "autocapitalize": "characters"}),
            "frete": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
            "frete_gratis_acima_de": forms.NumberInput(
                attrs={"step": "0.01", "inputmode": "decimal", "placeholder": "usa o padrão da loja"}
            ),
            "horario_a_partir_de": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "observacao": forms.TextInput(
                attrs={"placeholder": "Ex.: entregamos só no centro"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["horario_a_partir_de"].input_formats = ["%H:%M"]
        if self.instance.pk and self.instance.dias_entrega:
            self.fields["dias"].initial = [str(d) for d in self.instance.dias]

    def save(self, commit=True):
        cidade = super().save(commit=False)
        cidade.dias_entrega = ",".join(self.cleaned_data.get("dias") or [])
        if commit:
            cidade.save()
        return cidade


class LocalidadeForm(_EstilizadoMixin, forms.ModelForm):
    class Meta:
        model = Localidade
        fields = ("cidade", "nome", "frete_adicional", "acesso_por_barco",
                  "prazo_extra_dias", "observacao", "ativo")
        widgets = {
            "nome": forms.TextInput(
                attrs={"placeholder": "Ilha de Guaibim, Povoado do Retiro…"}
            ),
            "frete_adicional": forms.NumberInput(
                attrs={"step": "0.01", "inputmode": "decimal"}
            ),
            "observacao": forms.TextInput(attrs={"placeholder": "Ex.: só de manhã"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cidade"].queryset = Cidade.objects.atendidas()
        self.fields["nome"].help_text = (
            "Vale o nome que o cliente usa, mesmo que não exista no mapa."
        )


class RegraEntregaForm(_EstilizadoMixin, forms.ModelForm):
    ICONES = [
        ("caminhao", "Caminhão (entrega)"), ("relogio", "Relógio (horário)"),
        ("info", "Informação"), ("alerta", "Alerta"), ("escudo", "Escudo"),
    ]
    icone = forms.ChoiceField(choices=ICONES, label="Ícone")

    class Meta:
        model = RegraEntrega
        fields = ("titulo", "mensagem", "momento", "icone", "destaque",
                  "cidade", "ordem", "ativo")
        widgets = {"mensagem": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cidade"].queryset = Cidade.objects.atendidas()
        self.fields["cidade"].empty_label = "Todas as cidades"


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
    grupo: str = "Loja"     # agrupa as abas: dez numa linha só vira sopa
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
        descricao=(
            "O topo da home. A “Apresentação” é o bloco de vídeo ou foto que "
            "aparece primeiro no celular; sem ela, entra o banner clássico."
        ),
        ordenacao=("ordem", "-criado_em"),
        busca=("titulo", "subtitulo"),
        colunas=[
            ("Título", lambda o: o.titulo),
            ("Selo", lambda o: o.selo or "—"),
            ("Posição", lambda o: o.get_posicao_display()),
            ("Produtos", lambda o: o.produtos.count() or "—"),
            ("Mídia", lambda o: ("vídeo" if o.video else "foto" if o.imagem else "—")),
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
    "cidades": Secao(
        slug="cidades", artigo="Nova", grupo="Entrega", titulo="Cidades atendidas", singular="cidade",
        model=Cidade, form=CidadeForm, icone="i-caminhao",
        descricao="Onde a loja entrega, com o frete e os dias de cada cidade.",
        ordenacao=("-sede", "ordem", "nome"),
        busca=("nome",),
        colunas=[
            ("Cidade", lambda o: f"{o.nome}/{o.uf}"),
            ("Sede", lambda o: o.sede),
            ("Frete", lambda o: f"R$ {o.frete:.2f}"),
            ("Dias", lambda o: o.dias_legivel),
            ("Prazo", lambda o: f"{o.prazo_dias} dia(s)"),
            ("Localidades", lambda o: o.localidades.count()),
            ("Atende", lambda o: o.ativo),
        ],
    ),
    "localidades": Secao(
        slug="localidades", artigo="Nova", grupo="Entrega", titulo="Ilhas e localidades",
        singular="localidade",
        model=Localidade, form=LocalidadeForm, icone="i-mapa",
        descricao=(
            "Povoados, ilhas e bairros com frete próprio — inclusive os que o "
            "mapa não conhece."
        ),
        ordenacao=("cidade__nome", "nome"),
        busca=("nome",),
        relacionados=("cidade",),
        colunas=[
            ("Localidade", lambda o: o.nome),
            ("Cidade", lambda o: o.cidade.nome),
            ("Acréscimo", lambda o: f"+ R$ {o.frete_adicional:.2f}"),
            ("De barco", lambda o: o.acesso_por_barco),
            ("Dias a mais", lambda o: o.prazo_extra_dias or "—"),
            ("Ativa", lambda o: o.ativo),
        ],
    ),
    "avisos-entrega": Secao(
        slug="avisos-entrega", grupo="Entrega", titulo="Avisos de entrega", singular="aviso",
        model=RegraEntrega, form=RegraEntregaForm, icone="i-info",
        descricao="Recados que o cliente lê durante a compra.",
        ordenacao=("ordem", "id"),
        busca=("titulo", "mensagem"),
        relacionados=("cidade",),
        colunas=[
            ("Aviso", lambda o: o.titulo),
            ("Onde aparece", lambda o: o.get_momento_display()),
            ("Cidade", lambda o: o.cidade.nome if o.cidade else "todas"),
            ("Destaque", lambda o: o.destaque),
            ("No ar", lambda o: o.ativo),
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


def secoes_agrupadas():
    """As abas de conteúdo em grupos, na ordem de cadastro."""
    grupos: dict[str, list[Secao]] = {}
    for secao in SECOES.values():
        grupos.setdefault(secao.grupo, []).append(secao)
    return grupos
