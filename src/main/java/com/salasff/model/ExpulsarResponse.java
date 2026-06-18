package com.salasff.model;

public class ExpulsarResponse {
    private boolean success;
    private int status;
    private String msg;
    private String pedidoid;
    private String jogadorid;
    private String atualizado;
    private long timestamp;

    public boolean isSuccess() { return success; }
    public int getStatus() { return status; }
    public String getMsg() { return msg; }
    public String getPedidoid() { return pedidoid; }
    public String getJogadorid() { return jogadorid; }
    public String getAtualizado() { return atualizado; }
    public long getTimestamp() { return timestamp; }
}
