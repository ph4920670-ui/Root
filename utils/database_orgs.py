# utils/database_orgs.py
# Extensões do banco de dados para o sistema de Orgs, Guild Commands e Saques.
# Importado pelo site e pelo bot. Requer que _get_db() do database.py esteja disponível.

import uuid, logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_log = logging.getLogger("salasff.db")
BRASILIA = ZoneInfo("America/Sao_Paulo")


def _now():
    return datetime.now(BRASILIA).isoformat()


# ── Lazy import da conexão Mongo para não criar dependência circular ──────────

def _get_db_conn():
    from utils.database import _get_db
    return _get_db()

def _col_guild_commands():
    return _get_db_conn()["guild_commands"]

def _col_orgs():
    return _get_db_conn()["orgs"]

def _col_saques():
    return _get_db_conn()["saques"]


# ══════════════════════════════════════════════════════════════
#  GUILD COMMANDS TOGGLE
# ══════════════════════════════════════════════════════════════

def guild_commands_get(guild_id: str) -> dict:
    """Retorna {comando: bool} para o servidor. Default: todos True."""
    try:
        doc = _col_guild_commands().find_one({"_id": str(guild_id)})
        if doc:
            return dict(doc.get("commands", {}))
    except Exception as e:
        _log.warning(f"[guild_commands_get] {e}")
    return {}


def guild_commands_set(guild_id: str, commands: dict):
    """Salva {comando: bool} no MongoDB."""
    try:
        _col_guild_commands().update_one(
            {"_id": str(guild_id)},
            {"$set": {"commands": dict(commands)}},
            upsert=True,
        )
    except Exception as e:
        _log.error(f"[guild_commands_set] {e}")


def command_enabled(guild_id: str, command_name: str) -> bool:
    """Verifica se um comando está ativo para o servidor. Default True."""
    cmds = guild_commands_get(str(guild_id))
    return bool(cmds.get(command_name, True))


# ══════════════════════════════════════════════════════════════
#  ORGS
# ══════════════════════════════════════════════════════════════

def org_get(guild_id: str) -> dict:
    """Retorna o documento da org ou dict vazio."""
    try:
        doc = _col_orgs().find_one({"_id": str(guild_id)})
        if doc:
            doc["guild_id"] = str(doc.pop("_id"))
            return doc
    except Exception as e:
        _log.warning(f"[org_get] {e}")
    return {}


def org_set(guild_id: str, data: dict):
    """Cria ou atualiza o documento da org."""
    try:
        d = dict(data)
        d.pop("_id", None)
        d.pop("guild_id", None)
        _col_orgs().update_one(
            {"_id": str(guild_id)},
            {"$set": d},
            upsert=True,
        )
    except Exception as e:
        _log.error(f"[org_set] {e}")


def org_registrar_venda(guild_id: str, valor: float, qtd_salas: int):
    """Acumula faturamento e saldo da org após uma venda confirmada."""
    try:
        org = org_get(guild_id)
        if not org or not org.get("ativo"):
            return
        porcentagem = float(org.get("porcentagem", 70))
        ganho_org = round(float(valor) * (porcentagem / 100.0), 4)
        _col_orgs().update_one(
            {"_id": str(guild_id)},
            {
                "$inc": {
                    "faturamento_total": round(float(valor), 4),
                    "saldo_acumulado": ganho_org,
                    "salas_total": int(qtd_salas),
                }
            },
            upsert=False,
        )
        _log.info(f"[org_registrar_venda] guild={guild_id} valor={valor} ganho={ganho_org}")
    except Exception as e:
        _log.error(f"[org_registrar_venda] {e}")


def org_saldo(guild_id: str) -> float:
    """Retorna o saldo acumulado do dono da org."""
    try:
        doc = _col_orgs().find_one({"_id": str(guild_id)}, {"saldo_acumulado": 1})
        if doc:
            return float(doc.get("saldo_acumulado", 0.0))
    except Exception as e:
        _log.warning(f"[org_saldo] {e}")
    return 0.0


def org_saque_criar(guild_id: str, valor: float, pix_key: str) -> str:
    """Cria registro de saque pendente. Retorna o id do saque."""
    org = org_get(guild_id)
    saldo_atual = float(org.get("saldo_acumulado", 0.0))
    if round(float(valor), 2) > round(saldo_atual, 2):
        raise ValueError(f"Saldo insuficiente: disponível R$ {saldo_atual:.2f}")

    saque_id = str(uuid.uuid4())
    doc = {
        "_id": saque_id,
        "guild_id": str(guild_id),
        "owner_discord_id": str(org.get("owner_discord_id", "")),
        "valor": round(float(valor), 2),
        "pix_key": str(pix_key),
        "status": "pendente",
        "criado_em": _now(),
        "resolvido_em": None,
        "motivo_rejeicao": None,
    }
    _col_saques().insert_one(doc)

    # Desconta o valor do saldo imediatamente (reserva)
    _col_orgs().update_one(
        {"_id": str(guild_id)},
        {"$inc": {"saldo_acumulado": -round(float(valor), 2)}},
    )
    return saque_id


def org_saque_list(status: str = "pendente") -> list:
    """Retorna lista de saques filtrados por status."""
    try:
        docs = list(_col_saques().find({"status": str(status)}))
        result = []
        for d in docs:
            d["id"] = str(d.pop("_id"))
            result.append(d)
        return sorted(result, key=lambda x: x.get("criado_em", ""), reverse=True)
    except Exception as e:
        _log.error(f"[org_saque_list] {e}")
        return []


def org_saque_aprovar(saque_id: str):
    """Aprova um saque pendente."""
    try:
        _col_saques().update_one(
            {"_id": str(saque_id)},
            {"$set": {"status": "aprovado", "resolvido_em": _now()}},
        )
    except Exception as e:
        _log.error(f"[org_saque_aprovar] {e}")


def org_saque_rejeitar(saque_id: str, motivo: str):
    """Rejeita um saque pendente e devolve o valor ao saldo da org."""
    try:
        doc = _col_saques().find_one({"_id": str(saque_id)})
        if not doc:
            return
        _col_saques().update_one(
            {"_id": str(saque_id)},
            {"$set": {
                "status": "rejeitado",
                "resolvido_em": _now(),
                "motivo_rejeicao": str(motivo),
            }},
        )
        # Devolve o valor ao saldo da org
        _col_orgs().update_one(
            {"_id": str(doc["guild_id"])},
            {"$inc": {"saldo_acumulado": round(float(doc.get("valor", 0)), 2)}},
        )
    except Exception as e:
        _log.error(f"[org_saque_rejeitar] {e}")


def org_salas_semana(guild_id: str) -> int:
    """Retorna salas criadas com saldo desta org nesta semana."""
    from utils.database import _load
    desde = (datetime.now(BRASILIA) - timedelta(days=7)).isoformat()
    salas = _load("salas")
    return sum(
        1 for s in salas.values()
        if s.get("guild_id") == str(guild_id) and s.get("criado_em", "") >= desde
    )


def org_salas_mes(guild_id: str) -> int:
    """Retorna salas criadas com saldo desta org neste mês."""
    from utils.database import _load
    desde = (datetime.now(BRASILIA) - timedelta(days=30)).isoformat()
    salas = _load("salas")
    return sum(
        1 for s in salas.values()
        if s.get("guild_id") == str(guild_id) and s.get("criado_em", "") >= desde
    )


def org_list_all() -> list:
    """Lista todas as orgs cadastradas."""
    try:
        docs = list(_col_orgs().find())
        result = []
        for d in docs:
            d["guild_id"] = str(d.pop("_id"))
            result.append(d)
        return result
    except Exception as e:
        _log.error(f"[org_list_all] {e}")
        return []
