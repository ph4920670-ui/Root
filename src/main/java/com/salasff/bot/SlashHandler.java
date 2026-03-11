package com.salasff.bot;

import com.salasff.SalasFFClient;
import com.salasff.model.*;
import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.entities.MessageEmbed;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import org.jetbrains.annotations.NotNull;

import java.awt.*;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Handles all slash command interactions for the SalasFF bot.
 */
public class SlashHandler extends ListenerAdapter {

    private final String salasKey;
    private final ExecutorService executor = Executors.newCachedThreadPool(r -> {
        Thread t = new Thread(r, "salasff-discord");
        t.setDaemon(true);
        return t;
    });

    public SlashHandler(String salasKey) {
        this.salasKey = salasKey;
    }

    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        // Defer immediately so Discord doesn't time out while we call the API
        event.deferReply().queue();

        executor.submit(() -> {
            try {
                switch (event.getName()) {
                    case "modos"    -> handleModos(event);
                    case "criar"    -> handleCriar(event);
                    case "info"     -> handleInfo(event);
                    case "listar"   -> handleListar(event);
                    case "expulsar" -> handleExpulsar(event);
                    case "iniciar"  -> handleIniciar(event);
                }
            } catch (ApiException e) {
                event.getHook().sendMessage("**Erro da API:** " + e.getMessage()).queue();
            } catch (Exception e) {
                event.getHook().sendMessage("**Erro interno:** " + e.getMessage()).queue();
            }
        });
    }

    // -------------------------------------------------------------------------

    private void handleModos(SlashCommandInteractionEvent event) throws Exception {
        SalasFFClient client = new SalasFFClient(salasKey);
        ModosResponse resp = client.getModos();

        EmbedBuilder eb = new EmbedBuilder()
                .setTitle("Modos Disponíveis")
                .setColor(new Color(233, 69, 96))
                .setFooter("Total de salas no sistema: " + resp.getSalas());

        addModosField(eb, "Privados", resp.getModos());
        addModosField(eb, "Públicos", resp.getModosPublico());

        event.getHook().sendMessageEmbeds(eb.build()).queue();
    }

    private void addModosField(EmbedBuilder eb, String title, List<Modo> modos) {
        if (modos == null || modos.isEmpty()) return;
        StringBuilder sb = new StringBuilder();
        for (Modo m : modos) {
            sb.append("**").append(m.getNome()).append("**\n")
              .append("`").append(m.getSalaid()).append("`\n");
        }
        eb.addField(title, sb.toString(), false);
    }

    // -------------------------------------------------------------------------

    private void handleCriar(SlashCommandInteractionEvent event) throws Exception {
        String salaid  = event.getOption("salaid").getAsString();
        Integer iniciar = event.getOption("iniciar") != null
                ? (int) event.getOption("iniciar").getAsLong() : null;
        Integer senha   = event.getOption("senha") != null
                ? (int) event.getOption("senha").getAsLong() : null;

        SalasFFClient client = new SalasFFClient(salasKey);
        SalaResponse resp = client.criarSala(salaid, iniciar, null, senha);

        event.getHook().sendMessageEmbeds(buildSalaEmbed(resp)).queue();
    }

    // -------------------------------------------------------------------------

    private void handleInfo(SlashCommandInteractionEvent event) throws Exception {
        String pedidoid = event.getOption("pedidoid").getAsString();
        SalasFFClient client = new SalasFFClient(salasKey);
        SalaResponse resp = client.getInfo(pedidoid);
        event.getHook().sendMessageEmbeds(buildSalaEmbed(resp)).queue();
    }

    // -------------------------------------------------------------------------

    private void handleListar(SlashCommandInteractionEvent event) throws Exception {
        SalasFFClient client = new SalasFFClient(salasKey);
        ListarResponse resp = client.listar();

        if (resp.getSalas() == null || resp.getSalas().isEmpty()) {
            event.getHook().sendMessage("Nenhuma sala ativa no momento.").queue();
            return;
        }

        EmbedBuilder eb = new EmbedBuilder()
                .setTitle("Salas Ativas (" + resp.getTotal() + ")")
                .setColor(new Color(83, 52, 131));

        for (SalaResponse s : resp.getSalas()) {
            String value = statusLabel(s.getStatus())
                    + (s.getSala() != null
                       ? "\nID: `" + s.getSala().getId() + "` | Senha: **" + s.getSala().getSenha() + "**"
                       : "")
                    + "\nAtualizado: " + s.getAtualizado();
            eb.addField(s.getSala() != null ? s.getSala().getNome() : s.getPedidoid(),
                        value, false);
        }

        event.getHook().sendMessageEmbeds(eb.build()).queue();
    }

    // -------------------------------------------------------------------------

    private void handleExpulsar(SlashCommandInteractionEvent event) throws Exception {
        String pedidoid  = event.getOption("pedidoid").getAsString();
        String jogadorid = event.getOption("jogadorid").getAsString();

        SalasFFClient client = new SalasFFClient(salasKey);
        ExpulsarResponse resp = client.expulsar(pedidoid, jogadorid);

        EmbedBuilder eb = new EmbedBuilder()
                .setTitle("Expulsão")
                .setColor(new Color(211, 84, 0))
                .addField("Status", resp.getMsg(), true)
                .addField("Jogador ID", resp.getJogadorid(), true)
                .addField("Atualizado", resp.getAtualizado(), false);

        event.getHook().sendMessageEmbeds(eb.build()).queue();
    }

    // -------------------------------------------------------------------------

    private void handleIniciar(SlashCommandInteractionEvent event) throws Exception {
        String pedidoid = event.getOption("pedidoid").getAsString();
        SalasFFClient client = new SalasFFClient(salasKey);
        SalaResponse resp = client.iniciar(pedidoid);

        EmbedBuilder eb = new EmbedBuilder()
                .setTitle("Partida Iniciada!")
                .setColor(new Color(192, 57, 43))
                .setDescription(resp.getMsg())
                .addField("Inicio", resp.getInicio() != null ? resp.getInicio() : "-", true)
                .addField("Atualizado", resp.getAtualizado(), true);

        if (resp.getSala() != null) {
            eb.addField("Sala", resp.getSala().getNome() + " | #" + resp.getSala().getId(), false);
        }

        event.getHook().sendMessageEmbeds(eb.build()).queue();
    }

    // -------------------------------------------------------------------------

    private MessageEmbed buildSalaEmbed(SalaResponse r) {
        EmbedBuilder eb = new EmbedBuilder()
                .setTitle(r.getMsg())
                .setColor(statusColor(r.getStatus()))
                .addField("Status", statusLabel(r.getStatus()), true)
                .addField("pedidoid", "`" + r.getPedidoid() + "`", false);

        if (r.getSala() != null) {
            Sala s = r.getSala();
            eb.addField("Nome", s.getNome(), true);
            eb.addField("Sala ID", String.valueOf(s.getId()), true);
            eb.addField("Senha", "**" + s.getSenha() + "**", true);

            if (s.getEquipes() != null && !s.getEquipes().isEmpty()) {
                for (Equipe eq : s.getEquipes()) {
                    StringBuilder players = new StringBuilder();
                    if (eq.getJogadores() == null || eq.getJogadores().isEmpty()) {
                        players.append("_(vazia)_");
                    } else {
                        for (Jogador j : eq.getJogadores()) {
                            players.append("• ").append(j.getNickname())
                                   .append(" `").append(j.getId()).append("`\n");
                        }
                    }
                    eb.addField("Time " + eq.getNumero(), players.toString(), true);
                }
            }
        }

        if (r.getInicioAutomatico() != null && !r.getInicioAutomatico().isBlank()) {
            eb.addField("Início Automático", r.getInicioAutomatico(), true);
        }
        if (r.getAtualizado() != null) {
            eb.setFooter("Atualizado: " + r.getAtualizado());
        }

        return eb.build();
    }

    private static String statusLabel(int status) {
        return switch (status) {
            case 2 -> "⏳ Criando sala...";
            case 3 -> "✅ Sala criada";
            case 4 -> "🎮 Partida iniciada";
            default -> "❓ Status " + status;
        };
    }

    private static Color statusColor(int status) {
        return switch (status) {
            case 2 -> new Color(241, 196, 15);   // yellow
            case 3 -> new Color(15, 155, 88);    // green
            case 4 -> new Color(52, 152, 219);   // blue
            default -> Color.GRAY;
        };
    }
}
