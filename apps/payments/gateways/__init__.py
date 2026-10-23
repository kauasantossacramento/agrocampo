"""Fábrica de drivers de pagamento."""
from .base import DadosCartao, ErroGateway, GatewayBase, ResultadoPagamento
from .cielo import CieloGateway
from .simulado import SimuladoGateway
from .stone import StoneGateway

DRIVERS = {
    "stone": StoneGateway,
    "cielo": CieloGateway,
    "simulado": SimuladoGateway,
}


def get_gateway(provedor=None):
    """Devolve o driver do provedor informado (ou do provedor padrão).

    Cai no driver simulado quando o provedor está marcado como Stone mas
    ainda não tem credenciais cadastradas — assim o checkout nunca quebra
    por configuração incompleta.
    """
    from apps.payments.models import ProvedorPagamento

    provedor = provedor or ProvedorPagamento.ativo_padrao()
    driver = provedor.driver
    de_verdade = {ProvedorPagamento.Driver.STONE, ProvedorPagamento.Driver.CIELO}
    if driver in de_verdade and not provedor.credenciais_completas:
        # escolher o adquirente sem preencher a credencial é meio caminho:
        # a loja segue no simulado até o cadastro ficar completo
        driver = ProvedorPagamento.Driver.SIMULADO
    return DRIVERS.get(driver, SimuladoGateway)(provedor)


__all__ = [
    "CieloGateway",
    "DadosCartao",
    "ErroGateway",
    "GatewayBase",
    "ResultadoPagamento",
    "SimuladoGateway",
    "StoneGateway",
    "get_gateway",
]
