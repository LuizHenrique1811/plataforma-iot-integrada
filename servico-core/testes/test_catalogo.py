"""Casos de uso do catálogo e do cadastro, com permissões por papel (RF-CEN-01 a 03, RF-DIS-01/02, RF-SEG-02)."""

import pytest

from adaptadores.credenciais import GeradorDeCredenciaisSeguro
from adaptadores.memoria import AutenticadorEmMemoria, CatalogoEmMemoria
from apoio import AGORA, RelogioFixo
from dominio.catalogo import Area, Dominio, Inquilino, ServicoDeCatalogo, Site
from dominio.erros import AcessoNegado, DadosInvalidos, JaExiste, NaoEncontrado
from dominio.modelos import DispositivoCadastrado, GrandezaDoPerfil, Origem, Perfil, TipoOrigem
from dominio.paginacao import ParametrosDePagina

ADMIN = Origem(TipoOrigem.CHAVE, None, papel="administrador")
PAGINA = ParametrosDePagina()


def chave(papel: str, inquilino: str = "coop-cerrado") -> Origem:
    return Origem(TipoOrigem.CHAVE, inquilino, papel=papel)


GESTOR = chave("gestor")


@pytest.fixture
def repositorio():
    return CatalogoEmMemoria()


@pytest.fixture
def servico(repositorio):
    servico = ServicoDeCatalogo(repositorio, GeradorDeCredenciaisSeguro(), RelogioFixo(AGORA))
    servico.criar_inquilino(ADMIN, Inquilino("coop-cerrado", "Cooperativa do Cerrado"))
    servico.criar_dominio(GESTOR, Dominio("agricultura", "Agricultura"))
    servico.criar_perfil(
        GESTOR,
        Perfil("sensor-solo", "Sensor de solo", {"umidade_solo": GrandezaDoPerfil("umidade_solo", "%", 0, 100)}, 900),
    )
    servico.criar_site(GESTOR, Site("fazenda-boa-vista", "Fazenda Boa Vista"))
    servico.criar_area(GESTOR, Area("talhao-07", "fazenda-boa-vista", "Talhão 07"))
    return servico


def novo(id_: str = "solo-01", **campos) -> DispositivoCadastrado:
    return DispositivoCadastrado(
        inquilino="",
        id=id_,
        perfil=campos.get("perfil", "sensor-solo"),
        dominio=campos.get("dominio", "agricultura"),
        site=campos.get("site", "fazenda-boa-vista"),
        area=campos.get("area", "talhao-07"),
    )


def test_dominio_novo_criado_so_por_configuracao(servico):
    # RF-CEN-01, RNF-08 e UC-06: domínio e perfil novos sem tocar no código.
    servico.criar_dominio(GESTOR, Dominio("recursos_hidricos", "Recursos hídricos"))
    servico.criar_perfil(
        GESTOR,
        Perfil("nivel-reservatorio", "Nível de reservatório", {"nivel": GrandezaDoPerfil("nivel", "m", 0, 10)}, 1800),
    )
    ids = [dominio.id for dominio in servico.listar_dominios(GESTOR, PAGINA).itens]
    assert ids == ["agricultura", "recursos_hidricos"]
    assert {perfil.id for perfil in servico.listar_perfis(GESTOR, PAGINA).itens} == {
        "sensor-solo",
        "nivel-reservatorio",
    }


def test_cadastro_emite_token_que_autentica_e_pode_ser_revogado(servico, repositorio):
    # RF-DIS-01 e RF-DIS-02
    dispositivo, token = servico.cadastrar_dispositivo(GESTOR, novo())
    autenticador = AutenticadorEmMemoria(catalogo=repositorio)

    assert dispositivo.inquilino == "coop-cerrado"
    assert dispositivo.criado_em == AGORA
    assert autenticador.por_token_dispositivo(token).dispositivo == "solo-01"

    servico.revogar_credencial(GESTOR, "solo-01")
    assert autenticador.por_token_dispositivo(token) is None
    assert servico.obter_dispositivo(GESTOR, "solo-01").revogado_em == AGORA


def test_cadastro_com_referencias_inexistentes(servico):
    with pytest.raises(DadosInvalidos) as erro:
        servico.cadastrar_dispositivo(GESTOR, novo(perfil="x", dominio="y", site="z"))
    assert {campo.caminho for campo in erro.value.erros} == {"/perfil", "/dominio", "/site"}

    with pytest.raises(DadosInvalidos) as erro:
        servico.cadastrar_dispositivo(GESTOR, novo(area="talhao-99"))
    assert [campo.caminho for campo in erro.value.erros] == ["/area"]


def test_identificador_repetido(servico):
    servico.cadastrar_dispositivo(GESTOR, novo())
    with pytest.raises(JaExiste):
        servico.cadastrar_dispositivo(GESTOR, novo())
    with pytest.raises(JaExiste):
        servico.criar_dominio(GESTOR, Dominio("agricultura", "Outra"))


def test_operador_nao_altera_dispositivos_nem_catalogo(servico):
    # Critério do RF-SEG-02.
    operador = chave("operador")
    with pytest.raises(AcessoNegado):
        servico.cadastrar_dispositivo(operador, novo())
    with pytest.raises(AcessoNegado):
        servico.criar_dominio(operador, Dominio("pecuaria", "Pecuária"))
    with pytest.raises(AcessoNegado):
        servico.revogar_credencial(operador, "solo-01")
    assert servico.listar_dominios(operador, PAGINA).total == 1


def test_leitor_so_le(servico):
    leitor = chave("leitor")
    assert servico.listar_sites(leitor, PAGINA).total == 1
    with pytest.raises(AcessoNegado):
        servico.criar_site(leitor, Site("outro", "Outro"))


def test_integrador_cadastra_dispositivo_mas_nao_mexe_no_catalogo(servico):
    integrador = chave("integrador")
    servico.cadastrar_dispositivo(integrador, novo())
    with pytest.raises(AcessoNegado):
        servico.criar_perfil(integrador, Perfil("p", "P", {}, 60))


def test_dispositivo_nao_gerencia_o_catalogo(servico):
    dispositivo = Origem(TipoOrigem.DISPOSITIVO, "coop-cerrado", dispositivo="solo-01")
    with pytest.raises(AcessoNegado):
        servico.listar_dominios(dispositivo, PAGINA)


def test_so_o_administrador_cria_inquilinos(servico):
    with pytest.raises(AcessoNegado):
        servico.criar_inquilino(GESTOR, Inquilino("outro", "Outro"))
    assert [inquilino.id for inquilino in servico.listar_inquilinos(ADMIN, PAGINA).itens] == ["coop-cerrado"]


def test_administrador_precisa_escolher_um_inquilino_existente(servico):
    with pytest.raises(DadosInvalidos):
        servico.criar_dominio(ADMIN, Dominio("pecuaria", "Pecuária"))
    with pytest.raises(NaoEncontrado):
        servico.criar_dominio(chave("administrador", "nao-existe"), Dominio("pecuaria", "Pecuária"))
    servico.criar_dominio(chave("administrador"), Dominio("pecuaria", "Pecuária"))


def test_area_precisa_de_local_existente(servico):
    with pytest.raises(NaoEncontrado):
        servico.criar_area(GESTOR, Area("a1", "nao-existe", "Área"))
    with pytest.raises(NaoEncontrado):
        servico.listar_areas(GESTOR, "nao-existe", PAGINA)
    assert [area.id for area in servico.listar_areas(GESTOR, "fazenda-boa-vista", PAGINA).itens] == ["talhao-07"]


def test_emissao_de_chaves_por_papel(servico, repositorio):
    chave_operador, segredo = servico.emitir_chave(GESTOR, "operador", "Centro de operações")
    autenticador = AutenticadorEmMemoria(catalogo=repositorio)
    assert autenticador.por_chave(segredo).papel == "operador"
    assert chave_operador.inquilino == "coop-cerrado"

    with pytest.raises(AcessoNegado):
        servico.emitir_chave(GESTOR, "administrador", None)
    with pytest.raises(DadosInvalidos):
        servico.emitir_chave(GESTOR, "superusuario", None)
    with pytest.raises(DadosInvalidos):
        servico.emitir_chave(ADMIN, "gestor", None)
    administrador, _ = servico.emitir_chave(ADMIN, "administrador", "Outro administrador")
    assert administrador.inquilino is None


def test_perfil_com_faixa_invertida(servico):
    with pytest.raises(DadosInvalidos):
        servico.criar_perfil(GESTOR, Perfil("p", "P", {"x": GrandezaDoPerfil("x", "m", 10, 1)}, 60))


def test_listagem_paginada_e_ordenada(servico):
    # RF-APP-07
    for identificador in ("clima", "pecuaria"):
        servico.criar_dominio(GESTOR, Dominio(identificador, identificador.title()))
    pagina = servico.listar_dominios(GESTOR, ParametrosDePagina(pagina=1, tamanho=2, ordenar="-id"))
    assert [dominio.id for dominio in pagina.itens] == ["pecuaria", "clima"]
    assert (pagina.total, pagina.tamanho) == (3, 2)
    segunda = servico.listar_dominios(GESTOR, ParametrosDePagina(pagina=2, tamanho=2, ordenar="-id"))
    assert [dominio.id for dominio in segunda.itens] == ["agricultura"]

    with pytest.raises(DadosInvalidos):
        servico.listar_dominios(GESTOR, ParametrosDePagina(ordenar="senha"))
    with pytest.raises(DadosInvalidos):
        ParametrosDePagina(pagina=0, tamanho=1000)


def test_filtro_de_dispositivos(servico):
    servico.criar_area(GESTOR, Area("talhao-08", "fazenda-boa-vista", "Talhão 08"))
    servico.cadastrar_dispositivo(GESTOR, novo("solo-01"))
    servico.cadastrar_dispositivo(GESTOR, novo("solo-02", area="talhao-08"))
    encontrados = servico.listar_dispositivos(GESTOR, {"area": "talhao-08", "ignorado": "x"}, PAGINA)
    assert [dispositivo.id for dispositivo in encontrados.itens] == ["solo-02"]


def test_dispositivo_inexistente(servico):
    with pytest.raises(NaoEncontrado):
        servico.obter_dispositivo(GESTOR, "nao-existe")
    with pytest.raises(NaoEncontrado):
        servico.revogar_credencial(GESTOR, "nao-existe")


def test_um_inquilino_nao_ve_o_catalogo_de_outro(servico):
    # RF-SEG-03
    servico.criar_inquilino(ADMIN, Inquilino("semma", "Secretaria do Meio Ambiente"))
    servico.cadastrar_dispositivo(GESTOR, novo())
    outro = chave("gestor", "semma")
    assert servico.listar_dispositivos(outro, {}, PAGINA).total == 0
    with pytest.raises(NaoEncontrado):
        servico.obter_dispositivo(outro, "solo-01")
