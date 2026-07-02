"""
Baixa os emojis antigos do CDN do Discord e salva na pasta emojis/.
Roda UMA vez. Depois pode apagar este arquivo.

Uso:
    python baixar_emojis.py
"""
import os
import urllib.request

PASTA = 'emojis'

# chave usada no bot  ->  (id do emoji antigo, animado?)
EMOJIS = {
    'seta':     (1443461499803664406, True),   # animado (.gif)
    'legenda1': (1491303291361951875, False),
    'legenda2': (1491303018509897869, False),
    'ticket':   (1499866324908769311, False),
    'key':      (1472143445203095577, False),
    'foguete':  (1388278180552376431, False),
    'cloud':    (1388596579786821642, False),
    'gear':     (1388278462342762587, False),
    'box':      (1389017197728235531, False),
    'clock':    (1388599128413573212, False),
}

os.makedirs(PASTA, exist_ok=True)

ok, falhou = 0, 0
for chave, (emoji_id, animado) in EMOJIS.items():
    ext = 'gif' if animado else 'png'
    url = f'https://cdn.discordapp.com/emojis/{emoji_id}.{ext}'
    destino = os.path.join(PASTA, f'{chave}.{ext}')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as r:
            dados = r.read()
        with open(destino, 'wb') as f:
            f.write(dados)
        print(f'  ok   {chave:10s} -> {destino}  ({len(dados)} bytes)')
        ok += 1
    except Exception as erro:
        print(f'  ERRO {chave:10s} -> {erro}')
        falhou += 1

print()
print(f'Concluido: {ok} baixado(s), {falhou} falha(s).')
if falhou:
    print('Emojis que falharam: provavelmente foram apagados do servidor de origem.')
    print('Coloque um arquivo manualmente em emojis/<nome>.png para esses.')
else:
    print('Agora e so rodar o bot (run.sh / run.bat) que ele sobe tudo sozinho.')
