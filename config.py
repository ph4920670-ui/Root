# config.py — Configurações do SalasFF Bot
# Lê tudo de variáveis de ambiente. Não há defaults com segredos aqui.

import os


def _load_dotenv():
    """Carrega .env da raiz do projeto pra os.environ (sem sobrescrever o que já existe).
    Permite rodar na Discloud apenas subindo o .env, sem mexer no painel."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


_load_dotenv()

# ── Discord ────────────────────────────────────────────────────────────────
DISCORD_TOKEN    = os.environ.get("DISCORD_TOKEN", "")
ADMIN_IDS        = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
OWNER_GUILD_IDS  = [int(x) for x in os.environ.get("OWNER_GUILD_IDS", "").split(",") if x.strip().isdigit()]
GUILD_IDS        = [int(x) for x in os.environ.get("GUILD_IDS", "").split(",") if x.strip().isdigit()]
BACKUP_CHANNEL_ID = int(os.environ.get("BACKUP_CHANNEL_ID", "0") or "0")

# ── API de Salas ───────────────────────────────────────────────────────────
SALASFF_BASE_URL = os.environ.get("SALASFF_BASE_URL", "")
SALASFF_API_KEY  = os.environ.get("SALASFF_API_KEY", "")
API1_URL         = os.environ.get("API1_URL", SALASFF_BASE_URL)
API1_KEY         = os.environ.get("API1_KEY", SALASFF_API_KEY)
API2_URL         = os.environ.get("API2_URL", SALASFF_BASE_URL)
API2_KEY         = os.environ.get("API2_KEY", SALASFF_API_KEY)

# ── Cores para Embeds ──────────────────────────────────────────────────────
COR_SUCESSO = int(os.environ.get("COR_SUCESSO", "0x57F287"), 16)
COR_ERRO    = int(os.environ.get("COR_ERRO",    "0xED4245"), 16)
COR_INFO    = int(os.environ.get("COR_INFO",    "0x5865F2"), 16)
COR_AVISO   = int(os.environ.get("COR_AVISO",   "0xFEE75C"), 16)
COR_AGUARDO = int(os.environ.get("COR_AGUARDO", "0x95A5A6"), 16)

# ── Modos de sala ──────────────────────────────────────────────────────────
MODOS = {
    1: "Normal",
    2: "Infinito",
    3: "Full Capa",
}

# ── Quantias disponíveis no menu de compra ─────────────────────────────────
QUANTIAS_DISPONIVEIS = [int(x) for x in os.environ.get(
    "QUANTIAS_DISPONIVEIS", "5,10,20,30,50,100"
).split(",") if x.strip().isdigit()]

# ── Tempos ─────────────────────────────────────────────────────────────────
DEFAULT_INICIAR_MINUTOS   = int(os.environ.get("DEFAULT_INICIAR_MINUTOS", "5"))
SALA_TIMEOUT_SECONDS      = int(os.environ.get("SALA_TIMEOUT_SECONDS", "60"))
POLLING_INTERVAL_SECONDS  = int(os.environ.get("POLLING_INTERVAL_SECONDS", "5"))
