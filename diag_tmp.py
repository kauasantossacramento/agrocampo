import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.test import Client
from apps.accounts.models import User

lojista = User.objects.filter(papel="lojista").first()
c = Client(); c.force_login(lojista)
r = c.get("/painel/conteudo/banners/novo/")
print("status:", r.status_code)
html = r.content.decode()
print("tamanho:", len(html))
print("tem name=titulo?", 'name="titulo"' in html)
print("tem name=imagem?", 'name="imagem"' in html)
print("---- inicio ----")
print(html[:1200])
