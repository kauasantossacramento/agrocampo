from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notificacao


class NotificacaoSerializer(serializers.ModelSerializer):
    lida = serializers.BooleanField(read_only=True)
    tipo_rotulo = serializers.CharField(source="get_tipo_display", read_only=True)

    class Meta:
        model = Notificacao
        fields = (
            "id", "titulo", "mensagem", "tipo", "tipo_rotulo", "nivel",
            "link", "lida", "lida_em", "criado_em",
        )


class NotificacaoViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificacaoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        usuario = self.request.user
        if usuario.e_operador:
            return Notificacao.objects.filter(publico=Notificacao.Publico.LOJISTA)
        return Notificacao.objects.do_usuario(usuario)

    @action(detail=True, methods=["post"])
    def lida(self, request, pk=None):
        self.get_object().marcar_lida()
        return Response({"ok": True})

    @action(detail=False, methods=["post"])
    def todas_lidas(self, request):
        self.get_queryset().nao_lidas().update(lida_em=timezone.now())
        return Response({"ok": True})
