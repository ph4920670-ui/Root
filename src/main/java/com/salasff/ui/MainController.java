package com.salasff.ui;

import com.salasff.SalasFFClient;
import com.salasff.model.*;
import javafx.application.Platform;
import javafx.collections.FXCollections;
import javafx.fxml.FXML;
import javafx.scene.control.*;

import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class MainController {

    @FXML private TextField tfApiKey;
    @FXML private ComboBox<Modo> cbModos;
    @FXML private TextField tfIniciar;
    @FXML private TextField tfSenha;
    @FXML private TextField tfPedidoid;
    @FXML private TextField tfJogadorId;
    @FXML private TextArea taOutput;
    @FXML private Label lblStatus;
    @FXML private Button btnModos;
    @FXML private Button btnCriar;
    @FXML private Button btnListar;
    @FXML private Button btnInfo;
    @FXML private Button btnIniciar;

    private final ScheduledExecutorService executor = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "salasff-bg");
        t.setDaemon(true);
        return t;
    });

    private static final DateTimeFormatter TIME_FMT = DateTimeFormatter.ofPattern("HH:mm:ss");

    // -------------------------------------------------------------------------
    // Actions
    // -------------------------------------------------------------------------

    @FXML
    private void onLoadModos() {
        String key = tfApiKey.getText().trim();
        if (key.isEmpty()) { status("Enter your API key first."); return; }

        status("Loading modes...");
        executor.submit(() -> {
            try {
                SalasFFClient client = new SalasFFClient(key);
                ModosResponse resp = client.getModos();

                List<Modo> all = new ArrayList<>();
                if (resp.getModos() != null) all.addAll(resp.getModos());
                if (resp.getModosPublico() != null) all.addAll(resp.getModosPublico());

                Platform.runLater(() -> {
                    cbModos.setItems(FXCollections.observableArrayList(all));
                    log("Loaded " + all.size() + " modes ("
                            + (resp.getModos() != null ? resp.getModos().size() : 0) + " private, "
                            + (resp.getModosPublico() != null ? resp.getModosPublico().size() : 0) + " public)");
                    log("Total rooms tracked by API: " + resp.getSalas());
                    status("Modes loaded.");
                });
            } catch (Exception e) {
                Platform.runLater(() -> { log("ERROR: " + e.getMessage()); status("Failed to load modes."); });
            }
        });
    }

    @FXML
    private void onCriarSala() {
        String key = tfApiKey.getText().trim();
        if (key.isEmpty()) { status("Enter your API key first."); return; }

        Modo selected = cbModos.getValue();
        if (selected == null) { status("Select a mode first."); return; }

        Integer iniciar = parseOptionalInt(tfIniciar.getText().trim(), "Auto-start minutes", 1, 10);
        Integer senha   = parseOptionalInt(tfSenha.getText().trim(), "Password", 1, 9999);
        if (iniciar == null && !tfIniciar.getText().trim().isEmpty()) return;
        if (senha == null && !tfSenha.getText().trim().isEmpty()) return;

        status("Creating room...");
        executor.submit(() -> {
            try {
                SalasFFClient client = new SalasFFClient(key);
                SalaResponse resp = client.criarSala(selected.getSalaid(), iniciar, null, senha);

                Platform.runLater(() -> {
                    tfPedidoid.setText(resp.getPedidoid());
                    logSalaResponse(resp);
                    status("Room creation requested (pedidoid saved).");
                });
            } catch (Exception e) {
                Platform.runLater(() -> { log("ERROR: " + e.getMessage()); status("Failed to create room."); });
            }
        });
    }

    @FXML
    private void onPollInfo() {
        String key = tfApiKey.getText().trim();
        String pedidoid = tfPedidoid.getText().trim();
        if (key.isEmpty() || pedidoid.isEmpty()) {
            status("API key and pedidoid are required.");
            return;
        }

        status("Fetching room info...");
        executor.submit(() -> {
            try {
                SalasFFClient client = new SalasFFClient(key);
                SalaResponse resp = client.getInfo(pedidoid);
                Platform.runLater(() -> { logSalaResponse(resp); status("Info updated."); });
            } catch (Exception e) {
                Platform.runLater(() -> { log("ERROR: " + e.getMessage()); status("Failed to fetch info."); });
            }
        });
    }

    @FXML
    private void onListar() {
        String key = tfApiKey.getText().trim();
        if (key.isEmpty()) { status("Enter your API key first."); return; }

        status("Listing active rooms...");
        executor.submit(() -> {
            try {
                SalasFFClient client = new SalasFFClient(key);
                ListarResponse resp = client.listar();
                Platform.runLater(() -> {
                    log("--- Active Rooms (" + resp.getTotal() + ") ---");
                    if (resp.getSalas() != null) {
                        for (SalaResponse s : resp.getSalas()) {
                            logSalaResponse(s);
                        }
                    }
                    status("Listed " + resp.getTotal() + " active rooms.");
                });
            } catch (Exception e) {
                Platform.runLater(() -> { log("ERROR: " + e.getMessage()); status("Failed to list rooms."); });
            }
        });
    }

    @FXML
    private void onExpulsar() {
        String key = tfApiKey.getText().trim();
        String pedidoid = tfPedidoid.getText().trim();
        String jogadorid = tfJogadorId.getText().trim();
        if (key.isEmpty() || pedidoid.isEmpty() || jogadorid.isEmpty()) {
            status("API key, pedidoid, and player ID are required.");
            return;
        }

        status("Kicking player " + jogadorid + "...");
        executor.submit(() -> {
            try {
                SalasFFClient client = new SalasFFClient(key);
                ExpulsarResponse resp = client.expulsar(pedidoid, jogadorid);
                Platform.runLater(() -> {
                    log("KICK: " + resp.getMsg() + " | player=" + resp.getJogadorid()
                            + " | updated=" + resp.getAtualizado());
                    status("Kick sent.");
                });
            } catch (Exception e) {
                Platform.runLater(() -> { log("ERROR: " + e.getMessage()); status("Kick failed."); });
            }
        });
    }

    @FXML
    private void onIniciar() {
        String key = tfApiKey.getText().trim();
        String pedidoid = tfPedidoid.getText().trim();
        if (key.isEmpty() || pedidoid.isEmpty()) {
            status("API key and pedidoid are required.");
            return;
        }

        Alert confirm = new Alert(Alert.AlertType.CONFIRMATION,
                "Start the match now? This cannot be undone.", ButtonType.YES, ButtonType.NO);
        confirm.setHeaderText("Confirm Start");
        confirm.showAndWait().ifPresent(btn -> {
            if (btn != ButtonType.YES) return;

            status("Starting match...");
            executor.submit(() -> {
                try {
                    SalasFFClient client = new SalasFFClient(key);
                    SalaResponse resp = client.iniciar(pedidoid);
                    Platform.runLater(() -> {
                        logSalaResponse(resp);
                        status("Match started at " + resp.getInicio());
                    });
                } catch (Exception e) {
                    Platform.runLater(() -> { log("ERROR: " + e.getMessage()); status("Failed to start match."); });
                }
            });
        });
    }

    @FXML
    private void onClearLog() {
        taOutput.clear();
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    private void logSalaResponse(SalaResponse r) {
        log("Status: " + r.getStatus() + " | " + r.getMsg()
                + " | pedidoid: " + r.getPedidoid());
        if (r.getSala() != null) {
            Sala s = r.getSala();
            log("  Room: #" + s.getId() + " | Nome: " + s.getNome() + " | Senha: " + s.getSenha());
            if (s.getEquipes() != null) {
                for (var eq : s.getEquipes()) {
                    StringBuilder sb = new StringBuilder("  Team ").append(eq.getNumero()).append(": ");
                    if (eq.getJogadores() == null || eq.getJogadores().isEmpty()) {
                        sb.append("(empty)");
                    } else {
                        eq.getJogadores().forEach(j -> sb.append(j.getNickname()).append(", "));
                    }
                    log(sb.toString());
                }
            }
        }
        if (r.getInicioAutomatico() != null && !r.getInicioAutomatico().isBlank()) {
            log("  Auto-start: " + r.getInicioAutomatico());
        }
    }

    private void log(String message) {
        String line = "[" + LocalTime.now().format(TIME_FMT) + "] " + message;
        Platform.runLater(() -> {
            taOutput.appendText(line + "\n");
            taOutput.setScrollTop(Double.MAX_VALUE);
        });
    }

    private void status(String msg) {
        Platform.runLater(() -> lblStatus.setText(msg));
    }

    /**
     * Returns null if text is blank. Returns the int value if valid.
     * Shows an error and returns null (flagged by setting text to indicate error) if invalid.
     */
    private Integer parseOptionalInt(String text, String fieldName, int min, int max) {
        if (text.isEmpty()) return null;
        try {
            int v = Integer.parseInt(text);
            if (v < min || v > max) {
                status(fieldName + " must be " + min + "–" + max + ".");
                return null;
            }
            return v;
        } catch (NumberFormatException e) {
            status(fieldName + " must be a number.");
            return null;
        }
    }
}
