// Testes com o executor nativo do Node: node --test
import assert from "node:assert/strict";
import { test } from "node:test";

import { mensagem, nivelEm } from "./simulador.mjs";

test("monta a mensagem canônica v1.0", () => {
  const carga = mensagem(4.2, new Date("2026-10-22T05:00:00Z"));
  assert.equal(carga.versao, "1.0");
  assert.equal(carga.tipo, "telemetria");
  assert.equal(carga.timestamp, "2026-10-22T05:00:00.000Z");
  assert.match(carga.id_mensagem, /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
  assert.deepEqual(carga.medidas, [{ grandeza: "nivel", valor: 4.2, unidade: "m" }]);
});

test("cada mensagem tem um id_mensagem novo", () => {
  assert.notEqual(mensagem(1).id_mensagem, mensagem(1).id_mensagem);
});

test("o nível fica dentro da faixa do perfil (0 a 10 m)", () => {
  for (let s = 0; s < 3600; s += 7) {
    const nivel = nivelEm(s);
    assert.ok(nivel >= 0 && nivel <= 10, `nivel fora da faixa: ${nivel}`);
  }
});
