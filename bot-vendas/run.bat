@echo off
REM ============================================================
REM   Bot de Vendas - instala tudo e roda. (Windows)
REM   Uso: clique duas vezes no run.bat  OU  digite  run.bat
REM ============================================================
cd /d "%~dp0"

echo ==================================================
echo   Bot de Vendas - inicializando
echo ==================================================

REM 1) Acha o python
where python >nul 2>nul
if %errorlevel%==0 (
    set PY=python
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set PY=py
    ) else (
        echo [ERRO] Python nao encontrado. Instale o Python 3.10+ e tente de novo.
        pause
        exit /b 1
    )
)
echo [1/4] Python encontrado.
%PY% --version

REM 2) Cria a venv se ainda nao existe
if not exist ".venv" (
    echo [2/4] Criando ambiente virtual ^(.venv^)...
    %PY% -m venv .venv
) else (
    echo [2/4] Ambiente virtual ja existe.
)
call .venv\Scripts\activate.bat

REM 3) Instala / atualiza as dependencias
echo [3/4] Instalando dependencias...
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
echo       ok.

REM 4) Roda o bot
if not exist ".env" (
    echo [ERRO] Arquivo .env nao encontrado. Coloque o .env na mesma pasta.
    pause
    exit /b 1
)
echo [4/4] Iniciando o bot...  ^(Ctrl+C para parar^)
echo ==================================================
python main.py

pause
