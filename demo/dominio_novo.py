"""Domínio novo ao vivo (UC-06, RNF-08): reservatórios de água sem tocar no código.

Cada passo é uma chamada à API; nada no núcleo conhece "reservatório". Ao final, o simulador em
JavaScript passa a enviar o nível do reservatório com o token emitido aqui.

Uso: docker compose -f demo/compose.yaml run --rm dominio-novo
     (com PAUSAR=1, espera Enter entre os passos, para narrar na apresentação)
"""

import os

from comum import ARQUIVO_DE_TOKENS, CENTRAL, RAIZ, Api, gravar_env, ler_env

INQUILINO = os.environ.get("INQUILINO", "coop-cerrado")


def passo(numero: int, texto: str) -> None:
    print(f"\n{numero}. {texto}")
    if os.environ.get("PAUSAR") == "1":
        input("   (Enter para executar) ")


def main() -> None:
    chave = ler_env(RAIZ / "infra" / "central" / ".env").get("CHAVE_ADMIN")
    if not chave:
        raise SystemExit("Preencha CHAVE_ADMIN em infra/central/.env (infra/README.md).")
    api = Api("central", CENTRAL, chave, INQUILINO)

    passo(1, "O gestor cria o domínio recursos_hidricos no catálogo do inquilino (RF-CEN-01).")
    api.garantir("/api/v1/catalogo/dominios", {"id": "recursos_hidricos", "nome": "Recursos hídricos"}, "domínio")

    passo(
        2, "Cria o perfil 'nível de reservatório': nível em metros, faixa de 0 a 10 m, envio a cada 30 min (RF-CEN-02)."
    )
    perfil = {
        "id": "nivel-reservatorio",
        "nome": "Nível de reservatório",
        "intervalo_envio_s": 1800,
        "grandezas": [{"grandeza": "nivel", "unidade": "m", "minimo": 0, "maximo": 10}],
    }
    api.garantir("/api/v1/catalogo/perfis", perfil, "perfil nivel-reservatorio")

    passo(3, "Cadastra a área do reservatório e o sensor, que recebe seu token (RF-CEN-03, RF-DIS-01).")
    api.garantir(
        "/api/v1/sites/fazenda-boa-vista/areas", {"id": "reservatorio-norte", "nome": "Reservatório Norte"}, "área"
    )
    sensor = {
        "id": "reservatorio-01",
        "perfil": "nivel-reservatorio",
        "dominio": "recursos_hidricos",
        "site": "fazenda-boa-vista",
        "area": "reservatorio-norte",
    }
    status, resposta = api.garantir("/api/v1/dispositivos", sensor, "dispositivo reservatorio-01")
    if status == 201:
        gravar_env(ARQUIVO_DE_TOKENS, {"TOKEN_RESERVATORIO": resposta["token"]})
        print("   token gravado em demo/.env.demo (TOKEN_RESERVATORIO), para o simulador em JavaScript")

    passo(4, "Cria uma regra: nível abaixo de 2 m abre um alarme (RF-PRO-02).")
    regra = {
        "id": "reservatorio-baixo",
        "nome": "Reservatório abaixo de 2 m",
        "condicao": {
            "tipo": "limite",
            "grandeza": "nivel",
            "operador": "<",
            "valor": 2,
            "dominio": "recursos_hidricos",
        },
        "acoes": [{"tipo": "alarme", "severidade": "aviso", "mensagem": "Reservatório Norte com nível baixo"}],
    }
    api.garantir("/api/v1/regras", regra, "regra reservatorio-baixo")

    print("\nNenhuma linha de código mudou: o domínio novo já tem histórico, regras, painéis e API (RNF-08).")
    print("Para enviar dados: docker compose -f simuladores/compose.yaml up -d reservatorio-javascript")


if __name__ == "__main__":
    main()
