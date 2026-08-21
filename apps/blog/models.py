"""Blog de conteúdo — cuidados, saúde animal e manejo rural."""
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import PublicadoQuerySet, SluggedModel, TimeStampedModel


class CategoriaPost(TimeStampedModel, SluggedModel):
    cor = models.CharField(max_length=20, default="#D62B20")

    class Meta:
        ordering = ["nome"]
        verbose_name = "categoria do blog"
        verbose_name_plural = "categorias do blog"

    def get_absolute_url(self):
        return reverse("blog:categoria", args=[self.slug])


class PostQuerySet(PublicadoQuerySet):
    def visiveis(self):
        return self.filter(publicado=True, publicado_em__lte=timezone.now())


class Post(TimeStampedModel, SluggedModel):
    slug_source = "titulo"

    titulo = models.CharField(max_length=200)
    categoria = models.ForeignKey(
        CategoriaPost, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="posts",
    )
    autor = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="posts",
    )
    capa = models.ImageField(upload_to="blog/", blank=True)
    resumo = models.CharField(max_length=250, blank=True)
    conteudo = models.TextField(help_text="Aceita HTML simples.")
    tempo_leitura = models.PositiveIntegerField("tempo de leitura (min)", default=4)
    destaque = models.BooleanField(default=False)
    publicado = models.BooleanField(default=True)
    publicado_em = models.DateTimeField(default=timezone.now)
    visualizacoes = models.PositiveIntegerField(default=0, editable=False)

    produtos_relacionados = models.ManyToManyField(
        "catalog.Produto", blank=True, related_name="posts"
    )

    objects = PostQuerySet.as_manager()

    class Meta:
        ordering = ["-publicado_em"]
        verbose_name = "post"
        verbose_name_plural = "posts"

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        self.nome = self.titulo
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog:post", args=[self.slug])
