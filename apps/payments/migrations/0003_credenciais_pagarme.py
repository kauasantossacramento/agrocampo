"""Credenciais da Pagar.me, e a separação entre Stone e Pagar.me.

Até aqui o driver "stone" se chamava "Stone / Pagar.me", como se fossem a
mesma coisa. Não são: a Stone autentica por OAuth em `api.stone.com.br` e
a Pagar.me por Basic em `api.pagar.me/core/v5`, com outro vocabulário de
pedido, cobrança e estorno. Agora são dois drivers, e o rótulo do antigo
deixa de prometer o que ele não faz.

Nenhuma linha muda de driver aqui: quem estava em "stone" continua em
"stone", quem estava no simulado continua no simulado.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_credenciais_cielo'),
    ]

    operations = [
        migrations.AddField(
            model_name='provedorpagamento',
            name='pagarme_account_id',
            field=models.CharField(blank=True, help_text='Começa com acc_. Aparece no painel, em Configurações.', max_length=120, verbose_name='Pagar.me · ID da conta'),
        ),
        migrations.AddField(
            model_name='provedorpagamento',
            name='pagarme_base_url',
            field=models.URLField(blank=True, default='https://api.pagar.me/core/v5', help_text='Mesma URL para teste e produção — quem separa é a chave.', verbose_name='Pagar.me · URL da API'),
        ),
        migrations.AddField(
            model_name='provedorpagamento',
            name='pagarme_public_key_producao',
            field=models.CharField(blank=True, help_text='Usada para cifrar o cartão no navegador. Pode ser pública.', max_length=300, verbose_name='Pagar.me · Chave pública (produção)'),
        ),
        migrations.AddField(
            model_name='provedorpagamento',
            name='pagarme_public_key_sandbox',
            field=models.CharField(blank=True, max_length=300, verbose_name='Pagar.me · Chave pública (teste)'),
        ),
        migrations.AddField(
            model_name='provedorpagamento',
            name='pagarme_secret_key_producao',
            field=models.CharField(blank=True, help_text='Cobra de verdade. Nunca exibida no site.', max_length=300, verbose_name='Pagar.me · Chave secreta (produção)'),
        ),
        migrations.AddField(
            model_name='provedorpagamento',
            name='pagarme_secret_key_sandbox',
            field=models.CharField(blank=True, help_text='Chave de teste. Não gera cobrança real.', max_length=300, verbose_name='Pagar.me · Chave secreta (teste)'),
        ),
        migrations.AddField(
            model_name='provedorpagamento',
            name='pagarme_webhook_senha',
            field=models.CharField(blank=True, max_length=200, verbose_name='Pagar.me · Senha do webhook'),
        ),
        migrations.AddField(
            model_name='provedorpagamento',
            name='pagarme_webhook_usuario',
            field=models.CharField(blank=True, help_text='Opcional. Se preenchido, a loja recusa notificação sem este Basic.', max_length=120, verbose_name='Pagar.me · Usuário do webhook'),
        ),
        migrations.AlterField(
            model_name='provedorpagamento',
            name='driver',
            field=models.CharField(choices=[('pagarme', 'Pagar.me (API v5)'), ('stone', 'Stone (API própria)'), ('cielo', 'Cielo (API e-Commerce 3.0)'), ('simulado', 'Simulado (desenvolvimento)')], default='simulado', max_length=20),
        ),
    ]
