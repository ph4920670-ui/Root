"""
Bot de vendas — Discord oficial, tudo em Componentes V2 (LayoutView/Container).

Comandos:
  /produtos      → adicionar/listar/remover produto (nome + preço)
  /estoque       → escolher produto e colar estoque (1 item por linha)
  /configplano   → adicionar/editar/remover plano (nome + preço + dias)
  /planos        → mostra os planos pro cliente comprar
  /painelcompras → painel de vendas V2 com menu dos produtos
  /botconfig     → cargo de cada plano + cargo de cliente
  /configwallet  → (só dono) liberar IDs + % de comissão por venda
  /wallet        → (IDs liberados) saldo, sacar via PIX e lucro

Pagamento: MisticPay (encaixado em pagamento.py — preencher com a API real).
Banco: Supabase (ver db.py + schema.sql).
"""
import os
import re
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
load_dotenv()  # lê o .env automaticamente
import discord
from discord import app_commands

import aiohttp
import db
import pagamento  # MisticPay (placeholder até ter a API)
import emojis as emojis_mod  # Application Emojis (funcionam em qualquer servidor)


# Tasks de auto-fechar thread / monitor pagamento por thread.id
# (cancelados quando o usuário confirma/cancela manualmente)
_THREAD_TASKS: dict[int, asyncio.Task] = {}

# Compra ativa por usuário: user_id -> thread.id
# Garante que cada usuário só pode ter 1 carrinho aberto por vez.
_COMPRAS_ATIVAS: dict[int, int] = {}


def _agendar_task(thread_id: int, coro):
    """Agenda uma task pra uma thread. Cancela a anterior se existir."""
    antiga = _THREAD_TASKS.pop(thread_id, None)
    if antiga and not antiga.done():
        antiga.cancel()
    _THREAD_TASKS[thread_id] = asyncio.create_task(coro)


def _cancelar_task(thread_id: int):
    t = _THREAD_TASKS.pop(thread_id, None)
    if t and not t.done():
        t.cancel()


def _liberar_compra(thread_id: int):
    """Remove a thread do registro de compras ativas (libera o user pra abrir outra)."""
    for uid, tid in list(_COMPRAS_ATIVAS.items()):
        if tid == thread_id:
            _COMPRAS_ATIVAS.pop(uid, None)
            return

TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '')

# ───────── Ponte com o configadm (fila de salas criadas) ─────────
# O bot-org puxa as salas criadas pelos selfbots a cada poucos segundos e
# posta no canal_logs_salas de cada guild (configurado via /botconfig).
# Mesma auth dos selfbots: header X-Bot-Secret.
CONFIGURADOR_URL = (os.environ.get('CONFIGURADOR_URL', '') or '').rstrip('/')
BOT_FETCH_SECRET = (os.environ.get('BOT_FETCH_SECRET', 'secret-bot-fetch-2026') or '').strip()
# URL do PAINEL DO CLIENTE (site onde o cliente loga com o ID e configura tudo
# + compra salas). Mostrado no .perfil no lugar das configs. Ajustável por env.
PAINEL_CLIENTE_URL = (os.environ.get('PAINEL_CLIENTE_URL', 'https://painel-clientej.discloud.app') or '').rstrip('/')
POLL_SALAS_INTERVALO = int(os.environ.get('POLL_SALAS_INTERVALO', '10') or '10')  # segundos

# ───────── EMOJIS ─────────
# Começa com fallback unicode (nada de texto cru). No on_ready o bot sobe
# as imagens da pasta emojis/ como Application Emojis da sua aplicação.
E = dict(emojis_mod.FALLBACK)

# Cor padrão dos containers
COR = discord.Color.from_str('#5865F2')


def _emoji_para_select(valor):
    """Converte um emoji do dict E (que pode ser unicode '🛒' ou custom no
    formato '<:cart:123>') num valor aceito por SelectOption.emoji. Custom vira
    PartialEmoji; unicode passa direto; se vier vazio/inválido, retorna None."""
    if not valor:
        return None
    try:
        if isinstance(valor, str) and valor.startswith('<') and ':' in valor:
            return discord.PartialEmoji.from_str(valor)
        return valor  # unicode
    except Exception:
        return None


# ── Sistema de sugestões ──
# Os emojis customizados (certo / xist) são subidos como Application Emojis
# no startup pelo emojis.py. Aqui só pegamos via E[...] que tem fallback
# unicode automático se o upload falhar. Esses 2 valores são preenchidos
# em runtime no on_ready (logo abaixo da carga dos emojis).
EMOJI_VOTO_SIM = '✅'  # placeholder — substituído no on_ready
EMOJI_VOTO_NAO = '❌'  # placeholder — substituído no on_ready

# Regex pra detectar links (http(s)://, www., discord.gg, ou domain.tld/path)
LINK_RE = re.compile(
    r'(https?://\S+|www\.\S+|discord\.gg/\S+|[a-z0-9\-]+\.[a-z]{2,}(?:/\S*)?)',
    re.IGNORECASE)


class VendasBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True          # pra dar cargo
        intents.message_content = True  # pra ler sugestões
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.http_session = None

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession()
        await self.tree.sync()
        print('[BOT] comandos sincronizados.', flush=True)

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        await super().close()


bot = VendasBot()


# Handler global: qualquer erro num /comando cai aqui. Loga o traceback real
# no console (pra diagnóstico) e avisa o usuário em vez de deixar o Discord
# mostrar só "o aplicativo não respondeu".
@bot.tree.error
async def _on_app_command_error(inter: discord.Interaction, error: Exception):
    import traceback as _tb
    cmd = inter.command.name if inter.command else '?'
    print(f'[ERRO-COMANDO] /{cmd}: {type(error).__name__}: {error}', flush=True)
    _tb.print_exception(type(error), error, error.__traceback__)
    aviso = f'⚠️ Ocorreu um erro ao executar **/{cmd}**. Tente de novo em instantes.'
    try:
        if inter.response.is_done():
            await inter.followup.send(aviso, ephemeral=True)
        else:
            await inter.response.send_message(aviso, ephemeral=True)
    except Exception:
        pass


# IDs de admin (sempre têm acesso aos comandos admin, mesmo sem permissão no servidor)
ADMIN_IDS = {1268379167519408139}


def _admin(inter: discord.Interaction) -> bool:
    """True se o usuário pode usar comandos admin.

    inter.user só tem guild_permissions quando é um Member (comando usado
    DENTRO de um servidor onde o bot está). Em DM — ou com o app instalado
    no perfil do usuário e usado num servidor sem o bot — vem como User,
    e aí acessar guild_permissions estoura AttributeError. Nesses casos
    tenta resolver o Member pela guild; se não der, nega o acesso.
    """
    if inter.user.id in ADMIN_IDS:
        return True
    if isinstance(inter.user, discord.Member):
        return inter.user.guild_permissions.administrator
    if inter.guild is not None:
        member = inter.guild.get_member(inter.user.id)
        if member is not None:
            return member.guild_permissions.administrator
    return False


# ════════════════════════════════════════════════════════════
#  /produtos  — adicionar / listar / remover
# ════════════════════════════════════════════════════════════
class ProdutoModal(discord.ui.Modal, title='Adicionar produto'):
    nome = discord.ui.TextInput(label='Nome do produto', max_length=100)
    preco = discord.ui.TextInput(label='Preço (ex: 9.90)', max_length=12)

    async def on_submit(self, inter: discord.Interaction):
        try:
            preco = float(str(self.preco.value).replace(',', '.'))
        except ValueError:
            await inter.response.send_message('Preço inválido.', ephemeral=True)
            return
        await db.add_produto(bot.http_session, str(self.nome.value), preco)
        await inter.response.send_message(
            f'{E["box"]} Produto **{self.nome.value}** adicionado por R$ {preco:.2f}.',
            ephemeral=True)


class ProdutosView(discord.ui.LayoutView):
    """Painel admin de produtos (V2)."""
    def __init__(self, produtos):
        super().__init__(timeout=300)
        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(f'## {E["box"]} Gerenciar Produtos'))
        c.add_item(discord.ui.Separator())
        if produtos:
            linhas = '\n'.join(f'{E["seta"]} **{p["nome"]}** — R$ {float(p["preco"]):.2f}'
                               for p in produtos)
            c.add_item(discord.ui.TextDisplay(linhas))
        else:
            c.add_item(discord.ui.TextDisplay('_Nenhum produto cadastrado ainda._'))
        c.add_item(discord.ui.Separator())
        row1 = discord.ui.ActionRow()
        row1.add_item(BtnAddProduto())
        c.add_item(row1)
        if produtos:
            row2 = discord.ui.ActionRow()
            row2.add_item(SelRemoverProduto(produtos))
            c.add_item(row2)
        self.add_item(c)


class BtnAddProduto(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Adicionar produto', style=discord.ButtonStyle.success, emoji='➕')

    async def callback(self, inter: discord.Interaction):
        await inter.response.send_modal(ProdutoModal())


class SelRemoverProduto(discord.ui.Select):
    def __init__(self, produtos):
        opts = [discord.SelectOption(label=p['nome'], value=str(p['id']),
                                     description=f'R$ {float(p["preco"]):.2f}')
                for p in produtos[:25]]
        super().__init__(placeholder='Remover um produto…', options=opts)

    async def callback(self, inter: discord.Interaction):
        await db.del_produto(bot.http_session, self.values[0])
        await inter.response.send_message('Produto removido.', ephemeral=True)


@bot.tree.command(name='produtos', description='Gerenciar produtos (admin)')
async def produtos(inter: discord.Interaction):
    if not _admin(inter):
        await inter.response.send_message('Só admin.', ephemeral=True)
        return
    lista = await db.listar_produtos(bot.http_session)
    await inter.response.send_message(view=ProdutosView(lista), ephemeral=True)


# ════════════════════════════════════════════════════════════
#  /estoque  — escolhe produto e cola o estoque (1 por linha)
# ════════════════════════════════════════════════════════════
class EstoqueModal(discord.ui.Modal, title='Adicionar estoque'):
    def __init__(self, produto_id, produto_nome):
        super().__init__()
        self.produto_id = produto_id
        self.conteudo = discord.ui.TextInput(
            label=f'Estoque de {produto_nome[:30]}',
            style=discord.TextStyle.paragraph,
            placeholder='Um item por linha…\nlogin1:senha1\nlogin2:senha2',
            max_length=4000)
        self.add_item(self.conteudo)

    async def on_submit(self, inter: discord.Interaction):
        linhas = [l.strip() for l in str(self.conteudo.value).splitlines() if l.strip()]
        n = await db.add_estoque(bot.http_session, self.produto_id, linhas)
        await inter.response.send_message(
            f'{E["key"]} {n} item(ns) adicionado(s) ao estoque.', ephemeral=True)


class EstoqueView(discord.ui.LayoutView):
    def __init__(self, produtos):
        super().__init__(timeout=300)
        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(f'## {E["key"]} Adicionar Estoque'))
        c.add_item(discord.ui.TextDisplay('Escolha o produto e cole o estoque (1 item por linha).'))
        c.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        row.add_item(SelProdutoEstoque(produtos))
        c.add_item(row)
        self.add_item(c)


class SelProdutoEstoque(discord.ui.Select):
    def __init__(self, produtos):
        opts = [discord.SelectOption(label=p['nome'], value=f'{p["id"]}|{p["nome"]}')
                for p in produtos[:25]]
        super().__init__(placeholder='Escolha o produto…', options=opts)

    async def callback(self, inter: discord.Interaction):
        pid, pnome = self.values[0].split('|', 1)
        await inter.response.send_modal(EstoqueModal(pid, pnome))


@bot.tree.command(name='estoque', description='Adicionar estoque a um produto (admin)')
async def estoque(inter: discord.Interaction):
    if not _admin(inter):
        await inter.response.send_message('Só admin.', ephemeral=True)
        return
    lista = await db.listar_produtos(bot.http_session)
    if not lista:
        await inter.response.send_message('Cadastre um produto primeiro com /produtos.', ephemeral=True)
        return
    await inter.response.send_message(view=EstoqueView(lista), ephemeral=True)


# ════════════════════════════════════════════════════════════
#  /configplano  — adicionar / editar plano
# ════════════════════════════════════════════════════════════
class PlanoModal(discord.ui.Modal, title='Adicionar plano'):
    nome = discord.ui.TextInput(label='Nome (ex: 15 dias)', max_length=50)
    dias = discord.ui.TextInput(label='Duração em dias', max_length=5)
    preco = discord.ui.TextInput(label='Preço (ex: 30.00)', max_length=12)

    async def on_submit(self, inter: discord.Interaction):
        try:
            dias = int(str(self.dias.value))
            preco = float(str(self.preco.value).replace(',', '.'))
        except ValueError:
            await inter.response.send_message('Dias ou preço inválido.', ephemeral=True)
            return
        await db.add_plano(bot.http_session, str(self.nome.value), dias, preco)
        await inter.response.send_message(
            f'{E["foguete"]} Plano **{self.nome.value}** ({dias}d) por R$ {preco:.2f} criado.',
            ephemeral=True)


class ConfigPlanoView(discord.ui.LayoutView):
    def __init__(self, planos):
        super().__init__(timeout=300)
        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(f'## {E["foguete"]} Configurar Planos'))
        c.add_item(discord.ui.Separator())
        if planos:
            linhas = '\n'.join(
                f'{E["seta"]} **{p["nome"]}** — {p["dias"]}d — '
                f'R$ {float(p["preco"]):.2f}'
                + (f' → <@&{p["cargo_id"]}>' if p.get('cargo_id') else '')
                for p in planos)
            c.add_item(discord.ui.TextDisplay(linhas))
        else:
            c.add_item(discord.ui.TextDisplay('_Nenhum plano._'))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.TextDisplay(
            f'_Cargo automático por plano: configure em **/botconfig**._'))
        c.add_item(discord.ui.Separator())
        row1 = discord.ui.ActionRow()
        row1.add_item(BtnAddPlano())
        c.add_item(row1)
        if planos:
            row2 = discord.ui.ActionRow()
            row2.add_item(SelRemoverPlano(planos))
            c.add_item(row2)
        self.add_item(c)


class BtnAddPlano(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Adicionar plano', style=discord.ButtonStyle.success, emoji='➕')

    async def callback(self, inter: discord.Interaction):
        await inter.response.send_modal(PlanoModal())


class SelRemoverPlano(discord.ui.Select):
    def __init__(self, planos):
        opts = [discord.SelectOption(label=p['nome'], value=str(p['id']),
                                     description=f'{p["dias"]}d — R$ {float(p["preco"]):.2f}')
                for p in planos[:25]]
        super().__init__(placeholder='Remover um plano…', options=opts)

    async def callback(self, inter: discord.Interaction):
        await db.del_plano(bot.http_session, self.values[0])
        await inter.response.send_message('Plano removido.', ephemeral=True)


@bot.tree.command(name='configplano', description='Adicionar/editar planos (admin)')
async def configplano(inter: discord.Interaction):
    if not _admin(inter):
        await inter.response.send_message('Só admin.', ephemeral=True)
        return
    planos = await db.listar_planos(bot.http_session)
    await inter.response.send_message(view=ConfigPlanoView(planos), ephemeral=True)


# Lista OFICIAL de planos (nome, dias, preço). As "salas" vão no nome.
PLANOS_OFICIAIS = [
    ('1 dia', 1, 2.50),
    ('1 dia + salas infinitas', 1, 4.00),
    ('3 dias + 10 salas inicial', 3, 4.00),
    ('3 dias + 100 salas', 3, 5.50),
    ('3 dias + 300 salas', 3, 8.00),
    ('3 dias + salas infinitas', 3, 11.00),
    ('7 dias', 7, 12.00),
    ('7 dias + 100 salas', 7, 13.00),
    ('7 dias + 300 salas', 7, 15.00),
    ('7 dias + salas infinitas', 7, 20.00),
]


@bot.tree.command(name='resetplanos',
                  description='APAGA todos os planos e recria a lista oficial + cargos (admin)')
async def resetplanos(inter: discord.Interaction):
    if not _admin(inter):
        await inter.response.send_message('Só admin.', ephemeral=True)
        return
    guild = inter.guild
    if guild is None:
        await inter.response.send_message('Use no servidor.', ephemeral=True)
        return
    await inter.response.defer(ephemeral=True)
    session = bot.http_session

    # 1) Apaga os planos atuais e os cargos antigos vinculados a eles ("tira as outras").
    antigos = await db.listar_planos(session)
    removidos_cargo = 0
    for p in antigos:
        cid = p.get('cargo_id')
        if cid:
            try:
                role_antigo = guild.get_role(int(cid))
                if role_antigo:
                    await role_antigo.delete(reason='resetplanos — plano antigo removido')
                    removidos_cargo += 1
            except Exception:
                pass
        try:
            await db.del_plano(session, p['id'])
        except Exception:
            pass

    # 2) Recria a lista oficial, criando um cargo pra cada plano.
    linhas = []
    for nome, dias, preco in PLANOS_OFICIAIS:
        cargo_id = None
        # Reaproveita um cargo com o mesmo nome se já existir; senão cria.
        try:
            role = discord.utils.get(guild.roles, name=nome)
            if role is None:
                role = await guild.create_role(name=nome, reason='resetplanos — cargo do plano')
            cargo_id = str(role.id)
        except discord.Forbidden:
            linhas.append(f'⚠️ Sem permissão pra criar o cargo de **{nome}** (cria o plano sem cargo).')
        except Exception as e:
            linhas.append(f'⚠️ Erro no cargo de **{nome}**: {e}')
        try:
            await db.add_plano(session, nome, dias, preco, cargo_id=cargo_id)
            tag = f' → <@&{cargo_id}>' if cargo_id else ''
            linhas.append(f'{E["seta"]} **{nome}** — {dias}d — R$ {preco:.2f}{tag}')
        except Exception as e:
            linhas.append(f'❌ Falha ao criar o plano **{nome}**: {e}')

    cab = (f'{E["foguete"]} **Planos recriados** ({len(PLANOS_OFICIAIS)}). '
           f'Cargos antigos removidos: {removidos_cargo}.\n')
    msg = cab + '\n'.join(linhas)
    await inter.followup.send(msg[:1900], ephemeral=True)


# ════════════════════════════════════════════════════════════
#  /criar-cupom  — criar / listar / remover cupons de desconto (admin)
# ════════════════════════════════════════════════════════════
class CupomModal(discord.ui.Modal, title='Criar cupom'):
    codigo = discord.ui.TextInput(
        label='Código do cupom', max_length=40,
        placeholder='Ex: BLACKFRIDAY')

    async def on_submit(self, inter: discord.Interaction):
        codigo = str(self.codigo.value).strip().upper()
        if not codigo:
            await inter.response.send_message('Código inválido.', ephemeral=True)
            return
        # O cupom é só o "código". O desconto é definido POR PLANO no
        # /configcupom. Aqui guardamos tipo/valor neutros (a tabela exige).
        try:
            await db.criar_cupom(bot.http_session, codigo, 'percent', 0)
        except Exception as e:
            await inter.response.send_message(f'Erro ao criar cupom: `{e}`', ephemeral=True)
            return
        await inter.response.send_message(
            f'{E["certo"]} Cupom **{codigo}** criado!\n'
            f'{E["seta"]} Agora use **/configcupom** pra definir a % de desconto em cada plano.',
            ephemeral=True)


class CupomView(discord.ui.LayoutView):
    """Painel admin de cupons: botão criar + select pra remover existentes."""
    def __init__(self, cupons):
        super().__init__(timeout=300)
        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(f'## {_ew("settings", "🏷️")} Cupons de Desconto'))
        if cupons:
            linhas = []
            for cp in cupons[:25]:
                estado = '🟢' if cp.get('ativo') else '🔴'
                linhas.append(f'{estado} **{cp["codigo"]}** — _% por plano em /configcupom_')
            c.add_item(discord.ui.TextDisplay('\n'.join(linhas)))
        else:
            c.add_item(discord.ui.TextDisplay('_Nenhum cupom criado ainda._'))
        c.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        row.add_item(BtnCriarCupom())
        c.add_item(row)
        if cupons:
            row2 = discord.ui.ActionRow()
            row2.add_item(SelRemoverCupom(cupons))
            c.add_item(row2)
        self.add_item(c)


class BtnCriarCupom(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Criar cupom', style=discord.ButtonStyle.success, emoji='➕')

    async def callback(self, inter: discord.Interaction):
        await inter.response.send_modal(CupomModal())


class SelRemoverCupom(discord.ui.Select):
    def __init__(self, cupons):
        opts = [discord.SelectOption(label=cp['codigo'][:100], value=str(cp['id']))
                for cp in cupons[:25]]
        super().__init__(placeholder='Remover um cupom…', options=opts)

    async def callback(self, inter: discord.Interaction):
        await db.del_cupom(bot.http_session, self.values[0])
        await inter.response.send_message('Cupom removido.', ephemeral=True)


@bot.tree.command(name='criar-cupom', description='Criar/gerenciar cupons de desconto (admin)')
async def criar_cupom(inter: discord.Interaction):
    if not _admin(inter):
        await inter.response.send_message('Só admin.', ephemeral=True)
        return
    # Responde JÁ pro Discord (evita "o aplicativo não respondeu" se o banco
    # demorar ou falhar). A view real vem no followup.
    await inter.response.defer(ephemeral=True)
    try:
        cupons = await db.listar_cupons(bot.http_session)
    except Exception as e:
        # Causa mais comum: a tabela 'cupons' ainda não foi criada no Supabase.
        msg = str(e)
        if 'cupons' in msg and ('404' in msg or '42P01' in msg or 'does not exist' in msg.lower()):
            await inter.followup.send(
                f'{E["box"]} A tabela **cupons** ainda não existe no banco.\n'
                f'{E["seta"]} Rode o **schema.sql** atualizado no SQL Editor do Supabase '
                f'(ele cria a tabela `cupons`) e tente de novo.', ephemeral=True)
        else:
            await inter.followup.send(
                f'{E["box"]} Erro ao carregar cupons: `{msg[:300]}`', ephemeral=True)
        return
    await inter.followup.send(view=CupomView(cupons), ephemeral=True)


# ════════════════════════════════════════════════════════════
#  /configcupom  — % de desconto POR PLANO em cada cupom (admin)
#    Fluxo: escolhe o cupom → vê/edita a % de cada plano → salva/remove.
# ════════════════════════════════════════════════════════════
async def _montar_view_configcupom(cupom, planos, perc_por_plano):
    """Painel de configuração de % por plano de UM cupom.
    perc_por_plano: dict {plano_id(str): percent(float)}."""
    c = discord.ui.Container(accent_color=COR)
    c.add_item(discord.ui.TextDisplay(
        f'## {_ew("settings", "🏷️")} Configurar cupom **{cupom["codigo"]}**'))
    c.add_item(discord.ui.TextDisplay(
        'Defina a **% de desconto por plano**. Plano sem % configurada '
        '_não recebe desconto_ com este cupom.'))
    c.add_item(discord.ui.Separator())
    if planos:
        linhas = []
        for p in planos:
            pid = str(p['id'])
            if pid in perc_por_plano:
                linhas.append(f'🟢 **{p["nome"]}** — {perc_por_plano[pid]:.0f}% off')
            else:
                linhas.append(f'⚪ **{p["nome"]}** — _sem desconto_')
        c.add_item(discord.ui.TextDisplay('\n'.join(linhas)))
    else:
        c.add_item(discord.ui.TextDisplay('_Nenhum plano cadastrado. Crie em /configplano._'))
    c.add_item(discord.ui.Separator())
    if planos:
        row1 = discord.ui.ActionRow()
        row1.add_item(SelDefinirPercentPlano(cupom, planos))
        c.add_item(row1)
        # Só mostra "remover" pros planos que já têm %.
        planos_com_perc = [p for p in planos if str(p['id']) in perc_por_plano]
        if planos_com_perc:
            row2 = discord.ui.ActionRow()
            row2.add_item(SelRemoverPercentPlano(cupom, planos_com_perc))
            c.add_item(row2)
    v = discord.ui.LayoutView(timeout=300)
    v.add_item(c)
    return v


async def _recarregar_configcupom(inter, cupom):
    """Recarrega o painel do /configcupom (após salvar/remover)."""
    planos = await db.listar_planos(bot.http_session)
    cps = await db.listar_cupom_planos(bot.http_session, cupom['id'])
    perc = {str(cp['plano_id']): float(cp['percent']) for cp in cps}
    v = await _montar_view_configcupom(cupom, planos, perc)
    try:
        await inter.response.edit_message(view=v)
    except Exception:
        await inter.followup.send(view=v, ephemeral=True)


class PercentPlanoModal(discord.ui.Modal, title='Desconto do cupom no plano'):
    def __init__(self, cupom, plano_id, plano_nome):
        super().__init__()
        self.cupom = cupom
        self.plano_id = plano_id
        self.plano_nome = plano_nome
        self.percent = discord.ui.TextInput(
            label=f'% off em {plano_nome[:28]}',
            max_length=6, placeholder='Ex: 10  (= 10% de desconto)')
        self.add_item(self.percent)

    async def on_submit(self, inter: discord.Interaction):
        try:
            pct = float(str(self.percent.value).replace(',', '.').strip())
        except ValueError:
            await inter.response.send_message('Porcentagem inválida.', ephemeral=True)
            return
        if pct <= 0 or pct > 100:
            await inter.response.send_message(
                'A porcentagem tem que ser entre 0 e 100.', ephemeral=True)
            return
        try:
            await db.set_cupom_plano_percent(
                bot.http_session, self.cupom['id'], self.plano_id, pct)
        except Exception as e:
            await inter.response.send_message(f'Erro ao salvar: `{e}`', ephemeral=True)
            return
        await _recarregar_configcupom(inter, self.cupom)


class SelDefinirPercentPlano(discord.ui.Select):
    def __init__(self, cupom, planos):
        self.cupom = cupom
        self._planos = {str(p['id']): p['nome'] for p in planos}
        opts = [discord.SelectOption(label=p['nome'][:100], value=str(p['id']),
                                     description=f'{p["dias"]}d — R$ {float(p["preco"]):.2f}')
                for p in planos[:25]]
        super().__init__(placeholder='Definir/editar % de um plano…', options=opts)

    async def callback(self, inter: discord.Interaction):
        pid = self.values[0]
        await inter.response.send_modal(
            PercentPlanoModal(self.cupom, pid, self._planos.get(pid, 'plano')))


class SelRemoverPercentPlano(discord.ui.Select):
    def __init__(self, cupom, planos_com_perc):
        self.cupom = cupom
        opts = [discord.SelectOption(label=p['nome'][:100], value=str(p['id']))
                for p in planos_com_perc[:25]]
        super().__init__(placeholder='Remover desconto de um plano…', options=opts)

    async def callback(self, inter: discord.Interaction):
        await db.del_cupom_plano(bot.http_session, self.cupom['id'], self.values[0])
        await _recarregar_configcupom(inter, self.cupom)


class ConfigCupomEscolheView(discord.ui.LayoutView):
    """Primeiro passo do /configcupom: escolher qual cupom configurar."""
    def __init__(self, cupons):
        super().__init__(timeout=300)
        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(f'## {_ew("settings", "🏷️")} Configurar Cupom por Plano'))
        c.add_item(discord.ui.TextDisplay('Escolha o cupom que quer configurar.'))
        c.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        row.add_item(SelEscolherCupom(cupons))
        c.add_item(row)
        self.add_item(c)


class SelEscolherCupom(discord.ui.Select):
    def __init__(self, cupons):
        self._cupons = {str(cp['id']): cp for cp in cupons}
        opts = [discord.SelectOption(label=cp['codigo'][:100], value=str(cp['id']))
                for cp in cupons[:25]]
        super().__init__(placeholder='Escolha o cupom…', options=opts)

    async def callback(self, inter: discord.Interaction):
        cupom = self._cupons.get(self.values[0])
        if not cupom:
            await inter.response.send_message('Cupom não encontrado.', ephemeral=True)
            return
        planos = await db.listar_planos(bot.http_session)
        cps = await db.listar_cupom_planos(bot.http_session, cupom['id'])
        perc = {str(cp['plano_id']): float(cp['percent']) for cp in cps}
        v = await _montar_view_configcupom(cupom, planos, perc)
        await inter.response.edit_message(view=v)


@bot.tree.command(name='configcupom', description='Configurar % de desconto por plano em cada cupom (admin)')
async def configcupom(inter: discord.Interaction):
    if not _admin(inter):
        await inter.response.send_message('Só admin.', ephemeral=True)
        return
    await inter.response.defer(ephemeral=True)
    try:
        cupons = await db.listar_cupons(bot.http_session)
    except Exception as e:
        msg = str(e)
        if 'cupons' in msg and ('404' in msg or '42P01' in msg or 'does not exist' in msg.lower()):
            await inter.followup.send(
                f'{E["box"]} A tabela **cupons** ainda não existe no banco.\n'
                f'{E["seta"]} Rode o **schema.sql** atualizado no Supabase e tente de novo.',
                ephemeral=True)
        else:
            await inter.followup.send(f'{E["box"]} Erro: `{msg[:300]}`', ephemeral=True)
        return
    if not cupons:
        await inter.followup.send(
            f'{E["box"]} Nenhum cupom criado ainda. Crie um com **/criar-cupom** primeiro.',
            ephemeral=True)
        return
    await inter.followup.send(view=ConfigCupomEscolheView(cupons), ephemeral=True)


# ════════════════════════════════════════════════════════════
#  /botconfig  — configurações globais (cargos + canais)
#    Cargo automático por plano foi movido pra /configplano.
# ════════════════════════════════════════════════════════════
class BotConfigView(discord.ui.LayoutView):
    """Painel global: cargos (cliente, compras, suporte) + canais (logs, logs vendas)."""
    def __init__(self, cargo_cliente, canal_logs=None,
                 cargo_compras=None, canal_logs_vendas=None,
                 cargo_suporte=None):
        super().__init__(timeout=300)
        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(f'## {E["gear"]} Configuração do Bot'))
        c.add_item(discord.ui.Separator())

        # cargo de cliente
        cc = f'<@&{cargo_cliente}>' if cargo_cliente else '_não definido_'
        c.add_item(discord.ui.TextDisplay(
            f'{E["ticket"]} **Cargo de cliente:** {cc}'))
        rowc = discord.ui.ActionRow()
        rowc.add_item(SelCargoCliente())
        c.add_item(rowc)
        c.add_item(discord.ui.Separator())

        # cargo de compras (mediadores que veem as threads)
        cm = f'<@&{cargo_compras}>' if cargo_compras else '_não definido_'
        c.add_item(discord.ui.TextDisplay(
            f'{E["foguete"]} **Cargo de compras** (vê os carrinhos): {cm}'))
        rowcm = discord.ui.ActionRow()
        rowcm.add_item(SelCargoCompras())
        c.add_item(rowcm)
        c.add_item(discord.ui.Separator())

        # cargo de suporte (marcado em tickets)
        cs = f'<@&{cargo_suporte}>' if cargo_suporte else '_não definido_'
        c.add_item(discord.ui.TextDisplay(
            f'{E["ticket"]} **Cargo de suporte** (marcado nos tickets): {cs}'))
        rowcs = discord.ui.ActionRow()
        rowcs.add_item(SelCargoSuporte())
        c.add_item(rowcs)
        c.add_item(discord.ui.Separator())

        # canal de logs (tickets/transcript)
        cl = f'<#{canal_logs}>' if canal_logs else '_não definido_'
        c.add_item(discord.ui.TextDisplay(
            f'{E["cloud"]} **Canal de logs (tickets):** {cl}'))
        rowl = discord.ui.ActionRow()
        rowl.add_item(SelCanalLogs())
        c.add_item(rowl)
        c.add_item(discord.ui.Separator())

        # canal de logs de vendas
        clv = f'<#{canal_logs_vendas}>' if canal_logs_vendas else '_não definido_'
        c.add_item(discord.ui.TextDisplay(
            f'{E["key"]} **Canal de logs de vendas:** {clv}'))
        rowlv = discord.ui.ActionRow()
        rowlv.add_item(SelCanalLogsVendas())
        c.add_item(rowlv)
        c.add_item(discord.ui.Separator())

        c.add_item(discord.ui.TextDisplay(
            f'_Cargo automático por plano: use **/configplano**._'))
        self.add_item(c)


class SelCanalLogs(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder='Definir canal de logs (tickets)…',
                         channel_types=[discord.ChannelType.text], max_values=1)

    async def callback(self, inter: discord.Interaction):
        await db.set_canal_logs(bot.http_session, inter.guild_id, self.values[0].id)
        await inter.response.send_message(
            f'{E["cloud"]} Canal de logs: {self.values[0].mention}', ephemeral=True)


class SelCanalLogsVendas(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder='Definir canal de logs de vendas…',
                         channel_types=[discord.ChannelType.text], max_values=1)

    async def callback(self, inter: discord.Interaction):
        await db.set_canal_logs_vendas(
            bot.http_session, inter.guild_id, self.values[0].id)
        await inter.response.send_message(
            f'{E["key"]} Canal de logs de vendas: {self.values[0].mention}',
            ephemeral=True)


class SelCanalLogsSalas(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder='Definir canal de logs de salas criadas…',
                         channel_types=[discord.ChannelType.text], max_values=1)

    async def callback(self, inter: discord.Interaction):
        try:
            await db.set_canal_logs_salas(
                bot.http_session, inter.guild_id, self.values[0].id)
        except Exception as erro:
            await inter.response.send_message(
                f'{E["box"]} Erro ao salvar o canal: `{erro}`', ephemeral=True)
            print(f'[SALA-LOG] erro ao set_canal_logs_salas: {erro}', flush=True)
            return
        await inter.response.send_message(
            f'{E["foguete"]} Canal de logs de salas criadas: {self.values[0].mention}',
            ephemeral=True)


class ConfigCanalSalasView(discord.ui.LayoutView):
    """3ª mensagem do /botconfig — canal de logs de salas criadas. Separada da
    BotConfigView porque aquela já tem 5 selects (limite do Discord por view)."""
    def __init__(self, canal_logs_salas=None):
        super().__init__(timeout=300)
        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(f'## {E["foguete"]} Logs de Salas Criadas'))
        c.add_item(discord.ui.Separator())
        cls_ = f'<#{canal_logs_salas}>' if canal_logs_salas else '_não definido_'
        c.add_item(discord.ui.TextDisplay(
            f'{E["cloud"]} **Canal de logs de salas:** {cls_}\n'
            f'{E["seta"]} Toda sala criada pelos bots (manual ou automática) '
            f'aparece aqui.'))
        row = discord.ui.ActionRow()
        row.add_item(SelCanalLogsSalas())
        c.add_item(row)
        self.add_item(c)


class SelCargoCliente(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder='Definir cargo de cliente…', max_values=1)

    async def callback(self, inter: discord.Interaction):
        await db.set_cargo_cliente(bot.http_session, inter.guild_id, self.values[0].id)
        await inter.response.send_message(
            f'{E["ticket"]} Cargo de cliente: {self.values[0].mention}', ephemeral=True)


class SelCargoCompras(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder='Definir cargo de compras (mediadores)…',
                         max_values=1)

    async def callback(self, inter: discord.Interaction):
        await db.set_cargo_compras(
            bot.http_session, inter.guild_id, self.values[0].id)
        await inter.response.send_message(
            f'{E["foguete"]} Cargo de compras: {self.values[0].mention}',
            ephemeral=True)


class SelCargoSuporte(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder='Definir cargo de suporte (tickets)…',
                         max_values=1)

    async def callback(self, inter: discord.Interaction):
        await db.set_cargo_suporte(
            bot.http_session, inter.guild_id, self.values[0].id)
        await inter.response.send_message(
            f'{E["ticket"]} Cargo de suporte: {self.values[0].mention}',
            ephemeral=True)


class SelCargoPlano(discord.ui.RoleSelect):
    def __init__(self, plano_id, plano_nome):
        self.plano_id = plano_id
        super().__init__(placeholder=f'Cargo do plano {plano_nome[:40]}…', max_values=1)

    async def callback(self, inter: discord.Interaction):
        try:
            await db.set_cargo_plano(bot.http_session, self.plano_id, self.values[0].id)
        except Exception as erro:
            await inter.response.send_message(
                f'{E["box"]} Erro ao salvar o cargo: `{erro}`', ephemeral=True)
            print(f'[CARGO-PLANO] erro ao set_cargo_plano: {erro}', flush=True)
            return
        await inter.response.send_message(
            f'{E["foguete"]} Cargo do plano definido: {self.values[0].mention}', ephemeral=True)


class ConfigPlanosCargosView(discord.ui.LayoutView):
    """Painel separado com os cargos automáticos por plano (até 5 planos)."""
    def __init__(self, planos):
        super().__init__(timeout=300)
        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(
            f'## {E["foguete"]} Cargo automático por plano'))
        c.add_item(discord.ui.Separator())
        if not planos:
            c.add_item(discord.ui.TextDisplay(
                '_Nenhum plano cadastrado. Use **/configplano** pra criar._'))
        else:
            linhas = '\n'.join(
                f'{E["seta"]} **{p["nome"]}** ({p["dias"]}d) — '
                + (f'<@&{p["cargo_id"]}>' if p.get('cargo_id') else '_sem cargo_')
                for p in planos[:5])
            c.add_item(discord.ui.TextDisplay(linhas))
            c.add_item(discord.ui.Separator())
            for p in planos[:5]:
                row = discord.ui.ActionRow()
                row.add_item(SelCargoPlano(p['id'], p['nome']))
                c.add_item(row)
            if len(planos) > 5:
                c.add_item(discord.ui.TextDisplay(
                    f'_Mostrando 5 de {len(planos)} planos._'))
        self.add_item(c)


@bot.tree.command(name='botconfig', description='Configurar cargos e canais (admin)')
async def botconfig(inter: discord.Interaction):
    if not _admin(inter):
        await inter.response.send_message('Só admin.', ephemeral=True)
        return
    await inter.response.defer(ephemeral=True)
    cfg = await db.get_config(bot.http_session, inter.guild_id)
    cargo_cliente     = cfg.get('cargo_cliente')      if cfg else None
    canal_logs        = cfg.get('canal_logs')         if cfg else None
    cargo_compras     = cfg.get('cargo_compras')      if cfg else None
    canal_logs_vendas = cfg.get('canal_logs_vendas')  if cfg else None
    cargo_suporte     = cfg.get('cargo_suporte')      if cfg else None
    canal_logs_salas  = ((cfg.get('dados_json') or {}).get('canal_logs_salas')
                         if cfg else None)
    planos = await db.listar_planos(bot.http_session)
    try:
        # 1ª mensagem: configurações globais (5 selects, no limite)
        await inter.followup.send(
            view=BotConfigView(cargo_cliente, canal_logs,
                               cargo_compras, canal_logs_vendas,
                               cargo_suporte),
            ephemeral=True)
        # 2ª mensagem: cargos por plano (até 5 selects)
        await inter.followup.send(
            view=ConfigPlanosCargosView(planos), ephemeral=True)
        # 3ª mensagem: canal de logs de salas criadas (select próprio porque a
        # BotConfigView já está no limite de 5 selects)
        await inter.followup.send(
            view=ConfigCanalSalasView(canal_logs_salas), ephemeral=True)
    except Exception as erro:
        await inter.followup.send(
            f'{E["box"]} Erro ao abrir o painel: `{erro}`', ephemeral=True)


# ════════════════════════════════════════════════════════════
#  /canalsugestao  — define canal onde mensagens viram sugestões
# ════════════════════════════════════════════════════════════
@bot.tree.command(
    name='canalsugestao',
    description='Define o canal onde mensagens viram sugestões (admin)')
@app_commands.describe(canal='Canal onde as sugestões serão postadas')
async def canalsugestao(inter: discord.Interaction, canal: discord.TextChannel):
    if not _admin(inter):
        await inter.response.send_message('Só admin.', ephemeral=True)
        return
    await db.set_canal_sugestao(bot.http_session, inter.guild_id, canal.id)
    c = discord.ui.Container(accent_color=COR)
    c.add_item(discord.ui.TextDisplay(f'## {E["foguete"]} Canal de Sugestões'))
    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.TextDisplay(
        f'{E["seta"]} Canal definido: {canal.mention}\n'
        f'{E["seta"]} Toda mensagem nesse canal vira sugestão com '
        f'{EMOJI_VOTO_SIM} e {EMOJI_VOTO_NAO} pra votar.\n'
        f'{E["box"]} **Links não são aceitos** e são removidos automaticamente.'))
    v = discord.ui.LayoutView(timeout=60)
    v.add_item(c)
    await inter.response.send_message(view=v, ephemeral=True)


# ════════════════════════════════════════════════════════════
#  /perfil (e .perfil) — ficha do cliente SalasFF deste servidor.
#  Acha o cliente pelo guild via configadm (GUILD_IDS), mostra em
#  Components V2 e deixa editar os MESMOS campos do painel por modal.
#  Precisa de CONFIGURADOR_URL + BOT_FETCH_SECRET (= do configadm).
# ════════════════════════════════════════════════════════════
PERFIL_LABELS = {
    'pix':       '💸 Chave PIX',
    'lucro':     '💰 Lucro por sala',
    'msg':       '💬 Mensagem auto',
    'nome':      '🏠 Nome da sala',
    'senha':     '🔒 Senha da sala',
    'modo':      '🎮 Modo padrão',
    'autostart': '⏱️ Auto-start',
    'valorpag':  '💵 Mostrar valor',
    'caixapag':  '🧾 Estilo da caixa',
    'presenca':  '🎮 Status (jogando)',
    'token':     '🔑 Token do bot',
}

# Dicas (placeholder) por campo — aparecem no modal de edição pra campos com
# valores específicos (liga/desliga, estilos), pra o cliente não chutar.
PERFIL_HINTS = {
    'valorpag': 'sim ou não (mostrar o valor na msg de pagamento)',
    'caixapag': 'pc · mobile_estrela · codeblock · compacto (sem caixa)',
    'presenca': 'sim ou não (mostrar o status "Jogando Power System")',
    'modo':     'ex: 1',
    'autostart': 'ex: 4',
}


async def _org_get(path, _tentativas=3):
    if not CONFIGURADOR_URL:
        return None
    import time as _t
    for i in range(_tentativas):
        # Cache-bust: a URL muda a cada tentativa pra o proxy/Cloudflare do Discloud
        # NUNCA servir um 504/erro cacheado (era o que travava o .perfil — a URL
        # fixa ?id=X devolvia erro de cache sem nem chegar no configadm).
        sep = '&' if '?' in path else '?'
        url = f'{CONFIGURADOR_URL}{path}{sep}_cb={int(_t.time()*1000)}'
        try:
            async with bot.http_session.get(
                    url,
                    headers={'X-Bot-Secret': BOT_FETCH_SECRET,
                             'Cache-Control': 'no-cache', 'Pragma': 'no-cache'},
                    timeout=aiohttp.ClientTimeout(total=45)) as r:
                if r.status >= 500:
                    txt = (await r.text())[:120]
                    print(f'[PERFIL] org_get {r.status} (tentativa {i+1}): {txt!r}', flush=True)
                    if i < _tentativas - 1:
                        await asyncio.sleep(5)
                    continue
                return await r.json(content_type=None)
        except Exception as e:
            print(f'[PERFIL] org_get erro (tentativa {i+1}): {type(e).__name__}: {e}', flush=True)
            if i < _tentativas - 1:
                await asyncio.sleep(5)
    return None


async def _org_post(path, payload, _tentativas=3):
    if not CONFIGURADOR_URL:
        return None
    import time as _t
    for i in range(_tentativas):
        sep = '&' if '?' in path else '?'
        url = f'{CONFIGURADOR_URL}{path}{sep}_cb={int(_t.time()*1000)}'
        try:
            async with bot.http_session.post(
                    url,
                    headers={'X-Bot-Secret': BOT_FETCH_SECRET,
                             'Cache-Control': 'no-cache', 'Pragma': 'no-cache'},
                    json=payload, timeout=aiohttp.ClientTimeout(total=120)) as r:
                if r.status >= 500:
                    txt = (await r.text())[:100]
                    print(f'[PERFIL] org_post {r.status} (tentativa {i+1}): {txt!r}', flush=True)
                    if i < _tentativas - 1:
                        await asyncio.sleep(4)
                    continue
                return await r.json(content_type=None)
        except Exception as e:
            print(f'[PERFIL] org_post erro (tentativa {i+1}): {type(e).__name__}: {e}', flush=True)
            if i < _tentativas - 1:
                await asyncio.sleep(4)
    return None


class PerfilEditarModal(discord.ui.Modal):
    def __init__(self, client_id, alias, atual):
        super().__init__(title=f'Editar {PERFIL_LABELS.get(alias, alias)}'[:45])
        self.client_id = client_id
        self.alias = alias
        self.valor = discord.ui.TextInput(
            label=PERFIL_LABELS.get(alias, alias)[:45],
            default=str(atual or '')[:300], required=False, max_length=500,
            placeholder=PERFIL_HINTS.get(alias, '')[:100] or None,
            style=discord.TextStyle.paragraph if alias == 'msg' else discord.TextStyle.short)
        self.add_item(self.valor)

    async def on_submit(self, inter: discord.Interaction):
        # Defere já (ack em <3s) — o _org_post pode demorar (configadm/commit),
        # senão o Discord mostra "Esta interação falhou".
        try:
            await inter.response.defer(ephemeral=True, thinking=True)
        except Exception:
            pass
        d = await _org_post('/bot/perfil-editar',
                            {'client_id': self.client_id, 'campo': self.alias,
                             'valor': str(self.valor.value)})
        if d and d.get('ok'):
            extra = ('\n⏳ Aplicando no seu bot (reinicia em ~1 min).'
                     if d.get('aplicado')
                     else f'\n⚠️ Salvei, mas **não consegui aplicar**: {d.get("aplica_msg", "erro")}')
            await inter.followup.send(
                f'{E.get("certo", "✅")} **{self.alias}** atualizado pra `{d.get("valor")}`.{extra}',
                ephemeral=True)
        else:
            await inter.followup.send(
                f'❌ {(d or {}).get("msg", "erro (configadm offline?)")}', ephemeral=True)


# Emoji do bot (Application Emoji) por botão — resolvido no runtime (E já está
# populado quando o .perfil abre). Cai no unicode da label se faltar.
_PERFIL_BTN_EMOJI = {
    'pix': 'store', 'lucro': 'cart', 'msg': 'mail', 'nome': 'home',
    'senha': 'settings', 'modo': 'config', 'autostart': 'seta', 'token': 'cloud',
}
# Campos editados por TEXTO (modal). Os de escolha viram menu de seleção.
PERFIL_TEXT_FIELDS = ['pix', 'lucro', 'msg', 'nome', 'senha', 'modo', 'autostart', 'token']


def _emoji_btn(alias):
    chave = _PERFIL_BTN_EMOJI.get(alias)
    return E.get(chave) if chave else None


class BtnPerfilEditar(discord.ui.Button):
    def __init__(self, client_id, alias, atual, dono_id):
        full = PERFIL_LABELS.get(alias, alias)
        emo = _emoji_btn(alias)
        # Se tem emoji do bot, usa ele no slot e tira o emoji da label (não dobra).
        label = (full.split(' ', 1)[1] if (emo and ' ' in full) else full)
        super().__init__(label=label[:80], style=discord.ButtonStyle.secondary, emoji=emo)
        self.client_id = client_id
        self.alias = alias
        self.atual = atual
        self.dono_id = dono_id

    async def callback(self, inter: discord.Interaction):
        if self.dono_id and inter.user.id != self.dono_id:
            await inter.response.send_message('Esse perfil não é seu.', ephemeral=True)
            return
        await inter.response.send_modal(PerfilEditarModal(self.client_id, self.alias, self.atual))


class PerfilSelect(discord.ui.Select):
    """Menu de seleção pra um campo de escolha do .perfil (liga/desliga, estilo)."""
    def __init__(self, client_id, alias, dono_id, placeholder, options):
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)
        self.client_id = client_id
        self.alias = alias
        self.dono_id = dono_id

    async def callback(self, inter: discord.Interaction):
        if self.dono_id and inter.user.id != self.dono_id:
            await inter.response.send_message('Esse perfil não é seu.', ephemeral=True)
            return
        # Defere já (ack em <3s) — o _org_post pode demorar; senão dá
        # "Esta interação falhou".
        try:
            await inter.response.defer(ephemeral=True, thinking=True)
        except Exception:
            pass
        d = await _org_post('/bot/perfil-editar',
                            {'client_id': self.client_id, 'campo': self.alias, 'valor': self.values[0]})
        if d and d.get('ok'):
            extra = ('\n⏳ Aplicando no seu bot (reinicia em ~1 min).'
                     if d.get('aplicado')
                     else f'\n⚠️ Salvei, mas **não consegui aplicar**: {d.get("aplica_msg", "erro")}')
            await inter.followup.send(
                f'{E.get("certo", "✅")} **{PERFIL_LABELS.get(self.alias, self.alias)}** = `{d.get("valor")}`.{extra}',
                ephemeral=True)
        else:
            await inter.followup.send(
                f'❌ {(d or {}).get("msg", "erro (configadm offline?)")}', ephemeral=True)


def _opts_valorpag():
    return [
        discord.SelectOption(label='Mostrar valor', value='sim', emoji=E.get('certo', '✅'),
                             description='Mostra o valor na msg de pagamento'),
        discord.SelectOption(label='Ocultar valor', value='nao', emoji=E.get('xist', '❌'),
                             description='Esconde o valor'),
    ]


def _opts_caixapag():
    return [
        discord.SelectOption(label='Caixa com bordas (PC)', value='pc', description='Visual padrão'),
        discord.SelectOption(label='Mobile (estrelas)', value='mobile_estrela', description='Compacto p/ celular'),
        discord.SelectOption(label='Bloco de código', value='codeblock', description='Renderiza dentro de ```'),
        discord.SelectOption(label='Sem caixa (compacto)', value='compacto', description='Só as linhas, sem moldura'),
    ]


def _opts_presenca():
    return [
        discord.SelectOption(label='Status ligado', value='sim', emoji=E.get('certo', '✅'),
                             description='Mostra "Jogando Power System" no perfil'),
        discord.SelectOption(label='Status desligado', value='nao', emoji=E.get('xist', '❌'),
                             description='Sem status de jogando'),
    ]


def _fmt_saldo(perfil):
    """Saldo do cliente: ∞ se for saldo infinito, senão o número."""
    if perfil.get('saldo_infinito'):
        return '♾️'
    return str(perfil.get('saldo_salas', 0))


class ServidorModal(discord.ui.Modal):
    """Configura um servidor EXTRA (slot 2..N): ID do servidor + ID do canal
    onde cai a fila. Manda pro configadm em /bot/perfil-servidor."""
    def __init__(self, client_id, slot, atual_guild='', atual_canal=''):
        super().__init__(title=f'Servidor {slot}'[:45])
        self.client_id = client_id
        self.slot = slot
        self.guild = discord.ui.TextInput(
            label='ID do servidor', default=str(atual_guild or '')[:30],
            required=True, max_length=25, placeholder='ex: 123456789012345678',
            style=discord.TextStyle.short)
        self.canal = discord.ui.TextInput(
            label='ID do canal da fila', default=str(atual_canal or '')[:30],
            required=False, max_length=25, placeholder='canal onde cai a fila',
            style=discord.TextStyle.short)
        self.add_item(self.guild)
        self.add_item(self.canal)

    async def on_submit(self, inter: discord.Interaction):
        try:
            await inter.response.defer(ephemeral=True, thinking=True)
        except Exception:
            pass
        d = await _org_post('/bot/perfil-servidor',
                            {'client_id': self.client_id, 'slot': self.slot,
                             'guild': str(self.guild.value), 'canal': str(self.canal.value)})
        if d and d.get('ok'):
            extra = ('\n⏳ Aplicando no seu bot (reinicia em ~1 min).'
                     if d.get('aplicado')
                     else f'\n⚠️ Salvei, mas **não consegui aplicar**: {d.get("aplica_msg", "erro")}')
            await inter.followup.send(
                f'{E.get("certo", "✅")} **Servidor {self.slot}** salvo '
                f'(`{d.get("guild")}`).{extra}', ephemeral=True)
        else:
            await inter.followup.send(
                f'❌ {(d or {}).get("msg", "erro (configadm offline?)")}', ephemeral=True)


class BtnPerfilServidor(discord.ui.Button):
    def __init__(self, client_id, slot, atual_guild, atual_canal, dono_id):
        cfg = bool(str(atual_guild or '').strip())
        super().__init__(
            label=f'Servidor {slot}' + (' ✓' if cfg else ''),
            style=discord.ButtonStyle.success if cfg else discord.ButtonStyle.secondary,
            emoji='🌐')
        self.client_id = client_id
        self.slot = slot
        self.atual_guild = atual_guild
        self.atual_canal = atual_canal
        self.dono_id = dono_id

    async def callback(self, inter: discord.Interaction):
        if self.dono_id and inter.user.id != self.dono_id:
            await inter.response.send_message('Esse perfil não é seu.', ephemeral=True)
            return
        await inter.response.send_modal(
            ServidorModal(self.client_id, self.slot, self.atual_guild, self.atual_canal))


class PerfilView(discord.ui.LayoutView):
    def __init__(self, perfil, dono_id=None):
        super().__init__(timeout=300)
        cid = perfil.get('client_id', '')
        cc = perfil.get('campos', {}) or {}
        _tok_ok = bool(perfil.get('token_set'))
        _valorpag = (cc.get('valorpag') or '').strip() or 'sim (padrão)'
        _caixapag = (cc.get('caixapag') or '').strip() or 'pc (padrão)'
        _presenca = (cc.get('presenca') or '').strip() or 'sim (padrão)'
        # COMPONENTE V2: tudo dentro de um Container (caixa), botões e menus dentro.
        cont = discord.ui.Container(accent_color=COR)
        cont.add_item(discord.ui.TextDisplay(f'## {E.get("pessoas", "👤")} Perfil — {perfil.get("nome", "—") or "—"}'))
        cont.add_item(discord.ui.Separator())
        cont.add_item(discord.ui.TextDisplay(
            f'📅 **Vencimento:** {perfil.get("vencimento") or "—"}\n'
            f'🎟️ **Saldo de salas:** {_fmt_saldo(perfil)}\n'
            f'💸 **PIX:** {cc.get("pix") or "—"}\n'
            f'💰 **Lucro/sala:** R$ {cc.get("lucro") or "0.00"}\n'
            f'🏠 **Nome da sala:** {cc.get("nome") or "—"}\n'
            f'🔒 **Senha:** {cc.get("senha") or "—"}\n'
            f'🎮 **Modo:** {cc.get("modo") or "—"}\n'
            f'⏱️ **Auto-start:** {cc.get("autostart") or "—"}\n'
            f'💵 **Mostrar valor (pgto):** {_valorpag}\n'
            f'🧾 **Estilo da caixa (pgto):** {_caixapag}\n'
            f'🎮 **Status "Jogando":** {_presenca}\n'
            + '🔑 **Token do bot:** ' + (f'{E.get("certo", "✅")} configurado'
              if _tok_ok else f'{E.get("xist", "❌")} não configurado — toque em 🔑 Token')))
        cont.add_item(discord.ui.TextDisplay('_Editar por texto (só você vê/edita):_'))
        for i in range(0, len(PERFIL_TEXT_FIELDS), 5):
            row = discord.ui.ActionRow()
            for al in PERFIL_TEXT_FIELDS[i:i + 5]:
                row.add_item(BtnPerfilEditar(cid, al, cc.get(al, ''), dono_id))
            cont.add_item(row)
        # Menus de seleção (escolha rápida) — um por linha:
        rv = discord.ui.ActionRow()
        rv.add_item(PerfilSelect(cid, 'valorpag', dono_id, '💵 Mostrar valor do pagamento…', _opts_valorpag()))
        cont.add_item(rv)
        rc = discord.ui.ActionRow()
        rc.add_item(PerfilSelect(cid, 'caixapag', dono_id, '🧾 Estilo da caixa do pagamento…', _opts_caixapag()))
        cont.add_item(rc)
        rp = discord.ui.ActionRow()
        rp.add_item(PerfilSelect(cid, 'presenca', dono_id, '🎮 Status "Jogando"…', _opts_presenca()))
        cont.add_item(rp)
        # ─── Servidores extras (multi-servidor) ───
        # Só aparece se o plano libera 2+ servidores. O servidor 1 é o principal
        # (já configurado no painel), então a gente mostra só do 2 pra frente.
        try:
            limite = int(perfil.get('servidores_permitidos', 1) or 1)
        except (TypeError, ValueError):
            limite = 1
        if limite > 1:
            extras = perfil.get('servidores_extra') or []
            cont.add_item(discord.ui.Separator())
            cont.add_item(discord.ui.TextDisplay(
                f'🌐 **Servidores extras** (seu plano: {limite}). '
                'O servidor 1 é o principal. Configure os demais — ID do servidor '
                'e o canal onde cai a fila:'))
            botoes = []
            # Cap de exibição: o Discord limita componentes por view. 10 extras
            # (slots 2..11) cobre qualquer plano real sem estourar o limite.
            for slot in range(2, min(limite, 11) + 1):
                idx = slot - 2
                e = extras[idx] if idx < len(extras) and isinstance(extras[idx], dict) else {}
                botoes.append(BtnPerfilServidor(cid, slot, e.get('guild', ''),
                                                e.get('canal', ''), dono_id))
            for i in range(0, len(botoes), 5):
                row = discord.ui.ActionRow()
                for b in botoes[i:i + 5]:
                    row.add_item(b)
                cont.add_item(row)
        self.add_item(cont)


# Canal pra onde mandamos quem ainda não tem plano ("compre seu plano aqui").
CANAL_COMPRA_ID = int(os.environ.get('CANAL_COMPRA_ID', '1506251608798003211') or '0')


class BtnDuvidaPlano(discord.ui.Button):
    """Abre um ticket de Dúvidas pra quem ainda não é cliente."""
    def __init__(self):
        super().__init__(label='Tirar dúvida', style=discord.ButtonStyle.secondary, emoji='❓')

    async def callback(self, inter: discord.Interaction):
        await _criar_ticket(inter, 'Dúvidas')


class SemPlanoView(discord.ui.LayoutView):
    """Mostrada no .perfil quando a pessoa ainda NÃO tem plano/cliente."""
    def __init__(self):
        super().__init__(timeout=300)
        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(
            f'## {E.get("cart", E.get("carrinho", "🛒"))} Você ainda não tem um plano'))
        c.add_item(discord.ui.Separator())
        canal_txt = f'<#{CANAL_COMPRA_ID}>' if CANAL_COMPRA_ID else 'o canal de compras'
        c.add_item(discord.ui.TextDisplay(
            f'{E.get("seta", "➡️")} **Compre seu plano** em {canal_txt} pra liberar seu bot.\n'
            f'{E.get("cloud", "☁️")} Já é cliente? Ligue/reinicie seu bot uma vez (ele registra '
            f'seu Discord) e rode `.perfil` de novo.\n'
            f'{E.get("ticket", "❓")} Ficou com dúvida? Toque no botão abaixo que a equipe te ajuda.'))
        c.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        row.add_item(BtnDuvidaPlano())
        c.add_item(row)
        self.add_item(c)


class BtnIniciarBot(discord.ui.Button):
    """Liga o bot do cliente na Discloud."""
    def __init__(self, dono_id, online):
        super().__init__(
            label='Iniciar bot' if not online else 'Reiniciar bot',
            style=discord.ButtonStyle.success,
            emoji='▶️')
        self.dono_id = dono_id

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != self.dono_id:
            await inter.response.send_message('Esse perfil não é seu.', ephemeral=True)
            return
        try:
            await inter.response.defer(ephemeral=True, thinking=True)
        except Exception:
            pass
        d = await _org_post('/bot/app-start', {'id': self.dono_id})
        if d and d.get('ok'):
            await inter.followup.send(
                f'{E.get("certo", "✅")} Bot **iniciando**… espera ~1 minuto e ele fica online. '
                'Rode `.perfil` de novo pra ver o status atualizado.', ephemeral=True)
        else:
            await inter.followup.send(
                f'❌ {(d or {}).get("msg", "não consegui iniciar (fale com o suporte)")}', ephemeral=True)


class BtnConfigurar(discord.ui.Button):
    """Abre o painel de configurações (PerfilView) no lugar da home."""
    def __init__(self, perfil, dono_id):
        super().__init__(label='Configurar', style=discord.ButtonStyle.primary, emoji='⚙️')
        self.perfil = perfil
        self.dono_id = dono_id

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != self.dono_id:
            await inter.response.send_message('Esse perfil não é seu.', ephemeral=True)
            return
        await inter.response.edit_message(view=PerfilView(self.perfil, self.dono_id))


class BtnConferirDeposito(discord.ui.Button):
    """Confere se o depósito PIX caiu e credita o saldo da carteira."""
    def __init__(self, dono_id, txid):
        super().__init__(label='Já paguei', style=discord.ButtonStyle.success, emoji='✅')
        self.dono_id = dono_id
        self.txid = txid

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != self.dono_id:
            await inter.response.send_message('Esse perfil não é seu.', ephemeral=True)
            return
        try:
            await inter.response.defer(ephemeral=True, thinking=True)
        except Exception:
            pass
        d = await _org_post('/bot/wallet2-checar', {'id': self.dono_id, 'txid': self.txid})
        if d and d.get('ok') and d.get('pago'):
            saldo = d.get('saldo')
            extra = f' Novo saldo: **R$ {float(saldo):.2f}**.' if saldo is not None else ''
            await inter.followup.send(f'{E.get("certo", "✅")} Pagamento confirmado!{extra}',
                                      ephemeral=True)
        elif d and d.get('ok'):
            await inter.followup.send('⏳ Ainda não caiu. Se já pagou, espera uns segundos '
                                      'e toque de novo.', ephemeral=True)
        else:
            await inter.followup.send(f'❌ {(d or {}).get("msg", "não consegui conferir agora")}',
                                      ephemeral=True)


class DepositarModal(discord.ui.Modal, title='Depositar na carteira'):
    def __init__(self, dono_id):
        super().__init__()
        self.dono_id = dono_id
        self.valor = discord.ui.TextInput(
            label='Valor do depósito (R$)', placeholder='ex: 10',
            required=True, max_length=12, style=discord.TextStyle.short)
        self.add_item(self.valor)

    async def on_submit(self, inter: discord.Interaction):
        try:
            await inter.response.defer(ephemeral=True, thinking=True)
        except Exception:
            pass
        d = await _org_post('/bot/wallet2-depositar',
                            {'id': self.dono_id, 'valor': str(self.valor.value)})
        if not (d and d.get('ok')):
            await inter.followup.send(f'❌ {(d or {}).get("msg", "não consegui gerar o PIX")}',
                                      ephemeral=True)
            return
        copia = d.get('copia_cola') or ''
        view = discord.ui.View(timeout=600)
        view.add_item(BtnConferirDeposito(self.dono_id, d.get('txid')))
        await inter.followup.send(
            f'{E.get("store", "💸")} **PIX gerado!** Copie o código abaixo e pague no seu banco:\n'
            f'```\n{copia}\n```\n'
            'Depois de pagar, toque em **✅ Já paguei** pra creditar seu saldo.',
            view=view, ephemeral=True)


class BtnDepositar(discord.ui.Button):
    """Abre o modal pra depositar na wallet2 (carteira)."""
    def __init__(self, dono_id):
        super().__init__(label='Depositar', style=discord.ButtonStyle.secondary, emoji='💰')
        self.dono_id = dono_id

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != self.dono_id:
            await inter.response.send_message('Esse perfil não é seu.', ephemeral=True)
            return
        await inter.response.send_modal(DepositarModal(self.dono_id))


class PerfilHomeView(discord.ui.LayoutView):
    """Tela inicial (após Continuar): status do bot + LINK do painel + ID de login.

    Mudança: em vez de editar as configs aqui no Discord, mandamos o cliente
    pro PAINEL DO CLIENTE (site). Mostramos o link e o ID dele pra logar e
    configurar tudo (chave PIX, sala, mensagens) e COMPRAR salas por lá."""
    def __init__(self, perfil, dono_id, online=False, tem_app=True):
        super().__init__(timeout=300)
        # ID de login do PAINEL = login_id (o painel-cliente loga SÓ por ele).
        # client_id (slug, ex: 'alef_guilherme') NÃO loga — não mostrar esse.
        login_id = (perfil.get('login_id') or '').strip() or (perfil.get('client_id', '') or '—')
        cont = discord.ui.Container(accent_color=COR)
        cont.add_item(discord.ui.TextDisplay(
            f'## {E.get("pessoas", "👤")} Perfil — {perfil.get("nome", "—") or "—"}'))
        cont.add_item(discord.ui.Separator())
        if not tem_app:
            status_txt = '⚪ **Status do bot:** ainda não criado'
        elif online:
            status_txt = f'🟢 **Status do bot:** {E.get("certo", "✅")} **ONLINE**'
        else:
            status_txt = '🔴 **Status do bot:** **DESLIGADO**'
        cont.add_item(discord.ui.TextDisplay(
            f'{status_txt}\n'
            f'📅 **Vencimento:** {perfil.get("vencimento") or "—"}\n'
            f'🎟️ **Saldo de salas:** {_fmt_saldo(perfil)}'))
        if tem_app and not online:
            cont.add_item(discord.ui.Separator())
            cont.add_item(discord.ui.TextDisplay(
                '⚠️ Seu bot está **desligado**. Toque em **▶️ Iniciar bot** pra ligar.'))
        # ─── BLOCO DO PAINEL (substitui as configs no Discord) ───
        cont.add_item(discord.ui.Separator())
        cont.add_item(discord.ui.TextDisplay(
            f'### {E.get("cloud", "🌐")} Configure tudo no seu Painel\n'
            f'Toda a configuração (chave PIX, sala, senha, mensagens) e a '
            f'**compra de salas** agora é pelo site — mais fácil e completo.\n\n'
            f'{E.get("seta", "🔗")} **Site:** {PAINEL_CLIENTE_URL}\n'
            f'🆔 **Seu ID de login:** `{login_id}`\n'
            f'-# Abra o site, toque em entrar e cole esse ID (não precisa senha).'))
        cont.add_item(discord.ui.Separator())
        cont.add_item(discord.ui.TextDisplay('_Escolha uma opção (só você vê/usa):_'))
        row = discord.ui.ActionRow()
        if tem_app:
            row.add_item(BtnIniciarBot(dono_id, online))
        # Botão LINK que abre o painel direto (sem callback — o Discord abre a URL).
        row.add_item(discord.ui.Button(
            label='Abrir Painel', style=discord.ButtonStyle.link,
            url=PAINEL_CLIENTE_URL, emoji='🌐'))
        # Botão Depositar — só se a carteira (wallet2/TurbofyPay) está ativa.
        if perfil.get('wallet2_ativo'):
            row.add_item(BtnDepositar(dono_id))
        cont.add_item(row)
        self.add_item(cont)


class BtnPerfilContinuar(discord.ui.Button):
    def __init__(self, perfil, dono_id):
        super().__init__(label='Continuar', style=discord.ButtonStyle.success, emoji='➡️')
        self.perfil = perfil
        self.dono_id = dono_id

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != self.dono_id:
            await inter.response.send_message('Esse perfil não é seu.', ephemeral=True)
            return
        # A mensagem pública (gate) vira um aviso curto; a home abre no PRIVADO.
        aviso = discord.ui.LayoutView(timeout=1)
        ca = discord.ui.Container(accent_color=COR)
        ca.add_item(discord.ui.TextDisplay(
            f'{E.get("certo", "✅")} Abri seu painel aqui no privado, {inter.user.mention} 👇'))
        aviso.add_item(ca)
        await inter.response.edit_message(view=aviso)
        # Busca o status do bot (on/off) antes de montar a home.
        st = await _org_get(f'/bot/app-status?id={self.dono_id}')
        online = bool((st or {}).get('online'))
        tem_app = bool((st or {}).get('tem_app', True)) if st else True
        await inter.followup.send(
            view=PerfilHomeView(self.perfil, self.dono_id, online, tem_app), ephemeral=True)


class BtnPerfilCancelar(discord.ui.Button):
    def __init__(self, dono_id):
        super().__init__(label='Cancelar', style=discord.ButtonStyle.secondary, emoji='✖️')
        self.dono_id = dono_id

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != self.dono_id:
            await inter.response.send_message('Esse perfil não é seu.', ephemeral=True)
            return
        v = discord.ui.LayoutView(timeout=1)
        cc = discord.ui.Container(accent_color=COR)
        cc.add_item(discord.ui.TextDisplay(f'{E.get("xist", "❌")} Cancelado.'))
        v.add_item(cc)
        await inter.response.edit_message(view=v)


class PerfilGateView(discord.ui.LayoutView):
    """Confirmação antes de abrir o painel — só o dono pode clicar (igual o resto)."""
    def __init__(self, perfil, dono_id):
        super().__init__(timeout=120)
        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(
            f'## {E.get("pessoas", "👤")} Perfil — {perfil.get("nome", "—") or "—"}'))
        c.add_item(discord.ui.TextDisplay(
            f'{E.get("clock", "⏱️")} Vencimento: **{perfil.get("vencimento") or "—"}** · '
            f'🎟️ Saldo: **{_fmt_saldo(perfil)}**\n'
            f'_Toque em **Continuar** pra abrir seu painel._'))
        c.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        row.add_item(BtnPerfilContinuar(perfil, dono_id))
        row.add_item(BtnPerfilCancelar(dono_id))
        c.add_item(row)
        self.add_item(c)


async def _abrir_perfil(user_id):
    """Acha o cliente vinculado ao Discord ID de quem rodou o comando.
    - Sem configurador → erro.
    - Achou cliente → tela Continuar/Cancelar (só o dono clica) → abre o painel.
    - Não achou → tela 'compre seu plano' com botão de dúvida (abre ticket)."""
    d = await _org_get(f'/bot/perfil?id={user_id}')
    if d is None:
        return None, '❌ Configurador não conectado (defina CONFIGURADOR_URL no .env do bot).'
    if not d.get('ok'):
        return SemPlanoView(), None
    return PerfilGateView(d, user_id), None


@bot.tree.command(name='perfil', description='Sua ficha de cliente (ver/editar a config do bot)')
async def perfil_slash(inter: discord.Interaction):
    view, err = await _abrir_perfil(inter.user.id)
    if err:
        await inter.response.send_message(err, ephemeral=True)
        return
    await inter.response.send_message(view=view, ephemeral=True)


@bot.tree.command(name='erros', description='(Admin) Define o canal de avisos de erro dos clientes')
@discord.app_commands.describe(canal='Canal de texto onde o bot vai avisar os erros (marcando o dono)')
async def erros_slash(inter: discord.Interaction, canal: discord.TextChannel):
    if not _admin(inter):
        await inter.response.send_message('Só admin pode usar isso.', ephemeral=True)
        return
    await db.set_canal_erros(bot.http_session, inter.guild.id, canal.id)
    await inter.response.send_message(
        f'{E.get("certo", "✅")} Canal de erros definido: {canal.mention}\n'
        f'Vou avisar aí (marcando o dono) quando o token de algum cliente falhar.',
        ephemeral=True)


# Dedup dos avisos de erro: (guild, client, estado) já postado. Reseta no restart.
_ERROS_POSTADOS = set()


async def _loop_avisar_erros():
    """Lê os clientes com erro de token no configadm (/bot/erros) e avisa no canal
    de erros de cada servidor (marcando o dono). Roda a cada 3 min."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            d = await _org_get('/bot/erros')
            erros = (d or {}).get('erros') or []
            if erros:
                for guild in list(bot.guilds):
                    try:
                        cfg = await db.get_config(bot.http_session, guild.id)
                    except Exception:
                        continue
                    dados = (cfg or {}).get('dados_json') or {}
                    canal_id = dados.get('canal_erros') if isinstance(dados, dict) else None
                    if not canal_id or not str(canal_id).isdigit():
                        continue
                    canal = guild.get_channel(int(canal_id))
                    if canal is None:
                        continue
                    gid = str(guild.id)
                    for er in erros:
                        gids = [str(x) for x in (er.get('guild_ids') or [])]
                        if gids and gid not in gids:
                            continue  # erro de cliente de outro servidor
                        chave = f"{guild.id}|{er.get('client_id')}|{er.get('estado')}"
                        if chave in _ERROS_POSTADOS:
                            continue
                        _ERROS_POSTADOS.add(chave)
                        did = (er.get('discord_id') or '').strip()
                        quem = f'<@{did}>' if did.isdigit() else (er.get('nome') or er.get('client_id') or 'cliente')
                        try:
                            await canal.send(
                                f'{E.get("xist", "⚠️")} {quem} {er.get("msg", "erro no seu bot.")}',
                                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
                        except Exception as e:
                            print(f'[ERROS] envio falhou: {e}', flush=True)
        except Exception as e:
            print(f'[ERROS] loop erro: {e}', flush=True)
        await asyncio.sleep(180)


@bot.event
async def on_message(message: discord.Message):
    # ignora bots e DMs
    if message.author.bot or not message.guild:
        return

    # .perfil (prefixo) — pega o ID de QUEM digitou e mostra a ficha dele.
    if (message.content or '').strip().lower() == '.perfil':
        view, err = await _abrir_perfil(message.author.id)
        try:
            if err:
                await message.channel.send(err, delete_after=12)
            else:
                await message.channel.send(view=view)
        except Exception as _e:
            print(f'[PERFIL] envio .perfil erro: {_e}', flush=True)
        return

    # checa se é o canal de sugestões
    try:
        cfg = await db.get_config(bot.http_session, message.guild.id)
    except Exception:
        return
    canal_sug_id = cfg.get('canal_sugestao') if cfg else None
    if not canal_sug_id or str(message.channel.id) != str(canal_sug_id):
        return

    conteudo = (message.content or '').strip()

    # mensagem vazia (só anexos/embeds) → tira
    if not conteudo:
        try:
            await message.delete()
        except Exception:
            pass
        try:
            aviso = await message.channel.send(
                f'{message.author.mention} {E["box"]} sua sugestão precisa ter '
                f'**texto** — anexos sozinhos não são aceitos.',
                delete_after=8)
        except Exception:
            pass
        return

    # detecta link → bloqueia
    if LINK_RE.search(conteudo):
        try:
            await message.delete()
        except Exception:
            pass
        try:
            await message.channel.send(
                f'{message.author.mention} {E["box"]} sugestões **não podem '
                f'conter links**. Reescreva sem URL.',
                delete_after=8)
        except Exception:
            pass
        return

    # limite: 1 sugestão a cada 24h por usuário
    try:
        ultima = await db.get_ultima_sugestao(
            bot.http_session, message.author.id, message.guild.id)
    except Exception as e:
        print(f'[SUGESTAO] erro ao ler último: {e}', flush=True)
        ultima = None
    if ultima:
        try:
            # PostgREST devolve ISO com fuso (ex: 2026-05-26T22:33:00+00:00)
            ts = datetime.fromisoformat(ultima.replace('Z', '+00:00'))
            agora = datetime.now(timezone.utc)
            passou = agora - ts
            if passou < timedelta(hours=24):
                falta = timedelta(hours=24) - passou
                horas = int(falta.total_seconds() // 3600)
                minutos = int((falta.total_seconds() % 3600) // 60)
                if horas > 0:
                    falta_txt = f'{horas}h {minutos}min'
                else:
                    falta_txt = f'{minutos}min'
                try:
                    await message.delete()
                except Exception:
                    pass
                try:
                    await message.channel.send(
                        f'{message.author.mention} {E["box"]} você já enviou '
                        f'uma sugestão hoje. Tente de novo em **{falta_txt}**.',
                        delete_after=10)
                except Exception:
                    pass
                return
        except Exception as e:
            print(f'[SUGESTAO] erro ao parsear data: {e}', flush=True)

    # vira sugestão: deleta a original e posta o painel
    try:
        await message.delete()
    except Exception:
        pass

    c = discord.ui.Container(accent_color=COR)
    c.add_item(discord.ui.TextDisplay(f'## {E["cloud"]} Nova Sugestão'))
    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.TextDisplay(
        f'{E["seta"]} **Por:** {message.author.mention}\n\n'
        f'{conteudo[:1800]}'))
    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.TextDisplay(
        f'{EMOJI_VOTO_SIM} Concordo  •  {EMOJI_VOTO_NAO} Discordo'))
    v = discord.ui.LayoutView(timeout=None)
    v.add_item(c)

    try:
        msg_post = await message.channel.send(view=v)
        await msg_post.add_reaction(EMOJI_VOTO_SIM)
        await msg_post.add_reaction(EMOJI_VOTO_NAO)
        # registra que o user enviou — só conta DEPOIS do post bem-sucedido
        try:
            await db.marcar_sugestao(
                bot.http_session, message.author.id, message.guild.id)
        except Exception as e:
            print(f'[SUGESTAO] erro ao marcar: {e}', flush=True)
    except Exception as e:
        print(f'[SUGESTAO] falhou ao postar/reagir: {e}', flush=True)


# ════════════════════════════════════════════════════════════
#  /planos  — cliente vê e compra um plano
# ════════════════════════════════════════════════════════════
# URL do banner do painel /planos (troque pela sua imagem se quiser)
PLANOS_BANNER_URL = 'https://i.imgur.com/COLOQUE_SUA_IMAGEM.png'

# Bancos exibidos na seção "Bancos permitidos" do painel /planos
PLANOS_BANCOS = ['Inter Kids', 'Nubank', 'SumUp', 'XP']


class PlanosView(discord.ui.LayoutView):
    def __init__(self, planos):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_color=COR)
        # banner no topo (imagem anexada do bot — assets/banner-planos.png)
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media='attachment://banner-planos.png')
        c.add_item(gallery)
        # título + descrição
        c.add_item(discord.ui.TextDisplay('## ◈ Bot de Mediar — Power Base'))
        c.add_item(discord.ui.TextDisplay(
            'Se você quer mediar automático sem se preocupar em tomar multa, '
            'compre aqui agora seu plano.'))
        c.add_item(discord.ui.Separator())
        # bancos permitidos — iOS tem lista específica, Android aceita qualquer um
        c.add_item(discord.ui.TextDisplay('### ◈ Bancos permitidos'))
        c.add_item(discord.ui.TextDisplay(
            f'{E["settings"]} **iOS:** ' + '  '.join(PLANOS_BANCOS) + '\n'
            f'{E["certo"]} **Android:** qualquer banco'))
        c.add_item(discord.ui.Separator())
        # select de planos (os planos aparecem só aqui, no menu)
        row = discord.ui.ActionRow()
        row.add_item(SelComprarPlano(planos))
        c.add_item(row)
        self.add_item(c)


class SelComprarPlano(discord.ui.Select):
    def __init__(self, planos=None):
        if planos:
            opts = []
            for p in planos[:25]:
                # todos os planos usam o emoji nuvem (cloud) do bot
                opts.append(discord.SelectOption(
                    label=p['nome'], value=str(p['id']),
                    description=f'{p["dias"]}d — R$ {float(p["preco"]):.2f}',
                    emoji=_emoji_para_select(E.get('cloud'))))
        else:
            # registro persistente (após restart): placeholder mínimo válido
            opts = [discord.SelectOption(label='—', value='__noop__')]
        super().__init__(placeholder='Escolher plano para configurar e enviar...',
                         options=opts, custom_id='comprar_plano')

    async def callback(self, inter: discord.Interaction):
        if self.values and self.values[0] == '__noop__':
            await inter.response.send_message(
                'Recarregando o painel… tente de novo.', ephemeral=True)
            return
        plano = next((p for p in await db.listar_planos(bot.http_session)
                      if str(p['id']) == self.values[0]), None)
        if not plano:
            await inter.response.send_message('Plano não encontrado.', ephemeral=True)
            return
        await iniciar_compra(inter, tipo='plano', ref=plano,
                             valor=float(plano['preco']), nome=plano['nome'])


# Views "shell" só para re-registrar os selects após restart (persistência).
# As opções reais são recarregadas do banco no momento do clique.
class PlanosPersistView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_color=COR)
        row = discord.ui.ActionRow()
        row.add_item(SelComprarPlano())
        c.add_item(row)
        self.add_item(c)


class PainelComprasPersistView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_color=COR)
        row = discord.ui.ActionRow()
        row.add_item(SelComprarProduto())
        c.add_item(row)
        self.add_item(c)


@bot.tree.command(name='planos', description='Ver e comprar planos')
async def planos(inter: discord.Interaction):
    lista = await db.listar_planos(bot.http_session)
    if not lista:
        await inter.response.send_message('Nenhum plano disponível.', ephemeral=True)
        return
    await inter.response.send_message(
        view=PlanosView(lista),
        file=discord.File('assets/banner-planos.png', filename='banner-planos.png'))


# ════════════════════════════════════════════════════════════
#  /painelcompras  — painel de vendas V2 com menu de produtos
# ════════════════════════════════════════════════════════════
class PainelComprasView(discord.ui.LayoutView):
    def __init__(self, produtos):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_color=COR)
        # banner no topo (imagem anexada — assets/banner-compra-sala.png)
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media='attachment://banner-compra-sala.png')
        c.add_item(gallery)
        c.add_item(discord.ui.TextDisplay(f'## {E["ticket"]} Painel de Compras'))
        c.add_item(discord.ui.TextDisplay(f'{E["cloud"]} Escolha um produto no menu abaixo pra comprar.'))
        c.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        row.add_item(SelComprarProduto(produtos))
        c.add_item(row)
        self.add_item(c)


class SelComprarProduto(discord.ui.Select):
    def __init__(self, produtos=None):
        if produtos:
            opts = [discord.SelectOption(
                label=p['nome'], value=str(p['id']),
                description=f'R$ {float(p["preco"]):.2f}',
                emoji=_emoji_para_select(E.get('carrinho') or E.get('cart')))
                for p in produtos[:25]]
        else:
            # registro persistente (após restart): placeholder mínimo válido
            opts = [discord.SelectOption(label='—', value='__noop__')]
        super().__init__(placeholder='Escolha um produto…', options=opts,
                         custom_id='comprar_produto')

    async def callback(self, inter: discord.Interaction):
        if self.values and self.values[0] == '__noop__':
            await inter.response.send_message(
                'Recarregando o painel… tente de novo.', ephemeral=True)
            return
        prod = next((p for p in await db.listar_produtos(bot.http_session)
                     if str(p['id']) == self.values[0]), None)
        if not prod:
            await inter.response.send_message('Produto não encontrado.', ephemeral=True)
            return
        estoque_n = await db.contar_estoque(bot.http_session, prod['id'])
        if estoque_n <= 0:
            await inter.response.send_message(
                f'{E["box"]} **{prod["nome"]}** está sem estoque no momento.', ephemeral=True)
            return
        await iniciar_compra(inter, tipo='produto', ref=prod,
                             valor=float(prod['preco']), nome=prod['nome'])


@bot.tree.command(name='painelcompras', description='Postar o painel de compras (admin)')
async def painelcompras(inter: discord.Interaction):
    if not _admin(inter):
        await inter.response.send_message('Só admin.', ephemeral=True)
        return
    lista = await db.listar_produtos(bot.http_session)
    if not lista:
        await inter.response.send_message('Cadastre produtos primeiro.', ephemeral=True)
        return
    await inter.response.send_message(
        view=PainelComprasView(lista),
        file=discord.File('assets/banner-compra-sala.png', filename='banner-compra-sala.png'))


# ════════════════════════════════════════════════════════════
#  WALLET — comissão de vendedores (saldo, saque PIX, lucro)
#    /configwallet  → só o DONO cadastra ID liberado + porcentagem
#    /wallet        → só IDs liberados veem saldo, sacam e veem lucro
# ════════════════════════════════════════════════════════════
DONO_ID = 1268379167519408139  # único que pode usar /configwallet (e /wallet)
# IDs (além do dono) liberados a abrir o /wallet
WALLET_IDS = {936397235401404416}


def _pode_wallet(user_id):
    """True se o usuário pode abrir/usar o /wallet."""
    return user_id == DONO_ID or user_id in WALLET_IDS

# emojis (usa custom do bot quando existir, senão cai no unicode)
def _ew(chave, padrao):
    return E.get(chave, padrao)


async def _creditar_comissoes(venda_id, valor):
    """Credita a comissão de cada ID liberado na venda confirmada.
    Idempotente por (venda_id, user_id): não credita o mesmo vendedor 2x."""
    configs = await db.listar_wallet_configs(bot.http_session)
    for cfg in configs:
        pct = float(cfg.get('porcentagem') or 0)
        if pct <= 0:
            continue
        comissao = round(valor * pct / 100.0, 2)
        if comissao <= 0:
            continue
        try:
            if await db.comissao_ja_creditada(
                    bot.http_session, venda_id, cfg['user_id']):
                continue
            await db.add_wallet_movimento(
                bot.http_session, cfg['user_id'], 'comissao', comissao, venda_id)
            print(f'[WALLET] +R$ {comissao:.2f} ({pct}%) p/ {cfg["user_id"]} '
                  f'venda {venda_id}', flush=True)
        except Exception as e:
            # 409 = já creditado (corrida) → ignora
            print(f'[WALLET] crédito ignorado {cfg["user_id"]}/{venda_id}: {e}', flush=True)


def _resumo_lucro(movimentos):
    """Calcula lucro (só comissões) de hoje, ontem, semana e total."""
    from datetime import datetime, timezone, timedelta
    agora = datetime.now(timezone.utc)
    ini_hoje = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    ini_ontem = ini_hoje - timedelta(days=1)
    ini_semana = ini_hoje - timedelta(days=ini_hoje.weekday())  # segunda
    hoje = ontem = semana = total = 0.0
    for m in movimentos:
        if m['tipo'] != 'comissao':
            continue
        v = float(m['valor'])
        total += v
        try:
            dt = datetime.fromisoformat(str(m['criado_em']).replace('Z', '+00:00'))
        except Exception:
            continue
        if dt >= ini_hoje:
            hoje += v
        elif dt >= ini_ontem:
            ontem += v
        if dt >= ini_semana:
            semana += v
    return {'hoje': round(hoje, 2), 'ontem': round(ontem, 2),
            'semana': round(semana, 2), 'total': round(total, 2)}


class WalletView(discord.ui.LayoutView):
    """Painel V2 da carteira: saldo + tabela de lucro + botões dentro do container."""
    def __init__(self, user_id, saldo, resumo):
        super().__init__(timeout=None)
        cifrao = _ew('settings', '💰')
        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(f'## {cifrao} Minha Carteira'))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.TextDisplay(
            f'{_ew("cart", "💵")} **Saldo disponível**\n'
            f'# R$ {saldo:.2f}'))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.TextDisplay(f'### {_ew("check", "📊")} Lucro'))
        c.add_item(discord.ui.TextDisplay(
            f'{_ew("seta", "📅")} **Hoje:** R$ {resumo["hoje"]:.2f}\n'
            f'{_ew("seta", "📆")} **Ontem:** R$ {resumo["ontem"]:.2f}\n'
            f'{_ew("seta", "🗓️")} **Esta semana:** R$ {resumo["semana"]:.2f}\n'
            f'{_ew("certo", "🏆")} **Total:** R$ {resumo["total"]:.2f}'))
        c.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        row.add_item(BtnSacar())
        row.add_item(BtnAtualizarWallet())
        c.add_item(row)
        self.add_item(c)


class BtnSacar(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Sacar', style=discord.ButtonStyle.success,
                         emoji='💸', custom_id='wallet_sacar')

    async def callback(self, inter: discord.Interaction):
        if not _pode_wallet(inter.user.id):
            await inter.response.send_message('Você não tem carteira liberada.',
                                              ephemeral=True)
            return
        saldo = await db.get_wallet_saldo(bot.http_session, inter.user.id)
        if saldo <= 0:
            await inter.response.send_message(
                f'{_ew("xist", "❌")} Sem saldo pra sacar.', ephemeral=True)
            return
        await inter.response.send_modal(SaqueModal(saldo))


class BtnAtualizarWallet(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Atualizar', style=discord.ButtonStyle.secondary,
                         emoji='🔄', custom_id='wallet_atualizar')

    async def callback(self, inter: discord.Interaction):
        if not _pode_wallet(inter.user.id):
            await inter.response.send_message('Você não tem carteira liberada.',
                                              ephemeral=True)
            return
        saldo = await db.get_wallet_saldo(bot.http_session, inter.user.id)
        movs = await db.listar_wallet_movimentos(bot.http_session, inter.user.id)
        resumo = _resumo_lucro(movs)
        await inter.response.edit_message(
            view=WalletView(inter.user.id, saldo, resumo))


class SaqueModal(discord.ui.Modal, title='Sacar via PIX'):
    def __init__(self, saldo):
        super().__init__()
        self.saldo = saldo
        self.valor = discord.ui.TextInput(
            label=f'Valor (saldo: R$ {saldo:.2f})', placeholder='Ex: 50.00',
            max_length=12)
        self.chave = discord.ui.TextInput(
            label='Chave PIX', placeholder='CPF, e-mail, telefone ou aleatória',
            max_length=80)
        self.tipo = discord.ui.TextInput(
            label='Tipo da chave',
            placeholder='CPF / CNPJ / EMAIL / TELEFONE / CHAVE_ALEATORIA',
            max_length=20)
        self.add_item(self.valor)
        self.add_item(self.chave)
        self.add_item(self.tipo)

    async def on_submit(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True)
        try:
            valor = float(str(self.valor.value).replace(',', '.'))
        except ValueError:
            await inter.followup.send('Valor inválido.', ephemeral=True)
            return
        if valor <= 0:
            await inter.followup.send('Valor tem que ser maior que zero.', ephemeral=True)
            return
        # revalida saldo no banco (evita corrida)
        saldo_atual = await db.get_wallet_saldo(bot.http_session, inter.user.id)
        if valor > saldo_atual:
            await inter.followup.send(
                f'{_ew("xist", "❌")} Saldo insuficiente. Disponível: '
                f'R$ {saldo_atual:.2f}', ephemeral=True)
            return
        tipos_ok = {'CPF', 'CNPJ', 'EMAIL', 'TELEFONE', 'CHAVE_ALEATORIA'}
        tipo_chave = str(self.tipo.value).strip().upper()
        if tipo_chave not in tipos_ok:
            await inter.followup.send(
                'Tipo de chave inválido. Use: CPF, CNPJ, EMAIL, TELEFONE ou '
                'CHAVE_ALEATORIA.', ephemeral=True)
            return
        # solicita o saque na MisticPay principal (saldo do adm)
        res = await pagamento.solicitar_saque_pix(
            bot.http_session, valor, str(self.chave.value), tipo_chave,
            f'Saque wallet {inter.user.id}')
        if not res.get('ok'):
            await inter.followup.send(
                f'{_ew("xist", "❌")} Falha no saque: {res.get("erro")}',
                ephemeral=True)
            return
        # debita o saldo da wallet do usuário (registra o saque)
        try:
            await db.add_wallet_movimento(
                bot.http_session, inter.user.id, 'saque', valor)
        except Exception as e:
            print(f'[WALLET] saque enviado mas falhou registrar débito: {e}', flush=True)
        novo_saldo = await db.get_wallet_saldo(bot.http_session, inter.user.id)
        await inter.followup.send(
            f'{_ew("certo", "✅")} **Saque solicitado!**\n'
            f'{_ew("seta", "➡️")} Valor: R$ {valor:.2f}\n'
            f'{_ew("seta", "➡️")} Status: {res.get("status")}\n'
            f'{_ew("cart", "💵")} Novo saldo: R$ {novo_saldo:.2f}',
            ephemeral=True)


@bot.tree.command(name='wallet', description='Sua carteira de comissões')
async def wallet(inter: discord.Interaction):
    liberado = _pode_wallet(inter.user.id)
    if not liberado:
        await inter.response.send_message(
            'Você não tem permissão pra usar a carteira.', ephemeral=True)
        return
    saldo = await db.get_wallet_saldo(bot.http_session, inter.user.id)
    movs = await db.listar_wallet_movimentos(bot.http_session, inter.user.id)
    resumo = _resumo_lucro(movs)
    await inter.response.send_message(
        view=WalletView(inter.user.id, saldo, resumo), ephemeral=True)


# ─── /configwallet — só o DONO ───
class WalletConfigModal(discord.ui.Modal, title='Liberar ID na carteira'):
    user_id = discord.ui.TextInput(
        label='ID do usuário do Discord', placeholder='Ex: 1268379167519408139',
        max_length=25)
    pct = discord.ui.TextInput(
        label='Porcentagem por venda (%)', placeholder='Ex: 70', max_length=6)

    async def on_submit(self, inter: discord.Interaction):
        uid = ''.join(filter(str.isdigit, str(self.user_id.value)))
        if not uid:
            await inter.response.send_message('ID inválido.', ephemeral=True)
            return
        try:
            p = float(str(self.pct.value).replace(',', '.'))
        except ValueError:
            await inter.response.send_message('Porcentagem inválida.', ephemeral=True)
            return
        if not (0 < p <= 100):
            await inter.response.send_message('Porcentagem tem que ser entre 0 e 100.',
                                              ephemeral=True)
            return
        await db.set_wallet_config(bot.http_session, uid, p)
        configs = await db.listar_wallet_configs(bot.http_session)
        await inter.response.edit_message(view=ConfigWalletView(configs))


class ConfigWalletView(discord.ui.LayoutView):
    def __init__(self, configs):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(f'## {_ew("settings", "⚙️")} Configurar Carteiras'))
        c.add_item(discord.ui.TextDisplay(
            'IDs liberados a usar **/wallet** e a % de cada venda que vira saldo deles.'))
        c.add_item(discord.ui.Separator())
        if configs:
            linhas = '\n'.join(
                f'{_ew("seta", "➡️")} <@{c["user_id"]}> (`{c["user_id"]}`) — '
                f'**{float(c["porcentagem"]):.0f}%**'
                for c in configs)
            c.add_item(discord.ui.TextDisplay(linhas))
        else:
            c.add_item(discord.ui.TextDisplay('_Nenhum ID liberado ainda._'))
        c.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        row.add_item(BtnAddWalletConfig())
        row.add_item(BtnAjustarSaldo())
        c.add_item(row)
        if configs:
            row2 = discord.ui.ActionRow()
            row2.add_item(SelRemoverWalletConfig(configs))
            c.add_item(row2)
        self.add_item(c)


class BtnAjustarSaldo(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Ajustar saldo',
                         style=discord.ButtonStyle.secondary, emoji='✏️')

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != DONO_ID:
            await inter.response.send_message('Só o dono.', ephemeral=True)
            return
        await inter.response.send_modal(AjustarSaldoModal())


class AjustarSaldoModal(discord.ui.Modal, title='Ajustar saldo manualmente'):
    user_id = discord.ui.TextInput(
        label='ID do usuário', placeholder='Ex: 936397235401404416', max_length=25)
    valor = discord.ui.TextInput(
        label='Valor (use - para debitar)', placeholder='Ex: 8.40  ou  -5.00',
        max_length=12)

    async def on_submit(self, inter: discord.Interaction):
        uid = ''.join(filter(str.isdigit, str(self.user_id.value)))
        if not uid:
            await inter.response.send_message('ID inválido.', ephemeral=True)
            return
        try:
            v = float(str(self.valor.value).replace(',', '.'))
        except ValueError:
            await inter.response.send_message('Valor inválido.', ephemeral=True)
            return
        if v == 0:
            await inter.response.send_message('Valor não pode ser zero.', ephemeral=True)
            return
        # crédito = comissao (entra) | débito = saque (sai)
        if v > 0:
            await db.add_wallet_movimento(bot.http_session, uid, 'comissao', v)
        else:
            await db.add_wallet_movimento(bot.http_session, uid, 'saque', abs(v))
        saldo = await db.get_wallet_saldo(bot.http_session, uid)
        await inter.response.send_message(
            f'{_ew("certo", "✅")} Ajuste aplicado em <@{uid}>: '
            f'{"+" if v > 0 else "−"}R$ {abs(v):.2f}\n'
            f'{_ew("cart", "💵")} Novo saldo: R$ {saldo:.2f}', ephemeral=True)


class BtnAddWalletConfig(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Liberar / editar ID',
                         style=discord.ButtonStyle.success, emoji='➕')

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != DONO_ID:
            await inter.response.send_message('Só o dono.', ephemeral=True)
            return
        await inter.response.send_modal(WalletConfigModal())


class SelRemoverWalletConfig(discord.ui.Select):
    def __init__(self, configs):
        opts = [discord.SelectOption(
            label=str(c['user_id']),
            description=f'{float(c["porcentagem"]):.0f}% — remover',
            value=str(c['user_id']))
            for c in configs[:25]]
        super().__init__(placeholder='Remover um ID liberado…', options=opts)

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != DONO_ID:
            await inter.response.send_message('Só o dono.', ephemeral=True)
            return
        await db.del_wallet_config(bot.http_session, self.values[0])
        configs = await db.listar_wallet_configs(bot.http_session)
        await inter.response.edit_message(view=ConfigWalletView(configs))


@bot.tree.command(name='configwallet',
                  description='Liberar IDs e % da carteira (só dono)')
async def configwallet(inter: discord.Interaction):
    if inter.user.id != DONO_ID:
        await inter.response.send_message('Só o dono pode usar isso.', ephemeral=True)
        return
    configs = await db.listar_wallet_configs(bot.http_session)
    await inter.response.send_message(view=ConfigWalletView(configs), ephemeral=True)


# View shell pra re-registrar os botões do /wallet após restart.
class WalletPersistView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_color=COR)
        row = discord.ui.ActionRow()
        row.add_item(BtnSacar())
        row.add_item(BtnAtualizarWallet())
        c.add_item(row)
        self.add_item(c)


# ════════════════════════════════════════════════════════════
#  FLUXO DE COMPRA — 3 fases em thread privada
#    Fase 1: Confirmar / Cancelar (auto-fecha em 10 min)
#    Fase 2: PIX com botão "Copiar PIX" + "Já paguei" + "Cancelar"
#    Fase 3: Embed "Pagamento Confirmado" + entrega na DM
#  Cada fase apaga a mensagem da fase anterior.
# ════════════════════════════════════════════════════════════
COR_OK   = discord.Color.from_str('#22c55e')  # verde
COR_FAIL = discord.Color.from_str('#ef4444')  # vermelho
COR_PIX  = discord.Color.from_str('#00BFA5')  # turquesa PIX


async def iniciar_compra(inter, tipo, ref, valor, nome):
    """Abre uma thread privada e posta o painel de Fase 1 (Confirmar/Cancelar)."""
    await inter.response.defer(ephemeral=True)
    canal = inter.channel

    # ── já tem compra ativa? bloqueia ──
    thread_existente_id = _COMPRAS_ATIVAS.get(inter.user.id)
    if thread_existente_id:
        t_existente = inter.guild.get_thread(thread_existente_id)
        if t_existente and not t_existente.archived:
            await inter.followup.send(
                f'{E["box"]} Você já tem uma compra aberta em {t_existente.mention}.\n'
                f'{E["seta"]} Finalize ou cancele aquela antes de abrir outra.',
                ephemeral=True)
            return
        # se a thread sumiu/arquivou e ficou no dict, limpa
        _COMPRAS_ATIVAS.pop(inter.user.id, None)

    # ── checa permissões do bot no canal ──
    perms = canal.permissions_for(inter.guild.me)
    if not (perms.create_private_threads or perms.create_public_threads):
        await inter.followup.send(
            f'{E["box"]} O bot não tem permissão pra criar threads neste canal.\n'
            f'Ative **Criar Tópicos Privados** pro cargo do bot.',
            ephemeral=True)
        return

    # ── abre a thread ──
    nome_thread = f'compra-{inter.user.name}-{nome}'[:90]
    try:
        if perms.create_private_threads:
            thread = await canal.create_thread(
                name=nome_thread,
                type=discord.ChannelType.private_thread,
                invitable=False)
        else:
            thread = await canal.create_thread(
                name=nome_thread,
                type=discord.ChannelType.public_thread)
    except Exception as e:
        await inter.followup.send(
            f'{E["box"]} Não consegui abrir a thread: `{e}`', ephemeral=True)
        return

    # registra como compra ativa do usuário
    _COMPRAS_ATIVAS[inter.user.id] = thread.id

    # adiciona o comprador + membros do cargo de compras (mediadores) na thread
    # truque pra não gerar linha "fulano adicionou X": mention + delete
    mentions = [inter.user.mention]
    cfg = await db.get_config(bot.http_session, inter.guild.id)
    cargo_compras_id = cfg.get('cargo_compras') if cfg else None
    if cargo_compras_id:
        cargo_compras = inter.guild.get_role(int(cargo_compras_id))
        if cargo_compras:
            for m in cargo_compras.members:
                if m.bot or m.id == inter.user.id:
                    continue
                mentions.append(m.mention)
                if len(mentions) >= 90:  # limite seguro de mentions/msg
                    break
    try:
        ping = await thread.send(' '.join(mentions))
        await ping.delete()
    except Exception:
        # fallback: adiciona o comprador via add_user (gera linha de sistema)
        try:
            await thread.add_user(inter.user)
        except Exception:
            pass

    # ── posta o painel de Fase 1 ──
    v = _montar_view_fase1(tipo, ref['id'], valor, nome, inter.user.id,
                           cupom_info=None)
    try:
        await thread.send(view=v)
    except Exception as e:
        await inter.followup.send(
            f'{E["box"]} Erro ao postar painel: `{e}`', ephemeral=True)
        return

    # agenda o auto-fechar em 10 min se ninguém clicar
    _agendar_task(thread.id, _auto_fechar_thread(thread, segundos=600))

    await inter.followup.send(
        f'{E["foguete"]} Sua compra foi aberta em: {thread.mention}',
        ephemeral=True)


async def _auto_fechar_thread(thread, segundos=600):
    """Fecha a thread se ninguém interagir no tempo dado."""
    try:
        await asyncio.sleep(segundos)
    except asyncio.CancelledError:
        return
    try:
        c = discord.ui.Container(accent_color=COR_FAIL)
        c.add_item(discord.ui.TextDisplay(f'## Tempo Esgotado'))
        c.add_item(discord.ui.TextDisplay(
            f'{E["seta"]} Esta compra expirou por inatividade. Arquivando…'))
        v = discord.ui.LayoutView(timeout=None)
        v.add_item(c)
        await thread.send(view=v)
        await asyncio.sleep(2)
        await thread.edit(archived=True, locked=True)
    except Exception:
        pass
    finally:
        _THREAD_TASKS.pop(thread.id, None)
        _liberar_compra(thread.id)


# ────────────────────── FASE 1: Confirmar / Cancelar ──────────────────────
def _montar_view_fase1(tipo, ref_id, valor_original, nome, user_id, cupom_info=None):
    """Monta o painel da Fase 1 (Confirmar/Cancelar + Cupom).

    cupom_info (opcional): dict {'codigo', 'percent', 'valor_final', 'desconto'}
    já resolvido pro plano/produto desta compra. Quando presente e com desconto,
    mostra o valor riscado e o final — e o Confirmar usa o valor final."""
    if cupom_info and cupom_info.get('desconto', 0) > 0:
        valor_final = cupom_info['valor_final']
        desconto = cupom_info['desconto']
    else:
        valor_final, desconto = valor_original, 0.0

    c = discord.ui.Container(accent_color=COR)
    c.add_item(discord.ui.TextDisplay(f'## {E["foguete"]} Confirmar Compra'))
    c.add_item(discord.ui.Separator())

    if cupom_info and desconto > 0:
        d_txt = f'{float(cupom_info["percent"]):.0f}%'
        c.add_item(discord.ui.TextDisplay(
            f'{E["seta"]} **Item:** {nome}\n'
            f'{E["seta"]} **Tipo:** {tipo.capitalize()}\n'
            f'{E["seta"]} ~~R$ {valor_original:.2f}~~  →  '
            f'{_ew("certo", "🏷️")} Cupom **{cupom_info["codigo"]}** ({d_txt})\n'
            f'{E["key"]} **Valor final:** R$ {valor_final:.2f}'))
    else:
        c.add_item(discord.ui.TextDisplay(
            f'{E["seta"]} **Item:** {nome}\n'
            f'{E["seta"]} **Tipo:** {tipo.capitalize()}\n'
            f'{E["key"]} **Valor:** R$ {valor_final:.2f}'))

    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.TextDisplay(
        f'{E["cloud"]} Olá <@{user_id}>, confirme abaixo pra gerar o PIX.\n'
        f'{E["seta"]} _Tem um cupom? Clique em **Cupom** antes de confirmar._\n'
        f'{E["seta"]} _Esta janela fecha sozinha em **10 minutos** sem confirmação._'))
    c.add_item(discord.ui.Separator())
    row = discord.ui.ActionRow()
    # O Confirmar carrega o valor FINAL (com desconto) — é o que vira PIX/venda.
    row.add_item(BtnConfirmarCompra(tipo, ref_id, valor_final, nome, user_id))
    row.add_item(BtnCupom(tipo, ref_id, valor_original, nome, user_id))
    if tipo == 'plano':
        row.add_item(BtnRenovacao(ref_id, user_id))
    row.add_item(BtnCancelarCompra(user_id))
    c.add_item(row)
    v = discord.ui.LayoutView(timeout=None)
    v.add_item(c)
    return v


class BtnRenovacao(discord.ui.Button):
    """Botão ao lado do Cupom: renovação. Em vez de pagar e configurar do zero,
    o cliente informa o ID de login/Discord e o bot soma os dias automático."""
    def __init__(self, ref_id, user_id):
        super().__init__(label='Renovação', style=discord.ButtonStyle.primary, emoji='🔄')
        self.ref_id = ref_id
        self.user_id = user_id

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != self.user_id:
            await inter.response.send_message('Só quem abriu a compra pode usar isso.', ephemeral=True)
            return
        dias = 0
        try:
            planos = await db.listar_planos(bot.http_session)
            p = next((p for p in planos if str(p['id']) == str(self.ref_id)), None)
            if p:
                dias = int(p['dias'])
        except Exception:
            dias = 0
        if dias <= 0:
            await inter.response.send_message(
                'Não consegui ler os dias do plano. Chame o suporte.', ephemeral=True)
            return
        await inter.response.send_modal(RenovacaoModal(dias))


class CupomInputModal(discord.ui.Modal, title='Aplicar cupom'):
    def __init__(self, tipo, ref_id, valor_original, nome, user_id):
        super().__init__()
        self.tipo = tipo
        self.ref_id = ref_id
        self.valor_original = valor_original
        self.nome = nome
        self.user_id = user_id
        self.codigo = discord.ui.TextInput(
            label='Código do cupom', max_length=40,
            placeholder='Digite o código do cupom')
        self.add_item(self.codigo)

    async def on_submit(self, inter: discord.Interaction):
        codigo = str(self.codigo.value).strip().upper()
        cupom = await db.get_cupom(bot.http_session, codigo)
        if not cupom:
            await inter.response.send_message(
                f'{E["box"]} Cupom **{codigo}** inválido ou inativo.', ephemeral=True)
            return
        # Cupom agora é POR PLANO: busca a % configurada pra ESTE plano.
        # Sem % pro plano → cupom não vale aqui.
        percent = await db.get_percent_cupom_plano(
            bot.http_session, cupom['id'], self.ref_id)
        if not percent:
            await inter.response.send_message(
                f'{E["box"]} O cupom **{codigo}** não dá desconto neste plano.',
                ephemeral=True)
            return
        valor_final, desconto = db.aplicar_desconto_percent(self.valor_original, percent)
        cupom_info = {
            'codigo': cupom['codigo'],
            'percent': percent,
            'valor_final': valor_final,
            'desconto': desconto,
        }
        # Re-renderiza o painel da Fase 1 com o desconto aplicado.
        v = _montar_view_fase1(self.tipo, self.ref_id, self.valor_original,
                               self.nome, self.user_id, cupom_info=cupom_info)
        try:
            await inter.response.edit_message(view=v)
        except Exception:
            await inter.response.send_message(
                f'{E["certo"]} Cupom **{codigo}** aplicado!', ephemeral=True)


class BtnCupom(discord.ui.Button):
    def __init__(self, tipo, ref_id, valor_original, nome, user_id):
        self.tipo = tipo
        self.ref_id = ref_id
        self.valor_original = valor_original
        self.nome = nome
        self.user_id = user_id
        super().__init__(label='Cupom', style=discord.ButtonStyle.secondary,
                         emoji='🏷️')

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != self.user_id:
            await inter.response.send_message('Esta compra não é sua.', ephemeral=True)
            return
        await inter.response.send_modal(CupomInputModal(
            self.tipo, self.ref_id, self.valor_original, self.nome, self.user_id))


class BtnConfirmarCompra(discord.ui.Button):
    def __init__(self, tipo, ref_id, valor, nome, user_id):
        self.tipo = tipo
        self.ref_id = ref_id
        self.valor = valor
        self.nome = nome
        self.user_id = user_id
        super().__init__(label='Confirmar Compra',
                         style=discord.ButtonStyle.success, emoji='✅')

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != self.user_id:
            await inter.response.send_message(
                'Esta compra não é sua.', ephemeral=True)
            return
        await inter.response.defer()
        thread = inter.channel
        if not isinstance(thread, discord.Thread):
            await inter.followup.send('Isso não é uma thread de compra.', ephemeral=True)
            return

        # cancela o auto-fechar — quem manda agora é o monitor do PIX
        _cancelar_task(thread.id)

        # cria a venda
        try:
            venda = await db.criar_venda(
                bot.http_session, inter.user.id, self.tipo, self.ref_id, self.valor)
        except Exception as e:
            await inter.followup.send(
                f'{E["box"]} Erro ao criar venda: `{e}`', ephemeral=True)
            return

        # gera a cobrança PIX
        cobranca = await pagamento.criar_cobranca_pix(
            bot.http_session, valor=self.valor,
            descricao=f'{self.nome} ({self.tipo})', venda_id=venda['id'])
        if not cobranca.get('ok'):
            await inter.followup.send(
                f'{E["box"]} Não consegui gerar a cobrança: '
                f'{cobranca.get("erro","erro")}.', ephemeral=True)
            return
        if cobranca.get('txid'):
            try:
                await db._patch(bot.http_session, 'vendas',
                                {'id': f'eq.{venda["id"]}'},
                                {'txid': cobranca['txid']})
            except Exception:
                pass

        # posta a Fase 2 e APAGA a Fase 1
        await _postar_fase2_pix(thread, venda['id'], self.nome, self.valor,
                                cobranca.get('pix_copia_cola', ''))
        try:
            await inter.message.delete()
        except Exception:
            pass


class BtnCancelarCompra(discord.ui.Button):
    def __init__(self, user_id):
        self.user_id = user_id
        super().__init__(label='Cancelar',
                         style=discord.ButtonStyle.danger, emoji='❌')

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != self.user_id:
            await inter.response.send_message(
                'Esta compra não é sua.', ephemeral=True)
            return
        await inter.response.defer()
        thread = inter.channel
        if not isinstance(thread, discord.Thread):
            await inter.followup.send('Isso não é uma thread de compra.', ephemeral=True)
            return
        _cancelar_task(thread.id)
        try:
            await inter.message.delete()
        except Exception:
            pass
        c = discord.ui.Container(accent_color=COR_FAIL)
        c.add_item(discord.ui.TextDisplay(f'## {E["box"]} Compra Cancelada'))
        c.add_item(discord.ui.TextDisplay(
            f'{E["seta"]} Você cancelou esta compra. Arquivando a thread…'))
        v = discord.ui.LayoutView(timeout=None)
        v.add_item(c)
        try:
            await thread.send(view=v)
            await asyncio.sleep(2)
            await thread.edit(archived=True, locked=True)
        except Exception:
            pass
        _liberar_compra(thread.id)


def _dono_da_thread(thread: discord.Thread) -> int:
    """(legado) Não usar — confiar nos botões com user_id passado explicitamente."""
    return thread.owner_id or 0


# ────────────────────── FASE 2: PIX ──────────────────────
async def _postar_fase2_pix(thread, venda_id, nome, valor, copia_cola):
    """Posta o painel de PIX (Fase 2) e dispara o monitor automático de pagamento."""
    c = discord.ui.Container(accent_color=COR_PIX)
    c.add_item(discord.ui.TextDisplay(f'## {E["key"]} Pagamento PIX'))
    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.TextDisplay(
        f'{E["seta"]} **Item:** {nome}\n'
        f'{E["key"]} **Valor:** R$ {valor:.2f}'))
    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.TextDisplay(f'{E["cloud"]} **PIX Copia e Cola:**'))
    if copia_cola:
        c.add_item(discord.ui.TextDisplay(f'```{copia_cola}```'))
    else:
        c.add_item(discord.ui.TextDisplay('_(PIX indisponível — chame o suporte)_'))
    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.TextDisplay(
        f'{E["seta"]} Clique em **Copiar PIX** pra receber o código limpo.\n'
        f'{E["seta"]} Após pagar, é confirmado **automaticamente** em poucos segundos.'))
    row = discord.ui.ActionRow()
    row.add_item(BtnCopiarPix(copia_cola))
    row.add_item(BtnCancelarPix(venda_id))
    c.add_item(row)
    v = discord.ui.LayoutView(timeout=None)
    v.add_item(c)
    msg_pix = await thread.send(view=v)

    # dispara monitor automático (poll a cada 15s, por até 20min)
    _agendar_task(thread.id, _monitor_pagamento(
        thread, venda_id, msg_pix, nome, valor))


async def _monitor_pagamento(thread, venda_id, msg_pix, nome, valor,
                              intervalo=15, tentativas=80):
    """Polla o status da venda. Quando paga, dispara Fase 3."""
    try:
        for _ in range(tentativas):
            await asyncio.sleep(intervalo)
            venda = await db.get_venda(bot.http_session, venda_id)
            if not venda:
                return
            if venda['status'] in ('entregue', 'cancelado'):
                return
            if venda['status'] == 'pago':
                # já marcada paga: garante o crédito (idempotente) e sai
                try:
                    await _creditar_comissoes(
                        venda_id, float(venda.get('valor') or valor))
                except Exception as e:
                    print(f'[WALLET] erro crédito (status pago) venda '
                          f'{venda_id}: {e}', flush=True)
                return
            pago = await pagamento.checar_pago(bot.http_session, venda.get('txid'))
            if pago:
                try:
                    await db.marcar_venda_paga(bot.http_session, venda_id)
                except Exception:
                    pass
                # credita a comissão imediatamente (idempotente por venda)
                try:
                    await _creditar_comissoes(
                        venda_id, float(venda.get('valor') or valor))
                except Exception as e:
                    print(f'[WALLET] erro crédito (pago agora) venda '
                          f'{venda_id}: {e}', flush=True)
                await _processar_pagamento_confirmado(
                    thread, venda_id, msg_pix, nome, valor, membro=None)
                return
        # esgotou → fecha a thread
        try:
            c = discord.ui.Container(accent_color=COR_FAIL)
            c.add_item(discord.ui.TextDisplay(f'## PIX Expirado'))
            c.add_item(discord.ui.TextDisplay(
                f'{E["seta"]} O tempo do PIX acabou. Abra outra compra se quiser tentar de novo.'))
            v = discord.ui.LayoutView(timeout=None)
            v.add_item(c)
            await thread.send(view=v)
            await asyncio.sleep(2)
            await thread.edit(archived=True, locked=True)
        except Exception:
            pass
    except asyncio.CancelledError:
        return
    finally:
        _THREAD_TASKS.pop(thread.id, None)
        # libera só se a thread foi de fato encerrada (timeout do pix)
        # — se foi cancelada por outro motivo (ex: confirmação manual virou Fase 3),
        # quem chamou já lida com a liberação.
        # Aqui não tem como distinguir bem; libera só se a venda final está fechada.
        try:
            v = await db.get_venda(bot.http_session, venda_id)
            if not v or v['status'] in ('cancelado', 'pendente'):
                _liberar_compra(thread.id)
        except Exception:
            pass


class BtnCopiarPix(discord.ui.Button):
    """Envia o copia-cola limpo (sem ```, sem emoji, sem nada em volta)."""
    def __init__(self, copia_cola):
        self.copia_cola = copia_cola or ''
        super().__init__(label='Copiar PIX',
                         style=discord.ButtonStyle.primary, emoji='📋')

    async def callback(self, inter: discord.Interaction):
        if not self.copia_cola:
            await inter.response.send_message(
                f'{E["box"]} PIX indisponível.', ephemeral=True)
            return
        # APENAS o código bruto, ephemeral, pra dar long-press → copiar no celular
        await inter.response.send_message(self.copia_cola, ephemeral=True)


class BtnCancelarPix(discord.ui.Button):
    def __init__(self, venda_id):
        self.venda_id = venda_id
        super().__init__(label='Cancelar',
                         style=discord.ButtonStyle.danger, emoji='❌')

    async def callback(self, inter: discord.Interaction):
        await inter.response.defer()
        thread = inter.channel
        if isinstance(thread, discord.Thread):
            _cancelar_task(thread.id)
        try:
            await db._patch(bot.http_session, 'vendas',
                            {'id': f'eq.{self.venda_id}'},
                            {'status': 'cancelado'})
        except Exception:
            pass
        try:
            await inter.message.delete()
        except Exception:
            pass
        c = discord.ui.Container(accent_color=COR_FAIL)
        c.add_item(discord.ui.TextDisplay(f'## {E["box"]} Compra Cancelada'))
        c.add_item(discord.ui.TextDisplay(
            f'{E["seta"]} Você cancelou esta compra. Arquivando a thread…'))
        v = discord.ui.LayoutView(timeout=None)
        v.add_item(c)
        if isinstance(thread, discord.Thread):
            try:
                await thread.send(view=v)
                await asyncio.sleep(2)
                await thread.edit(archived=True, locked=True)
            except Exception:
                pass
            _liberar_compra(thread.id)


# ────────────────────── Configurar nick (após compra de plano) ──────────────────────
class NickModal(discord.ui.Modal, title='Configurar Nick'):
    """Modal que pede o nome do ADM para setar o nick com a data de expiração."""
    nome_adm = discord.ui.TextInput(
        label='Seu nome de ADM na organização',
        placeholder='Ex: Carlos, Pedro, NomeDoJogo…',
        min_length=2, max_length=24, required=True)

    def __init__(self, user_id, data_expira_txt, nome_atual=None):
        super().__init__()
        self.user_id = user_id
        self.data_expira_txt = data_expira_txt  # 'DD/MM'
        # Na renovação, pré-preenche o nome que já está no nick (sem a data),
        # pra o cliente não ter que digitar de novo — é só confirmar.
        if nome_atual:
            self.nome_adm.default = nome_atual[:24]

    async def on_submit(self, inter: discord.Interaction):
        if inter.user.id != self.user_id:
            await inter.response.send_message('Esse painel não é seu.', ephemeral=True)
            return
        nome_in = self.nome_adm.value.strip()
        novo_nick = f'{nome_in} {self.data_expira_txt}'
        # nick do Discord tem limite de 32 caracteres
        if len(novo_nick) > 32:
            sobra = 32 - (len(self.data_expira_txt) + 1)
            novo_nick = f'{nome_in[:sobra]} {self.data_expira_txt}'
        try:
            await inter.user.edit(nick=novo_nick, reason='Compra de plano')
            await inter.response.send_message(
                f'{E["foguete"]} Nick atualizado pra **{novo_nick}**.',
                ephemeral=True)
        except discord.Forbidden:
            await inter.response.send_message(
                f'{E["box"]} Não consegui mudar seu nick — meu cargo precisa '
                f'estar **acima** do seu na hierarquia. Avise um admin.',
                ephemeral=True)
        except Exception as e:
            await inter.response.send_message(
                f'{E["box"]} Erro ao mudar nick: `{e}`', ephemeral=True)


class BtnConfigurarNick(discord.ui.Button):
    def __init__(self, user_id, data_expira_txt):
        self.user_id = user_id
        self.data_expira_txt = data_expira_txt
        super().__init__(label='Configurar Meu Nick',
                         style=discord.ButtonStyle.primary, emoji='📝')

    async def callback(self, inter: discord.Interaction):
        if inter.user.id != self.user_id:
            await inter.response.send_message(
                'Esse painel não é seu.', ephemeral=True)
            return
        # Tenta reaproveitar o nome que já está no nick (tirando a data no fim),
        # pra pré-preencher na renovação.
        nome_atual = None
        nick = getattr(inter.user, 'nick', None) or inter.user.display_name
        if nick:
            nome_atual = re.sub(r'\s*\d{1,2}/\d{1,2}\s*$', '', nick).strip() or None
        await inter.response.send_modal(
            NickModal(self.user_id, self.data_expira_txt, nome_atual))


# ────────────────────── FASE 3: Pagamento Confirmado + Entrega na DM ──────────────────────
def _data_br_agora():
    """Agora no fuso de Brasília (UTC-3)."""
    return datetime.now(timezone(timedelta(hours=-3)))


def _extrair_venc_do_nick(nick, agora):
    """Lê uma data DD/MM no fim do nick (ex: 'MIGUEL 08/06') e devolve um
    datetime com o ano certo. Como o nick só tem dia/mês, assume o ano atual;
    se a data já passou há muito (>300 dias), considera que é do ano que vem
    (vira do ano). Retorna None se não achar data no nick."""
    if not nick:
        return None
    m = re.search(r'(\d{1,2})/(\d{1,2})\s*$', nick.strip())
    if not m:
        return None
    dia, mes = int(m.group(1)), int(m.group(2))
    if not (1 <= dia <= 31 and 1 <= mes <= 12):
        return None
    try:
        cand = agora.replace(month=mes, day=dia, hour=23, minute=59,
                             second=0, microsecond=0)
    except ValueError:
        return None
    # Corrige virada de ano: se a data ficou muito no passado, é do ano seguinte.
    if (agora - cand).days > 300:
        try:
            cand = cand.replace(year=cand.year + 1)
        except ValueError:
            pass
    return cand


def _calcular_nova_expiracao(membro, dias_plano):
    """Regra de renovação: se o cliente AINDA está ativo (a data no nick é
    futura), soma os dias NOVOS em cima do vencimento atual. Se já venceu (ou
    não tem data no nick), conta a partir de hoje. Retorna (datetime, 'DD/MM').

    Ex.: nick 'MIGUEL 08/06', hoje 09/06 (venceu ontem) + 3 dias → 12/06.
         nick 'MIGUEL 15/06', hoje 09/06 (ativo) + 3 dias → 18/06.
    """
    agora = _data_br_agora()
    base = agora
    nick_atual = getattr(membro, 'nick', None) or getattr(membro, 'display_name', None)
    venc_atual = _extrair_venc_do_nick(nick_atual, agora)
    if venc_atual and venc_atual > agora:
        # ainda ativo → soma em cima do que já tem (não perde os dias restantes)
        base = venc_atual
    nova = base + timedelta(days=dias_plano)
    return nova, nova.strftime('%d/%m')



async def _processar_pagamento_confirmado(thread, venda_id, msg_pix,
                                          nome, valor, membro=None):
    """Posta a Fase 3 na thread, apaga a Fase 2 e entrega o produto na DM.
    Idempotente: se a venda já está 'entregue', sai sem fazer nada."""
    venda = await db.get_venda(bot.http_session, venda_id)
    if not venda:
        return
    if venda['status'] == 'entregue':
        # outro caminho (monitor automático ou Já paguei) já entregou
        return

    # Se veio sem membro (ex.: caminho do monitor automático de PIX), resolve o
    # membro pelo user_id da venda — assim o vencimento/assinatura é registrado E
    # o ticket automático abre mesmo quando o pagamento é detectado sozinho.
    if membro is None:
        try:
            _uid_venda = int(str(venda.get('user_id') or '').strip())
            _g = getattr(thread, 'guild', None)
            if _g is not None and _uid_venda:
                membro = _g.get_member(_uid_venda)
                if membro is None:
                    membro = await _g.fetch_member(_uid_venda)
        except Exception as _e_m:
            print(f'[ENTREGA] não consegui resolver o membro da venda {venda_id}: {_e_m}', flush=True)
            membro = None

    # ── crédito de comissão na wallet dos IDs liberados (idempotente por venda) ──
    try:
        await _creditar_comissoes(venda_id, float(venda.get('valor') or valor))
    except Exception as e:
        print(f'[WALLET] erro ao creditar comissão da venda {venda_id}: {e}', flush=True)

    # resolve o membro (pode vir None do background monitor)
    if membro is None:
        try:
            membro = thread.guild.get_member(int(venda['user_id'])) \
                or await thread.guild.fetch_member(int(venda['user_id']))
        except Exception:
            membro = None

    # entrega o conteúdo
    conteudo_dm = ''
    if venda['tipo'] == 'produto':
        item = await db.pegar_um_estoque(bot.http_session, venda['ref_id'])
        if not item:
            try:
                c = discord.ui.Container(accent_color=COR_FAIL)
                c.add_item(discord.ui.TextDisplay(f'## {E["box"]} Estoque esgotado!'))
                c.add_item(discord.ui.TextDisplay(
                    f'{E["seta"]} Pagamento confirmado, mas o estoque acabou. '
                    f'Abra um ticket pra resolver.'))
                v = discord.ui.LayoutView(timeout=None)
                v.add_item(c)
                await thread.send(view=v)
            except Exception:
                pass
            return
        conteudo_dm = item
    else:  # plano → cargo automático
        planos = await db.listar_planos(bot.http_session)
        plano = next((p for p in planos
                      if str(p['id']) == str(venda['ref_id'])), None)
        cargo_id = plano.get('cargo_id') if plano else None
        if not plano:
            print(f'[CARGO-PLANO] venda {venda_id}: plano ref_id={venda.get("ref_id")} '
                  f'não encontrado na lista.', flush=True)
            conteudo_dm = f'Plano: {nome}.'
        elif not cargo_id:
            print(f'[CARGO-PLANO] venda {venda_id}: plano "{plano["nome"]}" SEM cargo_id '
                  f'configurado — defina em /botconfig.', flush=True)
            conteudo_dm = f'Plano: {plano["nome"]} ({plano["dias"]} dias). (sem cargo configurado)'
        elif not membro:
            print(f'[CARGO-PLANO] venda {venda_id}: membro {venda.get("user_id")} NÃO resolvido '
                  f'(intent Server Members ligado no portal?) — cargo não aplicado.', flush=True)
            conteudo_dm = (f'Plano: {plano["nome"]} ({plano["dias"]} dias). '
                           f'⚠️ Não te encontrei no servidor pra dar o cargo — chame o suporte.')
        else:
            # get_role olha só o cache; se falhar, varre a lista de roles do guild.
            cargo = thread.guild.get_role(int(cargo_id)) \
                or discord.utils.get(thread.guild.roles, id=int(cargo_id))
            if cargo is None:
                print(f'[CARGO-PLANO] venda {venda_id}: cargo id={cargo_id} NÃO existe no '
                      f'servidor (deletado/recriado?) — reconfigure em /botconfig.', flush=True)
                conteudo_dm = (f'Plano: {plano["nome"]} ({plano["dias"]} dias). '
                               f'⚠️ O cargo configurado não existe mais — reconfigure no /botconfig.')
            else:
                try:
                    await membro.add_roles(cargo, reason='Compra de plano')
                    print(f'[CARGO-PLANO] venda {venda_id}: cargo "{cargo.name}" dado a {membro} ✓',
                          flush=True)
                    conteudo_dm = (
                        f'Plano: {plano["nome"]}\n'
                        f'Duração: {plano["dias"]} dias\n'
                        f'Cargo liberado: {cargo.name}')
                except discord.Forbidden:
                    # Causa #1: cargo do bot abaixo do cargo a dar, ou sem permissão.
                    print(f'[CARGO-PLANO] venda {venda_id}: FORBIDDEN ao dar "{cargo.name}". '
                          f'O cargo do BOT precisa estar ACIMA de "{cargo.name}" na lista de '
                          f'cargos do servidor E o bot precisa da permissão "Gerenciar Cargos".',
                          flush=True)
                    conteudo_dm = (f'Plano: {plano["nome"]} ({plano["dias"]} dias). '
                                   f'⚠️ Não consegui dar o cargo (permissão/hierarquia) — chame o suporte.')
                except Exception as e:
                    print(f'[CARGO-PLANO] venda {venda_id}: erro inesperado ao dar cargo: '
                          f'{type(e).__name__}: {e}', flush=True)
                    conteudo_dm = (f'Plano: {plano["nome"]} ({plano["dias"]} dias). '
                                   f'⚠️ Erro ao dar o cargo — chame o suporte.')

    # cargo de cliente
    cfg = await db.get_config(bot.http_session, thread.guild.id)
    if cfg and cfg.get('cargo_cliente') and membro:
        cc = thread.guild.get_role(int(cfg['cargo_cliente'])) \
            or discord.utils.get(thread.guild.roles, id=int(cfg['cargo_cliente']))
        if cc:
            try:
                await membro.add_roles(cc, reason='Cliente')
                print(f'[CARGO-CLIENTE] venda {venda_id}: cargo "{cc.name}" dado a {membro} ✓',
                      flush=True)
            except discord.Forbidden:
                print(f'[CARGO-CLIENTE] venda {venda_id}: FORBIDDEN ao dar "{cc.name}" — '
                      f'cargo do bot precisa estar ACIMA dele + permissão Gerenciar Cargos.',
                      flush=True)
            except Exception as e:
                print(f'[CARGO-CLIENTE] venda {venda_id}: erro ao dar cargo: '
                      f'{type(e).__name__}: {e}', flush=True)
        else:
            print(f'[CARGO-CLIENTE] venda {venda_id}: cargo_cliente id={cfg["cargo_cliente"]} '
                  f'não existe no servidor.', flush=True)

    # apaga a Fase 2 (painel do PIX)
    try:
        if msg_pix:
            await msg_pix.delete()
    except Exception:
        pass

    # calcula data de expiração se for plano (pra mostrar no painel + usar no nick)
    eh_plano = (venda['tipo'] == 'plano')
    dias_plano = None
    data_expira_txt = None
    if eh_plano:
        planos_all = await db.listar_planos(bot.http_session)
        p_atual = next((p for p in planos_all
                        if str(p['id']) == str(venda['ref_id'])), None)
        if p_atual:
            dias_plano = int(p_atual['dias'])
            # Renovação inteligente: se o cliente ainda está ativo, soma os dias
            # em cima do vencimento atual (lido do nick); se venceu, conta de hoje.
            if membro is not None:
                data_expira, data_expira_txt = _calcular_nova_expiracao(membro, dias_plano)
            else:
                data_expira = _data_br_agora() + timedelta(days=dias_plano)
                data_expira_txt = data_expira.strftime('%d/%m')

            # Registra/atualiza a assinatura pra o bot remover cargo+nick quando
            # vencer. Guarda o cargo do plano e o nome base (sem a data).
            if membro is not None:
                try:
                    _nick_atual = getattr(membro, 'nick', None) or membro.display_name
                    _nome_base = re.sub(r'\s*\d{1,2}/\d{1,2}\s*$', '', _nick_atual or '').strip() or None
                    await db.registrar_assinatura(
                        bot.http_session, membro.id, thread.guild.id,
                        cargo_id, _nome_base, data_expira.isoformat())
                    # Arma o TEMPORIZADOR exato já (sem esperar o loop de rede).
                    _agendar_expiracao({
                        'user_id': str(membro.id), 'guild_id': str(thread.guild.id),
                        'cargo_id': cargo_id, 'nome_base': _nome_base,
                        'vence_em': data_expira.isoformat()})
                except Exception as e:
                    print(f'[ASSINATURA] venda {venda_id}: falha ao registrar: {e}', flush=True)

    # posta a Fase 3 na thread
    c = discord.ui.Container(accent_color=COR_OK)
    c.add_item(discord.ui.TextDisplay(f'## Pagamento Confirmado!'))
    c.add_item(discord.ui.Separator())
    info = (
        f'{E["seta"]} **Item:** {nome}\n'
        f'{E["key"]} **Valor:** R$ {float(valor):.2f}\n'
        f'{E["seta"]} **Status:** Pago e liberado')
    if data_expira_txt:
        info += f'\n{E["seta"]} **Expira em:** {data_expira_txt}'
    c.add_item(discord.ui.TextDisplay(info))
    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.TextDisplay(
        f'{E["cloud"]} Sua entrega foi enviada na **DM**. '
        f'Se a DM estiver fechada, abra um ticket.'))
    # se for plano e o membro está aqui, oferece pra configurar o nick
    if eh_plano and membro and data_expira_txt:
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.TextDisplay(
            f'{E["foguete"]} **Defina seu nick na comunidade.** '
            f'Vai ficar `<Seu Nome> {data_expira_txt}`.'))
        row = discord.ui.ActionRow()
        row.add_item(BtnConfigurarNick(membro.id, data_expira_txt))
        c.add_item(row)
    v = discord.ui.LayoutView(timeout=None)
    v.add_item(c)
    try:
        await thread.send(view=v)
    except Exception:
        pass

    # Após a compra: abre o TICKET automático e posta `.iniciar` pro atendente IA.
    # (A RENOVAÇÃO é tratada ANTES, pelo botão "Renovação" ao lado do Cupom — quem
    # renova nem chega aqui; soma os dias na hora sem abrir ticket.)
    try:
        canal_base = getattr(thread, 'parent', None)
        if canal_base is not None and membro is not None:
            bot.loop.create_task(_abrir_ticket_atendente(membro, canal_base))
        else:
            print(f'[ATENDENTE] não abri ticket (canal_base={canal_base}, membro={membro}).', flush=True)
    except Exception as e:
        print(f'[ATENDENTE] falha ao abrir ticket: {e}', flush=True)

    # entrega na DM
    dm_ok = False
    if membro and conteudo_dm:
        try:
            cdm = discord.ui.Container(accent_color=COR_OK)
            cdm.add_item(discord.ui.TextDisplay(f'## Compra Liberada'))
            cdm.add_item(discord.ui.Separator())
            cdm.add_item(discord.ui.TextDisplay(
                f'{E["seta"]} **Item:** {nome}\n'
                f'{E["key"]} **Valor:** R$ {float(valor):.2f}'))
            cdm.add_item(discord.ui.Separator())
            cdm.add_item(discord.ui.TextDisplay(f'{E["cloud"]} **Seu conteúdo:**'))
            cdm.add_item(discord.ui.TextDisplay(f'```{conteudo_dm}```'))
            cdm.add_item(discord.ui.Separator())
            cdm.add_item(discord.ui.TextDisplay(
                f'{E["foguete"]} Obrigado pela compra!'))
            vdm = discord.ui.LayoutView(timeout=None)
            vdm.add_item(cdm)
            await membro.send(view=vdm)
            dm_ok = True
        except discord.Forbidden:
            dm_ok = False
        except Exception:
            dm_ok = False

    if not dm_ok and membro:
        # DM fechada — manda o conteúdo na própria thread como fallback
        try:
            cf = discord.ui.Container(accent_color=COR_FAIL)
            cf.add_item(discord.ui.TextDisplay(
                f'## {E["box"]} Não consegui te chamar na DM'))
            cf.add_item(discord.ui.TextDisplay(
                f'{E["seta"]} {membro.mention}, sua DM parece fechada. '
                f'Segue aqui mesmo:'))
            cf.add_item(discord.ui.TextDisplay(f'```{conteudo_dm}```'))
            vf = discord.ui.LayoutView(timeout=None)
            vf.add_item(cf)
            await thread.send(view=vf)
        except Exception:
            pass

    # marca como entregue
    try:
        await db.marcar_venda_entregue(bot.http_session, venda_id)
    except Exception:
        pass

    # log de venda no canal_logs_vendas (se configurado)
    try:
        cfg = await db.get_config(bot.http_session, thread.guild.id)
        canal_logs_vendas_id = cfg.get('canal_logs_vendas') if cfg else None
        if canal_logs_vendas_id:
            canal_log = thread.guild.get_channel(int(canal_logs_vendas_id))
            if canal_log:
                clog = discord.ui.Container(accent_color=COR_OK)
                clog.add_item(discord.ui.TextDisplay(
                    f'## {E["key"]} Venda Concluída'))
                clog.add_item(discord.ui.Separator())
                user_mention = membro.mention if membro else \
                    f'<@{venda.get("user_id","?")}>'
                clog.add_item(discord.ui.TextDisplay(
                    f'{E["ticket"]} **Comprador:** {user_mention}\n'
                    f'{E["foguete"]} **Item:** {nome}\n'
                    f'{E["seta"]} **Tipo:** {venda.get("tipo","?").capitalize()}\n'
                    f'{E["key"]} **Valor:** R$ {float(valor):.2f}\n'
                    f'{E["cloud"]} **TXID:** `{venda.get("txid") or "—"}`\n'
                    f'{E["seta"]} **Venda ID:** `{venda_id}`'))
                vlog = discord.ui.LayoutView(timeout=None)
                vlog.add_item(clog)
                await canal_log.send(view=vlog)
    except Exception as e:
        print(f'[LOG VENDAS] falhou: {e}', flush=True)

    # libera o usuário pra abrir outra compra agora
    # (não precisa esperar a thread arquivar)
    _liberar_compra(thread.id)

    # arquiva a thread depois de um tempo pra dar tempo de ler
    async def _arquivar_depois():
        try:
            await asyncio.sleep(120)
            await thread.edit(archived=True, locked=True)
        except Exception:
            pass
    asyncio.create_task(_arquivar_depois())


# ════════════════════════════════════════════════════════════
#  /ticket  — painel com menu (Suporte/Compras/Dúvidas) → abre thread
# ════════════════════════════════════════════════════════════
TICKET_OPCOES = [
    ('Renovação', 'Renovar seu plano atual', '🔄'),
    ('Suporte', 'Precisa de ajuda ou suporte', '🛟'),
    ('Compras', 'Dúvidas ou problema com compra', '🛒'),
    ('Dúvidas', 'Tirar uma dúvida geral', '❓'),
]


class TicketPainelView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(f'## {E["ticket"]} Central de Atendimento'))
        c.add_item(discord.ui.TextDisplay(
            f'{E["cloud"]} Escolha abaixo o tipo de atendimento. '
            f'Um canal privado será aberto pra você.'))
        c.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        row.add_item(SelAbrirTicket())
        c.add_item(row)
        self.add_item(c)


class SelAbrirTicket(discord.ui.Select):
    def __init__(self):
        opts = [discord.SelectOption(label=nome, description=desc, emoji=emoji, value=nome)
                for nome, desc, emoji in TICKET_OPCOES]
        super().__init__(placeholder='Selecione o atendimento…', options=opts,
                         custom_id='abrir_ticket')

    async def callback(self, inter: discord.Interaction):
        await _criar_ticket(inter, self.values[0])


# Texto que dispara o atendente IA (selfbot). Configurável por env.
ATENDENTE_CMD = (os.environ.get('ATENDENTE_CMD', '') or '.iniciar').strip()


async def _renovar_remoto(login_id=None, discord_id=None, dias=0, _tentativas=3):
    """Chama /atendente/renovar no configadm pra somar os dias no vencimento do
    cliente já existente. Retorna o dict de resposta ou None em erro.

    Tolerante a instabilidade: 5xx e resposta não-JSON (ex: página HTML de 502
    do Cloudflare) entram em retry em vez de falhar na primeira tentativa."""
    if not CONFIGURADOR_URL:
        return None
    headers = {'X-Bot-Secret': BOT_FETCH_SECRET, 'Content-Type': 'application/json'}
    payload = {'login_id': login_id or '', 'discord_id': discord_id or '', 'dias': int(dias)}
    for i in range(_tentativas):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f'{CONFIGURADOR_URL}/atendente/renovar', headers=headers,
                                 json=payload, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status >= 500:
                        txt = (await r.text())[:120]
                        print(f'[RENOVAR] HTTP {r.status} (tentativa {i+1}): {txt!r}', flush=True)
                        if i < _tentativas - 1:
                            await asyncio.sleep(4)
                            continue
                        return None
                    d = await r.json(content_type=None)
                    if r.status != 200 or not (d or {}).get('ok'):
                        return {'_erro': (d or {}).get('msg', f'HTTP {r.status}')}
                    return d
        except (aiohttp.ContentTypeError, ValueError) as e:
            # resposta vazia/HTML em vez de JSON — instabilidade passageira
            print(f'[RENOVAR] resposta inválida (tentativa {i+1}): {e}', flush=True)
            if i < _tentativas - 1:
                await asyncio.sleep(4)
        except Exception as e:
            print(f'[RENOVAR] erro (tentativa {i+1}): {type(e).__name__}: {e}', flush=True)
            if i < _tentativas - 1:
                await asyncio.sleep(4)
    return None


class RenovacaoModal(discord.ui.Modal, title='Renovação'):
    ident = discord.ui.TextInput(
        label='ID de login OU ID do Discord',
        placeholder='cole seu ID de login do painel ou seu ID do Discord',
        max_length=60)

    def __init__(self, dias_plano):
        super().__init__()
        self.dias_plano = int(dias_plano or 0)

    async def on_submit(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True)
        valor = str(self.ident.value).strip()
        # Se for só números longos, trata como ID do Discord; senão, login_id.
        so_num = ''.join(ch for ch in valor if ch.isdigit())
        eh_discord = valor.isdigit() and len(so_num) >= 15
        res = await _renovar_remoto(
            login_id=None if eh_discord else valor,
            discord_id=valor if eh_discord else None,
            dias=self.dias_plano)
        if not res:
            await inter.followup.send(
                f'{E["box"]} Não consegui falar com o painel agora. Chame o suporte.', ephemeral=True)
            return
        if res.get('_erro'):
            await inter.followup.send(
                f'{E["box"]} {res["_erro"]}\nConfira o ID e tente de novo, ou chame o suporte.', ephemeral=True)
            return
        nome = res.get('nome', '')
        venc = res.get('vencimento', '—')
        await inter.followup.send(
            f'{E["foguete"]} **Renovado!** +{self.dias_plano} dia(s)\n'
            f'{E["seta"]} Cliente: **{nome}**\n'
            f'{E["seta"]} Novo vencimento: **{venc}**', ephemeral=True)


class CompraTipoView(discord.ui.View):
    """Após o pagamento de um PLANO: pergunta se é primeira compra ou renovação.
    Primeira → abre ticket + .iniciar (atendente monta o cliente novo).
    Renovação → pede o ID e soma os dias automático (sem ticket)."""
    def __init__(self, buyer_id, canal_base, dias_plano):
        super().__init__(timeout=1800)
        self.buyer_id = int(buyer_id)
        self.canal_base = canal_base
        self.dias_plano = int(dias_plano or 0)

    async def interaction_check(self, inter: discord.Interaction) -> bool:
        if inter.user.id != self.buyer_id:
            await inter.response.send_message('Só quem comprou pode escolher aqui.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Primeira compra', style=discord.ButtonStyle.success, emoji='🆕')
    async def primeira(self, inter: discord.Interaction, btn: discord.ui.Button):
        await inter.response.send_message(
            '🆕 Beleza! Vou abrir seu atendimento pra configurar tudo.', ephemeral=True)
        for c in self.children:
            c.disabled = True
        try:
            await inter.message.edit(view=self)
        except Exception:
            pass
        membro = inter.guild.get_member(self.buyer_id) if inter.guild else None
        if membro and self.canal_base is not None:
            await _abrir_ticket_atendente(membro, self.canal_base)

    @discord.ui.button(label='Renovação', style=discord.ButtonStyle.primary, emoji='🔄')
    async def renovacao(self, inter: discord.Interaction, btn: discord.ui.Button):
        await inter.response.send_modal(RenovacaoModal(self.dias_plano))


async def _abrir_ticket_atendente(membro, canal_base):
    """Após a compra: cria um ticket NOVO (thread no canal base), adiciona o
    comprador e posta `.iniciar` pro atendente IA (selfbot) reagir. Best-effort:
    nunca quebra a entrega da compra."""
    try:
        guild = canal_base.guild
        perms = canal_base.permissions_for(guild.me)
        thread = None
        if getattr(perms, 'create_private_threads', False):
            thread = await canal_base.create_thread(
                name=f'atendimento-{membro.name}'[:90],
                type=discord.ChannelType.private_thread, invitable=False)
        elif getattr(perms, 'create_public_threads', False):
            thread = await canal_base.create_thread(
                name=f'atendimento-{membro.name}'[:90],
                type=discord.ChannelType.public_thread)
        else:
            print(f'[ATENDENTE] sem permissão de criar thread em #{getattr(canal_base,"name","?")}.', flush=True)
            return None
        # adiciona o comprador sem gerar a linha "X adicionou Y"
        try:
            ping = await thread.send(membro.mention)
            await ping.delete()
        except Exception:
            try:
                await thread.add_user(membro)
            except Exception:
                pass
        # posta o comando que o atendente IA (selfbot) escuta
        await thread.send(ATENDENTE_CMD)
        print(f'[ATENDENTE] ✅ ticket {thread.id} aberto e "{ATENDENTE_CMD}" enviado p/ {membro}.', flush=True)
        return thread
    except discord.Forbidden:
        print(f'[ATENDENTE] sem permissão pra abrir ticket/postar.', flush=True)
    except Exception as e:
        print(f'[ATENDENTE] erro ao abrir ticket: {e}', flush=True)
    return None


async def _criar_ticket(inter, opcao):
        """Cria a thread de atendimento. Reutilizado pelo menu /ticket e pelo
        botão de dúvida do .perfil (quem ainda não tem plano)."""
        await inter.response.defer(ephemeral=True)
        canal = inter.channel  # abre a thread NO canal onde o painel foi postado

        # checa permissões do bot no canal antes de tentar
        perms = canal.permissions_for(inter.guild.me)
        if not perms.create_private_threads and not perms.create_public_threads:
            await inter.followup.send(
                f'{E["box"]} O bot não tem permissão para criar threads neste canal.\n'
                f'Peça a um admin para ativar **Criar Tópicos Privados** '
                f'(e **Criar Tópicos**) para o cargo do bot, '
                f'nas permissões deste canal ou do servidor.',
                ephemeral=True)
            return
        if not perms.send_messages_in_threads:
            await inter.followup.send(
                f'{E["box"]} O bot não tem permissão **Enviar Mensagens em Tópicos** '
                f'neste canal. Peça a um admin para ativar.',
                ephemeral=True)
            return

        # tenta thread privada; se não puder, cai pra pública
        # prefixo do nome da thread conforme o tipo (renovacao fica fácil de achar)
        _pref = 'renovacao' if opcao == 'Renovação' else 'ticket'
        thread = None
        try:
            if perms.create_private_threads:
                thread = await canal.create_thread(
                    name=f'{_pref}-{inter.user.name}'[:90],
                    type=discord.ChannelType.private_thread,
                    invitable=False)
            else:
                thread = await canal.create_thread(
                    name=f'{_pref}-{inter.user.name}'[:90],
                    type=discord.ChannelType.public_thread)
        except discord.Forbidden:
            await inter.followup.send(
                f'{E["box"]} Sem permissão para abrir o ticket aqui. '
                f'Verifique se o bot tem **Criar Tópicos Privados** e '
                f'**Gerenciar Tópicos** no canal.',
                ephemeral=True)
            return
        except Exception as e:
            await inter.followup.send(
                f'{E["box"]} Não consegui abrir o ticket: `{e}`', ephemeral=True)
            return

        # 1) Adiciona o usuário à thread SEM gerar "X adicionou Y ao tópico":
        #    manda menção e apaga em seguida.
        try:
            ping = await thread.send(inter.user.mention)
            await ping.delete()
        except Exception:
            # fallback: add_user (gera a linha de sistema, mas garante o acesso)
            try:
                await thread.add_user(inter.user)
            except Exception:
                pass

        # 2) Menciona o cargo de suporte (se configurado) — mensagem fica visível
        #    pra notificar a equipe e adicionar todos do cargo à thread.
        cfg = await db.get_config(bot.http_session, inter.guild.id)
        cargo_suporte_id = cfg.get('cargo_suporte') if cfg else None
        if cargo_suporte_id:
            try:
                await thread.send(
                    f'<@&{cargo_suporte_id}>',
                    allowed_mentions=discord.AllowedMentions(
                        users=False, roles=True, everyone=False))
            except Exception:
                pass

        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(f'## {E["ticket"]} Ticket — {opcao}'))
        c.add_item(discord.ui.Separator())
        if opcao == 'Renovação':
            # mostra o vencimento atual lido do nick (ajuda o suporte)
            venc_txt = ''
            try:
                nick_atual = getattr(inter.user, 'nick', None) or inter.user.display_name
                m = re.search(r'(\d{1,2}/\d{1,2})\s*$', (nick_atual or '').strip())
                if m:
                    venc_txt = f'\n{E["clock"]} Seu vencimento atual: **{m.group(1)}**'
            except Exception:
                pass
            c.add_item(discord.ui.TextDisplay(
                f'{E["seta"]} Olá {inter.user.mention}, vamos renovar seu plano!{venc_txt}\n'
                f'{E["seta"]} Diga qual **plano** você quer renovar e envie o **comprovante** do pagamento.\n'
                f'{E["cloud"]} A equipe vai confirmar e atualizar seu acesso em seguida.'))
        else:
            c.add_item(discord.ui.TextDisplay(
                f'{E["seta"]} Olá {inter.user.mention}, bem-vindo ao atendimento!\n'
                f'{E["seta"]} Você abriu um ticket de **{opcao}**.\n'
                f'{E["cloud"]} Descreva com detalhes o motivo do contato que já te respondemos.'))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.TextDisplay(
            f'{E["clock"]} Para encerrar, use os botões abaixo.'))
        row = discord.ui.ActionRow()
        row.add_item(BtnFinalizarTicket())
        row.add_item(BtnSairTicket())
        c.add_item(row)
        v = discord.ui.LayoutView(timeout=None)
        v.add_item(c)
        # Components V2 (LayoutView) não aceita 'content' junto — manda só a view.
        try:
            await thread.send(view=v)
        except Exception as e:
            await inter.followup.send(
                f'{E["box"]} Ticket aberto, mas falhou ao postar o painel: `{e}`',
                ephemeral=True)
            return
        await inter.followup.send(
            f'{E["ticket"]} Ticket aberto: {thread.mention}', ephemeral=True)


class BtnFinalizarTicket(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Finalizar Ticket', style=discord.ButtonStyle.danger,
                         emoji='🔒', custom_id='finalizar_ticket')

    async def callback(self, inter: discord.Interaction):
        await inter.response.defer()
        thread = inter.channel
        if not isinstance(thread, discord.Thread):
            await inter.followup.send('Isso não é um ticket.', ephemeral=True)
            return
        # Monta o transcript (histórico) e manda pro canal de logs
        await _enviar_transcript(inter, thread)
        await inter.followup.send(f'{E["clock"]} Ticket finalizado. Arquivando…')
        try:
            await thread.edit(archived=True, locked=True)
        except Exception:
            pass


class BtnSairTicket(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Sair Ticket', style=discord.ButtonStyle.secondary,
                         emoji='🚪', custom_id='sair_ticket')

    async def callback(self, inter: discord.Interaction):
        thread = inter.channel
        if not isinstance(thread, discord.Thread):
            await inter.response.send_message('Isso não é um ticket.', ephemeral=True)
            return
        await inter.response.send_message(f'{E["seta"]} {inter.user.mention} saiu do ticket.')
        try:
            await thread.remove_user(inter.user)
        except Exception:
            pass


async def _enviar_transcript(inter, thread):
    """Coleta as mensagens da thread e posta um transcript no canal de logs."""
    cfg = await db.get_config(bot.http_session, inter.guild_id)
    canal_logs_id = cfg.get('canal_logs') if cfg else None
    if not canal_logs_id:
        return
    canal_logs = inter.guild.get_channel(int(canal_logs_id))
    if not canal_logs:
        return
    linhas = []
    try:
        async for msg in thread.history(limit=500, oldest_first=True):
            if msg.content:
                linhas.append(f'[{msg.created_at:%d/%m %H:%M}] {msg.author.display_name}: {msg.content}')
    except Exception:
        pass
    texto = '\n'.join(linhas) or '(sem mensagens de texto)'
    import io
    arquivo = discord.File(io.BytesIO(texto.encode('utf-8')),
                           filename=f'transcript-{thread.name}.txt')
    c = discord.ui.Container(accent_color=COR)
    c.add_item(discord.ui.TextDisplay(f'## {E["ticket"]} Transcript — {thread.name}'))
    c.add_item(discord.ui.TextDisplay(f'{E["seta"]} Fechado por {inter.user.mention}'))
    v = discord.ui.LayoutView(timeout=300)
    v.add_item(c)
    await canal_logs.send(view=v)
    await canal_logs.send(file=arquivo)


class TicketInternoView(discord.ui.LayoutView):
    """View persistente dos botões dentro do ticket (Finalizar/Sair)."""
    def __init__(self):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_color=COR)
        c.add_item(discord.ui.TextDisplay(f'{E["clock"]} Encerrar atendimento:'))
        row = discord.ui.ActionRow()
        row.add_item(BtnFinalizarTicket())
        row.add_item(BtnSairTicket())
        c.add_item(row)
        self.add_item(c)


@bot.tree.command(name='ticket', description='Postar o painel de tickets (admin)')
async def ticket(inter: discord.Interaction):
    if not _admin(inter):
        await inter.response.send_message('Só admin.', ephemeral=True)
        return
    await inter.response.send_message(view=TicketPainelView())


@bot.tree.command(name='syncemojis',
                  description='Recriar os emojis do bot do zero (admin)')
async def syncemojis(inter: discord.Interaction):
    """Apaga os Application Emojis antigos e sobe as imagens novas da pasta
    emojis/. Use se algum emoji estiver errado (ex: fundo preto)."""
    if not _admin(inter):
        await inter.response.send_message('Só admin.', ephemeral=True)
        return
    await inter.response.defer(ephemeral=True)
    novos = await emojis_mod.carregar(bot, forcar=True)
    E.update(novos)

    c = discord.ui.Container(accent_color=COR)
    c.add_item(discord.ui.TextDisplay(f'## {E["gear"]} Emojis recriados'))
    c.add_item(discord.ui.Separator())
    linhas = '\n'.join(f'{E[k]} `{k}`' for k in emojis_mod.ICONES)
    c.add_item(discord.ui.TextDisplay(linhas))
    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.TextDisplay(
        f'{E["cloud"]} Os emojis foram recriados a partir das imagens da pasta. '
        f'Rode os outros comandos pra ver.'))
    v = discord.ui.LayoutView(timeout=300)
    v.add_item(c)
    await inter.followup.send(view=v, ephemeral=True)


async def _postar_sala_log(canal, sala):
    """Monta e posta o embed de uma sala criada no canal de logs."""
    import re as _re
    tipo = sala.get('tipo', 'auto')
    if tipo == 'manual':
        tipo_label = f"🕹️ Manual — {sala.get('user', '') or 'admin'}"
    else:
        tipo_label = '🤖 Automático (venda)'
    # Limpa o sufixo de provider do modo (ex: "modo 1 (salasff)" → "Modo 1").
    modo_limpo = _re.sub(r'\s*\((salasff|salasbot)\)\s*', '', str(sala.get('modo', '?')),
                         flags=_re.IGNORECASE).strip()
    modo_limpo = (modo_limpo[:1].upper() + modo_limpo[1:]) if modo_limpo else 'Modo ?'
    room_id = sala.get('room_id', '?')
    senha = sala.get('senha', '') or '—'
    emb = discord.Embed(title='🎮  Nova Sala Criada', color=0x2ecc71)
    emb.add_field(name='🆔  ID da Sala', value=f'```{room_id}```',                 inline=True)
    emb.add_field(name='🔑  Senha',      value=f'```{senha}```',                   inline=True)
    emb.add_field(name='\u200b',         value='\u200b',                           inline=True)
    emb.add_field(name='🎯  Modo',       value=modo_limpo[:256],                   inline=True)
    emb.add_field(name='📍  Canal',      value=f'#{sala.get("canal_nome", "?")}'[:256], inline=True)
    emb.add_field(name='\u200b',         value='\u200b',                           inline=True)
    emb.add_field(name='⚙️  Origem',     value=tipo_label[:256],                   inline=False)
    cid = sala.get('client_id')
    if cid:
        emb.set_footer(text=f'cliente: {cid}')
    emb.timestamp = datetime.now(timezone.utc)
    await canal.send(embed=emb)


async def _poll_salas_criadas_once():
    """Puxa a fila de salas do configadm, posta cada uma no canal_logs_salas do
    guild de origem, e confirma (remove da fila). Confirma também as que não têm
    canal/canal inacessível pra a fila não crescer sem limite."""
    if not CONFIGURADOR_URL:
        return
    headers = {'X-Bot-Secret': BOT_FETCH_SECRET}
    async with bot.http_session.get(
            f'{CONFIGURADOR_URL}/bot/salas-criadas-pendentes',
            headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
        if r.status != 200:
            return
        data = await r.json()
    salas = data.get('salas') or []
    if not salas:
        return
    try:
        cfgs = await db.listar_configs_com_canal_salas(bot.http_session)
    except Exception:
        cfgs = []
    canal_por_guild = {str(c['guild_id']): str(c.get('canal_logs_salas') or '')
                       for c in cfgs if c.get('canal_logs_salas')}
    confirmados = []
    for sala in salas:
        sid = sala.get('id')
        gid = str(sala.get('guild_id') or '')
        canal_id = canal_por_guild.get(gid)
        if not canal_id:
            confirmados.append(sid)  # guild sem canal configurado — descarta
            continue
        canal = bot.get_channel(int(canal_id)) if canal_id.isdigit() else None
        if canal is None:
            try:
                canal = await bot.fetch_channel(int(canal_id))
            except Exception:
                canal = None
        if canal is None:
            confirmados.append(sid)  # canal inacessível — descarta
            continue
        try:
            await _postar_sala_log(canal, sala)
        except Exception as e:
            print(f'[SALA-LOG] falha ao postar sala {sid} no guild {gid}: {e}', flush=True)
        confirmados.append(sid)  # sempre confirma (evita travar a fila)
    if confirmados:
        try:
            async with bot.http_session.post(
                    f'{CONFIGURADOR_URL}/bot/salas-criadas-confirmar',
                    json={'ids': confirmados}, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)) as r:
                await r.read()
        except Exception as e:
            print(f'[SALA-LOG] falha ao confirmar: {e}', flush=True)


async def _poll_salas_criadas_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await _poll_salas_criadas_once()
        except Exception as e:
            print(f'[SALA-LOG] erro no poll: {type(e).__name__}: {e}', flush=True)
        await asyncio.sleep(POLL_SALAS_INTERVALO)


async def _expirar_uma_assinatura(a):
    """Processa UMA assinatura vencida: remove o cargo do plano e tira a data do
    nick (deixa só o nome). NÃO mexe no cargo de cliente. Idempotente."""
    uid = a.get('user_id')
    gid = a.get('guild_id')
    cargo_id = a.get('cargo_id')
    nome_base = a.get('nome_base')
    try:
        guild = bot.get_guild(int(gid))
        if guild is None:
            await db.marcar_assinatura_expirada(bot.http_session, uid, gid)
            return
        membro = guild.get_member(int(uid))
        if membro is None:
            try:
                membro = await guild.fetch_member(int(uid))
            except Exception:
                membro = None
        if membro is not None:
            # 1) remove o cargo do plano (se ainda tiver)
            if cargo_id:
                cargo = guild.get_role(int(cargo_id)) \
                    or discord.utils.get(guild.roles, id=int(cargo_id))
                if cargo and cargo in membro.roles:
                    try:
                        await membro.remove_roles(cargo, reason='Plano vencido')
                        print(f'[ASSINATURA] {membro}: cargo "{cargo.name}" removido (vencido).', flush=True)
                    except discord.Forbidden:
                        print(f'[ASSINATURA] {membro}: SEM permissao/hierarquia pra tirar "{cargo.name}".', flush=True)
                    except Exception as e:
                        print(f'[ASSINATURA] {membro}: erro ao tirar cargo: {e}', flush=True)
            # 2) limpa a data do nick (deixa so o nome base)
            try:
                nick_atual = getattr(membro, 'nick', None) or membro.display_name
                novo = nome_base or re.sub(r'\s*\d{1,2}/\d{1,2}\s*$', '', nick_atual or '').strip()
                if novo and novo != nick_atual:
                    await membro.edit(nick=novo[:32], reason='Plano vencido - data removida')
                    print(f'[ASSINATURA] {membro}: nick limpo pra "{novo[:32]}".', flush=True)
            except discord.Forbidden:
                print(f'[ASSINATURA] {membro}: SEM permissao pra limpar o nick.', flush=True)
            except Exception as e:
                print(f'[ASSINATURA] {membro}: erro ao limpar nick: {e}', flush=True)
        # 3) marca como processada (nao repete)
        await db.marcar_assinatura_expirada(bot.http_session, uid, gid)
    except Exception as e:
        print(f'[ASSINATURA] erro processando user={uid} guild={gid}: {e}', flush=True)


# Temporizadores ativos por (user_id, guild_id) — pra cancelar/reagendar na renovação.
_timers_expiracao = {}


def _parse_venc(vence_em):
    """ISO (timestamptz) → datetime aware no fuso de Brasília. None se inválido."""
    try:
        dt = datetime.fromisoformat(str(vence_em))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=-3)))
        return dt
    except Exception:
        return None


def _agendar_expiracao(a):
    """TEMPORIZADOR: agenda a remoção do cargo pra disparar na HORA EXATA do
    vencimento. Na renovação, cancela o timer antigo e reagenda."""
    uid = str(a.get('user_id'))
    gid = str(a.get('guild_id'))
    chave = (uid, gid)
    # cancela timer anterior desse cliente (renovação)
    velho = _timers_expiracao.pop(chave, None)
    if velho and not velho.done():
        velho.cancel()
    venc = _parse_venc(a.get('vence_em'))
    if venc is None:
        return
    delay = (venc - _data_br_agora()).total_seconds()

    async def _tarefa():
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            await _expirar_uma_assinatura(a)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f'[ASSINATURA] erro no temporizador user={uid}: {e}', flush=True)
        finally:
            _timers_expiracao.pop(chave, None)

    _timers_expiracao[chave] = bot.loop.create_task(_tarefa())
    quando = venc.strftime('%d/%m %H:%M')
    print(f'[ASSINATURA] ⏲️ timer agendado p/ user={uid}: expira {quando} (em {max(0, delay)/60:.0f}min).', flush=True)


async def _loop_expirar_assinaturas():
    """REDE DE SEGURANÇA do temporizador: a cada 5min varre vencidas que por
    algum motivo (reinício no exato momento, timer perdido) não dispararam, e
    (re)agenda timers de assinaturas ativas sem timer."""
    await bot.wait_until_ready()
    # No boot, agenda um temporizador pra CADA assinatura ativa.
    try:
        for a in (await db.listar_assinaturas_ativas(bot.http_session) or []):
            _agendar_expiracao(a)
    except Exception as e:
        print(f'[ASSINATURA] erro ao agendar timers no boot: {e}', flush=True)
    while not bot.is_closed():
        try:
            agora_iso = _data_br_agora().isoformat()
            vencidas = await db.listar_assinaturas_vencidas(bot.http_session, agora_iso)
            for a in (vencidas or []):
                await _expirar_uma_assinatura(a)
            # reagenda timers que sumiram (ex.: assinatura nova sem timer ainda)
            for a in (await db.listar_assinaturas_ativas(bot.http_session) or []):
                chave = (str(a.get('user_id')), str(a.get('guild_id')))
                if chave not in _timers_expiracao:
                    _agendar_expiracao(a)
        except Exception as e:
            print(f'[ASSINATURA] erro no loop de vencimento: {e}', flush=True)
        await asyncio.sleep(5 * 60)


@bot.event
async def on_ready():
    global EMOJI_VOTO_SIM, EMOJI_VOTO_NAO
    print(f'[BOT] online como {bot.user} ({bot.user.id})', flush=True)
    # sobe as imagens da pasta emojis/ como Application Emojis da aplicação
    # (modo normal: reaproveita os que já existem)
    novos = await emojis_mod.carregar(bot)
    E.update(novos)
    # já com os emojis carregados, atualiza as constantes de voto.
    # Se o custom subiu, vira <:certo:ID>; senão, fallback unicode.
    EMOJI_VOTO_SIM = E.get('certo', '✅')
    EMOJI_VOTO_NAO = E.get('xist',  '❌')
    print(f'[BOT] emojis carregados. voto_sim={EMOJI_VOTO_SIM} voto_nao={EMOJI_VOTO_NAO}', flush=True)
    # views persistentes (botões/menus continuam funcionando após restart)
    bot.add_view(TicketPainelView())
    bot.add_view(TicketInternoView())
    bot.add_view(PlanosPersistView())
    bot.add_view(PainelComprasPersistView())
    bot.add_view(WalletPersistView())
    # inicia o poller da fila de salas criadas (só uma vez)
    if CONFIGURADOR_URL and not getattr(bot, '_poll_salas_iniciado', False):
        bot._poll_salas_iniciado = True
        bot.loop.create_task(_poll_salas_criadas_loop())
        print(f'[SALA-LOG] poller iniciado (cada {POLL_SALAS_INTERVALO}s, '
              f'configadm={CONFIGURADOR_URL})', flush=True)
    elif not CONFIGURADOR_URL:
        print('[SALA-LOG] CONFIGURADOR_URL vazio — poller de salas desativado.', flush=True)
    # inicia o verificador de assinaturas vencidas (remove cargo + limpa nick)
    if not getattr(bot, '_venc_iniciado', False):
        bot._venc_iniciado = True
        bot.loop.create_task(_loop_expirar_assinaturas())
        print('[ASSINATURA] verificador de vencimento iniciado (checa a cada 30min).', flush=True)
    # inicia o avisador de erros dos bots dos clientes (token inválido etc.)
    if CONFIGURADOR_URL and not getattr(bot, '_erros_iniciado', False):
        bot._erros_iniciado = True
        bot.loop.create_task(_loop_avisar_erros())
        print('[ERROS] avisador de erros iniciado (checa a cada 3min).', flush=True)


if __name__ == '__main__':
    if not TOKEN:
        print('[BOT] faltando DISCORD_BOT_TOKEN', flush=True)
    bot.run(TOKEN)
