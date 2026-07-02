"""
Integração de pagamento — MisticaPay (API v1).

Auth: headers ci (Client ID) + cs (Client Secret).
Criar PIX:  POST /api/transactions/create
Verificar:  POST /api/transactions/check  (rate limit 60/min por IP)

Variáveis de ambiente:
  MISTICAPAY_CI  = seu client id
  MISTICAPAY_CS  = seu client secret
"""
import os
import random
import aiohttp

MISTICAPAY_BASE = 'https://api.misticpay.com/api'
MISTICAPAY_CI   = os.environ.get('MISTICAPAY_CI', '')
MISTICAPAY_CS   = os.environ.get('MISTICAPAY_CS', '')

_CONFIGURADO = bool(MISTICAPAY_CI and MISTICAPAY_CS)

_NOMES = ['Joao Silva', 'Maria Souza', 'Pedro Santos', 'Ana Oliveira',
          'Lucas Lima', 'Carla Costa', 'Bruno Alves', 'Julia Rocha',
          'Rafael Dias', 'Beatriz Melo', 'Gabriel Nunes', 'Larissa Ramos']


def _cpf_aleatorio():
    """Gera um CPF aleatório matematicamente válido."""
    n = [random.randint(0, 9) for _ in range(9)]
    for _ in range(2):
        s = sum((len(n) + 1 - i) * v for i, v in enumerate(n))
        d = (s * 10) % 11
        n.append(0 if d == 10 else d)
    return ''.join(map(str, n))


def _nome_aleatorio():
    return random.choice(_NOMES)


def _headers():
    return {
        'ci': MISTICAPAY_CI,
        'cs': MISTICAPAY_CS,
        'Content-Type': 'application/json',
    }


async def criar_cobranca_pix(session, valor, descricao, venda_id,
                             payer_nome=None, payer_doc=None):
    """Cria a cobrança PIX na MisticaPay.
    Retorna {ok, txid, pix_copia_cola, qr_base64} ou {ok:False, erro}."""
    if not _CONFIGURADO:
        return {'ok': False, 'erro': 'MisticaPay não configurado (MISTICAPAY_CI/CS)'}
    if not payer_nome:
        payer_nome = _nome_aleatorio()
    if not payer_doc:
        payer_doc = _cpf_aleatorio()
    body = {
        'amount':          round(float(valor), 2),
        'payerName':       payer_nome[:80],
        'payerDocument':   ''.join(filter(str.isdigit, str(payer_doc))),
        'transactionId':   str(venda_id),
        'description':     descricao[:140],
    }
    try:
        async with session.post(f'{MISTICAPAY_BASE}/transactions/create',
                                headers=_headers(), json=body) as r:
            d = await r.json()
            if r.status not in (200, 201):
                return {'ok': False, 'erro': d.get('message', f'HTTP {r.status}')}
            data = d.get('data', {})
            return {
                'ok':           True,
                'txid':         str(data.get('transactionId', '')),
                'pix_copia_cola': data.get('copyPaste', ''),
                'qr_base64':    data.get('qrCodeBase64', ''),
            }
    except Exception as e:
        return {'ok': False, 'erro': str(e)[:140]}


async def checar_pago(session, txid):
    """Consulta o status da transação. Retorna True se COMPLETO."""
    if not _CONFIGURADO or not txid:
        return False
    try:
        async with session.post(f'{MISTICAPAY_BASE}/transactions/check',
                                headers=_headers(),
                                json={'transactionId': str(txid)}) as r:
            if r.status != 200:
                return False
            d = await r.json()
            estado = (d.get('transaction', {}) or {}).get('transactionState', '')
            return estado == 'COMPLETO'
    except Exception:
        return False


async def consultar_saldo(session):
    """Consulta o saldo disponível na conta MisticPay principal (do adm).
    Retorna {ok, saldo} ou {ok:False, erro}."""
    if not _CONFIGURADO:
        return {'ok': False, 'erro': 'MisticaPay não configurado'}
    try:
        async with session.get(f'{MISTICAPAY_BASE}/users/balance',
                               headers=_headers()) as r:
            d = await r.json()
            if r.status != 200:
                return {'ok': False, 'erro': d.get('message', f'HTTP {r.status}')}
            return {'ok': True, 'saldo': float(d.get('data', {}).get('balance', 0))}
    except Exception as e:
        return {'ok': False, 'erro': str(e)[:140]}


async def solicitar_saque_pix(session, valor, pix_key, pix_key_type, descricao):
    """Solicita saque PIX na MisticPay principal (debita do saldo do adm).
    pix_key_type: CPF | CNPJ | EMAIL | TELEFONE | CHAVE_ALEATORIA.
    Retorna {ok, txid, status} ou {ok:False, erro}."""
    if not _CONFIGURADO:
        return {'ok': False, 'erro': 'MisticaPay não configurado (MISTICAPAY_CI/CS)'}
    body = {
        'amount':      round(float(valor), 2),
        'pixKey':      str(pix_key).strip(),
        'pixKeyType':  str(pix_key_type).strip().upper(),
        'description': str(descricao)[:140],
    }
    try:
        async with session.post(f'{MISTICAPAY_BASE}/transactions/withdraw',
                                headers=_headers(), json=body) as r:
            d = await r.json()
            if r.status not in (200, 201):
                return {'ok': False, 'erro': d.get('message', f'HTTP {r.status}')}
            data = d.get('data', {}) or {}
            return {
                'ok':     True,
                'txid':   str(data.get('transactionId', '')),
                'status': data.get('status', 'QUEUED'),
            }
    except Exception as e:
        return {'ok': False, 'erro': str(e)[:140]}
