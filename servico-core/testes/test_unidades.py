import pytest

from dominio.unidades import UnidadeIncompativel, converter


@pytest.mark.parametrize(
    ("valor", "de", "para", "esperado"),
    [
        (21.8, "Cel", "Cel", 21.8),
        (71.6, "[degF]", "Cel", 22.0),
        (295.15, "K", "Cel", 22.0),
        (22.0, "Cel", "[degF]", 71.6),
        (150, "cm", "m", 1.5),
        (1, "m3/h", "L/s", 1000 / 3600),
        (0.5, "mg/m3", "ug/m3", 500),
    ],
)
def test_conversoes(valor, de, para, esperado):
    assert converter(valor, de, para) == pytest.approx(esperado)


@pytest.mark.parametrize(("de", "para"), [("Cel", "m"), ("%", "Cel"), ("xyz", "m")])
def test_sem_conversao(de, para):
    with pytest.raises(UnidadeIncompativel):
        converter(1.0, de, para)
