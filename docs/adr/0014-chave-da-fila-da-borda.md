# ADR-0014: Chave de cifragem da fila da borda

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-SEG-05, RNF-11, RNF-07

## Contexto

O RF-SEG-05 exige cifrar a fila local da borda, com o critério "disco retirado de um nó de borda não revela os dados guardados". A fila usa SQLCipher. Se a chave ficar no mesmo disco que o banco, quem leva o disco leva também a chave, e o critério não é cumprido. A borda também precisa voltar a funcionar sozinha depois de uma queda de energia, inclusive sem internet (RNF-04, RNF-07).

## Alternativas

| # | Onde fica a chave | Cumpre o critério? | Liga sozinha sem internet? | Custo |
|---|---|---|---|---|
| 1 | Arquivo ou variável de ambiente no mesmo disco | Não | Sim | Nenhum |
| 2 | Mídia separada do disco de dados (pendrive), montada como Docker secret | Sim, para o disco retirado | Sim | Um pendrive |
| 3 | TPM 2.0 ou elemento seguro, com a chave selada ao hardware | Sim | Sim | Módulo extra no Raspberry Pi |
| 4 | Entregue pela central a cada inicialização, mantida só em memória | Sim | **Não**: depois de uma queda de energia sem link, a fila fica inacessível | Nenhum |
| 5 | Senha digitada por um operador na inicialização | Sim | **Não**, sem atendimento | Nenhum |

## Decisão

Opção **2** no trabalho, com a opção **3** documentada como caminho para produção.

- A chave fica num arquivo fora do volume de dados da borda e é montada no contêiner como Docker secret (`/run/secrets/chave_fila`), nunca na imagem nem no Compose. A chave de 256 bits do SQLCipher é o SHA-256 do conteúdo do arquivo.
- O banco da borda inteiro (fila, catálogo, medições e alarmes) é aberto pelo SQLCipher (pacote `sqlcipher3`, com a biblioteca embutida) quando `CHAVE_FILA_ARQUIVO` está definida; sem ela, a borda funciona em claro e registra um aviso.
- Na demonstração, a mídia separada é simulada pela pasta `infra/borda/segredos/`, fora do volume de dados e fora do repositório.
- **Evidência para o RF-SEG-05:** `test_disco_retirado_nao_revela_os_dados` grava na fila, confere que o conteúdo não aparece no arquivo e que ele não abre sem a chave nem com a chave errada.

## Consequências

- O critério do documento (disco retirado) é atendido.
- Não protege contra o roubo do equipamento inteiro com o pendrive conectado. Essa ameaça fica documentada.
- Perder o pendrive torna a fila ilegível. Os dados ainda não sincronizados são perdidos, então é preciso ter uma cópia da chave guardada fora da borda.
