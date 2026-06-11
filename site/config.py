import os

DISCORD_CLIENT_ID     = os.environ.get("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
SITE_URL              = os.environ.get("SITE_URL", "http://localhost:8080")
ADMIN_DISCORD_ID      = os.environ.get("ADMIN_DISCORD_ID", "")
COOKIE_SECRET         = os.environ.get("COOKIE_SECRET", "change-me-in-production")

MONGO_URI = os.environ.get(
    "MONGO_URI",
    "mongodb+srv://pedrinnight12_db_user:kitinho1210@cluster0.pde47ik.mongodb.net/salasff?retryWrites=true&w=majority",
)

OAUTH2_REDIRECT = f"{SITE_URL}/auth/callback"
DISCORD_API     = "https://discord.com/api/v10"
