package com.salasff.bot;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.JDABuilder;
import net.dv8tion.jda.api.interactions.commands.OptionType;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.OptionData;
import net.dv8tion.jda.api.requests.GatewayIntent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Entry point for the SalasFF Discord bot.
 *
 * Required environment variables:
 *   DISCORD_TOKEN  — your Discord bot token
 *   SALASFF_KEY    — your salasff.com API key
 *
 * Run:
 *   java -jar target/salasff-bot.jar
 *
 * Or set env vars inline:
 *   DISCORD_TOKEN=xxx SALASFF_KEY=yyy java -jar target/salasff-bot.jar
 */
public class DiscordBot {

    private static final Logger log = LoggerFactory.getLogger(DiscordBot.class);

    public static void main(String[] args) throws Exception {
        String token = System.getenv("DISCORD_TOKEN");
        String salasKey = System.getenv("SALASFF_KEY");

        if (token == null || token.isBlank()) {
            log.error("DISCORD_TOKEN environment variable is not set.");
            System.exit(1);
        }
        if (salasKey == null || salasKey.isBlank()) {
            log.error("SALASFF_KEY environment variable is not set.");
            System.exit(1);
        }

        SlashHandler handler = new SlashHandler(salasKey);

        JDA jda = JDABuilder.createLight(token, GatewayIntent.GUILD_MESSAGES)
                .addEventListeners(handler)
                .build();

        jda.awaitReady();
        registerCommands(jda);
        log.info("SalasFF bot is online as {}", jda.getSelfUser().getAsTag());
    }

    private static void registerCommands(JDA jda) {
        jda.updateCommands().addCommands(

            Commands.slash("modos", "Lista os modos disponíveis de sala"),

            Commands.slash("criar", "Cria uma nova sala personalizada")
                .addOptions(
                    new OptionData(OptionType.STRING, "salaid", "ID do modo (de /modos)", true),
                    new OptionData(OptionType.INTEGER, "iniciar", "Minutos para início automático (1–10)", false)
                        .setMinValue(1).setMaxValue(10),
                    new OptionData(OptionType.INTEGER, "senha", "Senha 1–9999 (99 = aleatória)", false)
                        .setMinValue(1).setMaxValue(9999)
                ),

            Commands.slash("info", "Consulta status e jogadores de uma sala")
                .addOptions(
                    new OptionData(OptionType.STRING, "pedidoid", "ID do pedido (de /criar)", true)
                ),

            Commands.slash("listar", "Lista todas as salas ativas da sua key"),

            Commands.slash("expulsar", "Expulsa um jogador da sala")
                .addOptions(
                    new OptionData(OptionType.STRING, "pedidoid", "ID do pedido", true),
                    new OptionData(OptionType.STRING, "jogadorid", "ID do jogador no Free Fire", true)
                ),

            Commands.slash("iniciar", "Inicia a partida manualmente")
                .addOptions(
                    new OptionData(OptionType.STRING, "pedidoid", "ID do pedido", true)
                )

        ).queue(ok -> log.info("Slash commands registered."),
                err -> log.error("Failed to register commands", err));
    }
}
