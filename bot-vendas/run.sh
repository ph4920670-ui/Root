#!/usr/bin/env bash
# ============================================================
#  Bot de Vendas — instala tudo e roda. (Linux / Mac)
#  Uso:  bash run.sh
# ============================================================
set -e
cd "$(dirname "$0")"

echo "=================================================="
echo "  Bot de Vendas - inicializando"
echo "=================================================="

# 1) Acha o python
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "[ERRO] Python nao encontrado. Instale o Python 3.10+ e tente de novo."
    exit 1
fi
echo "[1/4] Python: $($PY --version)"

# 2) Cria a venv (ambiente isolado) se ainda nao existe
if [ ! -d ".venv" ]; then
    echo "[2/4] Criando ambiente virtual (.venv)..."
    $PY -m venv .venv
else
    echo "[2/4] Ambiente virtual ja existe."
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 3) Instala / atualiza as dependencias
echo "[3/4] Instalando dependencias..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "      ok."

# 4) Roda o bot
if [ ! -f ".env" ]; then
    echo "[ERRO] Arquivo .env nao encontrado. Coloque o .env na mesma pasta."
    exit 1
fi
echo "[4/4] Iniciando o bot...  (Ctrl+C para parar)"
echo "=================================================="
$PY main.py
