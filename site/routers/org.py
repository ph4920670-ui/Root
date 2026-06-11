"""Org owner panel routes."""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from site.auth import get_session
from site import db as _db

router = APIRouter(prefix="/org")
templates = Jinja2Templates(directory="site/templates")


def _require_org(request: Request):
    """Returns (session, org_doc) or (None, None) if not authorized."""
    sess = get_session(request)
    if not sess:
        return None, None
    uid = sess.get("id", "")
    # Find org where owner_discord_id matches
    org = _db.col_orgs().find_one({"owner_discord_id": str(uid), "ativo": True})
    if not org:
        return None, None
    return sess, org


# ── Dashboard ─────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def org_dashboard(request: Request):
    sess, org = _require_org(request)
    if not sess:
        if not get_session(request):
            return RedirectResponse("/login?next=/org/")
        return templates.TemplateResponse("org/nao_autorizado.html", {"request": request, "user": get_session(request)})

    guild_id = org["_id"]

    # Stats from salas collection
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    inicio_semana = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    inicio_mes = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    salas_col = _db.get_db()["salas"]
    salas_semana = salas_col.count_documents({
        "guild_id": guild_id,
        "criado_em": {"$gte": inicio_semana},
    })
    salas_mes = salas_col.count_documents({
        "guild_id": guild_id,
        "criado_em": {"$gte": inicio_mes},
    })

    # Price per sala from guild_config
    guild_cfg = _db.col_guild_config().find_one({"_id": guild_id}) or {}
    preco_sala = float(guild_cfg.get("preco_sala", 1.5))

    faturamento_semana = salas_semana * preco_sala
    faturamento_mes    = salas_mes    * preco_sala

    porcentagem = float(org.get("porcentagem", 70))
    saldo       = float(org.get("saldo_acumulado", 0.0))

    saques_pendentes = list(
        _db.col_saques().find({"guild_id": guild_id, "status": "pendente"})
    )

    return templates.TemplateResponse("org/dashboard.html", {
        "request":          request,
        "user":             sess,
        "org":              org,
        "salas_semana":     salas_semana,
        "salas_mes":        salas_mes,
        "faturamento_semana": faturamento_semana,
        "faturamento_mes":    faturamento_mes,
        "preco_sala":       preco_sala,
        "porcentagem":      porcentagem,
        "saldo":            saldo,
        "saques_pendentes": saques_pendentes,
    })


# ── Saques ─────────────────────────────────────────────────────────────────

@router.get("/saques", response_class=HTMLResponse)
async def org_saques(request: Request):
    sess, org = _require_org(request)
    if not sess:
        if not get_session(request):
            return RedirectResponse("/login?next=/org/saques")
        return templates.TemplateResponse("org/nao_autorizado.html", {"request": request, "user": get_session(request)})

    guild_id = org["_id"]
    saques   = list(_db.col_saques().find({"guild_id": guild_id}).sort("criado_em", -1))
    saldo    = float(org.get("saldo_acumulado", 0.0))

    return templates.TemplateResponse("org/saques.html", {
        "request": request,
        "user":    sess,
        "org":     org,
        "saques":  saques,
        "saldo":   saldo,
    })


@router.post("/saques/solicitar")
async def org_saque_solicitar(
    request: Request,
    valor: float = Form(...),
    pix_key: str = Form(...),
):
    sess, org = _require_org(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)

    guild_id = org["_id"]
    saldo    = float(org.get("saldo_acumulado", 0.0))

    if valor <= 0 or valor > saldo:
        return RedirectResponse("/org/saques?erro=saldo_insuficiente", status_code=303)

    import uuid
    from datetime import datetime, timezone

    saque_id = str(uuid.uuid4())
    _db.col_saques().insert_one({
        "_id":              saque_id,
        "guild_id":         guild_id,
        "owner_discord_id": str(sess.get("id", "")),
        "valor":            valor,
        "pix_key":          pix_key.strip(),
        "status":           "pendente",
        "criado_em":        datetime.now(timezone.utc).isoformat(),
        "resolvido_em":     None,
        "motivo_rejeicao":  None,
    })

    # Deduz do saldo
    _db.col_orgs().update_one(
        {"_id": guild_id},
        {"$inc": {"saldo_acumulado": -valor}},
    )

    return RedirectResponse("/org/saques?msg=solicitado", status_code=303)
