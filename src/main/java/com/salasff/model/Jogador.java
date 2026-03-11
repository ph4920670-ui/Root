package com.salasff.model;

public class Jogador {
    private String nickname;
    private String id;

    public String getNickname() { return nickname; }
    public String getId() { return id; }

    @Override
    public String toString() {
        return nickname + " (" + id + ")";
    }
}
