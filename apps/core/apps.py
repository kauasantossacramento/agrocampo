from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Nucleo"

    def ready(self):
        # toda exceção não tratada (o erro 500) passa por aqui antes de
        # virar a página de erro: é a hora de registrar e avisar
        from django.core.signals import got_request_exception

        from .erros import registrar_excecao

        def _ao_estourar(sender, request=None, **kwargs):
            import sys

            registrar_excecao(request, sys.exc_info())

        got_request_exception.connect(_ao_estourar, dispatch_uid="core.registrar_erro_500")
