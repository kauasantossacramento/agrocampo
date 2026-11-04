"""CPF: limpar, conferir e formatar.

O adquirente recusa a cobrança inteira quando o documento do comprador
falta ou não fecha os dígitos verificadores — e recusa depois de o cliente
já ter clicado em pagar. Conferir aqui, antes de chamar a API, troca uma
recusa sem explicação por um aviso no próprio formulário.
"""


def so_digitos(texto) -> str:
    return "".join(c for c in str(texto or "") if c.isdigit())


def cpf_valido(texto) -> bool:
    """Confere os dois dígitos verificadores do CPF."""
    cpf = so_digitos(texto)
    # 111.111.111-11 e afins fecham a conta e não existem
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for posicao in (9, 10):
        soma = sum(int(cpf[i]) * (posicao + 1 - i) for i in range(posicao))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[posicao]):
            return False
    return True


def formatar_cpf(texto) -> str:
    """000.000.000-00 — o formato em que o cadastro da loja já guarda."""
    cpf = so_digitos(texto)
    if len(cpf) != 11:
        return str(texto or "")
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
