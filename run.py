"""run.py — Entry point unificado: bot Discord + site FastAPI no mesmo processo."""

import asyncio
import logging
import os
import sys

import discord
from discord.ext import commands
import uvicorn

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
_log = logging.getLogger("salasff.run")

# ── Cogs a carregar ────────────────────────────────────────────────────────
COGS = [
    "cogs.main",
    "cogs.botconfig",
    "cogs.comprar",
    "cogs.convites",
    "cogs.dev",
    "cogs.mediador_painel",
    "cogs.painel_org",
    "cogs.pg_match",
    "cogs.pg_polling",
    "cogs.pg_user_gateway",
    "cogs.pix_banco",
    "cogs.plano",
    "cogs.preview",
    "cogs.ranking",
    "cogs.ticket",
    "cogs.token_mode",
    "cogs.aposta_auto",
    "cogs.migracao",
]


def create_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.members     = True
    intents.message_content = True
    intents.guilds      = True

    bot = commands.Bot(
        command_prefix=".",
        intents=intents,
        help_command=None,
    )

    @bot.event
    async def on_ready():
        _log.info(f"[Bot] Logado como {bot.user} (id={bot.user.id})")
        # Inicializa banco de dados Supabase
        try:
            from utils.database import init_db
            init_db()
        except Exception as e:
            _log.error(f"[Bot] init_db erro: {e}")

    async def setup_hook_impl():
        for cog in COGS:
            try:
                await bot.load_extension(cog)
                _log.info(f"[Bot] Cog carregado: {cog}")
            except Exception as e:
                _log.error(f"[Bot] Erro ao carregar {cog}: {e}")

    bot.setup_hook = setup_hook_impl
    return bot


async def main():
    # Importa o app FastAPI do site
    from site.main import app as web_app

    bot = create_bot()

    web_config = uvicorn.Config(
        web_app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        log_level="warning",
    )
    server = uvicorn.Server(web_config)

    _log.info("[run] Iniciando bot + site juntos...")

    await asyncio.gather(
        bot.start(config.DISCORD_TOKEN),
        server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
