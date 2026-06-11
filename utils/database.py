# utils/database.py — MongoDB-based storage (v6 — PERSISTENT CLOUD DB)
#
# MIGRAÇÃO de JSON → MongoDB Atlas.
# Cache em memória continua para performance (mesma lógica do v5).
# Backend agora é MongoDB: dados NUNCA se perdem com restart/redeploy.
#
# Interface pública 100% compatível — nenhum cog precisa mudar.
#
# COMPAT: KEYS_PATH, SALAS_PATH, PEDIDOS_PATH, DATA_DIR, _CODE_DIR
# são mantidos como aliases para não quebrar imports existentes.
# _load() e _save() aceitam tanto o path antigo quanto o nome da coleção.

import uuid, secrets, string, os, logging, asyncio
from datetime import datetime, timedelta, timezone
from threading import Lock
from zoneinfo import ZoneInfo

_log = logging.getLogger("salasff.db")

BRASILIA = ZoneInfo("America/Sao_Paulo")

# ══════════════════════════════════════════════════════════════
#  MONGODB CONNECTION
# ══════════════════════════════════════════════════════════════

from pymongo import MongoClient, UpdateOne

MONGO_URI = os.environ.get(
    "MONGO_URI",
    "mongodb+srv://pedrinnight12_db_user:kitinho1210@cluster0.pde47ik.mongodb.net/salasff?retryWrites=true&w=majority"
)

# Conexão configurada. Lembre-se de trocar a senha depois (exposta no chat).

_mongo_client = None
_db = None

def _get_db():
    global _mongo_client, _db
    if _db is None:
        _mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        _db = _mongo_client["salasff"]
        _log.info("[MongoDB] Conectado ao Atlas")
    return _db

# Coleções
def _col_keys():
    return _get_db()["keys"]

def _col_salas():
    return _get_db()["salas"]

def _col_pedidos():
    return _get_db()["pedidos_pix"]

def _col_lucro():
    return _get_db()["lucro_config"]

def _col_guild():
    return _get_db()["guild_config"]

def _col_bonus():
    return _get_db()["bonus_data"]

def _col_botconfig():
    return _get_db()["botconfig"]

# ── botconfig helpers ────────────────────────────────────────────────────
_botconfig_cache = {}

def botconfig_load() -> dict:
    """Carrega botconfig do MongoDB (com cache)."""
    global _botconfig_cache
    if _botconfig_cache:
        return dict(_botconfig_cache)
    try:
        doc = _col_botconfig().find_one({"_id": "main"})
        if doc:
            doc.pop("_id", None)
            _botconfig_cache = doc
            return dict(doc)
    except Exception as e:
        _log.warning(f"[botconfig load] {e}")
    return {}

def botconfig_save(data: dict):
    """Salva botconfig no MongoDB e atualiza cache."""
    global _botconfig_cache
    _botconfig_cache = dict(data)
    try:
        d = dict(data)
        d.pop("_id", None)
        _col_botconfig().update_one({"_id": "main"}, {"$set": d}, upsert=True)
    except Exception as e:
        _log.error(f"[botconfig save] {e}")

# ══════════════════════════════════════════════════════════════
#  CACHE EM MEMÓRIA (mesma lógica do v5, agora sincroniza com Mongo)
# ══════════════════════════════════════════════════════════════

_lock = Lock()

_cache = {}       # collection_name -> {doc_id: doc}
_dirty = set()    # collection names que foram alterados

# Mapeamento de nomes para funções de coleção
_COLLECTIONS = {
    "keys": _col_keys,
    "salas": _col_salas,
    "pedidos": _col_pedidos,
}

# ══════════════════════════════════════════════════════════════
#  COMPAT — aliases para imports antigos (main.py, cogs/main.py)
# ══════════════════════════════════════════════════════════════

DATA_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CODE_DIR  = DATA_DIR
KEYS_PATH    = "keys"      # antes era caminho de arquivo, agora é nome da coleção
SALAS_PATH   = "salas"
PEDIDOS_PATH = "pedidos"

# Mapa path antigo → nome de coleção (caso alguém passe o path do JSON)
_PATH_ALIASES = {}
for _old_name, _col_name in [("keys.json", "keys"), ("salas.json", "salas"), ("pedidos_pix.json", "pedidos")]:
    _PATH_ALIASES[os.path.join(DATA_DIR, _old_name)] = _col_name

def _now():
    return datetime.now(BRASILIA).isoformat()

def _now_utc():
    return datetime.now(timezone.utc).isoformat()

def _code():
    ch = string.ascii_uppercase + string.digits
    return "-".join("".join(secrets.choice(ch) for _ in range(4)) for _ in range(4))

def _load_from_mongo(col_name):
    """Carrega todos os docs de uma coleção do MongoDB."""
    try:
        col_func = _COLLECTIONS[col_name]
        col = col_func()
        data = {}
        for doc in col.find():
            doc_id = doc.pop("_id")
            data[str(doc_id)] = doc
        _log.info(f"[_load_from_mongo] {col_name}: {len(data)} registros")
        return data
    except Exception as e:
        _log.error(f"[_load_from_mongo] Erro ao carregar {col_name}: {e}")
        return {}

def _resolve_col(name_or_path):
    """Resolve um path antigo ou nome de coleção para o nome da coleção."""
    if name_or_path in _COLLECTIONS:
        return name_or_path
    return _PATH_ALIASES.get(name_or_path, name_or_path)

def _load(col_name):
    """Retorna dados do cache em memória. Aceita nome de coleção ou path antigo."""
    col_name = _resolve_col(col_name)
    if col_name not in _cache:
        _cache[col_name] = _load_from_mongo(col_name)
    return _cache[col_name]

def _save(col_name, data):
    """Atualiza cache e marca para flush no MongoDB. Aceita nome de coleção ou path antigo."""
    col_name = _resolve_col(col_name)
    _cache[col_name] = data
    _dirty.add(col_name)

def _flush(col_name):
    """Sincroniza dados dirty para o MongoDB."""
    col_name = _resolve_col(col_name)
    if col_name not in _dirty:
        return
    data = _cache.get(col_name)
    if data is None:
        return
    try:
        col_func = _COLLECTIONS[col_name]
        col = col_func()

        # Pega IDs existentes no Mongo
        existing_ids = set()
        for doc in col.find({}, {"_id": 1}):
            existing_ids.add(str(doc["_id"]))

        cache_ids = set(data.keys())

        # Upsert todos os docs do cache
        ops = []
        for doc_id, doc_data in data.items():
            doc_copy = dict(doc_data)
            doc_copy.pop("_id", None)
            ops.append(UpdateOne(
                {"_id": doc_id},
                {"$set": doc_copy},
                upsert=True
            ))

        # Deletar docs que foram removidos do cache (ex: pruning)
        removed = existing_ids - cache_ids
        if removed:
            col.delete_many({"_id": {"$in": list(removed)}})

        if ops:
            col.bulk_write(ops, ordered=False)

        _dirty.discard(col_name)
        _log.info(f"[_flush] {col_name}: {len(ops)} upserts, {len(removed)} removidos")
    except Exception as e:
        _log.error(f"[_flush] Erro ao salvar {col_name}: {e}")

def flush_all():
    """Força escrita de todos os caches dirty no MongoDB."""
    for col_name in list(_dirty):
        _flush(col_name)
    # Também flush configs auxiliares (lucro, guild, bonus)
    _flush_lucro()
    _flush_guild()
    _flush_bonus()

def init_db():
    """Carrega os 3 coleções principais do MongoDB pro cache em memória."""
    db = _get_db()

    # Criar índices para performance
    try:
        _col_keys().create_index("dono_id")
        _col_keys().create_index("code", unique=True, sparse=True)
        _col_salas().create_index("user_id")
        _col_salas().create_index("criado_em")
        _col_salas().create_index("guild_id")
        _col_pedidos().create_index("txid")
        _col_pedidos().create_index("user_id")
        _col_pedidos().create_index("status")
        _log.info("[init_db] Índices MongoDB criados/verificados")
    except Exception as e:
        _log.warning(f"[init_db] Erro ao criar índices: {e}")

    # Prunar salas antigas direto no MongoDB antes de carregar (economiza RAM)
    try:
        limite = (datetime.now(BRASILIA) - timedelta(days=30)).isoformat()
        result = _col_salas().delete_many({"criado_em": {"$lt": limite}})
        if result.deleted_count > 0:
            _log.info(f"[init_db] Pruning MongoDB: {result.deleted_count} salas antigas removidas")
    except Exception as ex:
        _log.warning(f"[init_db] Pruning erro: {ex}")

    for col_name in ["keys", "salas", "pedidos"]:
        try:
            data = _load_from_mongo(col_name)
            _cache[col_name] = data
            _log.info(f"[init_db] {col_name}: {len(data)} registros OK (MongoDB)")
        except Exception as ex:
            _log.error(f"[init_db] {col_name} ERRO: {ex} — cache vazio")
            _cache[col_name] = {}

# ══════════════════════════════════════════════════════════════
#  PRUNING — remove salas antigas pra manter RAM baixa
# ══════════════════════════════════════════════════════════════

def prunar_salas_antigas(dias=30):
    """Remove salas com mais de N dias."""
    limite = (datetime.now(BRASILIA) - timedelta(days=dias)).isoformat()
    with _lock:
        salas = _load("salas")
        antes = len(salas)
        salas_novas = {k: v for k, v in salas.items() if v.get("criado_em", "") >= limite}
        removidas = antes - len(salas_novas)
        if removidas > 0:
            _save("salas", salas_novas)
            _log.info(f"[pruning] Removidas {removidas} salas antigas (>{dias} dias). {len(salas_novas)} restantes.")
    return removidas

# ══════════════════════════════════════════════════════════════
#  KEYS
# ══════════════════════════════════════════════════════════════

def criar_keys(quantia, modo, quantidade, criado_por):
    criadas = []
    with _lock:
        keys = _load("keys")
        codigos = {k["code"] for k in keys.values()}
        for _ in range(quantidade):
            kid  = str(uuid.uuid4())
            code = _code()
            while code in codigos:
                code = _code()
            codigos.add(code)
            keys[kid] = {
                "id": kid, "code": code, "quantia": quantia,
                "modo": modo, "salas_usadas": 0,
                "criado_por": criado_por, "criado_em": _now(),
                "dono_id": None, "dono_nome": None, "resgatado_em": None,
            }
            criadas.append({"id": kid, "code": code})
        _save("keys", keys)
    return criadas

def buscar_key(code):
    keys = _load("keys")
    code = code.upper().strip()
    for k in keys.values():
        if k["code"] == code:
            return k
    return None

def validar_key(code):
    row = buscar_key(code)
    if not row:
        return False, "❌ Key não encontrada. Verifique o código.", None
    if row["salas_usadas"] >= row["quantia"]:
        return False, "❌ Esta key não tem mais salas disponíveis.", None
    return True, "OK", row

def resgatar_key(code, user_id, user_nome):
    ok, msg, row = validar_key(code)
    if not ok:
        return False, msg, None
    if row["dono_id"] and row["dono_id"] != user_id:
        return False, "❌ Esta key já pertence a outro usuário.", None
    with _lock:
        keys = _load("keys")
        if not keys[row["id"]]["dono_id"]:
            keys[row["id"]]["dono_id"]      = user_id
            keys[row["id"]]["dono_nome"]    = user_nome
            keys[row["id"]]["resgatado_em"] = _now()
            _save("keys", keys)
        row = keys[row["id"]]
    return True, "OK", row

def consumir_sala_key(key_id):
    with _lock:
        keys = _load("keys")
        if key_id in keys:
            keys[key_id]["salas_usadas"] += 1
            _save("keys", keys)


def saldo_total_usuario(user_id) -> int:
    """Retorna saldo total (soma de salas restantes em todas as keys) do user."""
    with _lock:
        keys = _load("keys")
        total = 0
        for k in keys.values():
            if str(k.get("dono_id")) == str(user_id):
                restante = int(k.get("quantia", 0)) - int(k.get("salas_usadas", 0))
                if restante > 0:
                    total += restante
        return total


def usuarios_com_saldo() -> list:
    """Retorna lista única de user_ids com saldo > 0."""
    with _lock:
        keys = _load("keys")
        ativos = set()
        for k in keys.values():
            dono = k.get("dono_id")
            if not dono or str(dono).startswith("PENDENTE_"):
                continue
            restante = int(k.get("quantia", 0)) - int(k.get("salas_usadas", 0))
            if restante > 0:
                ativos.add(str(dono))
        return list(ativos)

def reservar_sala_key(user_id, modo, user_nome=None):
    """Atômico: encontra a melhor key com saldo e consome 1 sala.
    Prioridade: origem venda→ranking→indicacao, com resgatado_em desc como desempate.
    """
    if user_nome:
        _sincronizar_pendentes(user_id, user_nome)
    _sync_keys_do_mongo(user_id)
    with _lock:
        keys = _load("keys")
        elegiveis = [k for k in keys.values()
                     if k["dono_id"] == user_id
                     and k["salas_usadas"] < k["quantia"]
                     and (k["modo"] == modo or k["modo"] == 0)]
        if not elegiveis:
            return None, 0

        def _rank(k):
            prio = _ORIGEM_PRIORIDADE.get(_origem_de(k), 99)
            # resgatado_em ISO sorting funciona como string desc
            ts = k.get("resgatado_em") or ""
            return (prio, ts)  # menor prio + maior ts vence

        # Primeiro pela menor prioridade (venda=0), depois ts desc
        candidatas = sorted(elegiveis, key=lambda k: (_ORIGEM_PRIORIDADE.get(_origem_de(k), 99), -ord(_first_char(k.get("resgatado_em") or "0"))))
        # Forma mais simples: ordena por prio asc, depois ts desc, em duas passadas
        candidatas = sorted(elegiveis, key=lambda k: k.get("resgatado_em") or "", reverse=True)
        candidatas = sorted(candidatas, key=lambda k: _ORIGEM_PRIORIDADE.get(_origem_de(k), 99))

        chosen = candidatas[0]
        keys[chosen["id"]]["salas_usadas"] += 1
        _save("keys", keys)
        restante = chosen["quantia"] - keys[chosen["id"]]["salas_usadas"]
        return dict(keys[chosen["id"]]), restante


def _first_char(s):
    return s[0] if s else "0"

def reverter_sala_key(key_id):
    """Reverte 1 sala consumida (rollback se a API falhar)."""
    with _lock:
        keys = _load("keys")
        if key_id in keys and keys[key_id]["salas_usadas"] > 0:
            keys[key_id]["salas_usadas"] -= 1
            _save("keys", keys)

def _sincronizar_pendentes(user_id, user_nome):
    with _lock:
        keys = _load("keys")
        alterado = False
        nome_lower = user_nome.lower().strip()
        for k in keys.values():
            dono = k.get("dono_id", "")
            if dono and dono.startswith("PENDENTE_"):
                nome_key = dono.replace("PENDENTE_", "").replace("_", " ").lower().strip()
                if nome_key == nome_lower or k.get("dono_nome", "").lower().strip() == nome_lower:
                    k["dono_id"] = user_id
                    k["dono_nome"] = user_nome
                    alterado = True
        if alterado:
            _save("keys", keys)

def _sync_keys_do_mongo(user_id):
    """Consulta o MongoDB por keys desse user_id e insere no cache qualquer uma
    que ainda não esteja lá. Necessário porque o site Node.js cria keys direto
    no Mongo (resgate de salas grátis) e o cache em memória do bot não sabe.
    """
    try:
        col = _COLLECTIONS["keys"]()
        # Busca todas as keys desse dono no Mongo
        docs = list(col.find({"dono_id": user_id}))
        if not docs:
            return 0
        cache_keys = _cache.get("keys")
        if cache_keys is None:
            cache_keys = _load_from_mongo("keys")
            _cache["keys"] = cache_keys
        adicionados = 0
        for doc in docs:
            doc_id = str(doc.pop("_id"))
            if doc_id not in cache_keys:
                cache_keys[doc_id] = doc
                adicionados += 1
        if adicionados:
            _log.info(f"[_sync_keys_do_mongo] user={user_id} +{adicionados} keys sincronizadas do Mongo")
        return adicionados
    except Exception as e:
        _log.warning(f"[_sync_keys_do_mongo] user={user_id} erro: {e}")
        return 0


def keys_do_usuario(user_id, user_nome=None):
    if user_nome:
        _sincronizar_pendentes(user_id, user_nome)
    _sync_keys_do_mongo(user_id)
    keys = _load("keys")
    return sorted(
        [k for k in keys.values() if k["dono_id"] == user_id],
        key=lambda k: k.get("resgatado_em") or "", reverse=True
    )

def todas_keys_com_saldo():
    keys = _load("keys")
    return sorted(
        [k for k in keys.values() if k["dono_id"] and k["salas_usadas"] < k["quantia"]],
        key=lambda k: (k.get("dono_nome") or "").lower()
    )

def remover_salas_cliente(user_id, quantidade):
    with _lock:
        keys = _load("keys")
        user_keys = sorted(
            [k for k in keys.values() if k["dono_id"] == user_id and k["salas_usadas"] < k["quantia"]],
            key=lambda k: k.get("resgatado_em") or ""
        )
        removidas = 0
        for k in user_keys:
            if removidas >= quantidade:
                break
            disp  = k["quantia"] - k["salas_usadas"]
            remov = min(disp, quantidade - removidas)
            keys[k["id"]]["salas_usadas"] += remov
            removidas += remov
        _save("keys", keys)
        total = sum(
            k["quantia"] - k["salas_usadas"]
            for k in keys.values()
            if k["dono_id"] == user_id
        )
    return removidas, int(total)

def saldo_total_usuario(user_id, user_nome=None):
    if user_nome:
        _sincronizar_pendentes(user_id, user_nome)
    _sync_keys_do_mongo(user_id)
    keys = _load("keys")
    return sum(
        k["quantia"] - k["salas_usadas"]
        for k in keys.values()
        if k["dono_id"] == user_id and k["salas_usadas"] < k["quantia"]
    )

def adicionar_saldo_usuario(user_id, user_nome, quantidade, origem: str = "venda"):
    """Adiciona saldo creditando uma key.
    `origem` define a "categoria" do saldo: 'venda', 'ranking', 'indicacao'.
    """
    if origem not in ("venda", "ranking", "indicacao"):
        origem = "venda"
    with _lock:
        keys = _load("keys")
        codigos = {k["code"] for k in keys.values()}
        kid  = str(uuid.uuid4())
        code = _code()
        while code in codigos:
            code = _code()
        keys[kid] = {
            "id": kid, "code": code, "quantia": quantidade,
            "modo": 0, "salas_usadas": 0,
            "criado_por": "admin_restauracao", "criado_em": _now(),
            "dono_id": user_id, "dono_nome": user_nome, "resgatado_em": _now(),
            "origem": origem,
        }
        _save("keys", keys)
    return code


# Prioridade de consumo: venda → ranking → indicacao
_ORIGEM_PRIORIDADE = {"venda": 0, "ranking": 1, "indicacao": 2}


def _origem_de(k: dict) -> str:
    """Retorna a origem da key (default venda pra keys antigas sem campo)."""
    o = k.get("origem")
    if o in ("venda", "ranking", "indicacao"):
        return o
    return "venda"


def saldo_por_origem(user_id: str) -> dict:
    """Retorna o saldo do user separado por origem: {venda, ranking, indicacao}."""
    _sync_keys_do_mongo(user_id)
    keys = _load("keys")
    out = {"venda": 0, "ranking": 0, "indicacao": 0}
    for k in keys.values():
        if k["dono_id"] != user_id:
            continue
        if k["salas_usadas"] >= k["quantia"]:
            continue
        rest = k["quantia"] - k["salas_usadas"]
        out[_origem_de(k)] += rest
    return out

# ══════════════════════════════════════════════════════════════
#  SALAS
# ══════════════════════════════════════════════════════════════

def registrar_sala(user_id, user_nome, modo, guild_id=None, saldo_origem="pessoal"):
    sid = str(uuid.uuid4())
    with _lock:
        salas = _load("salas")
        salas[sid] = {
            "id": sid, "user_id": user_id, "user_nome": user_nome,
            "modo": modo, "pedidoid": None, "sala_id": None,
            "sala_senha": None, "sala_nome": None, "criado_em": _now(),
            "guild_id": str(guild_id) if guild_id else None,
            "saldo_origem": saldo_origem,
        }
        _save("salas", salas)
    return sid

def atualizar_sala(sid, pedidoid, sala_id, senha, nome, link=None):
    with _lock:
        salas = _load("salas")
        if sid in salas:
            update_data = {"pedidoid": pedidoid, "sala_id": sala_id, "sala_senha": senha, "sala_nome": nome}
            if link:
                update_data["sala_link"] = link
            salas[sid].update(update_data)
            _save("salas", salas)

def salas_usuario_periodo(user_id, horas):
    desde = (datetime.now(BRASILIA) - timedelta(hours=horas)).isoformat()
    salas = _load("salas")
    return sum(1 for s in salas.values() if s["user_id"] == user_id and s["criado_em"] >= desde)

def salas_usuario_ontem(user_id):
    agora = datetime.now(BRASILIA)
    hoje_meia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    ontem_meia = (hoje_meia - timedelta(days=1)).isoformat()
    ate_ontem = hoje_meia.isoformat()
    salas = _load("salas")
    return sum(1 for s in salas.values()
               if s["user_id"] == user_id and ontem_meia <= s["criado_em"] < ate_ontem)

def perfil_usuario(user_id):
    """Versão otimizada: carrega salas e keys 1x só."""
    salas = _load("salas")
    keys  = _load("keys")
    agora = datetime.now(BRASILIA)

    user_salas = [s for s in salas.values() if s["user_id"] == user_id]

    hoje_meia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    ontem_meia = (hoje_meia - timedelta(days=1))
    desde_hoje = hoje_meia.isoformat()
    desde_ontem = ontem_meia.isoformat()
    ate_ontem = hoje_meia.isoformat()

    def _contar_desde(dias):
        desde = (agora - timedelta(days=dias)).isoformat()
        return sum(1 for s in user_salas if s["criado_em"] >= desde)

    hoje_count = sum(1 for s in user_salas if s["criado_em"] >= desde_hoje)
    ontem_count = sum(1 for s in user_salas if desde_ontem <= s["criado_em"] < ate_ontem)

    saldo = sum(
        k["quantia"] - k["salas_usadas"]
        for k in keys.values()
        if k["dono_id"] == user_id and k["salas_usadas"] < k["quantia"]
    )

    return {
        "hoje":   hoje_count,
        "ontem":  ontem_count,
        "3dias":  _contar_desde(3),
        "semana": _contar_desde(7),
        "mes":    _contar_desde(30),
        "total":  len(user_salas),
        "saldo":  saldo,
    }

# ══════════════════════════════════════════════════════════════
#  PEDIDOS PIX
# ══════════════════════════════════════════════════════════════

def expirar_pedidos_velhos():
    limite = (datetime.now(BRASILIA) - timedelta(hours=2)).isoformat()
    with _lock:
        pedidos = _load("pedidos")
        alterado = False
        for p in pedidos.values():
            if p.get("status") == "pendente" and (p.get("criado_em") or "") < limite:
                p["status"] = "expirado"
                alterado = True
        if alterado:
            _save("pedidos", pedidos)

def criar_pedido_pix(user_id, user_nome, txid, quantia, valor, banco: str = None, guild_id: str = None, guild_nome: str = None):
    pid = str(uuid.uuid4())
    with _lock:
        pedidos = _load("pedidos")
        pedidos[pid] = {
            "id": pid, "user_id": user_id, "user_nome": user_nome,
            "txid": txid, "quantia": quantia, "valor": valor,
            "status": "pendente", "criado_em": _now(),
            "pago_em": None, "key_gerada": None,
            "banco": banco or "mistic",
            "guild_id": str(guild_id) if guild_id else None,
            "guild_nome": guild_nome,
        }
        _save("pedidos", pedidos)
    return pid

def buscar_pedido_por_txid(txid):
    pedidos = _load("pedidos")
    for p in pedidos.values():
        if p["txid"] == txid:
            return p
    return None

def confirmar_pedido_pix(txid, nome_pagador: str = None, endtoend: str = None):
    with _lock:
        pedidos = _load("pedidos")
        for p in pedidos.values():
            if p["txid"] == txid:
                p["status"] = "pago"
                p["pago_em"] = _now()
                if nome_pagador:
                    p["nome_pagador"] = nome_pagador
                if endtoend:
                    p["endtoend"] = endtoend
        _save("pedidos", pedidos)

def pedidos_pendentes():
    pedidos = _load("pedidos")
    return [p for p in pedidos.values() if p["status"] == "pendente"]

def salvar_key_pedido(txid, key_code):
    with _lock:
        pedidos = _load("pedidos")
        for p in pedidos.values():
            if p["txid"] == txid:
                p["key_gerada"] = key_code
        _save("pedidos", pedidos)

def pedidos_por_nome(nome, limite=None):
    pedidos = _load("pedidos")
    result = [p for p in pedidos.values() if nome.lower() in p["user_nome"].lower()]
    result = sorted(result, key=lambda p: p["criado_em"], reverse=True)
    return result[:limite] if limite else result

def pedidos_por_id(user_id, limite=None):
    pedidos = _load("pedidos")
    result = [p for p in pedidos.values() if p["user_id"] == user_id]
    result = sorted(result, key=lambda p: p["criado_em"], reverse=True)
    return result[:limite] if limite else result

def vendas_usuario(user_id: str = None) -> dict:
    """Retorna salas vendidas (pedidos pagos) por período.
    Se user_id=None, retorna totais gerais do negócio.
    """
    agora   = datetime.now(BRASILIA)
    hoje    = agora.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    ontem_i = (agora.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)).isoformat()
    d7      = (agora - timedelta(days=7)).isoformat()

    pedidos = _load("pedidos")
    if user_id:
        pagos = [p for p in pedidos.values()
                 if p["status"] == "pago" and p.get("user_id") == user_id]
    else:
        pagos = [p for p in pedidos.values() if p["status"] == "pago"]

    v_hoje  = sum(p["quantia"] for p in pagos if (p.get("pago_em") or "") >= hoje)
    v_ontem = sum(p["quantia"] for p in pagos if ontem_i <= (p.get("pago_em") or "") < hoje)
    v7d     = sum(p["quantia"] for p in pagos if (p.get("pago_em") or "") >= d7)
    vtot    = sum(p["quantia"] for p in pagos)

    return {
        "hoje":   v_hoje,
        "ontem":  v_ontem,
        "semana": v7d,
        "total":  vtot,
    }


def salas_criadas_usuario(user_id: str) -> dict:
    """Retorna nº de SALAS que o usuário CRIOU (não compras PIX) por período.
    Usado pelo painel 'Ver Lucro' do usuário comum — ele lucra criando salas
    pros clientes dele, então o lucro é (salas_criadas * valor_por_sala).
    """
    agora   = datetime.now(BRASILIA)
    hoje_d  = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    hoje    = hoje_d.isoformat()
    ontem_i = (hoje_d - timedelta(days=1)).isoformat()
    d7      = (agora - timedelta(days=7)).isoformat()

    salas = _load("salas")
    minhas = [s for s in salas.values() if s.get("user_id") == user_id]

    def _ts(s):
        return s.get("criado_em") or ""

    n_hoje   = sum(1 for s in minhas if _ts(s) >= hoje)
    n_ontem  = sum(1 for s in minhas if ontem_i <= _ts(s) < hoje)
    n_semana = sum(1 for s in minhas if _ts(s) >= d7)
    n_total  = len(minhas)

    return {
        "hoje":   n_hoje,
        "ontem":  n_ontem,
        "semana": n_semana,
        "total":  n_total,
    }


def lucro_resumo(user_id: str = None) -> dict:
    """Retorna resumo financeiro completo: receita, custo, bônus, lucro líquido.

    Períodos: hoje / ontem / semana (7d) / total
    - receita: R$ recebido em pedidos pagos
    - salas_vendidas: nº de salas vendidas (pedidos pagos)
    - bonus_dadas: salas dadas grátis (eventos + resgates de bônus)
    - custo: (salas_vendidas + bonus_dadas) × valor_compra_por_sala
    - lucro_bruto: receita - custo
    - perda_bonus: bonus_dadas × valor_compra_por_sala (custo de presentear)
    """
    agora   = datetime.now(BRASILIA)
    hoje_d  = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    hoje    = hoje_d.isoformat()
    ontem_i = (hoje_d - timedelta(days=1)).isoformat()
    d7      = (agora - timedelta(days=7)).isoformat()

    pedidos = _load("pedidos")
    pagos = [p for p in pedidos.values() if p.get("status") == "pago"]

    def _no_periodo(p, ini, fim=None):
        ts = p.get("pago_em") or ""
        if fim:
            return ini <= ts < fim
        return ts >= ini

    def _agg(filtro):
        salas = sum(int(p.get("quantia", 0)) for p in pagos if filtro(p))
        receita = sum(float(p.get("valor", 0) or 0) for p in pagos if filtro(p))
        return salas, receita

    s_hoje, r_hoje   = _agg(lambda p: _no_periodo(p, hoje))
    s_ont,  r_ont    = _agg(lambda p: _no_periodo(p, ontem_i, hoje))
    s_7d,   r_7d     = _agg(lambda p: _no_periodo(p, d7))
    s_tot,  r_tot    = _agg(lambda p: True)

    # Bônus dado: keys com criado_por começando em "EVENTO_" + bonus_resgatado total
    keys = _load("keys")
    def _bonus_keys_periodo(ini, fim=None):
        total = 0
        for k in keys.values():
            if not str(k.get("criado_por", "")).startswith(("EVENTO_", "bonus_evento_")):
                continue
            ts = k.get("criado_em") or k.get("resgatado_em") or ""
            if fim:
                if ini <= ts < fim:
                    total += int(k.get("quantia", 0))
            else:
                if ts >= ini:
                    total += int(k.get("quantia", 0))
        return total

    b_hoje  = _bonus_keys_periodo(hoje)
    b_ont   = _bonus_keys_periodo(ontem_i, hoje)
    b_7d    = _bonus_keys_periodo(d7)
    b_tot   = sum(int(k.get("quantia", 0)) for k in keys.values()
                  if str(k.get("criado_por", "")).startswith(("EVENTO_", "bonus_evento_")))

    # Bônus resgatados (sistema /c → Bônus): adiciona ao total de bônus dado
    try:
        bonus_data = _load_bonus()
        # bonus_resgatado é cumulativo, não dá pra filtrar por período facilmente
        # então só somamos no total
        bonus_resgatado_tot = sum(int(reg.get("bonus_resgatado", 0)) for reg in bonus_data.values())
        b_tot += bonus_resgatado_tot
    except Exception:
        pass

    # Custo: precisa de lucro_config_get(user_id) pra pegar valor_compra_por_sala
    # Default: 0.03 se não configurado
    valor_compra = 0.03
    if user_id:
        try:
            cfg = lucro_config_get(user_id)
            v = float(cfg.get("valor_por_sala", 0) or 0)
            if v > 0:
                valor_compra = v
        except Exception:
            pass

    def _calc(salas, receita, bonus):
        custo = (salas + bonus) * valor_compra
        return {
            "salas":       salas,
            "receita":     round(receita, 2),
            "bonus":       bonus,
            "custo":       round(custo, 2),
            "perda_bonus": round(bonus * valor_compra, 2),
            "lucro":       round(receita - custo, 2),
        }

    return {
        "valor_compra_por_sala": valor_compra,
        "hoje":   _calc(s_hoje, r_hoje, b_hoje),
        "ontem":  _calc(s_ont,  r_ont,  b_ont),
        "semana": _calc(s_7d,   r_7d,   b_7d),
        "total":  _calc(s_tot,  r_tot,  b_tot),
    }


def lucro_periodo():
    agora  = datetime.now(BRASILIA)
    hoje   = agora.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    d3     = (agora - timedelta(days=3)).isoformat()
    d7     = (agora - timedelta(days=7)).isoformat()

    salas = _load("salas")
    todas = list(salas.values())
    c_hoje = sum(1 for s in todas if s["criado_em"] >= hoje)
    c3d    = sum(1 for s in todas if s["criado_em"] >= d3)
    c7d    = sum(1 for s in todas if s["criado_em"] >= d7)
    ctot   = len(todas)

    pedidos = _load("pedidos")
    pagos   = [p for p in pedidos.values() if p["status"] == "pago"]
    v_hoje  = sum(p["quantia"] for p in pagos if (p["pago_em"] or "") >= hoje)
    v3d     = sum(p["quantia"] for p in pagos if (p["pago_em"] or "") >= d3)
    v7d     = sum(p["quantia"] for p in pagos if (p["pago_em"] or "") >= d7)
    vtot    = sum(p["quantia"] for p in pagos)

    lps = 0.03
    return {
        "vendidas_hoje": v_hoje, "lucro_hoje": round(v_hoje * lps, 2),
        "vendidas_3d":   v3d,    "lucro_3d":  round(v3d  * lps, 2),
        "vendidas_7d":   v7d,    "lucro_7d":  round(v7d  * lps, 2),
        "vendidas_tot":  vtot,   "lucro_tot": round(vtot * lps, 2),
        "criadas_hoje":  c_hoje,
        "criadas_3d":    c3d,
        "criadas_7d":    c7d,
        "criadas_tot":   ctot,
    }

def stats_globais():
    agora = datetime.now(BRASILIA)
    hoje_meia  = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    ontem_meia = (hoje_meia - timedelta(days=1))
    desde_hoje  = hoje_meia.isoformat()
    desde_ontem = ontem_meia.isoformat()
    ate_ontem   = hoje_meia.isoformat()
    d7   = (agora - timedelta(days=7)).isoformat()
    salas   = _load("salas")
    pedidos = _load("pedidos")
    pagos   = [p for p in pedidos.values() if p["status"] == "pago"]
    return {
        "salas_hoje":   sum(1 for s in salas.values() if s["criado_em"] >= desde_hoje),
        "salas_ontem":  sum(1 for s in salas.values() if desde_ontem <= s["criado_em"] < ate_ontem),
        "salas_7d":     sum(1 for s in salas.values() if s["criado_em"] >= d7),
        "salas_tot":    len(salas),
        "vendas_hoje":  sum(p["quantia"] for p in pagos if (p["pago_em"] or "") >= desde_hoje),
        "vendas_ontem": sum(p["quantia"] for p in pagos if desde_ontem <= (p["pago_em"] or "") < ate_ontem),
        "vendas_7d":    sum(p["quantia"] for p in pagos if (p["pago_em"] or "") >= d7),
        "vendas_tot":   sum(p["quantia"] for p in pagos),
        "pedidos_hoje":  sum(1 for p in pagos if (p["pago_em"] or "") >= desde_hoje),
        "pedidos_ontem": sum(1 for p in pagos if desde_ontem <= (p["pago_em"] or "") < ate_ontem),
        "pedidos_7d":    sum(1 for p in pagos if (p["pago_em"] or "") >= d7),
        "pedidos_tot":   len(pagos),
        "receita_hoje":  sum(p["valor"] for p in pagos if (p["pago_em"] or "") >= desde_hoje),
        "receita_ontem": sum(p["valor"] for p in pagos if desde_ontem <= (p["pago_em"] or "") < ate_ontem),
        "receita_7d":    sum(p["valor"] for p in pagos if (p["pago_em"] or "") >= d7),
        "receita_tot":   sum(p["valor"] for p in pagos),
    }

def ultimas_compras(limite=None):
    pedidos = _load("pedidos")
    pagos = [p for p in pedidos.values() if p["status"] == "pago"]
    result = sorted(pagos, key=lambda p: p["pago_em"] or "", reverse=True)
    return result[:limite] if limite else result

def top_compradores(limite=None):
    pedidos = _load("pedidos")
    pagos = [p for p in pedidos.values() if p["status"] == "pago"]
    totais = {}
    for p in pagos:
        uid = p["user_id"]
        if uid not in totais:
            totais[uid] = {"user_nome": p["user_nome"], "pedidos": 0, "total_salas": 0, "total_valor": 0.0}
        totais[uid]["pedidos"]     += 1
        totais[uid]["total_salas"] += p["quantia"]
        totais[uid]["total_valor"] += p["valor"]
    result = sorted(totais.values(), key=lambda x: x["total_salas"], reverse=True)
    return result[:limite] if limite else result

def stats_por_guild(limite=None):
    """Retorna vendas PIX pagas agrupadas por servidor de origem.
    Retorna lista de dicts ordenada por salas vendidas (maior primeiro).
    """
    agora = datetime.now(BRASILIA)
    hoje_meia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    desde_hoje = hoje_meia.isoformat()
    d7 = (agora - timedelta(days=7)).isoformat()

    pedidos = _load("pedidos")
    pagos = [p for p in pedidos.values() if p.get("status") == "pago"]
    grupos = {}
    for p in pagos:
        gid = p.get("guild_id") or "desconhecido"
        gnome = p.get("guild_nome") or ("DM / Direto" if gid == "desconhecido" else f"ID {gid}")
        if gid not in grupos:
            grupos[gid] = {
                "guild_id": gid, "guild_nome": gnome,
                "pedidos_hoje": 0, "pedidos_7d": 0, "pedidos_tot": 0,
                "salas_hoje": 0, "salas_7d": 0, "salas_tot": 0,
                "receita_hoje": 0.0, "receita_7d": 0.0, "receita_tot": 0.0,
            }
        g = grupos[gid]
        pago_em = p.get("pago_em") or ""
        g["pedidos_tot"] += 1
        g["salas_tot"] += p.get("quantia", 0)
        g["receita_tot"] += float(p.get("valor", 0.0))
        if pago_em >= d7:
            g["pedidos_7d"] += 1
            g["salas_7d"] += p.get("quantia", 0)
            g["receita_7d"] += float(p.get("valor", 0.0))
        if pago_em >= desde_hoje:
            g["pedidos_hoje"] += 1
            g["salas_hoje"] += p.get("quantia", 0)
            g["receita_hoje"] += float(p.get("valor", 0.0))
    result = sorted(grupos.values(), key=lambda x: x["salas_tot"], reverse=True)
    return result[:limite] if limite else result

def stats_guild(guild_id: str) -> dict:
    """Estatísticas de salas criadas com saldo do servidor."""
    agora = datetime.now(BRASILIA)
    hoje_meia  = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    ontem_meia = hoje_meia - timedelta(days=1)
    desde_hoje  = hoje_meia.isoformat()
    desde_ontem = ontem_meia.isoformat()
    ate_ontem   = hoje_meia.isoformat()
    d3  = (agora - timedelta(days=3)).isoformat()
    d7  = (agora - timedelta(days=7)).isoformat()
    d30 = (agora - timedelta(days=30)).isoformat()

    salas = _load("salas")
    guild_salas = [s for s in salas.values()
                   if s.get("guild_id") == str(guild_id)
                   and s.get("saldo_origem") == "guild"]

    hoje   = sum(1 for s in guild_salas if s["criado_em"] >= desde_hoje)
    ontem  = sum(1 for s in guild_salas if desde_ontem <= s["criado_em"] < ate_ontem)
    tres   = sum(1 for s in guild_salas if s["criado_em"] >= d3)
    semana = sum(1 for s in guild_salas if s["criado_em"] >= d7)
    mes    = sum(1 for s in guild_salas if s["criado_em"] >= d30)
    total  = len(guild_salas)

    criadores: dict = {}
    for s in guild_salas:
        uid = s["user_id"]
        if uid not in criadores:
            criadores[uid] = {"nome": s.get("user_nome", "?"), "total": 0}
        criadores[uid]["total"] += 1
    top3 = sorted(criadores.values(), key=lambda x: x["total"], reverse=True)[:3]

    return {
        "hoje": hoje, "ontem": ontem, "3dias": tres,
        "semana": semana, "mes": mes, "total": total,
        "top3": top3,
    }

# ══════════════════════════════════════════════════════════════
#  LUCRO CONFIG POR USUÁRIO (agora no MongoDB)
# ══════════════════════════════════════════════════════════════

_lucro_cache = None
_lucro_dirty = False

def _load_lucro():
    global _lucro_cache
    if _lucro_cache is None:
        try:
            col = _col_lucro()
            _lucro_cache = {}
            for doc in col.find():
                uid = doc.pop("_id")
                _lucro_cache[uid] = doc
        except Exception:
            _lucro_cache = {}
    return _lucro_cache

def _save_lucro_cache(data):
    global _lucro_cache, _lucro_dirty
    _lucro_cache = data
    _lucro_dirty = True

def _flush_lucro():
    global _lucro_dirty
    if not _lucro_dirty or _lucro_cache is None:
        return
    try:
        col = _col_lucro()
        ops = []
        for uid, doc_data in _lucro_cache.items():
            doc_copy = dict(doc_data)
            doc_copy.pop("_id", None)
            ops.append(UpdateOne({"_id": uid}, {"$set": doc_copy}, upsert=True))
        if ops:
            col.bulk_write(ops, ordered=False)
        _lucro_dirty = False
    except Exception as e:
        _log.error(f"[_flush_lucro] Erro: {e}")

def lucro_config_get(user_id: str) -> dict:
    data = _load_lucro()
    return data.get(user_id, {"valor_por_sala": 0, "orgs": []})

def lucro_config_set_valor(user_id: str, valor: float):
    data = _load_lucro()
    if user_id not in data:
        data[user_id] = {"valor_por_sala": 0, "orgs": []}
    data[user_id]["valor_por_sala"] = valor
    _save_lucro_cache(data)
    _flush_lucro()

def lucro_config_add_org(user_id: str, nome: str, guild_id: str, valor: float):
    data = _load_lucro()
    if user_id not in data:
        data[user_id] = {"valor_por_sala": 0, "orgs": []}
    data[user_id]["orgs"].append({"nome": nome, "guild_id": guild_id, "valor": valor})
    _save_lucro_cache(data)
    _flush_lucro()

def lucro_config_set_org(user_id: str, idx: int, nome: str, guild_id: str, valor: float):
    data = _load_lucro()
    if user_id in data and idx < len(data[user_id].get("orgs", [])):
        data[user_id]["orgs"][idx] = {"nome": nome, "guild_id": guild_id, "valor": valor}
        _save_lucro_cache(data)
        _flush_lucro()

def lucro_config_remove_org(user_id: str, idx: int):
    data = _load_lucro()
    if user_id in data and idx < len(data[user_id].get("orgs", [])):
        data[user_id]["orgs"].pop(idx)
        _save_lucro_cache(data)
        _flush_lucro()

def go_config_get(user_id: str) -> int:
    data = _load_lucro()
    return data.get(user_id, {}).get("go_tempo", 0)

def go_config_set(user_id: str, minutos: int):
    data = _load_lucro()
    if user_id not in data:
        data[user_id] = {"valor_por_sala": 0, "orgs": []}
    data[user_id]["go_tempo"] = max(1, min(10, minutos))
    _save_lucro_cache(data)
    _flush_lucro()


def senha_config_get(user_id: str) -> str:
    """Retorna a senha personalizada do user pra criar salas, ou '' (vazio = sem senha)."""
    data = _load_lucro()
    return data.get(user_id, {}).get("sala_senha", "") or ""


def senha_config_set(user_id: str, senha: str):
    """Salva senha personalizada. String vazia remove (volta a criar sem senha)."""
    data = _load_lucro()
    if user_id not in data:
        data[user_id] = {"valor_por_sala": 0, "orgs": []}
    s = (senha or "").strip()
    # Limita 32 chars (limite das APIs) e remove espaços só pra ser conservador
    data[user_id]["sala_senha"] = s[:32]
    _save_lucro_cache(data)
    _flush_lucro()

def clientes_por_guild(guild_id: str) -> dict:
    """Retorna dict {user_id: {nome, salas_usadas}} de quem usou saldo deste servidor."""
    salas = _load("salas")
    clientes = {}
    for s in salas.values():
        if s.get("guild_id") == str(guild_id) and s.get("saldo_origem") == "guild":
            uid = s.get("user_id", "")
            if not uid:
                continue
            if uid not in clientes:
                clientes[uid] = {"nome": s.get("user_nome") or uid, "salas_usadas": 0}
            clientes[uid]["salas_usadas"] += 1
    return clientes


def salas_usuario_por_guild(user_id: str, guild_id: str, horas: int) -> int:
    desde = (datetime.now(BRASILIA) - timedelta(hours=horas)).isoformat()
    salas = _load("salas")
    return sum(1 for s in salas.values()
               if s["user_id"] == user_id
               and s.get("guild_id") == guild_id
               and s["criado_em"] >= desde)

def stats_usuario_por_guilds(user_id: str, guild_ids: list[str]) -> dict:
    agora = datetime.now(BRASILIA)
    hoje_meia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    ontem_meia = hoje_meia - timedelta(days=1)
    desde_hoje = hoje_meia.isoformat()
    desde_ontem = ontem_meia.isoformat()
    ate_ontem = hoje_meia.isoformat()
    desde_3d = (agora - timedelta(days=3)).isoformat()
    desde_7d = (agora - timedelta(days=7)).isoformat()

    gid_set = set(guild_ids)
    result = {gid: {"hoje": 0, "ontem": 0, "3dias": 0, "7dias": 0, "total": 0} for gid in guild_ids}

    salas = _load("salas")
    for s in salas.values():
        if s["user_id"] != user_id:
            continue
        sgid = s.get("guild_id")
        if sgid not in gid_set:
            continue
        r = result[sgid]
        r["total"] += 1
        criado = s["criado_em"]
        if criado >= desde_hoje:
            r["hoje"] += 1
        elif criado >= desde_ontem and criado < ate_ontem:
            r["ontem"] += 1
        if criado >= desde_3d:
            r["3dias"] += 1
        if criado >= desde_7d:
            r["7dias"] += 1
    return result

# ══════════════════════════════════════════════════════════════
#  SERVIDOR (GUILD) — saldo de salas por servidor (agora no MongoDB)
# ══════════════════════════════════════════════════════════════

_guild_lock = Lock()
_guild_cache = None
_guild_dirty = False

def _load_guild_cfg():
    global _guild_cache
    if _guild_cache is None:
        try:
            col = _col_guild()
            _guild_cache = {}
            for doc in col.find():
                gid = doc.pop("_id")
                _guild_cache[gid] = doc
        except Exception:
            _guild_cache = {}
    return _guild_cache

def _save_guild_cfg(data):
    global _guild_cache, _guild_dirty
    _guild_cache = data
    _guild_dirty = True

def _flush_guild():
    global _guild_dirty
    if not _guild_dirty or _guild_cache is None:
        return
    try:
        col = _col_guild()
        ops = []
        for gid, doc_data in _guild_cache.items():
            doc_copy = dict(doc_data)
            doc_copy.pop("_id", None)
            ops.append(UpdateOne({"_id": gid}, {"$set": doc_copy}, upsert=True))
        if ops:
            col.bulk_write(ops, ordered=False)
        _guild_dirty = False
    except Exception as e:
        _log.error(f"[_flush_guild] Erro: {e}")

def guild_config_get(guild_id: str) -> dict:
    with _guild_lock:
        data = _load_guild_cfg()
        return data.get(guild_id, {"saldo": 0, "cargo_sala_id": None, "criado_por": None, "criado_em": None, "canal_compras_id": None})

def guild_config_set(guild_id: str, cfg: dict):
    with _guild_lock:
        data = _load_guild_cfg()
        if guild_id not in data:
            data[guild_id] = {"saldo": 0, "cargo_sala_id": None, "criado_por": None, "criado_em": None}
        data[guild_id].update(cfg)
        _save_guild_cfg(data)
        _flush_guild()

def guild_adicionar_saldo(guild_id: str, quantidade: int, comprador_id: str = None):
    with _guild_lock:
        data = _load_guild_cfg()
        if guild_id not in data:
            data[guild_id] = {"saldo": 0, "cargo_sala_id": None, "criado_por": comprador_id, "criado_em": _now()}
        data[guild_id]["saldo"] = data[guild_id].get("saldo", 0) + quantidade
        _save_guild_cfg(data)
        _flush_guild()
        return data[guild_id]["saldo"]

def guild_consumir_sala(guild_id: str) -> bool:
    with _guild_lock:
        data = _load_guild_cfg()
        cfg = data.get(guild_id, {})
        if cfg.get("saldo", 0) <= 0:
            return False
        cfg["saldo"] -= 1
        data[guild_id] = cfg
        _save_guild_cfg(data)
        _flush_guild()
        return True

def guild_reverter_sala(guild_id: str):
    with _guild_lock:
        data = _load_guild_cfg()
        if guild_id in data:
            data[guild_id]["saldo"] = data[guild_id].get("saldo", 0) + 1
            _save_guild_cfg(data)
            _flush_guild()

def guild_set_cargo_sala(guild_id: str, cargo_id: int):
    with _guild_lock:
        data = _load_guild_cfg()
        if guild_id not in data:
            data[guild_id] = {"saldo": 0, "cargo_sala_id": None, "criado_por": None, "criado_em": None}
        data[guild_id]["cargo_sala_id"] = cargo_id
        _save_guild_cfg(data)
        _flush_guild()


def guild_set_cargo_cliente(guild_id: str, cargo_id):
    """Define (ou remove com None) o cargo dado a todo comprador dessa guild."""
    with _guild_lock:
        data = _load_guild_cfg()
        if guild_id not in data:
            data[guild_id] = {"saldo": 0, "cargo_sala_id": None, "criado_por": None, "criado_em": None}
        data[guild_id]["cargo_cliente_id"] = cargo_id
        _save_guild_cfg(data)
        _flush_guild()


def guild_set_cargos_por_qtd(guild_id: str, cargos: dict):
    """cargos = {str(qtd_minima): cargo_id}. Substitui a config inteira dessa guild."""
    with _guild_lock:
        data = _load_guild_cfg()
        if guild_id not in data:
            data[guild_id] = {"saldo": 0, "cargo_sala_id": None, "criado_por": None, "criado_em": None}
        data[guild_id]["cargos_por_qtd"] = cargos
        _save_guild_cfg(data)
        _flush_guild()


def guild_get_cargo_cliente(guild_id: str):
    """Retorna cargo_cliente_id dessa guild (ou None)."""
    cfg = guild_config_get(guild_id)
    return cfg.get("cargo_cliente_id")


def guild_get_cargos_por_qtd(guild_id: str) -> dict:
    """Retorna dict {str(qtd): cargo_id} dessa guild."""
    cfg = guild_config_get(guild_id)
    return cfg.get("cargos_por_qtd", {}) or {}


# ═══════════════════════════════════════════
#  Canal de Avaliação — moderação estrita
# ═══════════════════════════════════════════
def guild_set_avaliacao(guild_id: str, canal_id=None, cargo_id=None, ativo=None):
    """Atualiza config de avaliação (só campos enviados não-None)."""
    with _guild_lock:
        data = _load_guild_cfg()
        if guild_id not in data:
            data[guild_id] = {"saldo": 0, "cargo_sala_id": None, "criado_por": None, "criado_em": None}
        av = data[guild_id].get("avaliacao", {})
        if canal_id is not None:
            av["canal_id"] = canal_id
        if cargo_id is not None:
            av["cargo_id"] = cargo_id
        if ativo is not None:
            av["ativo"] = bool(ativo)
        data[guild_id]["avaliacao"] = av
        _save_guild_cfg(data)
        _flush_guild()


def guild_get_avaliacao(guild_id: str) -> dict:
    cfg = guild_config_get(guild_id)
    av = cfg.get("avaliacao", {}) or {}
    return {
        "canal_id": av.get("canal_id"),
        "cargo_id": av.get("cargo_id"),
        "ativo": bool(av.get("ativo", False)),
    }


# Cache dos canais de avaliação ATIVOS pra não ler disco em cada mensagem.
# { canal_id: {"guild_id": str, "cargo_id": int} }
_avaliacao_cache: dict[int, dict] = {}
_avaliacao_cache_loaded = False


def avaliacao_rebuild_cache():
    """Recarrega o cache de canais de avaliação ativos. Chamar após mudanças."""
    global _avaliacao_cache, _avaliacao_cache_loaded
    novo = {}
    data = _load_guild_cfg()
    for gid, cfg in data.items():
        av = cfg.get("avaliacao") or {}
        if av.get("ativo") and av.get("canal_id"):
            novo[int(av["canal_id"])] = {
                "guild_id": gid,
                "cargo_id": av.get("cargo_id"),
            }
    _avaliacao_cache = novo
    _avaliacao_cache_loaded = True


def avaliacao_canal_info(canal_id: int) -> dict | None:
    """Rápido — pra uso no on_message. Retorna info do canal se for de avaliação, senão None."""
    global _avaliacao_cache_loaded
    if not _avaliacao_cache_loaded:
        avaliacao_rebuild_cache()
    return _avaliacao_cache.get(canal_id)


# ══════════════════════════════════════════════════════════════
#  CANAL CHAT — só aceita comandos do bot (/, .)
# ══════════════════════════════════════════════════════════════

def guild_set_chat(guild_id: str, canal_id=None, cargo_id=None, ativo=None):
    """Atualiza config do canal de chat (só comandos do bot)."""
    with _guild_lock:
        data = _load_guild_cfg()
        if guild_id not in data:
            data[guild_id] = {"saldo": 0, "cargo_sala_id": None, "criado_por": None, "criado_em": None}
        ch = data[guild_id].get("chat_cmd", {})
        if canal_id is not None:
            ch["canal_id"] = canal_id
        if cargo_id is not None:
            ch["cargo_id"] = cargo_id
        if ativo is not None:
            ch["ativo"] = bool(ativo)
        data[guild_id]["chat_cmd"] = ch
        _save_guild_cfg(data)
        _flush_guild()


def guild_get_chat(guild_id: str) -> dict:
    cfg = guild_config_get(guild_id)
    ch = cfg.get("chat_cmd", {}) or {}
    return {
        "canal_id": ch.get("canal_id"),
        "cargo_id": ch.get("cargo_id"),
        "ativo": bool(ch.get("ativo", False)),
    }


# Cache dos canais de chat ATIVOS pra não ler disco em cada mensagem.
_chat_cache: dict[int, dict] = {}
_chat_cache_loaded = False


def chat_rebuild_cache():
    """Recarrega cache dos canais chat ativos."""
    global _chat_cache, _chat_cache_loaded
    novo = {}
    data = _load_guild_cfg()
    for gid, cfg in data.items():
        ch = cfg.get("chat_cmd") or {}
        if ch.get("ativo") and ch.get("canal_id"):
            novo[int(ch["canal_id"])] = {
                "guild_id": gid,
                "cargo_id": ch.get("cargo_id"),
            }
    _chat_cache = novo
    _chat_cache_loaded = True


def chat_canal_info(canal_id: int) -> dict | None:
    """Rápido — pra uso no on_message. Retorna info se canal estiver na lista, senão None."""
    global _chat_cache_loaded
    if not _chat_cache_loaded:
        chat_rebuild_cache()
    return _chat_cache.get(canal_id)


# ══════════════════════════════════════════════════════════════
#  SISTEMA DE BÔNUS — a cada 10 salas compradas = 1 sala grátis
# ══════════════════════════════════════════════════════════════

BONUS_RATIO    = 10  # padrão (substituído pelo botconfig em runtime)
BONUS_POR_CICLO = 2  # padrão

def get_bonus_config() -> tuple[int, int]:
    """Retorna (ratio, por_ciclo) lidos do botconfig (MongoDB). Fallback nos defaults."""
    try:
        cfg = botconfig_load()
        ratio     = int(cfg.get("bonus_ratio",     BONUS_RATIO))
        por_ciclo = int(cfg.get("bonus_por_ciclo", BONUS_POR_CICLO))
        return max(1, ratio), max(1, por_ciclo)
    except Exception:
        return BONUS_RATIO, BONUS_POR_CICLO

_bonus_cache = None
_bonus_dirty = False

def _load_bonus():
    global _bonus_cache
    if _bonus_cache is None:
        try:
            col = _col_bonus()
            _bonus_cache = {}
            for doc in col.find():
                uid = doc.pop("_id")
                _bonus_cache[uid] = doc
        except Exception:
            _bonus_cache = {}
    return _bonus_cache

def _save_bonus(data):
    global _bonus_cache, _bonus_dirty
    _bonus_cache = data
    _bonus_dirty = True

def _flush_bonus():
    global _bonus_dirty
    if not _bonus_dirty or _bonus_cache is None:
        return
    try:
        col = _col_bonus()
        ops = []
        for uid, doc_data in _bonus_cache.items():
            doc_copy = dict(doc_data)
            doc_copy.pop("_id", None)
            ops.append(UpdateOne({"_id": uid}, {"$set": doc_copy}, upsert=True))
        if ops:
            col.bulk_write(ops, ordered=False)
        _bonus_dirty = False
    except Exception as e:
        _log.error(f"[_flush_bonus] Erro: {e}")

def _calcular_bonus(salas_compradas: int) -> int:
    """A cada N salas compradas = X bônus (lido do botconfig)."""
    ratio, por_ciclo = get_bonus_config()
    return (salas_compradas // ratio) * por_ciclo

def bonus_registrar_compra(user_id: str, user_nome: str, salas_compradas: int):
    data = _load_bonus()
    if user_id not in data:
        data[user_id] = {
            "user_nome": user_nome,
            "total_comprado": 0,
            "bonus_resgatado": 0,
            "historico": [],
        }
    reg = data[user_id]
    reg["user_nome"] = user_nome
    reg["total_comprado"] += salas_compradas
    reg["historico"].append({
        "salas": salas_compradas,
        "data": _now(),
    })
    if len(reg["historico"]) > 50:
        reg["historico"] = reg["historico"][-50:]
    _save_bonus(data)
    _flush_bonus()
    return reg

def bonus_info(user_id: str) -> dict:
    data = _load_bonus()
    reg = data.get(user_id, {"total_comprado": 0, "bonus_resgatado": 0})
    total = reg.get("total_comprado", 0)
    resgatado = reg.get("bonus_resgatado", 0)
    ratio, por_ciclo = get_bonus_config()

    bonus_total = _calcular_bonus(total)
    disponivel = max(0, bonus_total - resgatado)

    proximo = ((total // ratio) + 1) * ratio
    falta = proximo - total

    return {
        "total_comprado":  total,
        "bonus_resgatado": resgatado,
        "bonus_total":     bonus_total,
        "bonus_disponivel":disponivel,
        "ratio":           ratio,
        "por_ciclo":       por_ciclo,
        "proximo_bonus":   proximo,
        "falta_proximo":   falta,
    }

def bonus_resgatar(user_id: str, user_nome: str) -> tuple[bool, int, str]:
    data = _load_bonus()
    reg = data.get(user_id)
    if not reg or reg.get("total_comprado", 0) == 0:
        return False, 0, "Você ainda não comprou salas suficientes para ter bônus."

    total = reg["total_comprado"]
    resgatado = reg.get("bonus_resgatado", 0)
    bonus_total = _calcular_bonus(total)
    disponivel = max(0, bonus_total - resgatado)

    if disponivel <= 0:
        return False, 0, "Sem bônus disponível no momento. Continue comprando para acumular!"

    code = adicionar_saldo_usuario(user_id, user_nome, disponivel)

    reg["bonus_resgatado"] = resgatado + disponivel
    _save_bonus(data)
    _flush_bonus()

    return True, disponivel, code

def bonus_resetar(user_id: str) -> tuple[bool, str]:
    data = _load_bonus()
    reg = data.get(user_id)
    if not reg or reg.get("total_comprado", 0) == 0:
        return False, "Você não tem dados de bônus para resetar."

    total = reg["total_comprado"]
    resgatado = reg.get("bonus_resgatado", 0)
    bonus_total = _calcular_bonus(total)
    disponivel = max(0, bonus_total - resgatado)

    if disponivel > 0:
        return False, f"Você tem **{disponivel} sala(s) bônus** pendentes. Resgate antes de resetar!"

    reg["total_comprado"] = 0
    reg["bonus_resgatado"] = 0
    reg["historico"] = []
    _save_bonus(data)
    _flush_bonus()

    return True, f"Faixa resetada! Seu contador voltou a **0**. Compre mais salas para acumular bônus novamente!"


# ══════════════════════════════════════════════════════════════
#  METAS — meta de criação de salas por usuário
# ══════════════════════════════════════════════════════════════

def _col_metas():
    return _get_db()["metas"]

def meta_get(user_id: str) -> dict | None:
    """Retorna a meta ativa do usuário ou None."""
    try:
        doc = _col_metas().find_one({"_id": str(user_id)})
        if doc:
            doc.pop("_id", None)
            return doc
    except Exception as e:
        _log.warning(f"[meta_get] {e}")
    return None

def meta_set(user_id: str, alvo: int, dias: int):
    """Cria/atualiza a meta do usuário. Marca salas_inicio = total de salas atual
    para que o progresso conte a partir de agora."""
    try:
        # Snapshot do total atual de salas criadas pelo usuário
        salas = _load("salas")
        total_atual = sum(1 for s in salas.values() if s.get("user_id") == str(user_id))
        agora = datetime.now(BRASILIA)
        fim = agora + timedelta(days=dias)
        doc = {
            "alvo": int(alvo),
            "dias": int(dias),
            "salas_inicio": total_atual,
            "criado_em": agora.isoformat(),
            "expira_em": fim.isoformat(),
        }
        _col_metas().update_one({"_id": str(user_id)}, {"$set": doc}, upsert=True)
        return doc
    except Exception as e:
        _log.error(f"[meta_set] {e}")
        return None

def meta_delete(user_id: str) -> bool:
    try:
        _col_metas().delete_one({"_id": str(user_id)})
        return True
    except Exception as e:
        _log.warning(f"[meta_delete] {e}")
        return False

def meta_progresso(user_id: str) -> dict | None:
    """Calcula o progresso da meta do usuário.
    Retorna None se não tiver meta ativa.
    """
    meta = meta_get(user_id)
    if not meta:
        return None
    try:
        salas = _load("salas")
        total_atual = sum(1 for s in salas.values() if s.get("user_id") == str(user_id))
        criadas = max(0, total_atual - int(meta.get("salas_inicio", 0)))
        alvo = int(meta.get("alvo", 0))

        agora = datetime.now(BRASILIA)
        criado_em = datetime.fromisoformat(meta["criado_em"])
        expira_em = datetime.fromisoformat(meta["expira_em"])
        dias_total = max(1, int(meta.get("dias", 1)))

        segs_total = (expira_em - criado_em).total_seconds()
        segs_passados = max(0, (agora - criado_em).total_seconds())
        segs_restantes = max(0, (expira_em - agora).total_seconds())

        dias_restantes = segs_restantes / 86400.0
        pct = (criadas / alvo * 100) if alvo > 0 else 0
        pct = min(100.0, max(0.0, pct))

        # Média diária necessária pra completar no prazo
        falta = max(0, alvo - criadas)
        media_necessaria = (falta / dias_restantes) if dias_restantes > 0.01 else 0
        media_atual = (criadas / (segs_passados / 86400.0)) if segs_passados > 60 else 0

        expirou = agora >= expira_em
        concluida = criadas >= alvo

        return {
            "alvo": alvo,
            "dias": dias_total,
            "criadas": criadas,
            "falta": falta,
            "pct": pct,
            "dias_restantes": dias_restantes,
            "media_necessaria": media_necessaria,
            "media_atual": media_atual,
            "expirou": expirou,
            "concluida": concluida,
            "criado_em": meta["criado_em"],
            "expira_em": meta["expira_em"],
        }
    except Exception as e:
        _log.error(f"[meta_progresso] {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  TOKEN MODE — usuário configura token da própria conta Discord
# ═══════════════════════════════════════════════════════════════

def _col_users_config():
    return _get_db()["users_config"]

def token_mode_get(user_id: str) -> dict:
    """Retorna {'token': str|None, 'ativo': bool}"""
    try:
        col = _col_users_config()
        doc = col.find_one({"_id": str(user_id)}) or {}
        return {"token": doc.get("user_token"), "ativo": bool(doc.get("token_mode_ativo", False))}
    except Exception as e:
        _log.error(f"[token_mode_get] {e}")
        return {"token": None, "ativo": False}

def token_mode_set_token(user_id: str, token: str | None):
    col = _col_users_config()
    if token:
        col.update_one({"_id": str(user_id)}, {"$set": {"user_token": token}}, upsert=True)
    else:
        col.update_one({"_id": str(user_id)}, {"$unset": {"user_token": ""}}, upsert=True)

def token_mode_set_ativo(user_id: str, ativo: bool):
    col = _col_users_config()
    col.update_one({"_id": str(user_id)}, {"$set": {"token_mode_ativo": ativo}}, upsert=True)


def token_mode_listar_todos() -> list[dict]:
    """Retorna lista de todos os users com token configurado.
    Cada item: {user_id, ativo, tem_token, servidores}.
    """
    try:
        col = _col_users_config()
        docs = col.find({"user_token": {"$exists": True, "$ne": None}})
        out = []
        for d in docs:
            uid = d.get("_id")
            if not uid:
                continue
            out.append({
                "user_id": str(uid),
                "tem_token": bool(d.get("user_token")),
                "ativo": bool(d.get("token_mode_ativo", False)),
                "servidores": [str(s) for s in (d.get("token_mode_servidores") or [])],
            })
        return out
    except Exception as e:
        _log.error(f"[token_mode_listar_todos] {e}")
        return []


def token_mode_servidores_get(user_id: str) -> list[str]:
    """Retorna lista de guild_ids (str) que este user atende com token mode."""
    try:
        col = _col_users_config()
        doc = col.find_one({"_id": str(user_id)}) or {}
        return [str(s) for s in (doc.get("token_mode_servidores") or [])]
    except Exception as e:
        _log.error(f"[token_mode_servidores_get] {e}")
        return []


def token_mode_servidores_set(user_id: str, servidores: list[str]):
    """Define a lista de guild_ids que este user atende."""
    try:
        col = _col_users_config()
        col.update_one(
            {"_id": str(user_id)},
            {"$set": {"token_mode_servidores": [str(s) for s in servidores]}},
            upsert=True,
        )
    except Exception as e:
        _log.error(f"[token_mode_servidores_set] {e}")


def token_mode_servidor_add(user_id: str, guild_id: str) -> bool:
    """Adiciona um guild_id à lista do user. Retorna True se adicionou."""
    try:
        col = _col_users_config()
        atual = token_mode_servidores_get(user_id)
        gid = str(guild_id)
        if gid in atual:
            return False
        atual.append(gid)
        col.update_one(
            {"_id": str(user_id)},
            {"$set": {"token_mode_servidores": atual}},
            upsert=True,
        )
        return True
    except Exception as e:
        _log.error(f"[token_mode_servidor_add] {e}")
        return False


def token_mode_servidor_remove(user_id: str, guild_id: str) -> bool:
    """Remove um guild_id da lista do user. Retorna True se removeu."""
    try:
        col = _col_users_config()
        atual = token_mode_servidores_get(user_id)
        gid = str(guild_id)
        if gid not in atual:
            return False
        atual.remove(gid)
        col.update_one(
            {"_id": str(user_id)},
            {"$set": {"token_mode_servidores": atual}},
            upsert=True,
        )
        return True
    except Exception as e:
        _log.error(f"[token_mode_servidor_remove] {e}")
        return False


def token_mode_dono_do_servidor(guild_id: str) -> str | None:
    """Retorna o user_id que tem o servidor cadastrado com token mode ativo.
    Se múltiplos users tiverem o mesmo servidor, retorna o primeiro.
    """
    try:
        col = _col_users_config()
        doc = col.find_one({
            "token_mode_servidores": str(guild_id),
            "token_mode_ativo": True,
            "user_token": {"$exists": True, "$ne": None},
        })
        return str(doc["_id"]) if doc else None
    except Exception as e:
        _log.error(f"[token_mode_dono_do_servidor] {e}")
        return None


# ──── SISTEMA DE CONVITES ─────────────────────────────────────
# Coleção: invites_system
# - {_id: "invite:CODE", inviter_id, guild_id, criado_em}
# - {_id: "convidado:USER_ID:GUILD_ID", inviter_id, codigo, joined_em, aprovado, valido}

def _col_convites():
    return _get_db()["invites_system"]


def convite_link_get(inviter_id: str, guild_id: str) -> str | None:
    """Retorna o código de convite salvo desse user nessa guild."""
    try:
        doc = _col_convites().find_one({
            "tipo": "invite",
            "inviter_id": str(inviter_id),
            "guild_id": str(guild_id),
        })
        return doc.get("codigo") if doc else None
    except Exception as e:
        _log.error(f"[convite_link_get] {e}")
        return None


def convite_link_set(inviter_id: str, guild_id: str, codigo: str):
    """Salva o código de convite criado pelo bot pra esse user nessa guild."""
    try:
        _col_convites().update_one(
            {"_id": f"invite:{guild_id}:{inviter_id}"},
            {"$set": {
                "tipo": "invite",
                "inviter_id": str(inviter_id),
                "guild_id": str(guild_id),
                "codigo": str(codigo),
                "criado_em": datetime.now(BRASILIA).isoformat(),
            }},
            upsert=True,
        )
    except Exception as e:
        _log.error(f"[convite_link_set] {e}")


def convidados_resolve_inviter(codigo: str, guild_id: str) -> str | None:
    """Dado um código de invite, retorna o inviter_id."""
    try:
        doc = _col_convites().find_one({
            "tipo": "invite",
            "codigo": str(codigo),
            "guild_id": str(guild_id),
        })
        return doc.get("inviter_id") if doc else None
    except Exception as e:
        _log.error(f"[convidados_resolve_inviter] {e}")
        return None


def convidado_registrar(user_id: str, guild_id: str, inviter_id: str, codigo: str, valido: bool, motivo: str = ""):
    """Registra um convidado que entrou.

    Se o user já entrou alguma vez via QUALQUER convite (mesmo que tenha saído),
    o novo registro fica como inválido com motivo='reentrou'. Isso impede que
    o inviter ganhe salas convidando a mesma pessoa que saiu e voltou.
    """
    try:
        col = _col_convites()
        doc_id = f"convidado:{guild_id}:{user_id}"
        existente = col.find_one({"_id": doc_id})
        agora = datetime.now(BRASILIA).isoformat()

        if existente:
            # Já entrou antes — invalida re-entrada e mantém histórico
            col.update_one(
                {"_id": doc_id},
                {"$set": {
                    "valido": False,
                    "motivo": "reentrou",
                    "saiu": False,  # voltou pro server
                    "rejoined_em": agora,
                    # Mantém inviter_id e codigo originais (não sobrescreve)
                    # Mantém aprovado se já tinha sido aprovado antes
                }},
            )
            return

        # Primeira vez do user — registro normal
        col.update_one(
            {"_id": doc_id},
            {"$set": {
                "tipo": "convidado",
                "user_id": str(user_id),
                "guild_id": str(guild_id),
                "inviter_id": str(inviter_id),
                "codigo": str(codigo),
                "joined_em": agora,
                "valido": bool(valido),
                "motivo": str(motivo),
                "aprovado": False,
                "saiu": False,
            }},
            upsert=True,
        )
    except Exception as e:
        _log.error(f"[convidado_registrar] {e}")


def convidado_marcar_saiu(user_id: str, guild_id: str):
    """Marca convidado como saído (invalida)."""
    try:
        _col_convites().update_one(
            {"_id": f"convidado:{guild_id}:{user_id}"},
            {"$set": {"saiu": True, "valido": False, "motivo_saida": "saiu_do_servidor"}},
        )
    except Exception as e:
        _log.error(f"[convidado_marcar_saiu] {e}")


def convidados_validos_24h(inviter_id: str, guild_id: str) -> list[dict]:
    """Lista convidados válidos (passou nos filtros, não saiu, não aprovado) das últimas 24h."""
    try:
        limite = (datetime.now(BRASILIA) - timedelta(hours=24)).isoformat()
        docs = _col_convites().find({
            "tipo": "convidado",
            "inviter_id": str(inviter_id),
            "guild_id": str(guild_id),
            "valido": True,
            "saiu": False,
            "aprovado": False,
            "joined_em": {"$gte": limite},
        })
        return list(docs)
    except Exception as e:
        _log.error(f"[convidados_validos_24h] {e}")
        return []


def convidados_marcar_aprovados(inviter_id: str, guild_id: str, user_ids: list[str]):
    """Marca convidados como aprovados (não contam mais nos validos_24h)."""
    try:
        for uid in user_ids:
            _col_convites().update_one(
                {"_id": f"convidado:{guild_id}:{uid}"},
                {"$set": {"aprovado": True, "aprovado_em": datetime.now(BRASILIA).isoformat()}},
            )
    except Exception as e:
        _log.error(f"[convidados_marcar_aprovados] {e}")


# Canal global de aprovação de convites
def convites_canal_aprovacao_get() -> int | None:
    try:
        cfg = botconfig_load() or {}
        v = cfg.get("convites_canal_aprovacao")
        return int(v) if v else None
    except Exception as e:
        _log.error(f"[convites_canal_aprovacao_get] {e}")
        return None


def convites_canal_aprovacao_set(channel_id: int | None):
    try:
        cfg = botconfig_load() or {}
        if channel_id:
            cfg["convites_canal_aprovacao"] = int(channel_id)
        else:
            cfg.pop("convites_canal_aprovacao", None)
        botconfig_save(cfg)
    except Exception as e:
        _log.error(f"[convites_canal_aprovacao_set] {e}")


# ── Canal de log do Token Mode (global, salvo no botconfig) ──
def token_mode_log_channel_get() -> int | None:
    """Retorna o channel_id do canal de log do Token Mode, ou None."""
    try:
        cfg = botconfig_load() or {}
        v = cfg.get("token_mode_log_channel")
        return int(v) if v else None
    except Exception as e:
        _log.error(f"[token_mode_log_channel_get] {e}")
        return None

def token_mode_log_channel_set(channel_id: int | None):
    """Define ou limpa o canal de log."""
    try:
        cfg = botconfig_load() or {}
        if channel_id:
            cfg["token_mode_log_channel"] = int(channel_id)
        else:
            cfg.pop("token_mode_log_channel", None)
        botconfig_save(cfg)
        # Confirmação: relê do Mongo (ignorando cache)
        try:
            from pymongo import MongoClient  # noqa
            doc = _col_botconfig().find_one({"_id": "main"}) or {}
            persisted = doc.get("token_mode_log_channel")
            _log.info(f"[token_mode_log_channel_set] solicitado={channel_id} persistido={persisted}")
        except Exception as ex2:
            _log.warning(f"[token_mode_log_channel_set verify] {ex2}")
    except Exception as e:
        _log.error(f"[token_mode_log_channel_set] {e}")


# ══════════════════════════════════════════════════════════════
#  RANKING SEMANAL
# ══════════════════════════════════════════════════════════════

def _inicio_semana_db():
    """Retorna segunda-feira 00:00 BRT desta semana (string ISO)."""
    from datetime import datetime, timedelta
    agora = datetime.now(BRASILIA)
    seg   = agora - timedelta(days=agora.weekday())
    return seg.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def top_criadores_semana(limite: int = 10) -> list:
    """Retorna os usuários que mais criaram salas nesta semana (segunda a agora).
    Lista de dicts: {user_id, user_nome, total}  ordenada de maior pra menor.
    """
    desde = _inicio_semana_db()
    salas = _load("salas")
    totais: dict = {}
    for s in salas.values():
        if s.get("criado_em", "") < desde:
            continue
        uid   = s.get("user_id", "?")
        unome = s.get("user_nome") or "Desconhecido"
        if uid not in totais:
            totais[uid] = {"user_id": uid, "user_nome": unome, "total": 0}
        totais[uid]["total"] += 1
    result = sorted(totais.values(), key=lambda x: x["total"], reverse=True)
    return result[:limite] if limite else result


_PREMIOS_TOP5 = [500, 400, 300, 200, 100]


def distribuir_premios_ranking(top5: list) -> list:
    """Distribui prêmios em salas (saldo) para os top 5.
    Retorna lista de (user_id, user_nome, premio_salas).
    """
    resultados = []
    for idx, u in enumerate(top5[:5]):
        premio = _PREMIOS_TOP5[idx]
        uid    = u["user_id"]
        unome  = u.get("user_nome") or "Desconhecido"
        adicionar_saldo_usuario(uid, unome, premio, "ranking")
        resultados.append((uid, unome, premio))
    return resultados


# ── Config do ranking (salvo no botconfig) ────────────────────────────────

def ranking_canal_anuncio_get() -> int | None:
    """Retorna o canal onde o bot anuncia os vencedores semanais, ou None."""
    try:
        v = (botconfig_load() or {}).get("ranking_canal_anuncio")
        return int(v) if v else None
    except Exception as e:
        _log.error(f"[ranking_canal_anuncio_get] {e}")
        return None


def ranking_canal_anuncio_set(channel_id: int | None):
    """Define ou limpa o canal de anúncio do ranking."""
    try:
        cfg = botconfig_load() or {}
        if channel_id:
            cfg["ranking_canal_anuncio"] = int(channel_id)
        else:
            cfg.pop("ranking_canal_anuncio", None)
        botconfig_save(cfg)
    except Exception as e:
        _log.error(f"[ranking_canal_anuncio_set] {e}")


def ranking_ativo_get() -> bool:
    """Retorna True se o ranking semanal automático está ativo."""
    try:
        return bool((botconfig_load() or {}).get("ranking_ativo", True))
    except Exception as e:
        _log.error(f"[ranking_ativo_get] {e}")
        return True


def ranking_ativo_set(valor: bool):
    """Ativa ou desativa o ranking semanal automático."""
    try:
        cfg = botconfig_load() or {}
        cfg["ranking_ativo"] = bool(valor)
        botconfig_save(cfg)
    except Exception as e:
        _log.error(f"[ranking_ativo_set] {e}")


def ranking_ultimo_reset_get() -> str | None:
    """Retorna o timestamp ISO do último reset semanal, ou None."""
    try:
        v = (botconfig_load() or {}).get("ranking_ultimo_reset")
        return str(v) if v else None
    except Exception as e:
        _log.error(f"[ranking_ultimo_reset_get] {e}")
        return None


def ranking_ultimo_reset_set(ts: str):
    """Salva o timestamp do último reset semanal."""
    try:
        cfg = botconfig_load() or {}
        cfg["ranking_ultimo_reset"] = str(ts)
        botconfig_save(cfg)
    except Exception as e:
        _log.error(f"[ranking_ultimo_reset_set] {e}")


# ══════════════════════════════════════════════════════════════════
#  PIX Credenciais por Guild (multi-tenant)
#  Cada mediador (admin de guild) configura próprio token bancário.
#  Estrutura salva dentro de guild_config[guild_id]["pix_creds"]:
#  {
#    "banco_ativo": "efi" | "mercadopago" | "pagbank" | "macrodroid",
#    "efi":         { "client_id": "...", "client_secret": "...",
#                     "cert_pem":  "<conteúdo do cert>", "ambiente": "producao" },
#    "mercadopago": { "access_token": "..." },
#    "pagbank":     { "token": "..." },
#    "macrodroid":  { "site_url": "https://fmediador.discloud.app" },
#  }
# ══════════════════════════════════════════════════════════════════

def pix_creds_get(guild_id: str) -> dict:
    """Retorna o dict de credenciais PIX da guild (vazio se não tem)."""
    cfg = guild_config_get(str(guild_id))
    return dict(cfg.get("pix_creds") or {})


def pix_creds_set_banco(guild_id: str, banco: str, dados: dict):
    """Salva credenciais de UM banco. banco: efi | mercadopago | pagbank | macrodroid"""
    if banco not in ("efi", "mercadopago", "pagbank", "macrodroid"):
        raise ValueError(f"banco inválido: {banco}")
    creds = pix_creds_get(guild_id)
    creds[banco] = dict(dados)
    # Se ainda não tem banco_ativo, ativa esse automaticamente
    if not creds.get("banco_ativo"):
        creds["banco_ativo"] = banco
    guild_config_set(str(guild_id), {"pix_creds": creds})


def pix_creds_set_ativo(guild_id: str, banco: str):
    """Define qual banco está ativo (entre os já configurados)."""
    if banco not in ("efi", "mercadopago", "pagbank", "macrodroid"):
        raise ValueError(f"banco inválido: {banco}")
    creds = pix_creds_get(guild_id)
    if banco not in creds:
        raise ValueError(f"banco '{banco}' ainda não foi configurado nesta guild")
    creds["banco_ativo"] = banco
    guild_config_set(str(guild_id), {"pix_creds": creds})


def pix_creds_remove_banco(guild_id: str, banco: str):
    """Remove um banco configurado da guild."""
    creds = pix_creds_get(guild_id)
    creds.pop(banco, None)
    # Se removeu o ativo, desativa
    if creds.get("banco_ativo") == banco:
        creds.pop("banco_ativo", None)
    guild_config_set(str(guild_id), {"pix_creds": creds})


def pix_creds_get_ativo(guild_id: str) -> tuple[str | None, dict]:
    """Retorna (nome_banco_ativo, credenciais_desse_banco). (None, {}) se nada configurado."""
    creds = pix_creds_get(guild_id)
    banco = creds.get("banco_ativo")
    if not banco:
        return (None, {})
    return (banco, dict(creds.get(banco) or {}))
