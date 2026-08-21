"""Fábrica de drivers de pagamento."""
from .base import DadosCartao, ErroGateway, GatewayBase, ResultadoPagamento
from .simulado import SimuladoGateway
from .stone import StoneGateway

DRIVERS = {
    "stone": StoneGateway,
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
    if driver == ProvedorPagamento.Driver.STONE and not provedor.credenciais_completas:
        driver = ProvedorPagamento.Driver.SIMULADO
    return DRIVERS.get(driver, SimuladoGateway)(provedor)


__all__ = [
    "DadosCartao",
    "ErroGateway",
    "GatewayBase",
    "ResultadoPagamento",
    "SimuladoGateway",
    "StoneGateway",
    "get_gateway",
]
