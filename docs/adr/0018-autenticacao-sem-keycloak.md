# ADR-0018: Autenticação por token de dispositivo e chave de API, sem Keycloak

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-SEG-01, RF-SEG-02, RF-SEG-03, RF-SEG-04, RF-DIS-02

## Contexto

O documento pede OpenID Connect com segundo fator para administradores (RF-SEG-01), cinco papéis (RF-SEG-02), isolamento por inquilino (RF-SEG-03), dispositivos restritos aos próprios tópicos (RF-SEG-04) e credencial única por dispositivo, com revogação (RF-DIS-02). Ele sugere o Keycloak (seção 9.1). O prazo do trabalho é de um dia ([ADR-0007](0007-infraestrutura-aberta.md)).

## Decisão

- **Dispositivos:** token aleatório por dispositivo, emitido no cadastro (`POST /api/v1/dispositivos`) e guardado só como hash. Ele vale para HTTP e para MQTT. Revogar apaga a credencial ([ADR-0015](0015-revogacao-de-credencial-na-borda.md) para a borda).
- **Pessoas e integrações:** chave de API com `tenant_id` e papel (administrador, gestor, operador, integrador ou leitor), guardada como hash numa tabela. A API confere o papel em cada rota.
- **Isolamento:** todas as tabelas de dados têm `tenant_id`, e o PostgreSQL aplica row-level security com o inquilino da requisição.
- **MQTT:** o Mosquitto autentica cada dispositivo e o restringe aos próprios tópicos com o plugin de segurança dinâmica, que vem na imagem oficial e é administrado pelo `servico-core` em tempo de execução. Se o plugin não couber no prazo, a alternativa é o `servico-core` recusar mensagens cujo tópico não corresponda ao dispositivo autenticado, com status "simplificado".
- **Segundo fator (RF-SEG-01):** não implementado e documentado. Keycloak com TOTP só se sobrar tempo.

## Alternativas consideradas

- **Keycloak** (sugerido pelo documento). Entrega OIDC, papéis e TOTP prontos, mas exige configurar realm, clientes e fluxo de tokens na API, e soma memória no notebook.
- **Certificados X.509 por dispositivo.** O RF-DIS-02 aceita token ou X.509; certificados exigiriam uma CA própria e TLS mútuo.

## Consequências

- Sem serviço de identidade para subir. A autenticação fica testável com pytest.
- RF-SEG-01 fica como "documentado": sem OIDC e sem segundo fator.
- Chaves de API não expiram sozinhas. A validade e o escopo das chaves são o RF-SEG-06 (Importante).
- **Evolução:** Keycloak como provedor OIDC, com a API validando tokens JWT no lugar da chave. Os papéis e o `tenant_id` continuam os mesmos.
