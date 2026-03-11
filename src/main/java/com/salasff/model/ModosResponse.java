package com.salasff.model;

import com.google.gson.annotations.SerializedName;
import java.util.List;

public class ModosResponse {
    private boolean success;
    private int codigo;
    private String error;
    private long salas;
    private List<Modo> modos;

    @SerializedName("modos_Publico")
    private List<Modo> modosPublico;

    private String info;

    public boolean isSuccess() { return success; }
    public int getCodigo() { return codigo; }
    public String getError() { return error; }
    public long getSalas() { return salas; }
    public List<Modo> getModos() { return modos; }
    public List<Modo> getModosPublico() { return modosPublico; }
    public String getInfo() { return info; }
}
