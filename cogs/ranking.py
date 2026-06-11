# cogs/ranking.py — Sistema de Ranking Semanal (Top Criadores de Sala)
#
# Fluxo:
#   • Toda segunda-feira 00:00 BRT → distribui prêmios ao top 5 e anuncia no canal
#   • /painelglobal → "🏆 Postar Ranking"  posta painel público com botão Atualizar
#   • /painelglobal → "📊 Ver Ranking"     mostra top 10 ephemeral para o admin
#   • /botconfig    → "🏆 Ranking Semanal" configura canal de anúncio / ativa-desativa

import asyncio
import logging
import aiohttp
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

import config
from utils.emojis import ON, OFF, DOT, INFO, TOP, GIFT, STATS, PE, CART, PRESENTE, e as _em_str

_log = logging.getLogger("salasff.ranking")
_BR  = ZoneInfo("America/Sao_Paulo")

# ── Constantes ──────────────────────────────────────────────────────────────

PREMIOS  = [500, 400, 300, 200, 100]
MEDALHAS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
NUMEROS  = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

# ── Helpers internos ─────────────────────────────────────────────────────────

def _emb(titulo="", cor=0x5865F2, desc=""):
    return discord.Embed(title=titulo, color=cor, description=desc)

def _ok(t, d=""):   return _emb(f"✅  {t}", config.COR_SUCESSO, d)
def _err(t, d=""):  return _emb(f"❌  {t}", config.COR_ERRO, d)
def _info(t, d=""): return _emb(f"{INFO}  {t}", config.COR_INFO, d)

def _is_admin(uid: int) -> bool:
    return not config.ADMIN_IDS or uid in config.ADMIN_IDS

def _inicio_semana() -> datetime:
    agora = datetime.now(_BR)
    seg   = agora - timedelta(days=agora.weekday())   # weekday: Mon=0
    return seg.replace(hour=0, minute=0, second=0, microsecond=0)

def _fim_semana() -> datetime:
    return _inicio_semana() + timedelta(days=7)

def _semana_str(inicio: datetime) -> str:
    fim = inicio + timedelta(days=6)
    return f"{inicio.strftime('%d/%m')} – {fim.strftime('%d/%m/%Y')}"

# ── Embeds ────────────────────────────────────────────────────────────────────

def _build_ranking_embed(top10: list) -> discord.Embed:
    inicio = _inicio_semana()
    prox   = _fim_semana().strftime("%d/%m às 00:00")

    em = discord.Embed(
        title="🏆  Ranking Semanal — Top Criadores de Sala",
        color=0xFFD700,
    )

    cabecalho = (
        f"**Semana: {_semana_str(inicio)}**\n"
        f"Quem criar mais salas essa semana entra no top!\n"
        f"**Top 5 recebe prêmios toda segunda-feira.**\n\n"
    )

    if not top10:
        em.description = cabecalho + "*Nenhuma sala criada esta semana ainda. Seja o primeiro!*"
    else:
        linhas = []
        for idx, u in enumerate(top10):
            medal  = MEDALHAS[idx] if idx < 5 else NUMEROS[idx]
            nome   = (u.get("user_nome") or "Desconhecido")[:24]
            total  = u.get("total", 0)
            premio = f"  ╸ **+{PREMIOS[idx]} salas**" if idx < 5 else ""
            s      = "s" if total != 1 else ""
            linhas.append(f"{medal} **{nome}** — {total} sala{s}{premio}")
        em.description = cabecalho + "\n".join(linhas)

    prizes = "\n".join(
        f"{MEDALHAS[i]} **{i+1}° lugar** → +{PREMIOS[i]} salas"
        for i in range(5)
    )
    em.add_field(name=f"{GIFT}  Prêmios (toda segunda-feira)", value=prizes, inline=False)
    em.set_footer(text=f"Próximo reset: {prox}  •  Contagem desde segunda 00:00 BRT")
    return em


def _build_ranking_v2_payload(top10: list = None) -> dict:
    """Painel público inicial em Components V2 — só cabeçalho + botões.
    O parâmetro top10 é mantido por compatibilidade mas ignorado (tabela só aparece no ephemeral)."""
    inicio = _inicio_semana()

    components = [{
        "id": 1,
        "type": 17,  # Container
        "accent_color": 0xFFD700,
        "components": [
            # Cabeçalho
            {
                "id": 2, "type": 10,
                "content": f"## {_em_str('top')}  Ranking Semanal — Top Criadores de Sala",
            },
            {
                "id": 3, "type": 10,
                "content": (
                    f"{_em_str('calendario')}  **Semana:** {_semana_str(inicio)}\n"
                    f"-# Quem criar mais salas essa semana entra no top — **Top 5** recebe prêmios toda segunda-feira.\n"
                    f"-# Clique em **Ranking** para ver a tabela completa, ou **Meu Perfil** para ver sua posição."
                ),
            },
            # Botões (Action Row)
            {
                "id": 4, "type": 1,  # Action Row
                "components": [
                    {
                        "type": 2,  # Button
                        "style": 1,  # Primary (azul)
                        "label": "Ranking",
                        "emoji": _emj("top"),
                        "custom_id": "ranking:atualizar",
                    },
                    {
                        "type": 2,
                        "style": 2,  # Secondary
                        "label": "Meu Perfil",
                        "emoji": _emj("info"),
                        "custom_id": "ranking:perfil",
                    },
                ],
            },
        ],
    }]

    # flag 32768 = IS_COMPONENTS_V2 (público — sem flag 64)
    return {"flags": 32768, "components": components}


def _build_ranking_tabela_v2_payload(top10: list) -> dict:
    """Container V2 ephemeral com a tabela completa do top 10 + prêmios + rodapé.
    Mostrado quando alguém clica em 'Ranking'."""
    inicio = _inicio_semana()
    prox   = _fim_semana().strftime("%d/%m às 00:00")

    # Emojis de posição (todos do bot)
    POS_EMOJIS = [
        _em_str("verified"),    # 1º — animado dourado
        _em_str("top"),         # 2º
        _em_str("swordbattle"), # 3º
    ]

    # Linhas do top
    if not top10:
        linhas_top = (
            f"{_em_str('off')}  *Nenhuma sala criada esta semana ainda.*\n"
            f"-# Seja o primeiro a entrar no ranking!"
        )
    else:
        linhas = []
        for idx, u in enumerate(top10):
            nome  = (u.get("user_nome") or "Desconhecido")[:24]
            total = u.get("total", 0)
            s = "s" if total != 1 else ""
            if idx < 3:
                badge = POS_EMOJIS[idx]
            else:
                badge = _em_str("dot")
            pos_label = f"**{idx+1}º**"

            if idx < 5:
                premio_txt = f" ╸ **+{PREMIOS[idx]} salas**"
            else:
                premio_txt = ""

            linhas.append(
                f"{badge} {pos_label} **{nome}** ╸ {total} sala{s}{premio_txt}"
            )
        linhas_top = "\n".join(linhas)

    # Bloco de prêmios
    medal_emojis = [
        _em_str("verified"),
        _em_str("top"),
        _em_str("swordbattle"),
        _em_str("dot"),
        _em_str("dot"),
    ]
    prizes_lines = []
    for i in range(5):
        prizes_lines.append(
            f"{medal_emojis[i]} **{i+1}º lugar** ╸ +{PREMIOS[i]} salas"
        )
    prizes_txt = "\n".join(prizes_lines)

    components = [{
        "id": 1,
        "type": 17,
        "accent_color": 0xFFD700,
        "components": [
            {
                "id": 2, "type": 10,
                "content": f"## {_em_str('top')}  Ranking Semanal — Top 10",
            },
            {
                "id": 3, "type": 10,
                "content": f"{_em_str('calendario')}  **Semana:** {_semana_str(inicio)}",
            },
            {"id": 4, "type": 14, "divider": True, "spacing": 2},
            {
                "id": 5, "type": 10,
                "content": linhas_top,
            },
            {"id": 6, "type": 14, "divider": True, "spacing": 2},
            {
                "id": 7, "type": 10,
                "content": f"### {_em_str('presente')}  Prêmios — toda segunda-feira\n{prizes_txt}",
            },
            {"id": 8, "type": 14, "divider": True, "spacing": 1},
            {
                "id": 9, "type": 10,
                "content": (
                    f"-# {_em_str('clockcheck')} Próximo reset: **{prox}**  •  "
                    f"Contagem desde segunda 00:00 BRT"
                ),
            },
        ],
    }]

    # flag 64 (ephemeral) | 32768 (Components V2)
    return {"flags": 64 | 32768, "components": components}


def _build_vencedores_embed(top5: list, semana_str: str) -> discord.Embed:
    em = discord.Embed(
        title="🏆  Ranking Semanal — Vencedores!",
        color=0xFFD700,
        description=(
            f"**Semana: {semana_str}**\n"
            "Parabéns aos criadores mais ativos! "
            "Os prêmios foram adicionados ao saldo de cada um. 🎉\n\n"
        ),
    )
    if not top5:
        em.description += "*Nenhum participante esta semana.*"
    else:
        linhas = []
        for idx, u in enumerate(top5):
            medal  = MEDALHAS[idx]
            uid    = u.get("user_id", "?")
            nome   = (u.get("user_nome") or "Desconhecido")[:24]
            total  = u.get("total", 0)
            s      = "s" if total != 1 else ""
            premio = PREMIOS[idx]
            linhas.append(
                f"{medal} <@{uid}> **{nome}**\n"
                f"  └ {total} sala{s} criada{s} → **+{premio} salas ganhas**"
            )
        em.description += "\n\n".join(linhas)
    em.set_footer(text="Nova semana começou! Corra para o top 🚀")
    return em


def _build_config_embed() -> discord.Embed:
    from utils.database import ranking_canal_anuncio_get, ranking_ativo_get
    canal_id = ranking_canal_anuncio_get()
    ativo    = ranking_ativo_get()
    canal_txt = f"<#{canal_id}>" if canal_id else f"{OFF} *Não definido*"
    status    = f"{ON} **Ativo**" if ativo else f"{OFF} **Desativado**"
    prox      = _fim_semana().strftime("%d/%m às 00:00")
    prizes    = "\n".join(f"{MEDALHAS[i]} {i+1}° lugar → +{PREMIOS[i]} salas" for i in range(5))

    em = discord.Embed(title=f"{TOP}  Ranking Semanal — Configuração", color=0xFFD700)
    em.description = (
        f"{DOT} **Status:** {status}\n"
        f"{DOT} **Canal de anúncio:** {canal_txt}\n"
        f"{DOT} **Reset automático:** toda segunda-feira 00:00 BRT\n"
        f"{DOT} **Próximo reset:** {prox}\n\n"
        f"**Prêmios (fixos):**\n{prizes}"
    )
    em.set_footer(text="Prêmios são adicionados ao saldo (salas) de cada vencedor automaticamente.")
    return em


# ── Views ─────────────────────────────────────────────────────────────────────

class RankingPublicoView(discord.ui.View):
    """View persistente postada no canal — 2 botões: Ranking (atualiza) e Meu Perfil (ephemeral V2)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Ranking",
        emoji=PE["top"],
        style=discord.ButtonStyle.primary,
        custom_id="ranking:atualizar",
    )
    async def btn_ranking(self, inter: discord.Interaction, btn: discord.ui.Button):
        """Mostra a tabela completa do top 10 num container V2 ephemeral."""
        try:
            from utils.database import top_criadores_semana
            top10 = await asyncio.to_thread(top_criadores_semana, 10)
            payload = _build_ranking_tabela_v2_payload(top10)
            await _respond_v2_initial(inter.id, inter.token, payload)
        except Exception as ex:
            _log.warning(f"[ranking:atualizar] {ex}")
            try:
                if not inter.response.is_done():
                    await inter.response.send_message(
                        embed=_err("Erro ao carregar ranking.", f"`{ex}`"),
                        ephemeral=True,
                    )
            except Exception:
                pass

    @discord.ui.button(
        label="Meu Perfil",
        emoji=PE["info"],
        style=discord.ButtonStyle.secondary,
        custom_id="ranking:perfil",
    )
    async def btn_perfil(self, inter: discord.Interaction, btn: discord.ui.Button):
        """Mostra posição no ranking + salas criadas na semana + saldo (ephemeral V2)."""
        try:
            from utils.database import top_criadores_semana, saldo_total_usuario
            uid = str(inter.user.id)

            # Pega ranking completo (sem limite) pra calcular posição
            todos = await asyncio.to_thread(top_criadores_semana, 0)
            saldo = await asyncio.to_thread(saldo_total_usuario, uid)

            posicao = None
            salas_semana = 0
            for idx, u in enumerate(todos, start=1):
                if str(u.get("user_id")) == uid:
                    posicao = idx
                    salas_semana = u.get("total", 0)
                    break

            payload = _build_perfil_v2_payload(
                inter.user, posicao, salas_semana, saldo, len(todos)
            )
            await _respond_v2_initial(inter.id, inter.token, payload)
        except Exception as ex:
            _log.warning(f"[ranking:perfil] {ex}")
            try:
                if not inter.response.is_done():
                    await inter.response.send_message(
                        embed=_err("Erro ao carregar perfil.", f"`{ex}`"),
                        ephemeral=True,
                    )
            except Exception:
                pass


# ── Helpers Components V2 ────────────────────────────────────────────────────

async def _respond_v2_initial(inter_id: int, inter_token: str, payload: dict) -> bool:
    """POST resposta inicial V2 ephemeral.
    Não usa defer antes (defer cria mensagem legacy e dá erro com flags V2)."""
    url = f"https://discord.com/api/v10/interactions/{inter_id}/{inter_token}/callback"
    body = {"type": 4, "data": payload}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=body, timeout=aiohttp.ClientTimeout(total=10)) as r:
                ok = r.status in (200, 204)
                if not ok:
                    _log.warning(f"[ranking v2 respond] {r.status} {(await r.text())[:200]}")
                return ok
    except Exception as ex:
        _log.error(f"[ranking v2 respond] {ex}")
        return False


async def _respond_v2_update(inter_id: int, inter_token: str, payload: dict) -> bool:
    """POST UPDATE_MESSAGE (type 7) — edita a mensagem da interaction com payload V2."""
    url = f"https://discord.com/api/v10/interactions/{inter_id}/{inter_token}/callback"
    body = {"type": 7, "data": payload}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=body, timeout=aiohttp.ClientTimeout(total=10)) as r:
                ok = r.status in (200, 204)
                if not ok:
                    _log.warning(f"[ranking v2 update] {r.status} {(await r.text())[:200]}")
                return ok
    except Exception as ex:
        _log.error(f"[ranking v2 update] {ex}")
        return False


def _emj(key: str):
    """Converte emoji do bot pro formato dict do Components V2."""
    em = PE.get(key)
    if not em:
        return None
    return {"id": str(em.id), "name": em.name, "animated": em.animated}


def _build_perfil_v2_payload(user, posicao, salas_semana, saldo, total_participantes) -> dict:
    """Container V2 do perfil pessoal de ranking."""
    nome = user.display_name

    # Linha de posição (só emojis do bot)
    if posicao is None:
        pos_txt = (
            f"{_em_str('off')} **Você ainda não criou salas esta semana**\n"
            f"-# Crie sua primeira sala pra entrar no ranking!"
        )
    else:
        if posicao == 1:
            medalha = _em_str("verified")
        elif posicao == 2:
            medalha = _em_str("top")
        elif posicao == 3:
            medalha = _em_str("swordbattle")
        else:
            medalha = _em_str("dot")
        s = "s" if salas_semana != 1 else ""
        pos_txt = (
            f"{medalha} **{posicao}º lugar** de 3k participantes\n"
            f"-# Você criou **{salas_semana} sala{s}** esta semana"
        )

    # Próximo reset
    prox = _fim_semana().strftime("%d/%m às 00:00")

    components = [{
        "id": 1,
        "type": 17,
        "accent_color": 0xFFD700,
        "components": [
            {
                "id": 2, "type": 10,
                "content": f"## {_em_str('top')}  Perfil de {nome}",
            },
            {"id": 3, "type": 14, "divider": True, "spacing": 1},
            {
                "id": 4, "type": 10,
                "content": pos_txt,
            },
            {"id": 5, "type": 14, "divider": True, "spacing": 1},
            {
                "id": 6, "type": 10,
                "content": (
                    f"{_em_str('carteira')}  **Saldo Atual**\n"
                    f"-# Você possui **{saldo} sala(s)** disponíveis"
                ),
            },
            {"id": 7, "type": 14, "divider": True, "spacing": 1},
            {
                "id": 8, "type": 10,
                "content": (
                    f"{_em_str('gift')}  **Próximo Reset**\n"
                    f"-# Toda segunda-feira às 00:00 BRT — próximo: **{prox}**"
                ),
            },
        ],
    }]

    # Flag 64 (ephemeral) | 32768 (Components V2)
    return {"flags": 64 | 32768, "components": components}


class RankingConfigView(discord.ui.View):
    """Sub-painel de configuração (aberto via /botconfig → Ranking Semanal)."""

    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Ativar / Desativar", emoji="🔁", style=discord.ButtonStyle.success, row=0)
    async def btn_toggle(self, inter: discord.Interaction, btn: discord.ui.Button):
        try:
            from utils.database import ranking_ativo_get, ranking_ativo_set
            novo = not await asyncio.to_thread(ranking_ativo_get)
            await asyncio.to_thread(ranking_ativo_set, novo)
            st = "ativado ✅" if novo else "desativado ❌"
            em_cfg = await asyncio.to_thread(_build_config_embed)
            await inter.response.edit_message(embed=em_cfg, view=self)
            await inter.followup.send(embed=_ok(f"Ranking semanal {st}!"), ephemeral=True)
        except Exception as ex:
            _log.error(f"[ranking:toggle] {ex}")
            try:
                await inter.response.send_message(embed=_err("Erro.", f"`{ex}`"), ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(label="Canal de Anúncio", emoji="📢", style=discord.ButtonStyle.primary, row=0)
    async def btn_canal(self, inter: discord.Interaction, btn: discord.ui.Button):
        try:
            em = _info(
                "Canal de Anúncio do Ranking",
                "Selecione o canal onde o bot vai anunciar os vencedores toda segunda-feira.",
            )
            await inter.response.send_message(embed=em, view=_RankingCanalSelectView(), ephemeral=True)
        except Exception as ex:
            _log.error(f"[ranking:canal] {ex}")

    @discord.ui.button(label="Ver Top 5 Atual", emoji="📊", style=discord.ButtonStyle.secondary, row=0)
    async def btn_top5(self, inter: discord.Interaction, btn: discord.ui.Button):
        try:
            await inter.response.defer(ephemeral=True)
            from utils.database import top_criadores_semana
            top5 = await asyncio.to_thread(top_criadores_semana, 5)
            em   = _build_ranking_embed(top5)
            em.title  = "📊  Top 5 Atual (Prévia Admin)"
            em.color  = config.COR_INFO
            await inter.followup.send(embed=em, ephemeral=True)
        except Exception as ex:
            _log.error(f"[ranking:top5] {ex}")
            try:
                await inter.followup.send(embed=_err("Erro.", f"`{ex}`"), ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(label="⚡ Forçar Reset Agora", style=discord.ButtonStyle.danger, row=1)
    async def btn_reset(self, inter: discord.Interaction, btn: discord.ui.Button):
        try:
            await inter.response.defer(ephemeral=True)
            from utils.database import (
                top_criadores_semana, distribuir_premios_ranking,
                ranking_canal_anuncio_get, ranking_ultimo_reset_set,
            )
            top5 = await asyncio.to_thread(top_criadores_semana, 5)
            if not top5:
                return await inter.followup.send(
                    embed=_err("Nenhum participante esta semana."), ephemeral=True
                )

            resultados = await asyncio.to_thread(distribuir_premios_ranking, top5)

            canal_id = await asyncio.to_thread(ranking_canal_anuncio_get)
            if canal_id:
                canal = inter.client.get_channel(int(canal_id))
                if canal:
                    inicio = _inicio_semana()
                    await canal.send(embed=_build_vencedores_embed(top5, _semana_str(inicio)))

            await asyncio.to_thread(ranking_ultimo_reset_set, datetime.now(_BR).isoformat())

            linhas = [
                f"{MEDALHAS[i]} **{nome}** → +{premio} salas"
                for i, (uid, nome, premio) in enumerate(resultados)
            ]
            await inter.followup.send(
                embed=_ok(f"Reset executado! {len(resultados)} premiado(s).", "\n".join(linhas)),
                ephemeral=True,
            )
        except Exception as ex:
            _log.error(f"[ranking:reset] {ex}")
            try:
                await inter.followup.send(embed=_err("Erro ao executar reset.", f"`{ex}`"), ephemeral=True)
            except Exception:
                pass


class _RankingCanalSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Selecione o canal de anúncio…",
        channel_types=[discord.ChannelType.text],
        row=0,
    )
    async def sel_canal(self, inter: discord.Interaction, sel: discord.ui.ChannelSelect):
        try:
            canal = sel.values[0]
            from utils.database import ranking_canal_anuncio_set
            await asyncio.to_thread(ranking_canal_anuncio_set, canal.id)
            await inter.response.send_message(
                embed=_ok(f"Canal de anúncio definido: {canal.mention}"), ephemeral=True
            )
        except Exception as ex:
            await inter.response.send_message(embed=_err("Erro.", f"`{ex}`"), ephemeral=True)

    @discord.ui.button(label="Limpar", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def btn_limpar(self, inter: discord.Interaction, btn: discord.ui.Button):
        try:
            from utils.database import ranking_canal_anuncio_set
            await asyncio.to_thread(ranking_canal_anuncio_set, None)
            await inter.response.send_message(embed=_ok("Canal de anúncio removido."), ephemeral=True)
        except Exception as ex:
            await inter.response.send_message(embed=_err("Erro.", f"`{ex}`"), ephemeral=True)


# ── Funções públicas (chamadas de cogs/main.py e cogs/botconfig.py) ──────────

async def postar_ranking_canal(inter: discord.Interaction):
    """Posta o painel de ranking público (Components V2) no canal atual."""
    try:
        if not _is_admin(inter.user.id):
            return await inter.response.send_message(embed=_err("Sem permissão."), ephemeral=True)
        await inter.response.defer(ephemeral=True)
        from utils.database import top_criadores_semana
        top10 = await asyncio.to_thread(top_criadores_semana, 10)
        payload = _build_ranking_v2_payload(top10)

        # Posta via HTTP raw porque discord.py não suporta a flag V2 em channel.send
        token = config.DISCORD_TOKEN
        url = f"https://discord.com/api/v10/channels/{inter.channel.id}/messages"
        headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status not in (200, 201):
                    body = (await r.text())[:300]
                    _log.error(f"[postar_ranking_canal] {r.status} {body}")
                    return await inter.followup.send(
                        embed=_err("Erro ao postar ranking.", f"HTTP {r.status}: `{body[:200]}`"),
                        ephemeral=True,
                    )

        await inter.followup.send(embed=_ok("Painel de ranking postado no canal!"), ephemeral=True)
    except Exception as ex:
        _log.error(f"[postar_ranking_canal] {ex}")
        try:
            await inter.followup.send(embed=_err("Erro ao postar ranking.", f"`{ex}`"), ephemeral=True)
        except Exception:
            try:
                await inter.response.send_message(embed=_err("Erro ao postar ranking.", f"`{ex}`"), ephemeral=True)
            except Exception:
                pass


async def ver_ranking_ephemeral(inter: discord.Interaction):
    """Mostra o top 10 atual só para o admin (ephemeral)."""
    try:
        if not _is_admin(inter.user.id):
            return await inter.response.send_message(embed=_err("Sem permissão."), ephemeral=True)
        await inter.response.defer(ephemeral=True)
        from utils.database import top_criadores_semana
        top10 = await asyncio.to_thread(top_criadores_semana, 10)
        em    = _build_ranking_embed(top10)
        em.title = "📊  Top 10 Atual (Prévia Admin)"
        em.color = config.COR_INFO
        await inter.followup.send(embed=em, ephemeral=True)
    except Exception as ex:
        _log.error(f"[ver_ranking_ephemeral] {ex}")
        try:
            await inter.followup.send(embed=_err("Erro ao buscar ranking.", f"`{ex}`"), ephemeral=True)
        except Exception:
            try:
                await inter.response.send_message(embed=_err("Erro.", f"`{ex}`"), ephemeral=True)
            except Exception:
                pass


async def abrir_config_ranking(inter: discord.Interaction):
    """Abre painel de configuração do ranking (chamado do /botconfig)."""
    try:
        if not _is_admin(inter.user.id):
            return await inter.response.send_message(embed=_err("Sem permissão."), ephemeral=True)
        await inter.response.defer(ephemeral=True)
        em = await asyncio.to_thread(_build_config_embed)
        await inter.followup.send(embed=em, view=RankingConfigView(), ephemeral=True)
    except Exception as ex:
        _log.error(f"[abrir_config_ranking] {ex}")
        try:
            await inter.followup.send(embed=_err("Erro ao abrir config.", f"`{ex}`"), ephemeral=True)
        except Exception:
            try:
                await inter.response.send_message(embed=_err("Erro.", f"`{ex}`"), ephemeral=True)
            except Exception:
                pass


# ── Cog principal ─────────────────────────────────────────────────────────────

class RankingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._check_task.start()

    def cog_unload(self):
        self._check_task.cancel()

    @tasks.loop(hours=1)
    async def _check_task(self):
        """Verifica toda hora se é segunda 00:xx BRT para fazer o reset."""
        await self.bot.wait_until_ready()
        try:
            from utils.database import ranking_ativo_get, ranking_ultimo_reset_get, ranking_ultimo_reset_set

            if not await asyncio.to_thread(ranking_ativo_get):
                return

            agora = datetime.now(_BR)
            if agora.weekday() != 0 or agora.hour > 1:   # só segunda, primeiras 2h
                return

            inicio_semana = _inicio_semana().isoformat()
            ultimo = await asyncio.to_thread(ranking_ultimo_reset_get)
            if ultimo and ultimo >= inicio_semana:
                return   # já resetou essa semana

            _log.info("[ranking] Iniciando reset semanal automático…")
            await self._executar_reset()
            await asyncio.to_thread(ranking_ultimo_reset_set, datetime.now(_BR).isoformat())

        except Exception as ex:
            _log.error(f"[ranking._check_task] {ex}")

    @_check_task.before_loop
    async def _before_check(self):
        await self.bot.wait_until_ready()

    async def _executar_reset(self):
        try:
            from utils.database import (
                top_criadores_semana, distribuir_premios_ranking, ranking_canal_anuncio_get,
            )
            top5 = await asyncio.to_thread(top_criadores_semana, 5)
            if not top5:
                _log.info("[ranking] Reset: nenhum participante.")
                return

            resultados = await asyncio.to_thread(distribuir_premios_ranking, top5)
            _log.info(f"[ranking] Prêmios: {resultados}")

            canal_id = await asyncio.to_thread(ranking_canal_anuncio_get)
            if not canal_id:
                _log.warning("[ranking] Canal de anúncio não configurado.")
                return

            canal = self.bot.get_channel(int(canal_id))
            if not canal:
                _log.warning(f"[ranking] Canal {canal_id} não encontrado.")
                return

            inicio_ant = _inicio_semana() - timedelta(days=7)
            em = _build_vencedores_embed(top5, _semana_str(inicio_ant))
            await canal.send(embed=em)
            _log.info(f"[ranking] Anúncio enviado em #{canal.name}")

        except Exception as ex:
            _log.error(f"[ranking._executar_reset] {ex}")


async def setup(bot: commands.Bot):
    await bot.add_cog(RankingCog(bot))
