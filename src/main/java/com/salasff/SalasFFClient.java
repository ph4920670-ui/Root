package com.salasff;

import com.google.gson.Gson;
import com.salasff.model.*;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

/**
 * API client for the salasff.com Free Fire Room API.
 *
 * Usage:
 *   SalasFFClient client = new SalasFFClient("SUA_CHAVE_AQUI");
 *
 *   // 1. List available modes
 *   ModosResponse modos = client.getModos();
 *
 *   // 2. Create a room
 *   SalaResponse sala = client.criarSala("196976212809609773", 5, null, null);
 *
 *   // 3. Poll until status = 3
 *   SalaResponse info = client.getInfo(sala.getPedidoid());
 *
 *   // 4. Start match
 *   SalaResponse started = client.iniciar(sala.getPedidoid());
 */
public class SalasFFClient {

    private static final String BASE_URL = "https://salasff.com";
    private static final Duration TIMEOUT = Duration.ofSeconds(30);

    private final String apiKey;
    private final HttpClient httpClient;
    private final Gson gson;

    public SalasFFClient(String apiKey) {
        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalArgumentException("API key must not be null or blank");
        }
        this.apiKey = apiKey;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(TIMEOUT)
                .build();
        this.gson = new Gson();
    }

    // -------------------------------------------------------------------------
    // Endpoint: /modos
    // -------------------------------------------------------------------------

    /**
     * Returns all available room modes (private + public) for this API key.
     */
    public ModosResponse getModos() throws ApiException, IOException, InterruptedException {
        String url = BASE_URL + "/modos?key=" + encode(apiKey);
        String body = get(url);
        ModosResponse response = gson.fromJson(body, ModosResponse.class);
        checkSuccess(response.isSuccess(), response.getError(), response.getCodigo());
        return response;
    }

    // -------------------------------------------------------------------------
    // Endpoint: /criar
    // -------------------------------------------------------------------------

    /**
     * Creates a new custom room.
     *
     * @param salaid      Mode ID obtained from {@link #getModos()} (required)
     * @param iniciar     Minutes until auto-start, 1–10 (null = API default ~4 min)
     * @param callbackUrl URL to receive POST updates (null = none; max 1024 chars)
     * @param senha       Custom password 1–9999, or 99 for random (null = mode default)
     * @return {@link SalaResponse} with status 2 (pending) or 3 (ready)
     */
    public SalaResponse criarSala(String salaid, Integer iniciar, String callbackUrl, Integer senha)
            throws ApiException, IOException, InterruptedException {

        if (salaid == null || salaid.isBlank()) {
            throw new IllegalArgumentException("salaid is required");
        }

        StringBuilder url = new StringBuilder(BASE_URL)
                .append("/criar?key=").append(encode(apiKey))
                .append("&salaid=").append(encode(salaid));

        if (iniciar != null) {
            if (iniciar < 1 || iniciar > 10) throw new IllegalArgumentException("iniciar must be 1–10");
            url.append("&iniciar=").append(iniciar);
        }
        if (callbackUrl != null && !callbackUrl.isBlank()) {
            if (callbackUrl.length() > 1024) throw new IllegalArgumentException("callbackUrl exceeds 1024 characters");
            url.append("&callback_url=").append(encode(callbackUrl));
        }
        if (senha != null) {
            if (senha < 1 || senha > 9999) throw new IllegalArgumentException("senha must be 1–9999");
            url.append("&senha=").append(senha);
        }

        String body = get(url.toString());
        SalaResponse response = gson.fromJson(body, SalaResponse.class);
        checkSuccess(response.isSuccess(), response.getMsg(), -1);
        return response;
    }

    // -------------------------------------------------------------------------
    // Endpoint: /info
    // -------------------------------------------------------------------------

    /**
     * Fetches current status and player list for a room.
     * Poll every 4–6 seconds until status = 3 (room ready).
     *
     * @param pedidoid Order ID returned by {@link #criarSala}
     */
    public SalaResponse getInfo(String pedidoid) throws ApiException, IOException, InterruptedException {
        requireNonBlank(pedidoid, "pedidoid");
        String url = BASE_URL + "/info?pedidoid=" + encode(pedidoid);
        String body = get(url);
        SalaResponse response = gson.fromJson(body, SalaResponse.class);
        checkSuccess(response.isSuccess(), response.getMsg(), -1);
        return response;
    }

    /**
     * Convenience method: polls {@link #getInfo} every {@code intervalMs} milliseconds
     * until status = 3 or timeout is reached.
     *
     * @param pedidoid   Order ID
     * @param intervalMs Polling interval in milliseconds (recommended: 4000–6000)
     * @param timeoutMs  Maximum total wait time in milliseconds
     * @return {@link SalaResponse} with status 3
     * @throws ApiException if status never reaches 3 within the timeout
     */
    public SalaResponse aguardarSalaCriada(String pedidoid, long intervalMs, long timeoutMs)
            throws ApiException, IOException, InterruptedException {

        long deadline = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < deadline) {
            SalaResponse info = getInfo(pedidoid);
            if (info.getStatus() == 3) return info;
            if (info.getStatus() >= 4) throw new ApiException("Room reached terminal status: " + info.getStatus());
            Thread.sleep(intervalMs);
        }
        throw new ApiException("Timeout waiting for room status 3 (pedidoid=" + pedidoid + ")");
    }

    // -------------------------------------------------------------------------
    // Endpoint: /listar
    // -------------------------------------------------------------------------

    /**
     * Lists active rooms (status 2 or 3) created in the last ~20–30 minutes by this key.
     */
    public ListarResponse listar() throws ApiException, IOException, InterruptedException {
        String url = BASE_URL + "/listar?key=" + encode(apiKey);
        String body = get(url);
        ListarResponse response = gson.fromJson(body, ListarResponse.class);
        checkSuccess(response.isSuccess(), "Failed to list rooms", -1);
        return response;
    }

    // -------------------------------------------------------------------------
    // Endpoint: /expulsar
    // -------------------------------------------------------------------------

    /**
     * Kicks a player from a room (only works when status = 3).
     *
     * @param pedidoid  Order ID of the room
     * @param jogadorid Free Fire player ID to kick
     */
    public ExpulsarResponse expulsar(String pedidoid, String jogadorid)
            throws ApiException, IOException, InterruptedException {

        requireNonBlank(pedidoid, "pedidoid");
        requireNonBlank(jogadorid, "jogadorid");

        String url = BASE_URL + "/expulsar?key=" + encode(apiKey)
                + "&pedidoid=" + encode(pedidoid)
                + "&jogadorid=" + encode(jogadorid);

        String body = get(url);
        ExpulsarResponse response = gson.fromJson(body, ExpulsarResponse.class);
        checkSuccess(response.isSuccess(), response.getMsg(), -1);
        return response;
    }

    // -------------------------------------------------------------------------
    // Endpoint: /iniciar
    // -------------------------------------------------------------------------

    /**
     * Manually starts the match (only works when status = 3).
     * After calling this the room moves to status 4 and cannot be modified.
     *
     * @param pedidoid Order ID of the room
     */
    public SalaResponse iniciar(String pedidoid) throws ApiException, IOException, InterruptedException {
        requireNonBlank(pedidoid, "pedidoid");
        String url = BASE_URL + "/iniciar?key=" + encode(apiKey) + "&pedidoid=" + encode(pedidoid);
        String body = get(url);
        SalaResponse response = gson.fromJson(body, SalaResponse.class);
        checkSuccess(response.isSuccess(), response.getMsg(), -1);
        return response;
    }

    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------

    private String get(String url) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(TIMEOUT)
                .GET()
                .build();
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IOException("HTTP " + response.statusCode() + " for " + url);
        }
        return response.body();
    }

    private void checkSuccess(boolean success, String message, int code) throws ApiException {
        if (!success) {
            throw new ApiException(message != null ? message : "API returned success=false", code);
        }
    }

    private static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    private static void requireNonBlank(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " is required");
        }
    }
}
