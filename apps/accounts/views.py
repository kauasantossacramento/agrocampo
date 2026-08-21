"""Cadastro, login, perfil e endereços."""
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.cart.services import mesclar_apos_login
from apps.catalog.models import ListaDesejos

from .forms import CadastroForm, EnderecoForm, PerfilForm
from .redirects import destino_seguro
from .models import Endereco


def entrar(request):
    destino = destino_seguro(request)
    if request.user.is_authenticated:
        return redirect(destino)

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.get_user()
        mesclar_apos_login(request, usuario)
        login(request, usuario)
        messages.success(request, f"Bem-vindo de volta, {usuario.primeiro_nome}!")
        return redirect(destino)

    if request.method == "POST":
        messages.error(request, "E-mail ou senha incorretos.")
    return render(request, "accounts/entrar.html", {"form": form, "destino": destino})


def cadastrar(request):
    destino = destino_seguro(request)
    if request.user.is_authenticated:
        return redirect(destino)

    form = CadastroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        mesclar_apos_login(request, usuario)
        login(request, usuario, backend="apps.accounts.backends.EmailOrUsernameBackend")
        # quem criou conta no meio da compra volta para o checkout, nao para a home
        voltando_para_compra = "carrinho" in destino or "pagamento" in destino
        messages.success(
            request,
            "Conta criada! Vamos concluir seu pedido."
            if voltando_para_compra
            else "Conta criada! Bem-vindo à AgroCampo.",
        )
        return redirect(destino)
    return render(request, "accounts/cadastrar.html", {"form": form, "destino": destino})


def sair(request):
    logout(request)
    messages.info(request, "Você saiu da sua conta.")
    return redirect("core:home")


@login_required
def perfil(request):
    form = PerfilForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Dados atualizados.")
        return redirect("accounts:perfil")
    return render(
        request,
        "accounts/perfil.html",
        {
            "form": form,
            "enderecos": request.user.enderecos.all(),
            "cartoes": request.user.cartoes.filter(ativo=True),
        },
    )


@login_required
def enderecos(request):
    destino = destino_seguro(request, padrao="accounts:enderecos")
    form = EnderecoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        endereco = form.save(commit=False)
        endereco.usuario = request.user
        primeiro = not request.user.enderecos.exists()
        if primeiro:
            endereco.padrao = True
        endereco.save()
        # quem veio do checkout so para cadastrar endereco volta direto para la
        if destino != reverse("accounts:enderecos"):
            messages.success(request, "Endereço salvo. Vamos continuar seu pedido.")
            return redirect(destino)
        messages.success(request, "Endereço salvo.")
        return redirect("accounts:enderecos")
    return render(
        request,
        "accounts/enderecos.html",
        {
            "form": form,
            "enderecos": request.user.enderecos.all(),
            "destino": destino,
        },
    )


@login_required
@require_POST
def remover_endereco(request, pk):
    get_object_or_404(Endereco, pk=pk, usuario=request.user).delete()
    messages.info(request, "Endereço removido.")
    return redirect("accounts:enderecos")


@login_required
@require_POST
def definir_endereco_padrao(request, pk):
    endereco = get_object_or_404(Endereco, pk=pk, usuario=request.user)
    endereco.padrao = True
    endereco.save()
    messages.success(request, f"{endereco.apelido} agora é o endereço padrão.")
    return redirect("accounts:enderecos")


@login_required
def desejos(request):
    itens = ListaDesejos.objects.filter(usuario=request.user).select_related(
        "produto__categoria"
    ).prefetch_related("produto__imagens")
    return render(request, "accounts/desejos.html", {"itens": itens})
