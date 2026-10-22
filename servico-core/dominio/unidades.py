"""Normalização de unidades UCUM (RF-PRO-01).

Tabela pequena de conversões lineares entre unidades da mesma dimensão. É genérica (não depende
de cenário): converte a unidade recebida para a unidade definida no perfil do dispositivo.
"""


class UnidadeIncompativel(ValueError):
    pass


# unidade -> (dimensão, fator, deslocamento), com base = valor * fator + deslocamento.
_UNIDADES: dict[str, tuple[str, float, float]] = {
    "Cel": ("temperatura", 1.0, 0.0),
    "K": ("temperatura", 1.0, -273.15),
    "[degF]": ("temperatura", 5 / 9, -32 * 5 / 9),
    "m": ("comprimento", 1.0, 0.0),
    "cm": ("comprimento", 0.01, 0.0),
    "mm": ("comprimento", 0.001, 0.0),
    "km": ("comprimento", 1000.0, 0.0),
    "Pa": ("pressao", 1.0, 0.0),
    "hPa": ("pressao", 100.0, 0.0),
    "kPa": ("pressao", 1000.0, 0.0),
    "bar": ("pressao", 100000.0, 0.0),
    "L": ("volume", 1.0, 0.0),
    "mL": ("volume", 0.001, 0.0),
    "m3": ("volume", 1000.0, 0.0),
    "L/s": ("vazao", 1.0, 0.0),
    "L/min": ("vazao", 1 / 60, 0.0),
    "m3/h": ("vazao", 1000 / 3600, 0.0),
    "ug/m3": ("concentracao", 1.0, 0.0),
    "mg/m3": ("concentracao", 1000.0, 0.0),
    "s": ("tempo", 1.0, 0.0),
    "min": ("tempo", 60.0, 0.0),
    "h": ("tempo", 3600.0, 0.0),
    "W": ("potencia", 1.0, 0.0),
    "kW": ("potencia", 1000.0, 0.0),
    "W.h": ("energia", 1.0, 0.0),
    "kW.h": ("energia", 1000.0, 0.0),
    "m/s": ("velocidade", 1.0, 0.0),
    "km/h": ("velocidade", 1000 / 3600, 0.0),
}


def converter(valor: float, de: str, para: str) -> float:
    """Converte `valor` da unidade `de` para `para`; levanta UnidadeIncompativel se não houver conversão."""
    if de == para:
        return valor
    origem = _UNIDADES.get(de)
    destino = _UNIDADES.get(para)
    if origem is None or destino is None or origem[0] != destino[0]:
        raise UnidadeIncompativel(f"não há conversão de '{de}' para '{para}'")
    base = valor * origem[1] + origem[2]
    return (base - destino[2]) / destino[1]
