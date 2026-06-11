"""Admin panel routes — only accessible by the bot owner."""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from site.auth import get_session, is_admin
from site import db as _db

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="site/templates")


def _require_admin(request: Request):
    sess = get_session(request)
    if not sess or not is_admin(sess.get("id", "")):
        return None
    return sess


# ── Dashboard ─────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    sess = _require_admin(request)
    if not sess:
        return RedirectResponse("/login?next=/admin/")

    guilds = list(_db.col_guild_config().find())
    orgs   = {o["_id"]: o for o in _db.col_orgs().find()}

    # Merge org info into guild list
    for g in guilds:
        gid = g.get("_id", "")
        g["org"] = orgs.get(gid)

    pending_saques = list(_db.col_saques().find({"status": "pendente"}))

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "user":    sess,
        "guilds":  guilds,
        "pending_saques": pending_saques,
    })


# ── Server detail / config ────────────────────────────────────────────────

@router.get("/server/{guild_id}", response_class=HTMLResponse)
async def admin_server(request: Request, guild_id: str):
    sess = _require_admin(request)
    if not sess:
        return RedirectResponse("/login?next=/admin/")

    guild_cfg = _db.col_guild_config().find_one({"_id": guild_id}) or {}
    org       = _db.col_orgs().find_one({"_id": guild_id}) or {}

    # Commands config
    cmd_doc  = _db.col_guild_commands().find_one({"_id": guild_id}) or {}
    commands = cmd_doc.get("commands", {})
    all_cmds = ["c", "c1", "c2", "c3", "painel"]
    for cmd in all_cmds:
        if cmd not in commands:
            commands[cmd] = True

    return templates.TemplateResponse("admin/server.html", {
        "request":   request,
        "user":      sess,
        "guild_id":  guild_id,
        "guild_cfg": guild_cfg,
        "org":       org,
        "commands":  commands,
        "all_cmds":  all_cmds,
    })


@router.post("/server/{guild_id}/org", response_class=HTMLResponse)
async def admin_server_org(
    request: Request,
    guild_id: str,
    ativo: str = Form("off"),
    porcentagem: int = Form(70),
    owner_discord_id: str = Form(""),
    nome: str = Form(""),
):
    sess = _require_admin(request)
    if not sess:
        return RedirectResponse("/login?next=/admin/")

    ativo_bool = ativo == "on"

    existing = _db.col_orgs().find_one({"_id": guild_id}) or {}
    from datetime import datetime, timezone
    update = {
        "ativo":            ativo_bool,
        "nome":             nome or existing.get("nome", ""),
        "owner_discord_id": owner_discord_id or existing.get("owner_discord_id", ""),
        "porcentagem":      max(1, min(99, porcentagem)),
    }
    if not existing:
        update["faturamento_total"] = 0.0
        update["saldo_acumulado"]   = 0.0
        update["salas_total"]       = 0
        update["criado_em"]         = datetime.now(timezone.utc).isoformat()

    _db.col_orgs().update_one({"_id": guild_id}, {"$set": update}, upsert=True)
    return RedirectResponse(f"/admin/server/{guild_id}?saved=1", status_code=303)


@router.post("/server/{guild_id}/commands", response_class=HTMLResponse)
async def admin_server_commands(request: Request, guild_id: str):
    sess = _require_admin(request)
    if not sess:
        return RedirectResponse("/login?next=/admin/")

    form = await request.form()
    all_cmds = ["c", "c1", "c2", "c3", "painel"]
    commands = {cmd: (form.get(f"cmd_{cmd}") == "on") for cmd in all_cmds}

    _db.col_guild_commands().update_one(
        {"_id": guild_id},
        {"$set": {"commands": commands}},
        upsert=True,
    )
    return RedirectResponse(f"/admin/server/{guild_id}?saved=1", status_code=303)


# ── Saques ────────────────────────────────────────────────────────────────

@router.get("/saques", response_class=HTMLResponse)
async def admin_saques(request: Request):
    sess = _require_admin(request)
    if not sess:
        return RedirectResponse("/login?next=/admin/saques")

    saques = list(_db.col_saques().find({"status": "pendente"}).sort("criado_em", -1))
    return templates.TemplateResponse("admin/saques.html", {
        "request": request,
        "user":    sess,
        "saques":  saques,
    })


@router.post("/saques/{saque_id}/aprovar")
async def admin_saque_aprovar(request: Request, saque_id: str):
    sess = _require_admin(request)
    if not sess:
        return RedirectResponse("/login")

    from datetime import datetime, timezone
    _db.col_saques().update_one(
        {"_id": saque_id},
        {"$set": {"status": "aprovado", "resolvido_em": datetime.now(timezone.utc).isoformat()}},
    )
    return RedirectResponse("/admin/saques?msg=aprovado", status_code=303)


@router.post("/saques/{saque_id}/rejeitar")
async def admin_saque_rejeitar(request: Request, saque_id: str, motivo: str = Form("")):
    sess = _require_admin(request)
    if not sess:
        return RedirectResponse("/login")

    from datetime import datetime, timezone
    saque = _db.col_saques().find_one({"_id": saque_id})
    if saque:
        # Devolve saldo para a org
        _db.col_orgs().update_one(
            {"_id": saque.get("guild_id", "")},
            {"$inc": {"saldo_acumulado": float(saque.get("valor", 0))}},
        )
    _db.col_saques().update_one(
        {"_id": saque_id},
        {"$set": {
            "status": "rejeitado",
            "resolvido_em": datetime.now(timezone.utc).isoformat(),
            "motivo_rejeicao": motivo,
        }},
    )
    return RedirectResponse("/admin/saques?msg=rejeitado", status_code=303)
