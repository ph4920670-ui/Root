package com.salasff.model;

public class Modo {
    private String nome;
    private String senha;
    private String salaid;

    public String getNome() { return nome; }
    public String getSenha() { return senha; }
    public String getSalaid() { return salaid; }

    @Override
    public String toString() {
        return nome + " (sala: " + salaid + ")";
    }
}
