from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """Permite login por e-mail ou por username, sem diferenciar maiúsculas."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        identificador = username or kwargs.get("email")
        if not identificador or not password:
            return None
        usuario = User.objects.filter(
            Q(email__iexact=identificador) | Q(username__iexact=identificador)
        ).first()
        if usuario and usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None
