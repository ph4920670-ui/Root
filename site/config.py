import os

DISCORD_CLIENT_ID     = os.environ.get("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
SITE_URL              = os.environ.get("SITE_URL", "http://localhost:8080")
ADMIN_DISCORD_ID      = os.environ.get("ADMIN_DISCORD_ID", "")
# COOKIE_SECRET mantido por compatibilidade mas não usado para sessões agora
COOKIE_SECRET         = os.environ.get("COOKIE_SECRET", "change-me-in-production")

OAUTH2_REDIRECT = f"{SITE_URL}/auth/callback"
DISCORD_API     = "https://discord.com/api/v10"
