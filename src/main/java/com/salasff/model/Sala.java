package com.salasff.model;

import java.util.List;

public class Sala {
    private long id;
    private String senha;
    private String nome;
    private List<Equipe> equipes;

    public long getId() { return id; }
    public String getSenha() { return senha; }
    public String getNome() { return nome; }
    public List<Equipe> getEquipes() { return equipes; }
}
