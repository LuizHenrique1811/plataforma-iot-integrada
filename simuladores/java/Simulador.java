// Simulador de lixeira com sensor de nível (UC-04) em Java.
//
// Integração de nível 1 por HTTP (RF-ING-02) usando só a biblioteca padrão do Java 21:
// java.net.http.HttpClient e java.util.UUID. Sem dependências, sem build: o arquivo roda direto com
// `java Simulador.java` (RF-INT-02).
//
// Uso: java Simulador.java            (envia a cada INTERVALO_S segundos)
//      java Simulador.java --amostra  (imprime uma mensagem e sai)

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Locale;
import java.util.UUID;

public class Simulador {

    static String ambiente(String nome, String padrao) {
        String valor = System.getenv(nome);
        return valor == null || valor.isBlank() ? padrao : valor;
    }

    static String mensagem(String dispositivo, double nivel, Instant agora) {
        return String.format(
            Locale.ROOT,
            "{\"versao\":\"1.0\",\"id_mensagem\":\"%s\",\"dispositivo\":\"%s\",\"tipo\":\"telemetria\","
                + "\"timestamp\":\"%s\",\"medidas\":[{\"grandeza\":\"nivel_enchimento\",\"valor\":%.1f,\"unidade\":\"%%\"}]}",
            UUID.randomUUID(), dispositivo, agora.truncatedTo(ChronoUnit.MILLIS), nivel);
    }

    // A lixeira enche a cada envio e é esvaziada pela coleta ao passar de 95%.
    static double proximoNivel(double nivel) {
        return nivel >= 95 ? 8 : Math.min(100, nivel + 6 + Math.random() * 4);
    }

    // Reenvia uma vez a mesma requisição se a conexão reaproveitada já tinha sido fechada pelo servidor.
    // É seguro: o id_mensagem é o mesmo e a plataforma descarta a cópia (RF-ING-08).
    static HttpResponse<String> enviar(HttpClient http, HttpRequest requisicao) throws Exception {
        try {
            return http.send(requisicao, HttpResponse.BodyHandlers.ofString());
        } catch (IOException conexaoFechada) {
            return http.send(requisicao, HttpResponse.BodyHandlers.ofString());
        }
    }

    public static void main(String[] args) throws Exception {
        String api = ambiente("API_URL", "http://host.docker.internal:8000");
        String token = ambiente("TOKEN_LIXEIRA", "");
        String dispositivo = ambiente("DISPOSITIVO", "lixeira-17");
        long intervalo = Long.parseLong(ambiente("INTERVALO_S", "5"));

        if (args.length > 0 && args[0].equals("--amostra")) {
            System.out.println(mensagem(dispositivo, 42.0, Instant.now()));
            return;
        }
        if (token.isEmpty()) {
            System.err.println("Defina TOKEN_LIXEIRA (token do dispositivo, emitido no cadastro)");
            System.exit(1);
        }
        // HTTP/1.1 explícito: sem isso o cliente tenta o upgrade para HTTP/2 em texto claro (h2c).
        HttpClient http = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).build();
        double nivel = 40;
        while (true) {
            nivel = proximoNivel(nivel);
            HttpRequest requisicao = HttpRequest.newBuilder(URI.create(api + "/api/v1/ingestao"))
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + token)
                .POST(HttpRequest.BodyPublishers.ofString(mensagem(dispositivo, nivel, Instant.now())))
                .build();
            try {
                HttpResponse<String> resposta = enviar(http, requisicao);
                System.out.printf(Locale.ROOT, "%s nivel=%.1f%% -> HTTP %d %s%n",
                    Instant.now(), nivel, resposta.statusCode(), resposta.body());
            } catch (Exception erro) {
                System.err.println("falha ao enviar: " + erro.getMessage());
            }
            Thread.sleep(intervalo * 1000);
        }
    }
}
