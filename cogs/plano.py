# cogs/plano.py — Painel de divulgação dos planos de Mediação Automática
#
# /plano (admin) → posta painel Components V2 com:
#   • Banner (Media Gallery) no topo
#   • Texto de apresentação do produto
#   • Bullets com as features (confirmação automática, IA, sala automática, etc)
#   • Lista de bancos compatíveis
#   • Select Menu com os 3 planos (7 dias, 1 mês, 3 meses)
#
# Quando o admin escolhe um plano no select, abre um PREVIEW ephemeral com botões:
#   • Editar Nome / Editar Preço / Editar Descrição
#   • Enviar no Canal / Cancelar
#
# As edições ficam salvas em planos_config.json (por guild), então o admin
# pode reabrir /plano e os preços/textos customizados continuam lá.
#
# Usa os emojis do bot (utils.emojis.PE) — emojis customizados do servidor,
# não unicode.

import json
import os
import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.emojis import PE, e as _emoji_str

_log = logging.getLogger("salasff.plano")

# ══════════════════════════════════════════════════════════════
#  Constantes
# ══════════════════════════════════════════════════════════════

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Banner: tenta o custom primeiro, depois fallback
BANNER_PATH_CUSTOM = os.path.join(_BASE_DIR, "assets", "banner_mediacao.png")
BANNER_PATH        = os.path.join(_BASE_DIR, "imagem_2026-04-12_224806271.png")

CONFIG_PATH = os.path.join(_BASE_DIR, "planos_config.json")

# Flags Components V2
FLAG_COMPONENTS_V2 = 1 << 15   # 32768
FLAG_EPHEMERAL     = 1 << 6    # 64

# Cores
COR_PAINEL  = 0x00FF7F   # verde neon do banner
COR_AVISO   = 0xFFD700   # dourado (preview)
COR_ERRO    = 0xED4245   # vermelho


# ══════════════════════════════════════════════════════════════
#  Helper — emoji do bot no formato dict que Components V2 espera
# ══════════════════════════════════════════════════════════════

def _emj(key: str) -> dict:
    """Converte um emoji do PE (PartialEmoji) pro dict que a API V2 aceita."""
    em = PE[key]
    return {"id": str(em.id), "name": em.name, "animated": bool(em.animated)}


# ══════════════════════════════════════════════════════════════
#  Planos padrão (admin pode editar via UI)
# ══════════════════════════════════════════════════════════════

PLANOS_PADRAO = {
    "7d": {
        "nome":  "7 Dias",
        "preco": 20.00,
        "desc":  "Acesso completo por 1 semana. Ideal pra testar o sistema.",
        "emoji_key": "clockcheck",
    },
    "30d": {
        "nome":  "1 Mês",
        "preco": 65.00,
        "desc":  "30 dias de mediação automática. Mais popular.",
        "emoji_key": "verified",
    },
    "90d": {
        "nome":  "3 Meses",
        "preco": 120.00,
        "desc":  "90 dias com o melhor custo-benefício. Economia de R$ 75.",
        "emoji_key": "presente",
    },
}


# ══════════════════════════════════════════════════════════════
#  Persistência por guild
# ══════════════════════════════════════════════════════════════

def _carregar_cfg() -> dict:
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as ex:
        _log.warning(f"[cfg load] {ex}")
    return {}


def _salvar_cfg(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as ex:
        _log.warning(f"[cfg save] {ex}")


def get_planos_guild(guild_id: int | str) -> dict:
    """Retorna os planos da guild (mescla padrão + customizações salvas)."""
    cfg = _carregar_cfg()
    gdata = cfg.get(str(guild_id), {})
    out = {}
    for k, v in PLANOS_PADRAO.items():
        out[k] = {**v, **gdata.get(k, {})}
    return out


def salvar_plano_guild(guild_id: int | str, plano_id: str, dados: dict):
    cfg = _carregar_cfg()
    g = cfg.setdefault(str(guild_id), {})
    p = g.setdefault(plano_id, {})
    p.update(dados)
    _salvar_cfg(cfg)


# ══════════════════════════════════════════════════════════════
#  Texto do painel — todo com emojis do bot
# ══════════════════════════════════════════════════════════════

def _texto_apresentacao() -> str:
    return (
        f"## {_emoji_str('bot')}  Quer Mediar Automático Sem Se Preocupar Com Mais Nada?\n"
        f"Nem precisa olhar o banco {_emoji_str('vision')} — o bot faz tudo sozinho. "
        f"Você só recebe o lucro {_emoji_str('otherdollar')}"
    )


def _texto_features() -> str:
    seta = _emoji_str("seta")
    return (
        f"### {_emoji_str('swordbattle')}  O que o sistema faz por você\n"
        f"{_emoji_str('clockcheck')}  **Confirmação automática** {seta} cliente digita "
        f"`pg Nome` e o bot confirma sozinho\n"
        f"{_emoji_str('vision')}  **Leitura de comprovante por IA** {seta} manda print, "
        f"o bot extrai nome e valor\n"
        f"{_emoji_str('swordbattle')}  **Sala criada no automático** {seta} após os 2 "
        f"pagamentos, o bot cria a sala sozinho\n"
        f"{_emoji_str('megafone')}  **Mensagens automáticas configuráveis** {seta} você "
        f"define o texto, o bot responde"
    )


def _texto_bancos() -> str:
    return (
        f"### {_emoji_str('pix')}  Bancos compatíveis\n"
        f"Se seu banco manda email de transação de PIX recebido, dá pra usar:\n"
        f"{_emoji_str('verified')} **Nubank**  {_emoji_str('dot')}  **Inter**  "
        f"{_emoji_str('dot')}  **C6**  {_emoji_str('dot')}  **PicPay**\n"
        f"{_emoji_str('verified')} **Bradesco**  {_emoji_str('dot')}  **Itaú**  "
        f"{_emoji_str('dot')}  **Santander**  {_emoji_str('dot')}  **Outros via Gmail** "
        f"{_emoji_str('cloud')}"
    )


def _texto_planos(planos: dict) -> str:
    seta = _emoji_str("seta")
    linhas = [f"### {_emoji_str('carteira')}  Escolha seu plano abaixo"]
    for k in ("7d", "30d", "90d"):
        p = planos[k]
        emj = _emoji_str(p.get("emoji_key", "clockcheck"))
        linhas.append(
            f"{emj}  **{p['nome']}** {seta} R$ {p['preco']:.2f}  {seta}  *{p['desc']}*"
        )
    return "\n".join(linhas)


# ══════════════════════════════════════════════════════════════
#  Components V2 — payload builders
# ══════════════════════════════════════════════════════════════

def _build_painel_publico_payload(planos: dict) -> dict:
    """Painel público com banner + textos + select dos 3 planos."""
    select_options = []
    for k in ("7d", "30d", "90d"):
        p = planos[k]
        select_options.append({
            "label":       f"{p['nome']} — R$ {p['preco']:.2f}",
            "value":       k,
            "description": p["desc"][:100],
            "emoji":       _emj(p.get("emoji_key", "clockcheck")),
        })

    return {
        "flags": FLAG_COMPONENTS_V2,
        "components": [
            {
                "id": 1, "type": 17, "accent_color": COR_PAINEL,
                "components": [
                    # ── Banner (Media Gallery) ─────────────────────────────
                    {
                        "id": 2, "type": 12,
                        "items": [{
                            "media": {"url": "attachment://banner_mediacao.png"},
                            "description": "Mediação Automática — F Apps",
                        }],
                    },
                    # ── Apresentação ───────────────────────────────────────
                    {"id": 3, "type": 10, "content": _texto_apresentacao()},
                    {"id": 4, "type": 14, "divider": True, "spacing": 1},
                    # ── Features ───────────────────────────────────────────
                    {"id": 5, "type": 10, "content": _texto_features()},
                    {"id": 6, "type": 14, "divider": True, "spacing": 1},
                    # ── Bancos ─────────────────────────────────────────────
                    {"id": 7, "type": 10, "content": _texto_bancos()},
                    {"id": 8, "type": 14, "divider": True, "spacing": 1},
                    # ── Planos ─────────────────────────────────────────────
                    {"id": 9, "type": 10, "content": _texto_planos(planos)},
                    # ── Select dos planos ──────────────────────────────────
                    {
                        "id": 10, "type": 1,
                        "components": [{
                            "type": 3,
                            "custom_id": "plano:select",
                            "placeholder": "Escolher plano para configurar e enviar…",
                            "min_values": 1,
                            "max_values": 1,
                            "options": select_options,
                        }],
                    },
                ],
            },
        ],
    }


def _build_preview_payload(plano_id: str, plano: dict) -> dict:
    """Preview ephemeral do plano selecionado, com botões de editar/enviar."""
    emj_plano = _emoji_str(plano.get("emoji_key", "clockcheck"))
    return {
        "flags": FLAG_COMPONENTS_V2 | FLAG_EPHEMERAL,
        "components": [
            {
                "id": 1, "type": 17, "accent_color": COR_AVISO,
                "components": [
                    {"id": 2, "type": 10,
                     "content": (
                         f"## {_emoji_str('vision')}  Pré-visualização\n"
                         f"Revise o plano abaixo antes de postar publicamente."
                     )},
                    {"id": 3, "type": 14, "divider": True, "spacing": 1},
                    {"id": 4, "type": 10,
                     "content": (
                         f"### {emj_plano}  {plano['nome']}\n"
                         f"{_emoji_str('otherdollar')}  **Preço:** R$ {plano['preco']:.2f}\n"
                         f"{_emoji_str('channel')}  **Descrição:** {plano['desc']}"
                     )},
                    {"id": 5, "type": 14, "divider": True, "spacing": 1},
                    {"id": 6, "type": 10,
                     "content": f"{_emoji_str('reloading')}  Você pode editar qualquer campo antes de enviar."},
                    # Linha 1 — edição
                    {"id": 7, "type": 1, "components": [
                        {"type": 2, "style": 2, "label": "Editar Nome",
                         "custom_id": f"plano:edit_nome:{plano_id}",
                         "emoji": _emj("click")},
                        {"type": 2, "style": 2, "label": "Editar Preço",
                         "custom_id": f"plano:edit_preco:{plano_id}",
                         "emoji": _emj("otherdollar")},
                        {"type": 2, "style": 2, "label": "Editar Descrição",
                         "custom_id": f"plano:edit_desc:{plano_id}",
                         "emoji": _emj("channel")},
                    ]},
                    # Linha 2 — ações finais
                    {"id": 8, "type": 1, "components": [
                        {"type": 2, "style": 3, "label": "Enviar no Canal",
                         "custom_id": f"plano:enviar:{plano_id}",
                         "emoji": _emj("megafone")},
                        {"type": 2, "style": 4, "label": "Cancelar",
                         "custom_id": "plano:cancelar",
                         "emoji": _emj("othertrash")},
                    ]},
                ],
            },
        ],
    }


def _build_compra_publica_payload(plano_id: str, plano: dict) -> dict:
    """Mensagem pública final com botão de comprar."""
    emj_plano = _emoji_str(plano.get("emoji_key", "clockcheck"))
    return {
        "flags": FLAG_COMPONENTS_V2,
        "components": [
            {
                "id": 1, "type": 17, "accent_color": COR_PAINEL,
                "components": [
                    {"id": 2, "type": 10,
                     "content": f"## {emj_plano}  {plano['nome']} — Mediação Automática"},
                    {"id": 3, "type": 10,
                     "content": (
                         f"{_emoji_str('otherdollar')}  **Investimento:** R$ {plano['preco']:.2f}\n"
                         f"{_emoji_str('channel')}  {plano['desc']}\n\n"
                         f"Clique em **Comprar** abaixo {_emoji_str('seta')} abrir um ticket e finalizar o pagamento."
                     )},
                    {"id": 4, "type": 14, "divider": True, "spacing": 1},
                    {"id": 5, "type": 1, "components": [
                        {"type": 2, "style": 3,
                         "label": f"Comprar — R$ {plano['preco']:.2f}",
                         "custom_id": f"plano:comprar:{plano_id}",
                         "emoji": _emj("carteira")},
                    ]},
                ],
            },
        ],
    }


# ══════════════════════════════════════════════════════════════
#  HTTP — envio dos payloads V2
# ══════════════════════════════════════════════════════════════

async def _callback_v2(inter: discord.Interaction, payload: dict) -> bool:
    """Faz a callback inicial da interação (type 4) com payload V2 raw."""
    url = f"https://discord.com/api/v10/interactions/{inter.id}/{inter.token}/callback"
    body = {"type": 4, "data": payload}
    headers = {"Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, headers=headers, json=body) as r:
                if r.status not in (200, 201, 204):
                    _log.warning(f"[callback v2] {r.status} {(await r.text())[:400]}")
                    return False
                return True
    except Exception as ex:
        _log.error(f"[callback v2] {ex}")
        return False


async def _post_v2_channel(channel_id: int, payload: dict,
                           banner_bytes: bytes | None = None) -> bool:
    """Posta payload V2 num canal público via REST."""
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {config.DISCORD_TOKEN}"}

    try:
        async with aiohttp.ClientSession() as s:
            if banner_bytes:
                form = aiohttp.FormData()
                form.add_field("payload_json", json.dumps(payload),
                               content_type="application/json")
                form.add_field("files[0]", banner_bytes,
                               filename="banner_mediacao.png",
                               content_type="image/png")
                async with s.post(url, headers=headers, data=form) as r:
                    if r.status not in (200, 201):
                        _log.warning(f"[v2 channel w/file] {r.status} {(await r.text())[:400]}")
                        return False
                    return True
            else:
                headers["Content-Type"] = "application/json"
                async with s.post(url, headers=headers, json=payload) as r:
                    if r.status not in (200, 201):
                        _log.warning(f"[v2 channel] {r.status} {(await r.text())[:400]}")
                        return False
                    return True
    except Exception as ex:
        _log.error(f"[v2 channel] {ex}")
        return False


async def _edit_v2_response(interaction: discord.Interaction, payload: dict) -> bool:
    """Edita a mensagem original da interação (usado pra atualizar o preview)."""
    url = (f"https://discord.com/api/v10/webhooks/"
           f"{interaction.application_id}/{interaction.token}/messages/@original")
    headers = {
        "Authorization": f"Bot {config.DISCORD_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {k: v for k, v in payload.items() if k != "flags"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.patch(url, headers=headers, json=body) as r:
                if r.status not in (200, 201):
                    _log.warning(f"[v2 edit] {r.status} {(await r.text())[:400]}")
                    return False
                return True
    except Exception as ex:
        _log.error(f"[v2 edit] {ex}")
        return False


def _ler_banner_bytes() -> bytes | None:
    """Lê o banner do disco. Tenta o custom primeiro, depois o fallback."""
    for path in (BANNER_PATH_CUSTOM, BANNER_PATH):
        try:
            if os.path.exists(path):
                with open(path, "rb") as f:
                    return f.read()
        except Exception as ex:
            _log.warning(f"[banner] erro lendo {path}: {ex}")
    return None


# ══════════════════════════════════════════════════════════════
#  Modais de edição
# ══════════════════════════════════════════════════════════════

class _EditNomeModal(discord.ui.Modal, title="Editar Nome do Plano"):
    def __init__(self, plano_id: str, valor_atual: str):
        super().__init__()
        self.plano_id = plano_id
        self.campo = discord.ui.TextInput(
            label="Novo nome do plano",
            placeholder="Ex: 1 Mês PRO",
            default=valor_atual,
            min_length=2, max_length=40,
        )
        self.add_item(self.campo)

    async def on_submit(self, inter: discord.Interaction):
        novo = self.campo.value.strip()
        salvar_plano_guild(inter.guild_id, self.plano_id, {"nome": novo})
        planos = get_planos_guild(inter.guild_id)
        novo_payload = _build_preview_payload(self.plano_id, planos[self.plano_id])
        try:
            # DEFERRED_UPDATE_MESSAGE (type 6) — não responde nada, edita a original
            url = f"https://discord.com/api/v10/interactions/{inter.id}/{inter.token}/callback"
            async with aiohttp.ClientSession() as s:
                await s.post(url, json={"type": 6})
            await _edit_v2_response(inter, novo_payload)
        except Exception as ex:
            _log.warning(f"[modal nome] {ex}")


class _EditPrecoModal(discord.ui.Modal, title="Editar Preço"):
    def __init__(self, plano_id: str, valor_atual: float):
        super().__init__()
        self.plano_id = plano_id
        self.campo = discord.ui.TextInput(
            label="Novo preço (ex: 65 ou 65,00 ou 65.00)",
            placeholder="Apenas números — vírgula ou ponto",
            default=f"{valor_atual:.2f}",
            min_length=1, max_length=10,
        )
        self.add_item(self.campo)

    async def on_submit(self, inter: discord.Interaction):
        bruto = self.campo.value.strip().replace(",", ".").replace("R$", "").strip()
        try:
            novo = float(bruto)
            if novo <= 0 or novo > 100000:
                raise ValueError("fora do intervalo")
        except Exception:
            await inter.response.send_message(
                content=f"{_emoji_str('off')}  Preço inválido. Use só números (ex: `65` ou `65,90`).",
                ephemeral=True,
            )
            return
        salvar_plano_guild(inter.guild_id, self.plano_id, {"preco": novo})
        planos = get_planos_guild(inter.guild_id)
        novo_payload = _build_preview_payload(self.plano_id, planos[self.plano_id])
        try:
            url = f"https://discord.com/api/v10/interactions/{inter.id}/{inter.token}/callback"
            async with aiohttp.ClientSession() as s:
                await s.post(url, json={"type": 6})
            await _edit_v2_response(inter, novo_payload)
        except Exception as ex:
            _log.warning(f"[modal preco] {ex}")


class _EditDescModal(discord.ui.Modal, title="Editar Descrição"):
    def __init__(self, plano_id: str, valor_atual: str):
        super().__init__()
        self.plano_id = plano_id
        self.campo = discord.ui.TextInput(
            label="Nova descrição",
            placeholder="O que o cliente recebe nesse plano?",
            default=valor_atual,
            style=discord.TextStyle.paragraph,
            min_length=5, max_length=300,
        )
        self.add_item(self.campo)

    async def on_submit(self, inter: discord.Interaction):
        nova = self.campo.value.strip()
        salvar_plano_guild(inter.guild_id, self.plano_id, {"desc": nova})
        planos = get_planos_guild(inter.guild_id)
        novo_payload = _build_preview_payload(self.plano_id, planos[self.plano_id])
        try:
            url = f"https://discord.com/api/v10/interactions/{inter.id}/{inter.token}/callback"
            async with aiohttp.ClientSession() as s:
                await s.post(url, json={"type": 6})
            await _edit_v2_response(inter, novo_payload)
        except Exception as ex:
            _log.warning(f"[modal desc] {ex}")


# ══════════════════════════════════════════════════════════════
#  Cog principal
# ══════════════════════════════════════════════════════════════

class PlanoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /plano (admin) ──────────────────────────────────────
    @app_commands.command(
        name="plano",
        description="[ADMIN] Posta o painel de planos de Mediação Automática.",
    )
    @app_commands.guilds(*[discord.Object(id=gid) for gid in config.OWNER_GUILD_IDS])
    async def plano(self, inter: discord.Interaction):
        if config.ADMIN_IDS and inter.user.id not in config.ADMIN_IDS:
            await inter.response.send_message(
                content=f"{_emoji_str('off')}  Apenas administradores podem usar este comando.",
                ephemeral=True,
            )
            return

        await inter.response.defer(ephemeral=True, thinking=True)

        planos = get_planos_guild(inter.guild_id)
        banner = _ler_banner_bytes()
        payload = _build_painel_publico_payload(planos)

        ok = await _post_v2_channel(inter.channel_id, payload, banner_bytes=banner)

        if ok:
            await inter.followup.send(
                content=f"{_emoji_str('on')}  Painel postado neste canal.",
                ephemeral=True,
            )
        else:
            # Fallback — sem banner
            ok2 = await _post_v2_channel(inter.channel_id, payload, banner_bytes=None)
            if ok2:
                await inter.followup.send(
                    content=(
                        f"{_emoji_str('awaiting')}  Painel postado, mas sem o banner.\n"
                        f"Coloque a imagem em `assets/banner_mediacao.png`."
                    ),
                    ephemeral=True,
                )
            else:
                await inter.followup.send(
                    content=f"{_emoji_str('off')}  Falha ao postar o painel. Verifique permissões do bot no canal.",
                    ephemeral=True,
                )

    # ══════════════════════════════════════════════════════════
    #  Listener — interações do /plano
    # ══════════════════════════════════════════════════════════
    @commands.Cog.listener()
    async def on_interaction(self, inter: discord.Interaction):
        if inter.type != discord.InteractionType.component:
            return
        cid = (inter.data or {}).get("custom_id", "")
        if not cid.startswith("plano:"):
            return

        # Botão "comprar" é público; o resto só admin
        eh_comprar = cid.startswith("plano:comprar:")
        if not eh_comprar:
            if config.ADMIN_IDS and inter.user.id not in config.ADMIN_IDS:
                try:
                    await inter.response.send_message(
                        content=f"{_emoji_str('off')}  Apenas administradores operam este painel.",
                        ephemeral=True,
                    )
                except Exception:
                    pass
                return

        try:
            # ── Select de plano ────────────────────────────────
            if cid == "plano:select":
                values = (inter.data or {}).get("values", [])
                if not values:
                    return
                plano_id = values[0]
                planos = get_planos_guild(inter.guild_id)
                if plano_id not in planos:
                    await inter.response.send_message(
                        content=f"{_emoji_str('off')}  Plano inválido.", ephemeral=True)
                    return
                payload = _build_preview_payload(plano_id, planos[plano_id])
                await _callback_v2(inter, payload)
                return

            # ── Botões de edição (abrem modal) ─────────────────
            if cid.startswith("plano:edit_nome:"):
                plano_id = cid.split(":")[-1]
                planos = get_planos_guild(inter.guild_id)
                if plano_id not in planos:
                    return
                await inter.response.send_modal(
                    _EditNomeModal(plano_id, planos[plano_id]["nome"]))
                return

            if cid.startswith("plano:edit_preco:"):
                plano_id = cid.split(":")[-1]
                planos = get_planos_guild(inter.guild_id)
                if plano_id not in planos:
                    return
                await inter.response.send_modal(
                    _EditPrecoModal(plano_id, planos[plano_id]["preco"]))
                return

            if cid.startswith("plano:edit_desc:"):
                plano_id = cid.split(":")[-1]
                planos = get_planos_guild(inter.guild_id)
                if plano_id not in planos:
                    return
                await inter.response.send_modal(
                    _EditDescModal(plano_id, planos[plano_id]["desc"]))
                return

            # ── Enviar pra todo mundo ──────────────────────────
            if cid.startswith("plano:enviar:"):
                plano_id = cid.split(":")[-1]
                planos = get_planos_guild(inter.guild_id)
                if plano_id not in planos:
                    return

                await inter.response.defer(ephemeral=True, thinking=True)

                payload = _build_compra_publica_payload(plano_id, planos[plano_id])
                ok = await _post_v2_channel(inter.channel_id, payload)

                if ok:
                    try:
                        await _edit_v2_response(inter, {
                            "components": [{
                                "id": 1, "type": 17, "accent_color": COR_PAINEL,
                                "components": [{
                                    "id": 2, "type": 10,
                                    "content": (
                                        f"{_emoji_str('on')}  **Plano {planos[plano_id]['nome']} "
                                        f"postado no canal!**"
                                    ),
                                }],
                            }],
                        })
                    except Exception:
                        pass
                    await inter.followup.send(
                        content=f"{_emoji_str('on')}  Plano **{planos[plano_id]['nome']}** postado no canal.",
                        ephemeral=True,
                    )
                else:
                    await inter.followup.send(
                        content=f"{_emoji_str('off')}  Falha ao postar no canal.",
                        ephemeral=True,
                    )
                return

            # ── Cancelar preview ───────────────────────────────
            if cid == "plano:cancelar":
                try:
                    # DEFERRED_UPDATE_MESSAGE
                    url = f"https://discord.com/api/v10/interactions/{inter.id}/{inter.token}/callback"
                    async with aiohttp.ClientSession() as s:
                        await s.post(url, json={"type": 6})
                    await _edit_v2_response(inter, {
                        "components": [{
                            "id": 1, "type": 17, "accent_color": COR_ERRO,
                            "components": [{"id": 2, "type": 10,
                                            "content": f"{_emoji_str('off')}  Cancelado."}],
                        }],
                    })
                except Exception:
                    pass
                return

            # ── Cliente clicou em "Comprar" no painel público ──
            if eh_comprar:
                plano_id = cid.split(":")[-1]
                planos = get_planos_guild(inter.guild_id)
                p = planos.get(plano_id, {})
                emj_plano = _emoji_str(p.get("emoji_key", "clockcheck"))
                await inter.response.send_message(
                    content=(
                        f"## {emj_plano}  Compra do plano {p.get('nome', plano_id)}\n"
                        f"{_emoji_str('otherdollar')}  Valor: **R$ {p.get('preco', 0):.2f}**\n\n"
                        f"{_emoji_str('seta')}  Abra um ticket de suporte para finalizar a compra."
                    ),
                    ephemeral=True,
                )
                return

        except Exception as ex:
            _log.error(f"[interaction {cid}] {ex}")
            try:
                if not inter.response.is_done():
                    await inter.response.send_message(
                        content=f"{_emoji_str('off')}  Erro: {ex}", ephemeral=True)
                else:
                    await inter.followup.send(
                        content=f"{_emoji_str('off')}  Erro: {ex}", ephemeral=True)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════
#  Setup
# ══════════════════════════════════════════════════════════════

async def setup(bot: commands.Bot):
    await bot.add_cog(PlanoCog(bot))
