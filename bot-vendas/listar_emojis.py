"""
Lista todos os Application Emojis da aplicação (nome + ID + animado).
Roda no terminal/console (Discloud ou local). Usa o token do .env.

Uso:
    python listar_emojis.py

Depois e so copiar a saida e enviar.
"""
import os
import asyncio

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import discord

TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '')


async def main():
    if not TOKEN:
        print('[ERRO] DISCORD_BOT_TOKEN nao encontrado no .env')
        return

    client = discord.Client(intents=discord.Intents.none())

    @client.event
    async def on_ready():
        print('=' * 50)
        print(f'Aplicacao: {client.user} (id {client.user.id})')
        print('=' * 50)
        try:
            emojis = await client.fetch_application_emojis()
        except Exception as erro:
            print(f'[ERRO] nao consegui listar: {erro}')
            await client.close()
            return

        if not emojis:
            print('Nenhum Application Emoji registrado.')
        else:
            print(f'Total: {len(emojis)} emoji(s)\n')
            for e in emojis:
                tipo = 'animado' if e.animated else 'estatico'
                tag = f'<a:{e.name}:{e.id}>' if e.animated else f'<:{e.name}:{e.id}>'
                print(f'  nome: {e.name:24s} id: {e.id:22d}  {tipo}')
                print(f'        tag: {tag}')
        print('=' * 50)
        await client.close()

    await client.start(TOKEN)


if __name__ == '__main__':
    asyncio.run(main())
