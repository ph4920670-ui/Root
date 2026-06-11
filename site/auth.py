"""Discord OAuth2 helpers + cookie-based session management."""

import httpx
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from site.config import (
    DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET,
    OAUTH2_REDIRECT, DISCORD_API, COOKIE_SECRET, ADMIN_DISCORD_ID,
)

_signer = URLSafeTimedSerializer(COOKIE_SECRET, salt="salasff-session")

COOKIE_NAME = "salasff_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


# ── Session helpers ────────────────────────────────────────────────────────

def session_encode(data: dict) -> str:
    return _signer.dumps(data)


def session_decode(token: str) -> dict | None:
    try:
        return _signer.loads(token, max_age=COOKIE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def set_session(response, data: dict):
    response.set_cookie(
        COOKIE_NAME,
        session_encode(data),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


def clear_session(response):
    response.delete_cookie(COOKIE_NAME)


def get_session(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return session_decode(token)


def require_session(request: Request) -> dict:
    sess = get_session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return sess


def is_admin(user_id: str) -> bool:
    return str(user_id) == str(ADMIN_DISCORD_ID)


# ── Discord OAuth2 ────────────────────────────────────────────────────────

def get_oauth_url(state: str = "") -> str:
    params = (
        f"client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={OAUTH2_REDIRECT}"
        f"&response_type=code"
        f"&scope=identify"
        + (f"&state={state}" if state else "")
    )
    return f"https://discord.com/api/oauth2/authorize?{params}"


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id": DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": OAUTH2_REDIRECT,
            },
        )
        r.raise_for_status()
        return r.json()


async def fetch_user(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        return r.json()
