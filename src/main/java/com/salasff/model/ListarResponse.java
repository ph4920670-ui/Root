package com.salasff.model;

import java.util.List;

public class ListarResponse {
    private boolean success;
    private int total;
    private List<SalaResponse> salas;
    private long time;

    public boolean isSuccess() { return success; }
    public int getTotal() { return total; }
    public List<SalaResponse> getSalas() { return salas; }
    public long getTime() { return time; }
}
