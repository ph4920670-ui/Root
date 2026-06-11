"""MongoDB helpers for the site (runs in the web process, separate from the bot)."""

from pymongo import MongoClient
from site.config import MONGO_URI

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        _db = _client["salasff"]
    return _db


def col_guild_config():
    return get_db()["guild_config"]


def col_orgs():
    return get_db()["orgs"]


def col_saques():
    return get_db()["saques"]


def col_guild_commands():
    return get_db()["guild_commands"]
