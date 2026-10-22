"""Prepara a demonstração: cenário rural com borda e cenário urbano, só por configuração (RNF-08).

- Rural (coop-cerrado), na central e na borda: solo, silo e válvula da Fazenda Boa Vista; regra local de
  irrigação na borda (UC-01) e regra de temperatura do silo com SMS na central (UC-02).
- Urbano (semma), na central: estação de qualidade do ar (UC-03, via adaptador) e lixeira (UC-04).
- Grava em demo/.env.demo o token da lixeira, usado pelo simulador em Java.
- Se a borda ainda não tem a chave da central, emite uma chave no_borda e grava em infra/borda/.env.

Uso: docker compose -f demo/compose.yaml run --rm preparar
"""

from comum import ARQUIVO_DE_TOKENS, BORDA, CENTRAL, RAIZ, Api, gravar_env, ler_env

RURAL, URBANO = "coop-cerrado", "semma"

CATALOGO_RURAL = [
    ("/api/v1/catalogo/dominios", {"id": "agricultura", "nome": "Agricultura"}),
    ("/api/v1/catalogo/dominios", {"id": "armazenagem", "nome": "Armazenagem"}),
    ("/api/v1/catalogo/perfis", {"id": "sensor-solo", "nome": "Sensor de solo", "intervalo_envio_s": 900,
                                 "grandezas": [{"grandeza": "umidade_solo", "unidade": "%", "minimo": 0,
                                                "maximo": 100}]}),
    ("/api/v1/catalogo/perfis", {"id": "termometria-silo", "nome": "Termometria de silo", "intervalo_envio_s": 900,
                                 "grandezas": [{"grandeza": "temperatura_graos", "unidade": "Cel", "minimo": -10,
                                                "maximo": 80}]}),
    ("/api/v1/catalogo/perfis", {"id": "valvula-irrigacao", "nome": "Válvula de irrigação", "intervalo_envio_s": 3600,
                                 "grandezas": [{"grandeza": "vazao", "unidade": "L/min"}]}),
    ("/api/v1/sites", {"id": "fazenda-boa-vista", "nome": "Fazenda Boa Vista",
                       "geo": {"type": "Point", "coordinates": [-49.1012, -16.4123]}}),
    ("/api/v1/sites/fazenda-boa-vista/areas", {"id": "talhao-07", "nome": "Talhão 07"}),
    ("/api/v1/sites/fazenda-boa-vista/areas", {"id": "silo-2", "nome": "Silo 2"}),
    ("/api/v1/dispositivos", {"id": "solo-talhao07-02", "perfil": "sensor-solo", "dominio": "agricultura",
                              "site": "fazenda-boa-vista", "area": "talhao-07"}),
    ("/api/v1/dispositivos", {"id": "valvula-talhao07", "perfil": "valvula-irrigacao", "dominio": "agricultura",
                              "site": "fazenda-boa-vista", "area": "talhao-07"}),
    ("/api/v1/dispositivos", {"id": "silo-02", "perfil": "termometria-silo", "dominio": "armazenagem",
                              "site": "fazenda-boa-vista", "area": "silo-2"}),
]  # fmt: skip

REGRA_DE_IRRIGACAO = {
    "id": "irrigacao-local", "nome": "Irrigar o talhão 07 com solo seco", "ambito": "borda",
    "condicao": {"tipo": "limite", "grandeza": "umidade_solo", "operador": "<", "valor": 20, "area": "talhao-07"},
    "acoes": [
        {"tipo": "alarme", "severidade": "critico", "mensagem": "Solo seco no talhão 07"},
        {"tipo": "comando", "dispositivo": "valvula-talhao07",
         "comando": {"nome": "abrir", "parametros": {"minutos": 30}}},
    ],
}  # fmt: skip

REGRA_DO_SILO = {
    "id": "silo-quente", "nome": "Silo acima de 30 °C por 1 minuto",
    "condicao": {"tipo": "janela", "grandeza": "temperatura_graos", "operador": ">", "valor": 30, "duracao_s": 60},
    "acoes": [
        {"tipo": "alarme", "severidade": "critico"},
        {"tipo": "notificar", "canal": "sms", "mensagem": "Silo 2 acima de 30 °C há mais de 1 minuto"},
    ],
}  # fmt: skip

CATALOGO_URBANO = [
    ("/api/v1/catalogo/dominios", {"id": "ambiente", "nome": "Meio ambiente"}),
    ("/api/v1/catalogo/dominios", {"id": "residuos", "nome": "Resíduos"}),
    ("/api/v1/catalogo/perfis", {"id": "estacao-ar", "nome": "Estação de qualidade do ar", "intervalo_envio_s": 60,
                                 "grandezas": [{"grandeza": "pm25", "unidade": "ug/m3", "minimo": 0, "maximo": 500},
                                               {"grandeza": "ruido", "unidade": "dB", "minimo": 0, "maximo": 140},
                                               {"grandeza": "temperatura_ar", "unidade": "Cel", "minimo": -10,
                                                "maximo": 50}]}),
    ("/api/v1/catalogo/perfis", {"id": "lixeira", "nome": "Lixeira com sensor de nível", "intervalo_envio_s": 600,
                                 "grandezas": [{"grandeza": "nivel_enchimento", "unidade": "%", "minimo": 0,
                                                "maximo": 100}]}),
    ("/api/v1/sites", {"id": "centro", "nome": "Bairro Centro"}),
    ("/api/v1/sites/centro/areas", {"id": "praca-bom-jesus", "nome": "Praça Bom Jesus"}),
    ("/api/v1/dispositivos", {"id": "ar-centro-03", "perfil": "estacao-ar", "dominio": "ambiente", "site": "centro",
                              "area": "praca-bom-jesus", "fabricante": "firmware legado"}),
]  # fmt: skip

REGRA_DA_LIXEIRA = {
    "id": "lixeira-cheia", "nome": "Lixeira acima de 80%",
    "condicao": {"tipo": "limite", "grandeza": "nivel_enchimento", "operador": ">", "valor": 80, "dominio": "residuos"},
    "acoes": [{"tipo": "alarme", "severidade": "aviso", "mensagem": "Lixeira cheia: incluir na rota de coleta"}],
}  # fmt: skip


def main() -> None:
    chave_central = ler_env(RAIZ / "infra" / "central" / ".env").get("CHAVE_ADMIN")
    env_da_borda = ler_env(RAIZ / "infra" / "borda" / ".env")
    if not chave_central or not env_da_borda.get("CHAVE_ADMIN"):
        raise SystemExit("Preencha CHAVE_ADMIN em infra/central/.env e infra/borda/.env (infra/README.md).")
    tokens = ler_env(ARQUIVO_DE_TOKENS)

    print("Cenário rural (coop-cerrado), na central e na borda:")
    central_rural = Api("central", CENTRAL, chave_central, RURAL)
    borda_rural = Api("borda", BORDA, env_da_borda["CHAVE_ADMIN"], RURAL)
    for api in (central_rural, borda_rural):
        api.garantir("/api/v1/inquilinos", {"id": RURAL, "nome": "Cooperativa do Cerrado"}, f"inquilino {RURAL}")
        for caminho, corpo in CATALOGO_RURAL:
            api.garantir(caminho, corpo, f"{caminho.rsplit('/', 1)[-1]} {corpo['id']}")
    borda_rural.garantir("/api/v1/regras", REGRA_DE_IRRIGACAO, "regra local de irrigação (UC-01)")
    central_rural.garantir("/api/v1/regras", REGRA_DO_SILO, "regra do silo com SMS (UC-02)")

    print("Cenário urbano (semma), na central:")
    central_urbano = Api("central", CENTRAL, chave_central, URBANO)
    central_urbano.garantir(
        "/api/v1/inquilinos", {"id": URBANO, "nome": "Secretaria do Meio Ambiente"}, "inquilino semma"
    )
    for caminho, corpo in CATALOGO_URBANO:
        central_urbano.garantir(caminho, corpo, f"{caminho.rsplit('/', 1)[-1]} {corpo['id']}")
    lixeira = {
        "id": "lixeira-17",
        "perfil": "lixeira",
        "dominio": "residuos",
        "site": "centro",
        "area": "praca-bom-jesus",
    }
    status, resposta = central_urbano.garantir("/api/v1/dispositivos", lixeira, "dispositivo lixeira-17")
    if status == 201:
        tokens["TOKEN_LIXEIRA"] = resposta["token"]
    elif "TOKEN_LIXEIRA" not in tokens:
        print("  aviso: a lixeira já existia e o token não está em demo/.env.demo; o simulador Java não vai autenticar")
    central_urbano.garantir("/api/v1/regras", REGRA_DA_LIXEIRA, "regra da lixeira cheia (UC-04)")
    gravar_env(ARQUIVO_DE_TOKENS, {chave: valor for chave, valor in tokens.items() if valor})

    if not env_da_borda.get("CHAVE_CENTRAL"):
        status, resposta = central_rural.chamar("POST", "/api/v1/chaves", {"papel": "no_borda", "descricao": "borda"})
        if status != 201:
            raise SystemExit(f"falhou ao emitir a chave da borda: HTTP {status} {resposta}")
        gravar_env(RAIZ / "infra" / "borda" / ".env", {"CHAVE_CENTRAL": resposta["chave"]})
        print("Chave no_borda gravada em infra/borda/.env: rode `docker compose up -d` em infra/borda para aplicar.")

    print("\nPronto. Próximos passos (README, roteiro da demonstração):")
    print("  docker compose -f demo/compose.yaml run --rm dominio-novo")
    print("  docker compose -f adaptadores-plugaveis/ar-urbano/compose.yaml up -d --build")
    print("  docker compose -f simuladores/compose.yaml up -d --build")


if __name__ == "__main__":
    main()
