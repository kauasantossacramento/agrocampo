from rest_framework import serializers

from .models import Categoria, Especie, Marca, Produto


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ("id", "nome", "slug", "icone", "pai")


class MarcaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Marca
        fields = ("id", "nome", "slug", "logo")


class EspecieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Especie
        fields = ("id", "nome", "slug", "grupo", "icone", "imagem")


class ProdutoSerializer(serializers.ModelSerializer):
    categoria = CategoriaSerializer(read_only=True)
    marca = MarcaSerializer(read_only=True)
    preco_atual = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    preco_assinatura = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    percentual_desconto = serializers.IntegerField(read_only=True)
    em_estoque = serializers.BooleanField(read_only=True)
    imagem = serializers.SerializerMethodField()

    class Meta:
        model = Produto
        fields = (
            "id", "nome", "slug", "sku", "resumo", "categoria", "marca",
            "preco", "preco_promocional", "preco_atual", "preco_assinatura",
            "percentual_desconto", "permite_assinatura", "desconto_assinatura",
            "estoque", "em_estoque", "destaque", "lancamento", "imagem",
        )

    def get_imagem(self, obj):
        principal = obj.imagem_principal
        if not principal:
            return None
        request = self.context.get("request")
        url = principal.imagem.url
        return request.build_absolute_uri(url) if request else url


class ProdutoDetalheSerializer(ProdutoSerializer):
    especies = EspecieSerializer(many=True, read_only=True)
    imagens = serializers.SerializerMethodField()
    beneficios_lista = serializers.ListField(source="lista_beneficios", read_only=True)

    class Meta(ProdutoSerializer.Meta):
        fields = ProdutoSerializer.Meta.fields + (
            "descricao", "beneficios_lista", "composicao", "especies", "imagens",
            "unidade", "peso_kg", "rotulo_estoque",
        )

    def get_imagens(self, obj):
        request = self.context.get("request")
        return [
            request.build_absolute_uri(i.imagem.url) if request else i.imagem.url
            for i in obj.imagens.all()
        ]
