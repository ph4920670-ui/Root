package com.salasff.model;

import com.google.gson.annotations.SerializedName;

/**
 * Shared response structure for /criar, /info, and /iniciar endpoints.
 */
public class SalaResponse {
    private boolean success;
    private int status;
    private String msg;
    private String telegramid;
    private String pedidoid;
    private Sala sala;
    private String atualizado;
    private long timestamp;

    @SerializedName("inicio_automatico")
    private String inicioAutomatico;

    private String urlinfo;
    private String urlstart;
    private String inicio;

    public boolean isSuccess() { return success; }
    public int getStatus() { return status; }
    public String getMsg() { return msg; }
    public String getTelegramid() { return telegramid; }
    public String getPedidoid() { return pedidoid; }
    public Sala getSala() { return sala; }
    public String getAtualizado() { return atualizado; }
    public long getTimestamp() { return timestamp; }
    public String getInicioAutomatico() { return inicioAutomatico; }
    public String getUrlinfo() { return urlinfo; }
    public String getUrlstart() { return urlstart; }
    public String getInicio() { return inicio; }
}
