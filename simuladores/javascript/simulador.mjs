// Simulador de nível de reservatório (UC-06) em JavaScript.
//
// Integração de nível 1 por HTTP (RF-ING-02) usando só a biblioteca padrão do Node 22: fetch e
// crypto.randomUUID. Nenhum pacote instalado: a plataforma não exige biblioteca própria (RF-INT-02).
//
// Uso: node simulador.mjs            (envia a cada INTERVALO_S segundos)
//      node simulador.mjs --amostra  (imprime uma mensagem e sai)

import { randomUUID } from "node:crypto";
import { pathToFileURL } from "node:url";

const API_URL = process.env.API_URL ?? "http://host.docker.internal:8000";
const TOKEN = process.env.TOKEN_RESERVATORIO ?? "";
const DISPOSITIVO = process.env.DISPOSITIVO ?? "reservatorio-01";
const INTERVALO_S = Number(process.env.INTERVALO_S ?? 5);

export function mensagem(nivel, agora = new Date()) {
  return {
    versao: "1.0",
    id_mensagem: randomUUID(),
    dispositivo: DISPOSITIVO,
    tipo: "telemetria",
    timestamp: agora.toISOString(),
    medidas: [{ grandeza: "nivel", valor: Number(nivel.toFixed(3)), unidade: "m" }],
  };
}

// O reservatório enche e esvazia devagar ao longo do dia (aqui, em poucos minutos).
export function nivelEm(segundos) {
  return 5 + 3.5 * Math.sin(segundos / 90);
}

async function enviar(carga) {
  const resposta = await fetch(`${API_URL}/api/v1/ingestao`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${TOKEN}` },
    body: JSON.stringify(carga),
  });
  const corpo = await resposta.json();
  console.log(`${new Date().toISOString()} nivel=${carga.medidas[0].valor} m -> HTTP ${resposta.status} ${corpo.situacao ?? corpo.codigo}`);
}

async function main() {
  if (process.argv.includes("--amostra")) {
    console.log(JSON.stringify(mensagem(nivelEm(0))));
    return;
  }
  if (!TOKEN) {
    console.error("Defina TOKEN_RESERVATORIO (token do dispositivo, emitido no cadastro)");
    process.exit(1);
  }
  const inicio = Date.now();
  for (;;) {
    try {
      await enviar(mensagem(nivelEm((Date.now() - inicio) / 1000)));
    } catch (erro) {
      console.error(`falha ao enviar: ${erro.message}`);
    }
    await new Promise((resolver) => setTimeout(resolver, INTERVALO_S * 1000));
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
