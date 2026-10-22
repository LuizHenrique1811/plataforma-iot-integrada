# Matriz de rastreabilidade

Liga cada requisito do Documento de Requisitos v2.0 ([requisitos.md](requisitos.md)) ao seu tratamento, ao status e à evidência de que foi atendido. As descrições abaixo são resumos; o texto oficial está no documento.

## Legenda

**Tratamento previsto:**

- **implementar**: implementado de verdade, com testes.
- **simplificar**: implementado numa versão reduzida, descrita nas observações.
- **documentar**: não implementado; a justificativa fica no ADR ou em `arquitetura.md`.

**Status:** `pendente`, `parcial` (parte implementada; o que falta está nas observações), `implementado`, `simplificado` ou `documentado`.

**Evidência:** hash do commit (que cita o ID do requisito), caminho do teste automatizado e/ou ADR.

## Requisitos funcionais Essenciais (33)

### CEN · Cenários e catálogo

| ID | Requisito | Critério de aceitação | Tratamento | Status | Evidência |
|---|---|---|---|---|---|
| RF-CEN-01 | Catálogo de domínios configurável por inquilino | Gestor cria o domínio "pecuaria" pela API ou painel, sem alterar código | implementar | implementado | [ADR-0003](adr/0003-catalogo-configuravel.md), `servico-core/testes/test_catalogo.py`, `servico-core/testes/test_api_catalogo.py` |
| RF-CEN-02 | Perfis de dispositivo: grandezas, unidades, faixa válida e intervalo esperado de envio | Medida fora da faixa é marcada como suspeita; perfil reutilizável entre projetos | implementar | implementado | [ADR-0003](adr/0003-catalogo-configuravel.md), `servico-core/testes/test_pipeline.py`, `servico-core/testes/test_api_catalogo.py` |
| RF-CEN-03 | Hierarquia inquilino → local → área → dispositivo | A mesma hierarquia representa um bairro com praças e uma fazenda com talhões | implementar | implementado | `servico-core/testes/test_catalogo.py`, `servico-core/testes/test_postgres.py` |

### ING · Conectividade e ingestão

| ID | Requisito | Critério de aceitação | Tratamento | Status | Evidência |
|---|---|---|---|---|---|
| RF-ING-01 | Telemetria via MQTT 3.1.1 e 5.0 sobre TLS | Dispositivo autenticado publica no tópico canônico; mensagem persistida em até 2 s | implementar | parcial | [ADR-0008](adr/0008-pipeline-de-ingestao.md), `servico-core/testes/test_mqtt.py` |
| RF-ING-02 | Telemetria via HTTPS (`POST /api/v1/ingestao`) | Válida retorna 202; inválida retorna 400 com a lista de erros | implementar | implementado | [ADR-0008](adr/0008-pipeline-de-ingestao.md), `servico-core/testes/test_api_ingestao.py` |
| RF-ING-03 | Lotes (`POST /api/v1/ingestao/lote`) com resultado por mensagem | Lote de 5.000 com 3 inválidas grava 4.997 e informa as 3 recusadas | implementar | implementado | [ADR-0008](adr/0008-pipeline-de-ingestao.md), `servico-core/testes/test_api_ingestao.py` |
| RF-ING-04 | Aceitar dados atrasados, armazenando pelo horário da medição | Medição de 48 h atrás entra na posição correta e não gera alarme como se fosse atual | implementar | implementado | [ADR-0013](adr/0013-dados-atrasados-e-agregados.md), `servico-core/testes/test_motor.py`, `servico-core/testes/test_api_regras.py` |
| RF-ING-06 | Validar cada mensagem contra o JSON Schema da sua versão | Mensagem fora do esquema vai para a DLQ, com o motivo | implementar | implementado | `contratos/json-schema/`, `servico-core/testes/test_pipeline.py`, `servico-core/testes/test_postgres.py` |
| RF-ING-08 | Descartar mensagens duplicadas pelo `id_mensagem` | Mensagem reenviada pela borda com o mesmo id é armazenada uma única vez | implementar | implementado | [ADR-0011](adr/0011-janela-de-deduplicacao.md), `servico-core/testes/test_postgres.py` |

- RF-ING-01: o consumidor MQTT assina os tópicos canônicos com sessão persistente e confirma cada mensagem só depois de gravar; o teste com um Mosquitto real exige gravação em até 2 s. Faltam o listener TLS e a autenticação no broker (os Compose usam a porta 1883 sem TLS).
- RF-ING-04: a medição atrasada entra pelo horário da medição, é marcada como não atual e não dispara regra; o teste usa uma medição de 48 h atrás acima do limite.

### EDG · Borda e conectividade limitada

| ID | Requisito | Critério de aceitação | Tratamento | Status | Evidência |
|---|---|---|---|---|---|
| RF-EDG-01 | Nó de borda com ingestão local (MQTT e HTTP) e fila persistente | Com o link desligado por 72 h, nenhuma mensagem aceita pelo nó é perdida | implementar | implementado | [ADR-0006](adr/0006-uma-imagem-dois-ambientes.md), [ADR-0020](adr/0020-repositorios-sql-na-borda.md), `testes-sistema/desconexao/test_desconexao_72h.py`, `servico-core/testes/test_borda.py` |
| RF-EDG-02 | Sincronizar com a central ao reconectar, em lotes, sem perdas nem duplicatas | Após a reconexão, cada mensagem chega uma única vez, ordenada pelo horário da medição | implementar | implementado | [ADR-0011](adr/0011-janela-de-deduplicacao.md), `testes-sistema/desconexao/test_desconexao_72h.py`, `servico-core/testes/test_sincronizacao.py` |

### DIS · Gestão de dispositivos

| ID | Requisito | Critério de aceitação | Tratamento | Status | Evidência |
|---|---|---|---|---|---|
| RF-DIS-01 | Cadastro com perfil, domínio, local, área, fabricante, firmware e inquilino | Dispositivo cadastrado pela API **e** pelo painel aparece com todos os atributos | implementar (API); simplificar (painel) | simplificado | [ADR-0019](adr/0019-painel-de-cadastro.md), `servico-core/testes/test_api_catalogo.py` |
| RF-DIS-02 | Credenciais únicas por dispositivo (X.509 ou token), com revogação | Credencial revogada é recusada na conexão seguinte, na central e nos nós de borda | simplificar | parcial | [ADR-0015](adr/0015-revogacao-de-credencial-na-borda.md), `servico-core/testes/test_api_catalogo.py`, `servico-core/testes/test_postgres.py` |
| RF-DIS-06 | Online/offline pelo intervalo esperado do perfil | Sensor que envia de hora em hora não aparece offline após 5 min sem dados | implementar | implementado | [ADR-0010](adr/0010-estado-desconhecido.md), `servico-core/testes/test_consultas.py` |

- RF-DIS-01: o critério pede cadastro pela API **e** por um painel. O painel é a documentação interativa da API (Swagger UI), sem interface web própria.
- RF-DIS-02: token por dispositivo é uma das opções do próprio requisito. Na central já funcionam a emissão no cadastro (só o hash é guardado), a revogação pela API e a recusa na conexão seguinte, além da recusa no pipeline de medições posteriores à revogação. Falta a borda aplicar a lista de revogação ao reconectar (ADR-0015).

### INT · Integração de projetos existentes

| ID | Requisito | Critério de aceitação | Tratamento | Status | Evidência |
|---|---|---|---|---|---|
| RF-INT-01 | Publicar o contrato canônico versionado (JSON Schema e AsyncAPI) | Contrato acessível por URL pública, com histórico de versões | implementar | implementado | [ADR-0002](adr/0002-integracao-por-contratos-abertos.md), rota `/contratos`, `servico-core/testes/test_api_ingestao.py` |
| RF-INT-02 | Integração apenas com protocolos padrão, sem biblioteca proprietária | Exemplos funcionais em três linguagens usando só bibliotecas genéricas de MQTT/HTTP | implementar | implementado | `simuladores/` (Python/MQTT, JavaScript/HTTP, Java/HTTP), job `integracao` do CI, [ADR-0021](adr/0021-simuladores-e-adaptador-como-clientes-externos.md) |
| RF-INT-03 | Adaptadores de protocolo plugáveis em contêiner, em qualquer linguagem | Novo adaptador implantado sem recompilar nem reiniciar o núcleo (central ou borda) | implementar | implementado | `adaptadores-plugaveis/ar-urbano/` e seus testes, [ADR-0021](adr/0021-simuladores-e-adaptador-como-clientes-externos.md) |

- RF-INT-02: os simuladores não usam nada do núcleo. O Python usa só `paho-mqtt`; o JavaScript, só o `fetch` nativo do Node 22, sem pacotes; o Java, só o `HttpClient` nativo, sem dependências. As amostras das três linguagens são validadas contra o JSON Schema canônico no CI.
- RF-INT-03: o adaptador `ar-urbano` roda em contêiner próprio, traduz o JSON legado das estações para a mensagem canônica e entra no ar sem reiniciar o núcleo (`docker compose ... up` separado). O `id_mensagem` derivado da estação e do horário faz a leitura reenviada pelo firmware ser deduplicada.

### PRO · Processamento e regras

| ID | Requisito | Critério de aceitação | Tratamento | Status | Evidência |
|---|---|---|---|---|---|
| RF-PRO-01 | Normalizar unidades e enriquecer com perfil, domínio, local e área | Mensagem armazenada contém inquilino, domínio, local e área do cadastro | implementar | implementado | [ADR-0008](adr/0008-pipeline-de-ingestao.md), `servico-core/testes/test_pipeline.py` |
| RF-PRO-02 | Regras condição → ação: limite, ausência de dados, janela de tempo e área geográfica | Regra "temperatura do silo > 30 °C" dispara em até 3 s após a mensagem | implementar | simplificado | `servico-core/testes/test_motor.py`, `servico-core/testes/test_api_regras.py`, [testes-sistema/carga](../testes-sistema/carga/README.md) (p95 de 0,40 s a 0,60 s até o disparo, a 1.000 msg/s) |
| RF-PRO-03 | Ações: gerar alarme, notificar, enviar comando, chamar webhook e publicar em tópico | Cada tipo de ação é demonstrado por um teste automatizado | implementar | implementado | `servico-core/testes/test_acoes.py` (um teste por ação) |
| RF-PRO-05 | Ciclo de vida dos alarmes (ativo, reconhecido, resolvido) com severidade | Alarme gerado na borda durante a desconexão aparece com o horário em que ocorreu | implementar | implementado | [ADR-0009](adr/0009-relogio-da-borda.md), `servico-core/testes/test_alarmes.py`, `servico-core/testes/test_borda.py`, `testes-sistema/desconexao/test_desconexao_72h.py` |

- RF-PRO-02: regras de limite, janela de tempo (condição contínua por um período, contada pelo horário da medição) e ausência de dados (verificação periódica). Cada regra dispara na transição e, quando a condição deixa de valer, resolve sozinha o alarme aberto. A avaliação acontece logo depois da gravação, na mesma requisição. "Área geográfica" é filtro pelo identificador da área (inconsistência 2), por isso "simplificado".
- RF-PRO-03: as cinco ações são classes do padrão Strategy, cada uma com seu teste: alarme, notificar (no MVP, registrado no log; ADR-0012), comando (mensagem canônica no tópico `comando` do dispositivo de destino), webhook (POST fora da thread de ingestão, sem novas tentativas, que são o RF-APP-03) e publicar (tópico do próprio inquilino). Uma ação com falha não impede as outras.
- RF-PRO-05: ciclo ativo → reconhecido → resolvido, com severidade, transições inválidas recusadas (409) e operação restrita a gestor, operador e administrador. Cada nó abre e resolve os alarmes que ele mesmo gera, um aberto por regra, dispositivo e origem. Na borda, a regra local abre o alarme e o resolve quando a condição deixa de valer; os eventos `alarme` e `alarme_resolvido` vão para a fila com prioridade e a central os aplica com os horários da borda, mesmo chegando atrasados.

### DAD · Dados

| ID | Requisito | Critério de aceitação | Tratamento | Status | Evidência |
|---|---|---|---|---|---|
| RF-DAD-01 | Séries temporais com consulta por dispositivo, grandeza, área e intervalo | Consulta de 24 h de um dispositivo responde em até 1 s | implementar | implementado | `servico-core/testes/test_consultas.py`, `servico-core/testes/test_postgres.py` |
| RF-DAD-02 | Último valor de cada grandeza de cada dispositivo | Último estado disponível sem consultar o histórico | implementar | implementado | [ADR-0017](adr/0017-ultimo-estado-no-postgresql.md), `servico-core/testes/test_consultas.py` |
| RF-DAD-05 | Anonimizar ou pseudonimizar dados pessoais antes de armazenar ou publicar | Nenhum dado pessoal identificável aparece na API pública | simplificar | documentado | Ver "Requisitos só documentados" |

- RF-DAD-01: `GET /api/v1/dispositivos/{id}/telemetria` filtra por grandeza e intervalo, pelo horário da medição. A tabela `medicoes` também guarda a área de cada medição, para consultas por área no Grafana; a API não tem uma rota de consulta por área.
- RF-DAD-05: não implementado; a justificativa e a proposta estão em "Requisitos só documentados".

### APP · Aplicação e serviços

| ID | Requisito | Critério de aceitação | Tratamento | Status | Evidência |
|---|---|---|---|---|---|
| RF-APP-01 | API REST versionada e documentada em OpenAPI 3 | Documentação interativa gerada a partir do contrato e testada no pipeline | implementar | implementado | [ADR-0019](adr/0019-painel-de-cadastro.md), `servico-core/testes/test_contratos.py` |
| RF-APP-07 | Paginação, filtros e ordenação padronizados nas listagens | Todas as listagens aceitam os mesmos parâmetros de paginação | implementar | implementado | `servico-core/testes/test_api_catalogo.py` |

- RF-APP-01: `/docs` é gerado de `contratos/openapi.yaml`, o contrato é validado no CI, os corpos das requisições são validados pelos schemas do contrato, todo erro (inclusive os do framework) sai no formato `Erro`, e um teste confere nos dois sentidos que as rotas implementadas e as operações do contrato coincidem.
- RF-APP-07: todas as listagens, inclusive as de regras e alarmes, aceitam `pagina`, `tamanho` e `ordenar` e respondem no envelope `Pagina`.

### SEG · Segurança e acesso

| ID | Requisito | Critério de aceitação | Tratamento | Status | Evidência |
|---|---|---|---|---|---|
| RF-SEG-01 | Autenticação por OpenID Connect, com segundo fator para administradores | Administrador sem segundo fator não acessa o painel | documentar | documentado | [ADR-0018](adr/0018-autenticacao-sem-keycloak.md) |
| RF-SEG-02 | Papéis: administrador, gestor, operador, integrador e leitor | Operador não consegue alterar regras nem dispositivos | simplificar | simplificado | [ADR-0018](adr/0018-autenticacao-sem-keycloak.md), `servico-core/testes/test_catalogo.py`, `servico-core/testes/test_api_catalogo.py` |
| RF-SEG-03 | Isolar os dados de cada inquilino | Usuário de um inquilino não vê dados de outro, nem pela API | simplificar | parcial | [ADR-0018](adr/0018-autenticacao-sem-keycloak.md), `servico-core/testes/test_pipeline.py` |
| RF-SEG-04 | Restringir cada dispositivo aos próprios tópicos MQTT, na central e na borda | Publicação em tópico de outro dispositivo é recusada | simplificar | parcial | [ADR-0018](adr/0018-autenticacao-sem-keycloak.md), `servico-core/testes/test_mqtt.py` |
| RF-SEG-05 | Credencial própria para nós de borda e fila local cifrada | Disco retirado de um nó de borda não revela os dados guardados | simplificar | simplificado | [ADR-0014](adr/0014-chave-da-fila-da-borda.md), `servico-core/testes/test_sqlite.py` (`test_disco_retirado_nao_revela_os_dados`) |

Simplificações previstas, sem Keycloak ([ADR-0018](adr/0018-autenticacao-sem-keycloak.md)):

- **SEG-01:** sem OIDC e sem segundo fator, apenas documentado. Keycloak com TOTP só se sobrar tempo.
- **SEG-02:** chave de API com papel guardado em tabela.
- **SEG-03:** `tenant_id` com row-level security no PostgreSQL.
- **SEG-04:** ACL por dispositivo no Mosquitto, sobre o padrão `{inquilino}/{site}/{dominio}/{dispositivo}/...`.
- **SEG-05:** SQLCipher na fila da borda.

### OBS · Observabilidade e administração

| ID | Requisito | Critério de aceitação | Tratamento | Status | Evidência |
|---|---|---|---|---|---|
| RF-OBS-01 | Métricas: mensagens por segundo, latência e erros por módulo | Métricas disponíveis em formato Prometheus | simplificar | simplificado | [ADR-0007](adr/0007-infraestrutura-aberta.md), `servico-core/testes/test_api_ingestao.py` |
| RF-OBS-02 | Logs estruturados (JSON) com identificador de correlação | Uma mensagem pode ser rastreada em todos os módulos, da borda à central | simplificar | simplificado | [ADR-0008](adr/0008-pipeline-de-ingestao.md), `servico-core/adaptadores/observabilidade.py` |

Simplificação prevista: endpoint `/metrics` no formato Prometheus, sem subir o servidor Prometheus, e logs JSON com `correlation_id` igual ao `id_mensagem`.

- RF-OBS-01: `/metrics` expõe mensagens por entrada, situação e motivo de rejeição, e um histograma do tempo de ingestão.
- RF-OBS-02: central e borda gravam logs JSON com `correlation_id` igual ao `id_mensagem`, e a mesma mensagem leva o mesmo `id_mensagem` e o campo `via` da borda até a central. Não há rastreamento distribuído (RF-OBS-03, Importante).
- RF-SEG-03 (acima): toda consulta e toda gravação filtram pelo inquilino da credencial, e os testes mostram um inquilino sem acesso ao catálogo e aos dispositivos de outro. Falta o row-level security como segunda barreira no banco.
- RF-SEG-04 (acima): enquanto a ACL do broker não existe, o `servico-core` recusa (DLQ, motivo `topico_divergente` ou `dispositivo_divergente`) mensagens publicadas no tópico de outro dispositivo, local ou domínio, que é a alternativa prevista no ADR-0018.

## Requisitos não funcionais

O documento não atribui prioridade aos RNFs.

| ID | Atributo | Métrica | Tratamento | Status | Evidência |
|---|---|---|---|---|---|
| RNF-01 | Desempenho | 1.000 msg/s num servidor central; 10.000 com réplicas | implementar 1.000; documentar 10.000 | implementado (1.000); documentado (10.000) | [testes-sistema/carga](../testes-sistema/carga/README.md), [resultado.md](../testes-sistema/carga/resultado.md), [ADR-0022](adr/0022-escala-da-ingestao-com-assinatura-compartilhada.md) |
| RNF-02 | Latência | p95 ingestão → persistência ≤ 2 s e → regra ≤ 3 s; regras de borda ≤ 3 s | implementar | implementado | [testes-sistema/carga](../testes-sistema/carga/README.md) (p95 de 0,09 s a 0,53 s até a persistência e de 0,40 s a 0,60 s até a regra, a 1.000 msg/s), painel de latência p95 no Grafana, `servico-core/testes/test_borda.py` |
| RNF-03 | Disponibilidade | 99,5% ao mês | documentar | documentado | Ver "Requisitos só documentados" |
| RNF-04 | Tolerância a desconexão | Borda opera 72 h sem link, sem perda | implementar | implementado | `testes-sistema/desconexao/test_desconexao_72h.py` |
| RNF-05 | Banda limitada | Sincronização a partir de 64 kbit/s, com cargas compactadas | documentar | documentado | Ver "Requisitos só documentados" |
| RNF-06 | Hardware de borda | 4 núcleos ARM e 4 GB de RAM | simplificar: limitar CPU e memória no Compose da borda e medir | simplificado | [infra/README.md](../infra/README.md#consumo-medido): 77 MB em repouso |
| RNF-07 | Robustez a falta de energia | Queda de energia não corrompe fila nem configuração | implementar WAL; documentar hardware | implementado | [ADR-0016](adr/0016-energia-e-armazenamento-da-borda.md), `testes-sistema/desconexao/test_desconexao_72h.py` (borda reiniciada no meio do corte) |
| RNF-08 | Neutralidade de cenário | Domínio, perfil ou modelo novo só por configuração | implementar | implementado | [ADR-0003](adr/0003-catalogo-configuravel.md), `servico-core/testes/test_api_catalogo.py` (`test_uc06_cenario_novo_de_reservatorios_sem_programar`), `demo/dominio_novo.py`, `testes-sistema/carga/carga.py` (cenário de carga criado só pela API) |
| RNF-09 | Escalabilidade | Serviços centrais sem estado, escaláveis horizontalmente | implementar | implementado | [ADR-0006](adr/0006-uma-imagem-dois-ambientes.md), [ADR-0022](adr/0022-escala-da-ingestao-com-assinatura-compartilhada.md) (10 processos num grupo de assinatura compartilhada), `servico-core/testes/test_mqtt.py` |
| RNF-10 | Durabilidade | Nenhuma mensagem confirmada (ACK) é perdida | implementar | simplificado | [ADR-0008](adr/0008-pipeline-de-ingestao.md), [ADR-0016](adr/0016-energia-e-armazenamento-da-borda.md), [ADR-0022](adr/0022-escala-da-ingestao-com-assinatura-compartilhada.md), `servico-core/testes/test_mqtt.py`, `servico-core/testes/test_sqlite.py` |
| RNF-11 | Segurança | TLS 1.2+ em toda interface externa; dados e segredos cifrados em repouso | simplificar | parcial | [ADR-0014](adr/0014-chave-da-fila-da-borda.md), `servico-core/testes/test_sqlite.py` |
| RNF-12 | Privacidade | LGPD: minimização, finalidade e registro das operações | simplificar | documentado | Ver "Requisitos só documentados" |
| RNF-13 | Independência de linguagem | 100% das interfaces descritas por contratos abertos | implementar | implementado | [ADR-0002](adr/0002-integracao-por-contratos-abertos.md), `.github/workflows/ci.yaml` |
| RNF-14 | Portabilidade | Contêineres OCI; Docker Compose no MVP e na borda | implementar | implementado | `infra/`, [ADR-0007](adr/0007-infraestrutura-aberta.md) |
| RNF-15 | Manutenibilidade | Cobertura ≥ 70% no núcleo; análise estática sem falhas críticas | implementar | implementado | `.github/workflows/ci.yaml`: cobertura de 98%, ruff |
| RNF-16 | Usabilidade e acessibilidade | Interface em português, responsiva, WCAG 2.1 AA | documentar | documentado | [ADR-0019](adr/0019-painel-de-cadastro.md); ver "Requisitos só documentados" |
| RNF-17 | Compatibilidade | APIs versionadas; versão descontinuada funciona por 12 meses | simplificar: prefixo `/api/v1` e política documentada | simplificado | `contratos/openapi.yaml` (1.1.0, prefixo `/api/v1`), `contratos/json-schema/` (campo `versao` em cada mensagem) |
| RNF-18 | Recuperação | Backup diário; RPO ≤ 24 h e RTO ≤ 4 h | documentar | documentado | Ver "Requisitos só documentados" |

- RNF-01: 1.000 msg/s por MQTT, sem perdas nem duplicatas, com 10 processos do `servico-core` no notebook da apresentação. A folga é pequena: o teto medido vai de 1.020 a 1.050 msg/s, conforme o que mais roda na máquina, e duas execuções com o notebook carregado e o banco ainda por TCP ficaram em 884 e 903 msg/s. As 10.000 msg/s ficam documentadas: exigem gravação em micro-lotes, mais servidores e réplicas do banco.
- RNF-02: a regra local da borda é avaliada na mesma chamada da ingestão local, sem depender do link; não foi medida sob carga.
- RNF-10: a central confirma ao broker só depois de gravar, e a borda grava a fila na mesma transação da ingestão. A exceção são as réplicas extras do teste de carga, de sessão MQTT limpa: se uma delas cair sem parar direito, perde até 20 mensagens recebidas e ainda não confirmadas (ADR-0022).
- RNF-11: cifrados em repouso estão a fila da borda (SQLCipher) e os tokens e chaves (só o hash é guardado). Os segredos ficam em `.env` e em segredo Docker, fora do repositório. Falta TLS nos brokers e nas APIs; as portas são publicadas só em 127.0.0.1 por padrão.
- RNF-17: as rotas têm o prefixo `/api/v1`, e cada mensagem diz a versão do contrato no campo `versao`; o validador aceita várias versões lado a lado. Política: uma quebra de contrato só vem numa versão MAJOR nova (`/api/v2`, mensagem `2.0`), e a anterior continua aceita por 12 meses.

## Requisitos fora do Essencial que entram no escopo

| ID | Prioridade | Requisito | Tratamento | Status | Evidência |
|---|---|---|---|---|---|
| RF-EDG-03 | Importante | Regras locais na borda, sem depender da central | simplificar | simplificado | `servico-core/testes/test_borda.py`, `testes-sistema/desconexao/test_desconexao_72h.py` |
| RF-CEN-04 | Importante | Geometrias GeoJSON e consultas espaciais | documentar | documentado | [ADR-0007](adr/0007-infraestrutura-aberta.md) |
| RF-APP-05 | Importante | Notificação por e-mail, aplicativo de mensagens e SMS | simplificar | simplificado | [ADR-0012](adr/0012-sms-pela-central.md), `servico-core/testes/test_api_regras.py` |
| RF-DAD-06 | Importante | Trilha de auditoria das operações administrativas | documentar | documentado | Ver "Requisitos só documentados" |
| RF-PRO-04 | Importante | Agregados por hora e por dia | documentar | documentado | [ADR-0013](adr/0013-dados-atrasados-e-agregados.md) |

- RF-EDG-03: a borda executa o mesmo motor de regras, só com as regras de `"ambito": "borda"`, cadastradas pela API da própria borda; a distribuição de regras pela central é o RF-EDG-04 (Importante). Sem link, o alarme é aberto na borda, o comando vai ao atuador pelo broker local e os eventos `alarme` e `comando_enviado` entram na fila para a central.
- RF-CEN-04: no MVP, área é identificador; geometria e consultas espaciais ficam para a fase 2. Os sites aceitam um ponto GeoJSON no cadastro, mas nada é consultado por geometria.
- RF-DAD-06: o briefing o listava entre os Essenciais "só documentar", mas no documento ele é Importante. Continua apenas documentado.
- RF-PRO-04: o ADR-0013 decidiu usar continuous aggregates do TimescaleDB, que recalculam a janela afetada por dados atrasados, mas eles não foram criados. O painel do Grafana agrega as medições brutas com `time_bucket`, o que basta no volume da demonstração.

## Casos de uso demonstrados

| UC | Requisitos citados no documento | Passo da demo | Status | Evidência |
|---|---|---|---|---|
| UC-01 · Fazenda com link via satélite | RF-CEN-03, RF-CEN-04, RF-EDG-01 a 03, RF-ING-03, RF-ING-04 | 2 e 3 | simplificado | `testes-sistema/desconexao/test_desconexao_72h.py`, `servico-core/testes/test_borda.py` |
| UC-02 · Alarme de temperatura em silo | RF-CEN-02, RF-PRO-02, RF-PRO-05, RF-APP-05 | 2 | simplificado | `servico-core/testes/test_api_regras.py` (`test_uc02_alarme_de_temperatura_em_silo`) |
| UC-04 · Alarme de lixeira cheia e rota de coleta | RF-PRO-02, RF-PRO-03, RF-PRO-05, RF-APP-03 | (teste) | implementado | `servico-core/testes/test_api_regras.py`, simulador `lixeira-java` |
| UC-03 · Qualidade do ar urbana (nível 2) | RF-INT-03, RF-INT-05, RF-INT-06, RF-ING-06 | 4 | simplificado | `adaptadores-plugaveis/ar-urbano/`, simulador `estacao-legada-python` |
| UC-06 · Cenário novo: reservatórios | RF-CEN-01, RF-CEN-02, RNF-08 | 1 | implementado | `servico-core/testes/test_api_catalogo.py`, `demo/dominio_novo.py`, simulador `reservatorio-javascript` |
| UC-05 · Dimerizar a iluminação de uma praça | RF-DIS-04, RF-DIS-05, RF-DIS-07 | — | documentado | Depende do gêmeo do dispositivo e de grupos (Importantes), fora do MVP; a regra com ação de comando já cobre o envio a um atuador |

## Critérios de aceite do MVP (seção 9.3)

| Critério | Status | Evidência |
|---|---|---|
| Um projeto urbano e um rural integrados; o rural com nó de borda | implementado | `demo/preparar.py` (rural coop-cerrado com borda; urbano semma), `testes-sistema/desconexao/test_desconexao_72h.py` |
| Link da borda cortado por 72 h sem perda nem duplicação após a reconexão | implementado | `testes-sistema/desconexao/test_desconexao_72h.py` |
| Um domínio novo criado só por configuração (RNF-08) | implementado | `servico-core/testes/test_api_catalogo.py` (`test_uc06_cenario_novo_de_reservatorios_sem_programar`) |
| Integração demonstrada em pelo menos três linguagens | implementado | `simuladores/` e job `integracao` do CI (amostras das três linguagens validadas contra o contrato) |
| Teste de carga comprovando RNF-01 e RNF-02 em ambiente de homologação | implementado | [testes-sistema/carga](../testes-sistema/carga/README.md): 1.000 msg/s, p95 abaixo de 0,6 s até a persistência e até a regra, sem perdas nem duplicatas, com 10 processos no notebook. O ambiente é o notebook, não uma homologação dedicada, e a folga é pequena |

O MVP foi ensaiado do zero num clone novo do repositório, seguindo o README: preparação, domínio novo, rural com borda, corte de link, urbano com adaptador, três linguagens e carga. O ensaio encontrou e corrigiu três problemas de documentação e de script, registrados nos commits do fechamento.

## Requisitos só documentados

Requisitos fora do que foi implementado, com a justificativa e o caminho previsto:

- **RF-SEG-01 (OIDC com segundo fator).** Substituído por chave de API com papel ([ADR-0018](adr/0018-autenticacao-sem-keycloak.md)). Caminho: Keycloak com o realm da plataforma e TOTP obrigatório para administradores. A API passa a aceitar o token OIDC, com papéis e inquilino vindos das claims.
- **RF-DAD-05 (dados pessoais).** Nenhum cenário do MVP coleta dado pessoal: as medições são de solo, silo, ar, lixeira e reservatório, sem pessoas nem placas. Proposta: o perfil marca quais grandezas são pessoais, e elas são pseudonimizadas (hash com sal por inquilino) antes de gravar e omitidas na API para quem não tem o papel adequado.
- **RF-DAD-06 (auditoria).** As operações administrativas já passam por um ponto único, os serviços de catálogo, regras e alarmes do domínio. Proposta: um observador grava quem, o quê, quando e o valor anterior numa tabela só de inserção.
- **RF-CEN-04 e RF-PRO-04.** Ver as observações acima.
- **RNF-01, segunda meta (10.000 msg/s).** Ver a observação do RNF-01 e o [ADR-0022](adr/0022-escala-da-ingestao-com-assinatura-compartilhada.md).
- **RNF-03 (99,5% ao mês).** O MVP roda numa instância só, sem redundância. O desenho permite alta disponibilidade sem mudar o código:
  - processos sem estado, já testados em 10 réplicas (ADR-0022);
  - broker em cluster ou com ponte;
  - PostgreSQL com réplica e failover;
  - sondas de saúde (`/saude`) já presentes nos Compose.

  Não houve medição de disponibilidade.
- **RNF-05 (64 kbit/s, cargas compactadas).** Os lotes vão em JSON sem compressão. Medido: um lote de 500 leituras tem 152 KB, cerca de 20 s num link de 64 kbit/s; com gzip cai para 13 KB, menos de 2 s. Caminho: `Content-Encoding: gzip` no `POST /api/v1/ingestao/lote` e lotes menores quando o link é lento. A sincronização já tolera quedas no meio do lote, e isso foi testado.
- **RNF-12 (LGPD).** Sem dado pessoal nos cenários (ver RF-DAD-05). O isolamento por inquilino e os papéis já limitam o acesso à finalidade. O registro das operações de tratamento depende da auditoria (RF-DAD-06).
- **RNF-16 (interface acessível em português).** O MVP não tem interface própria: o cadastro é feito pela documentação interativa da API ([ADR-0019](adr/0019-painel-de-cadastro.md)), com descrições em português, e os painéis ficam no Grafana. Uma interface própria teria de passar por avaliação WCAG 2.1 AA.
- **RNF-18 (backup, RPO e RTO).** Os dados da central ficam no volume `timescaledb-dados`. Proposta:
  - `pg_dump` diário, copiado para fora do servidor (RPO de 24 h);
  - restauração ensaiada com `docker compose up` e `pg_restore`, que leva minutos no volume do MVP (RTO bem abaixo de 4 h).

  A borda não precisa de backup próprio: o que importa nela é a fila, que esvazia na central.

## Inconsistências do documento

1. **Regra local na borda.** UC-01 e RF-PRO-05 (Essencial) dependem de regras locais na borda (RF-EDG-03) e de desenho de áreas (RF-CEN-04), ambos Importantes (fase 2), enquanto o MVP promete o caso rural com borda. **Decisão:** implementar uma regra local simples já no MVP.
2. **Condição por área geográfica.** RF-PRO-02 (Essencial) inclui condição por área geográfica, mas as consultas espaciais (RF-CEN-04) são fase 2. **Decisão:** no MVP, "área" é filtro por identificador.
3. **Revogação na borda desconectada.** O critério do RF-DIS-02 exige recusar a credencial revogada "na conexão seguinte" também nos nós de borda, o que é impossível enquanto a borda está sem link. **Decisão:** lista de revogação aplicada na reconexão, com mitigação na central ([ADR-0015](adr/0015-revogacao-de-credencial-na-borda.md)).
4. **Casos de uso que dependem de requisitos Importantes.** UC-02 depende do SMS (RF-APP-05), e UC-03 depende de NGSI-LD (RF-INT-05) e do sandbox (RF-INT-06), todos Importantes. **Decisão:** na demonstração, o UC-02 usa o adaptador de SMS falso ([ADR-0012](adr/0012-sms-pela-central.md)), e o UC-03 mostra só o adaptador em contêiner (RF-INT-03); NGSI-LD e sandbox ficam documentados.

As decisões de arquitetura estão em [adr/README.md](adr/README.md).
