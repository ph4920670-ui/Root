"""
Camada de banco de dados — Supabase REST API (PostgREST via HTTPS).
Funciona no Discloud (porta 443, sem bloqueio de firewall).

Tabelas: produtos, estoque, planos, config, vendas
"""
import os
import aiohttp

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')


def _headers():
    return {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation',
    }


def _base():
    return f'{SUPABASE_URL}/rest/v1'


async def _get(session, tabela, params=None):
    async with session.get(f'{_base()}/{tabela}', headers=_headers(),
                           params=params or {}) as r:
        if r.status not in (200, 206):
            raise RuntimeError(f'GET {tabela} HTTP {r.status}: {(await r.text())[:200]}')
        return await r.json()


async def _post(session, tabela, body):
    async with session.post(f'{_base()}/{tabela}', headers=_headers(),
                            json=body) as r:
        if r.status not in (200, 201):
            raise RuntimeError(f'POST {tabela} HTTP {r.status}: {(await r.text())[:200]}')
        return await r.json()


async def _patch(session, tabela, params, body):
    async with session.patch(f'{_base()}/{tabela}', headers=_headers(),
                             params=params, json=body) as r:
        if r.status not in (200, 204):
            raise RuntimeError(f'PATCH {tabela} HTTP {r.status}: {(await r.text())[:200]}')
        return await r.json() if r.status == 200 else []


async def _delete(session, tabela, params):
    async with session.delete(f'{_base()}/{tabela}', headers=_headers(),
                              params=params) as r:
        if r.status not in (200, 204):
            raise RuntimeError(f'DELETE {tabela} HTTP {r.status}: {(await r.text())[:200]}')


async def _upsert(session, tabela, body, on_conflict):
    """INSERT ... ON CONFLICT DO UPDATE via Prefer: resolution=merge-duplicates.
    on_conflict precisa ir na query string pro PostgREST resolver o conflito na
    coluna/índice certo (não na PK). Aceita coluna única ('codigo') ou composta
    ('cupom_id,plano_id')."""
    hdrs = {**_headers(), 'Prefer': 'resolution=merge-duplicates,return=representation'}
    params = {'on_conflict': on_conflict} if on_conflict else {}
    async with session.post(f'{_base()}/{tabela}', headers=hdrs, json=body,
                            params=params) as r:
        if r.status not in (200, 201):
            raise RuntimeError(f'UPSERT {tabela} HTTP {r.status}: {(await r.text())[:200]}')
        return await r.json()


# ───────────────────────── PRODUTOS ─────────────────────────

async def listar_produtos(session):
    return await _get(session, 'produtos', {'order': 'criado_em.desc'})


async def add_produto(session, nome, preco):
    rows = await _post(session, 'produtos', {'nome': nome, 'preco': preco})
    return rows[0] if rows else None


async def del_produto(session, produto_id):
    await _delete(session, 'produtos', {'id': f'eq.{produto_id}'})


# ───────────────────────── ESTOQUE ─────────────────────────

async def add_estoque(session, produto_id, linhas):
    if not linhas:
        return 0
    body = [{'produto_id': produto_id, 'conteudo': l, 'vendido': False} for l in linhas]
    rows = await _post(session, 'estoque', body)
    return len(rows)


async def contar_estoque(session, produto_id):
    rows = await _get(session, 'estoque', {
        'produto_id': f'eq.{produto_id}', 'vendido': 'eq.false', 'select': 'id'})
    return len(rows)


async def pegar_um_estoque(session, produto_id):
    """Pega o item mais antigo não vendido e marca como vendido."""
    rows = await _get(session, 'estoque', {
        'produto_id': f'eq.{produto_id}', 'vendido': 'eq.false',
        'order': 'criado_em.asc', 'limit': '1'})
    if not rows:
        return None
    item = rows[0]
    await _patch(session, 'estoque', {'id': f'eq.{item["id"]}'}, {'vendido': True})
    return item['conteudo']


# ───────────────────────── PLANOS ─────────────────────────

async def listar_planos(session):
    return await _get(session, 'planos', {'order': 'preco.asc'})


async def add_plano(session, nome, dias, preco, cargo_id=None):
    rows = await _post(session, 'planos', {
        'nome': nome, 'dias': dias, 'preco': preco, 'cargo_id': cargo_id})
    return rows[0] if rows else None


async def set_cargo_plano(session, plano_id, cargo_id):
    await _patch(session, 'planos', {'id': f'eq.{plano_id}'}, {'cargo_id': str(cargo_id)})


async def del_plano(session, plano_id):
    await _delete(session, 'planos', {'id': f'eq.{plano_id}'})


# ───────────────────────── CONFIG ─────────────────────────

async def get_config(session, guild_id):
    rows = await _get(session, 'config', {'guild_id': f'eq.{guild_id}'})
    return rows[0] if rows else None


async def set_cargo_cliente(session, guild_id, cargo_id):
    await _upsert(session, 'config',
                  {'guild_id': str(guild_id), 'cargo_cliente': str(cargo_id)},
                  on_conflict='guild_id')


async def set_canal_logs(session, guild_id, canal_id):
    await _upsert(session, 'config',
                  {'guild_id': str(guild_id), 'canal_logs': str(canal_id)},
                  on_conflict='guild_id')


async def set_cargo_compras(session, guild_id, cargo_id):
    """Cargo que pode ver as threads de compra (carrinhos)."""
    await _upsert(session, 'config',
                  {'guild_id': str(guild_id), 'cargo_compras': str(cargo_id)},
                  on_conflict='guild_id')


async def set_cargo_suporte(session, guild_id, cargo_id):
    """Cargo que é marcado quando um ticket de suporte é aberto."""
    await _upsert(session, 'config',
                  {'guild_id': str(guild_id), 'cargo_suporte': str(cargo_id)},
                  on_conflict='guild_id')


async def set_canal_sugestao(session, guild_id, canal_id):
    """Canal onde mensagens viram sugestões com reactions de voto."""
    await _upsert(session, 'config',
                  {'guild_id': str(guild_id), 'canal_sugestao': str(canal_id)},
                  on_conflict='guild_id')


async def set_canal_logs_salas(session, guild_id, canal_id):
    """Canal onde aparecem os logs de salas criadas (puxados do configadm).
    Guardado dentro de dados_json (jsonb) pra NÃO exigir migration de coluna —
    funciona em qualquer tabela config já existente."""
    cfg = await get_config(session, guild_id) or {}
    dados = cfg.get('dados_json') or {}
    if not isinstance(dados, dict):
        dados = {}
    dados['canal_logs_salas'] = str(canal_id)
    await _upsert(session, 'config',
                  {'guild_id': str(guild_id), 'dados_json': dados},
                  on_conflict='guild_id')


async def set_canal_erros(session, guild_id, canal_id):
    """Canal onde o bot avisa erros dos bots dos clientes (token inválido etc.),
    marcando o dono. Guardado em dados_json pra não exigir migration de coluna."""
    cfg = await get_config(session, guild_id) or {}
    dados = cfg.get('dados_json') or {}
    if not isinstance(dados, dict):
        dados = {}
    dados['canal_erros'] = str(canal_id)
    await _upsert(session, 'config',
                  {'guild_id': str(guild_id), 'dados_json': dados},
                  on_conflict='guild_id')


async def listar_configs_com_canal_salas(session):
    """Retorna [{guild_id, canal_logs_salas}] de todos os guilds que configuraram
    o canal (lido de dados_json). Usado pelo poller pra rotear cada sala pro
    canal certo do guild de origem."""
    rows = await _get(session, 'config', {'select': 'guild_id,dados_json'})
    out = []
    for r in rows or []:
        dj = r.get('dados_json') or {}
        canal = dj.get('canal_logs_salas') if isinstance(dj, dict) else None
        if canal:
            out.append({'guild_id': r['guild_id'], 'canal_logs_salas': canal})
    return out


async def get_ultima_sugestao(session, user_id, guild_id):
    """Retorna o timestamp ISO da última sugestão do usuário, ou None."""
    params = {
        'user_id':  f'eq.{user_id}',
        'guild_id': f'eq.{guild_id}',
        'select':   'enviada_em',
        'limit':    '1',
    }
    linhas = await _get(session, 'sugestoes_log', params)
    if linhas:
        return linhas[0].get('enviada_em')
    return None


async def marcar_sugestao(session, user_id, guild_id):
    """Marca que o usuário acabou de enviar uma sugestão (upsert)."""
    from datetime import datetime, timezone
    agora_iso = datetime.now(timezone.utc).isoformat()
    await _upsert(session, 'sugestoes_log',
                  {'user_id':  str(user_id),
                   'guild_id': str(guild_id),
                   'enviada_em': agora_iso},
                  on_conflict='user_id,guild_id')


async def set_canal_logs_vendas(session, guild_id, canal_id):
    """Canal onde o bot posta o log de cada venda confirmada."""
    await _upsert(session, 'config',
                  {'guild_id': str(guild_id), 'canal_logs_vendas': str(canal_id)},
                  on_conflict='guild_id')


# ───────────────────────── VENDAS ─────────────────────────

async def criar_venda(session, user_id, tipo, ref_id, valor, txid=None):
    rows = await _post(session, 'vendas', {
        'user_id': str(user_id), 'tipo': tipo, 'ref_id': str(ref_id),
        'valor': valor, 'status': 'pendente', 'txid': txid})
    return rows[0] if rows else None


async def marcar_venda_paga(session, venda_id):
    await _patch(session, 'vendas', {'id': f'eq.{venda_id}'}, {'status': 'pago'})


async def marcar_venda_entregue(session, venda_id):
    await _patch(session, 'vendas', {'id': f'eq.{venda_id}'},
                 {'status': 'entregue'})


async def get_venda(session, venda_id):
    rows = await _get(session, 'vendas', {'id': f'eq.{venda_id}'})
    return rows[0] if rows else None


async def get_venda_por_txid(session, txid):
    rows = await _get(session, 'vendas', {'txid': f'eq.{txid}'})
    return rows[0] if rows else None


# ───────────────────────── WALLET ─────────────────────────

async def get_wallet_config(session, user_id):
    """Retorna {user_id, porcentagem} se o ID estiver liberado, senão None."""
    rows = await _get(session, 'wallet_config', {'user_id': f'eq.{user_id}'})
    return rows[0] if rows else None


async def listar_wallet_configs(session):
    return await _get(session, 'wallet_config', {'order': 'criado_em.desc'})


async def set_wallet_config(session, user_id, porcentagem):
    """Cadastra/atualiza um ID liberado e sua porcentagem."""
    await _upsert(session, 'wallet_config',
                  {'user_id': str(user_id), 'porcentagem': float(porcentagem)},
                  on_conflict='user_id')


async def del_wallet_config(session, user_id):
    await _delete(session, 'wallet_config', {'user_id': f'eq.{user_id}'})


async def add_wallet_movimento(session, user_id, tipo, valor, venda_id=None):
    """Registra um movimento (comissao/saque). Para comissão, o índice único
    em venda_id evita crédito duplicado (lança erro 409 silenciado pelo caller)."""
    body = {'user_id': str(user_id), 'tipo': tipo, 'valor': float(valor)}
    if venda_id is not None:
        body['venda_id'] = int(venda_id)
    rows = await _post(session, 'wallet_movimentos', body)
    return rows[0] if rows else None


async def comissao_ja_creditada(session, venda_id, user_id):
    rows = await _get(session, 'wallet_movimentos', {
        'venda_id': f'eq.{venda_id}', 'user_id': f'eq.{user_id}',
        'tipo': 'eq.comissao', 'select': 'id'})
    return bool(rows)


async def listar_wallet_movimentos(session, user_id):
    return await _get(session, 'wallet_movimentos', {
        'user_id': f'eq.{user_id}', 'order': 'criado_em.desc'})


async def get_wallet_saldo(session, user_id):
    """Saldo atual = soma das comissões − soma dos saques."""
    movs = await listar_wallet_movimentos(session, user_id)
    saldo = 0.0
    for m in movs:
        v = float(m['valor'])
        saldo += v if m['tipo'] == 'comissao' else -v
    return round(saldo, 2)


# ───────────────────────── CUPONS ─────────────────────────
async def criar_cupom(session, codigo, tipo, valor):
    """Cria (ou reativa/atualiza) um cupom. Código é guardado em MAIÚSCULAS.
    Usa upsert pelo código pra evitar duplicar — se já existe, atualiza os
    dados e reativa."""
    codigo = (codigo or '').strip().upper()
    body = {'codigo': codigo, 'tipo': tipo, 'valor': valor, 'ativo': True}
    rows = await _upsert(session, 'cupons', body, on_conflict='codigo')
    return rows[0] if rows else None


async def get_cupom(session, codigo):
    """Busca um cupom ATIVO pelo código (case-insensitive). None se não achar."""
    codigo = (codigo or '').strip().upper()
    if not codigo:
        return None
    rows = await _get(session, 'cupons', {
        'codigo': f'eq.{codigo}', 'ativo': 'eq.true', 'limit': '1'})
    return rows[0] if rows else None


async def listar_cupons(session):
    return await _get(session, 'cupons', {'order': 'criado_em.desc'})


async def set_cupom_ativo(session, cupom_id, ativo):
    await _patch(session, 'cupons', {'id': f'eq.{cupom_id}'}, {'ativo': bool(ativo)})


async def del_cupom(session, cupom_id):
    await _delete(session, 'cupons', {'id': f'eq.{cupom_id}'})


def aplicar_desconto(valor, cupom):
    """Calcula o valor final aplicando o cupom. Nunca deixa abaixo de R$0,01.
    Retorna (valor_final, desconto_aplicado)."""
    try:
        valor = float(valor)
    except (TypeError, ValueError):
        return valor, 0.0
    if not cupom:
        return round(valor, 2), 0.0
    tipo = (cupom.get('tipo') or 'percent').strip().lower()
    cval = float(cupom.get('valor') or 0)
    if tipo == 'percent':
        desconto = valor * (cval / 100.0)
    else:  # 'fixo'
        desconto = cval
    final = valor - desconto
    if final < 0.01:
        final = 0.01
    desconto = round(valor - final, 2)
    return round(final, 2), desconto


# ─────────────── % DO CUPOM POR PLANO (cupom_planos) ───────────────
async def set_cupom_plano_percent(session, cupom_id, plano_id, percent):
    """Define (ou redefine) a % de desconto de um cupom num plano específico.
    Upsert pela chave (cupom_id, plano_id)."""
    body = {'cupom_id': int(cupom_id), 'plano_id': int(plano_id),
            'percent': float(percent)}
    rows = await _upsert(session, 'cupom_planos', body,
                         on_conflict='cupom_id,plano_id')
    return rows[0] if rows else None


async def listar_cupom_planos(session, cupom_id):
    """Lista as %s por plano de um cupom. Retorna lista de
    {plano_id, percent}."""
    return await _get(session, 'cupom_planos', {
        'cupom_id': f'eq.{int(cupom_id)}', 'order': 'criado_em.asc'})


async def del_cupom_plano(session, cupom_id, plano_id):
    """Remove a % daquele plano (o cupom deixa de valer pra esse plano)."""
    await _delete(session, 'cupom_planos', {
        'cupom_id': f'eq.{int(cupom_id)}', 'plano_id': f'eq.{int(plano_id)}'})


async def get_percent_cupom_plano(session, cupom_id, plano_id):
    """Retorna a % (float) que o cupom dá nesse plano, ou None se não houver."""
    rows = await _get(session, 'cupom_planos', {
        'cupom_id': f'eq.{int(cupom_id)}', 'plano_id': f'eq.{int(plano_id)}',
        'limit': '1'})
    if not rows:
        return None
    try:
        return float(rows[0]['percent'])
    except (KeyError, TypeError, ValueError):
        return None


def aplicar_desconto_percent(valor, percent):
    """Aplica uma % de desconto direta. Retorna (valor_final, desconto).
    Nunca deixa abaixo de R$0,01."""
    try:
        valor = float(valor)
        percent = float(percent)
    except (TypeError, ValueError):
        return round(float(valor), 2), 0.0
    desconto = valor * (percent / 100.0)
    final = valor - desconto
    if final < 0.01:
        final = 0.01
    desconto = round(valor - final, 2)
    return round(final, 2), desconto


# ───────────────────────── ASSINATURAS (vencimento de plano) ─────────────────────────
async def registrar_assinatura(session, user_id, guild_id, cargo_id, nome_base, vence_em_iso):
    """Cria/atualiza a assinatura do cliente (1 por user+guild). Na renovação,
    sobrescreve o vence_em e o cargo. vence_em_iso = string ISO (timestamptz)."""
    body = {
        'user_id': str(user_id),
        'guild_id': str(guild_id),
        'cargo_id': str(cargo_id) if cargo_id else None,
        'nome_base': nome_base or None,
        'vence_em': vence_em_iso,
        'ativo': True,
        'atualizado_em': 'now()',
    }
    return await _upsert(session, 'assinaturas', body, 'user_id,guild_id')


async def listar_assinaturas_vencidas(session, agora_iso):
    """Devolve as assinaturas ativas cujo vence_em já passou (<= agora)."""
    params = {
        'ativo': 'eq.true',
        'vence_em': f'lte.{agora_iso}',
        'select': '*',
        'limit': '100',
    }
    return await _get(session, 'assinaturas', params)


async def listar_assinaturas_ativas(session):
    """Todas as assinaturas ativas (pra agendar o temporizador de cada uma no boot)."""
    return await _get(session, 'assinaturas',
                      {'ativo': 'eq.true', 'select': '*', 'limit': '1000'})


async def marcar_assinatura_expirada(session, user_id, guild_id):
    """Marca a assinatura como inativa (já foi processada a expiração)."""
    params = {'user_id': f'eq.{user_id}', 'guild_id': f'eq.{guild_id}'}
    return await _patch(session, 'assinaturas', params, {'ativo': False})
