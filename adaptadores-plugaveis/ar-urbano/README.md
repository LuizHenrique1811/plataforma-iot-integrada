# Adaptador ar-urbano (nível 2)

Adaptador plugável do UC-03 (RF-INT-03): as estações de qualidade do ar publicam um JSON próprio, que não pode mudar, no tópico `legado/estacoes/{estacao}`. Este contêiner traduz cada mensagem para a mensagem canônica v1.0 e a publica no tópico canônico `{inquilino}/{site}/{dominio}/{dispositivo}/telemetria`.

- Não usa nenhum código do núcleo: só MQTT e o contrato (`contratos/json-schema`).
- Sobe e desce sem recompilar nem reiniciar o núcleo:

```bash
docker compose -f adaptadores-plugaveis/ar-urbano/compose.yaml up -d --build
```

- A temperatura chega em Fahrenheit e segue com a unidade `[degF]`; o núcleo converte para a unidade do perfil (RF-PRO-01).
- O `id_mensagem` é derivado da estação e do horário (UUID v5): a mesma leitura reenviada pela estação é descartada pela deduplicação (RF-ING-08).

Testes (validam a saída contra o JSON Schema canônico):

```bash
docker run --rm -v "${PWD}:/repo" -w /repo/adaptadores-plugaveis/ar-urbano python:3.12-slim sh -c "pip install -q pytest jsonschema && pytest -q testes"
```
