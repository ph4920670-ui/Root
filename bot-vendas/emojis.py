"""
Gerenciador de Application Emojis.

Sobe as imagens da pasta emojis/ como Application Emojis DA APLICACAO do bot.
Funcionam em QUALQUER servidor onde o bot esteja.

Arquivos em emojis/:
    settings.png  cart.png  people.png  trash.png  cloud.png  seta.png  check.png
"""
import os

PASTA_EMOJIS = 'emojis'
EXTENSOES = ('.png', '.gif', '.jpg', '.jpeg', '.webp')

# Os icones reais -> emoji unicode de fallback.
ICONES = {
    'settings': '\u2699\uFE0F',
    'cart':     '\U0001F6D2',
    'carrinho': '\U0001F6D2',   # 🛒 — fallback caso o custom não suba
    'people':   '\U0001F465',
    'trash':    '\U0001F5D1\uFE0F',
    'cloud':    '\u2601\uFE0F',
    'seta':     '\U0001F504',
    'check':    '\u2705',
    'certo':    '\u2705',   # ✅ — fallback caso o custom não suba
    'xist':     '\u274C',   # ❌ — fallback caso o custom não suba
}

# Apelidos: chaves antigas do main.py -> os 7 icones.
APELIDOS = {
    'foguete':  'cart',
    'ticket':   'people',
    'clock':    'check',
    'key':      'cart',
    'box':      'trash',
    'cloud':    'cloud',
    'gear':     'settings',
    'legenda1': 'settings',
    'legenda2': 'settings',
}

FALLBACK = dict(ICONES)
for _antiga, _nova in APELIDOS.items():
    FALLBACK[_antiga] = ICONES[_nova]


def _formatar(emoji):
    return f'<a:{emoji.name}:{emoji.id}>' if emoji.animated else f'<:{emoji.name}:{emoji.id}>'


def _arquivos_locais():
    achados = {}
    if not os.path.isdir(PASTA_EMOJIS):
        return achados
    for arq in os.listdir(PASTA_EMOJIS):
        nome, ext = os.path.splitext(arq)
        if ext.lower() in EXTENSOES:
            achados[nome.lower()] = os.path.join(PASTA_EMOJIS, arq)
    return achados


async def carregar(client, forcar=False):
    """
    Sincroniza os Application Emojis da aplicacao do bot e devolve o dict E.

    forcar=False (padrao): se o emoji ja existe na aplicacao, reaproveita.
    forcar=True: APAGA o emoji antigo e sobe a imagem nova da pasta emojis/.
                 Use quando o emoji antigo esta errado (ex: fundo preto).

    Ordem por chave:
      - (forcar) existe + tem arquivo -> apaga o antigo, sobe o novo
      - existe -> usa o existente
      - tem arquivo -> sobe e usa
      - senao -> fallback unicode
    """
    E = dict(FALLBACK)
    try:
        existentes = {e.name.lower(): e for e in await client.fetch_application_emojis()}
    except Exception as erro:
        print(f'[EMOJIS] nao consegui listar Application Emojis: {erro}', flush=True)
        return E

    arquivos = _arquivos_locais()

    for chave in ICONES:
        ja_existe = existentes.get(chave)
        caminho = arquivos.get(chave)

        # modo forcar: apaga o antigo se houver imagem nova pra subir
        if forcar and ja_existe and caminho:
            try:
                await ja_existe.delete()
                print(f'[EMOJIS] apagado (antigo): {chave}', flush=True)
                ja_existe = None
            except Exception as erro:
                print(f'[EMOJIS] falha ao apagar {chave}: {erro}', flush=True)

        if ja_existe:
            E[chave] = _formatar(ja_existe)
            print(f'[EMOJIS] ja existia: {chave}', flush=True)
            continue

        if caminho:
            try:
                with open(caminho, 'rb') as f:
                    dados = f.read()
                novo = await client.create_application_emoji(name=chave, image=dados)
                E[chave] = _formatar(novo)
                print(f'[EMOJIS] subido: {chave}', flush=True)
                continue
            except Exception as erro:
                print(f'[EMOJIS] falha ao subir {chave}: {erro}', flush=True)

        print(f'[EMOJIS] fallback unicode para "{chave}"', flush=True)

    for antiga, nova in APELIDOS.items():
        E[antiga] = E[nova]

    return E
