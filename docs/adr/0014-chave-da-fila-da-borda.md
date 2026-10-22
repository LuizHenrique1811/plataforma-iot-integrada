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

Opção **2** no trabalho, com a opção **3** documentada como caminho para produção. A cifragem da fila é o último item da ordem de corte do plano: se não couber no prazo, o RF-SEG-05 fica documentado com esta decisão.

- A chave fica num arquivo fora do volume de dados da borda e é montada no contêiner como Docker secret (`/run/secrets/...`), nunca na imagem nem no Compose.
- Na demonstração, a mídia separada é simulada por um diretório fora do volume de dados.
- **Evidência para o RF-SEG-05:** um teste automatizado copia o arquivo da fila e mostra que ele não abre sem a chave.

## Consequências

- O critério do documento (disco retirado) é atendido.
- Não protege contra o roubo do equipamento inteiro com o pendrive conectado. Essa ameaça fica documentada.
- Perder o pendrive torna a fila ilegível. Os dados ainda não sincronizados são perdidos, então é preciso ter uma cópia da chave guardada fora da borda.
