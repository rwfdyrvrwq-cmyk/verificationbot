import os
from dotenv import load_dotenv
import discord

load_dotenv()

intents = discord.Intents.default()
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'\nBot: {client.user.name} (ID: {client.user.id})')
    print(f'\nServers this bot is in:')
    print('-' * 60)
    for guild in client.guilds:
        print(f'Server: {guild.name}')
        print(f'Guild ID: {guild.id}')
        print(f'Members: {guild.member_count}')
        print('-' * 60)
    await client.close()

token = os.getenv("DISCORD_TOKEN")
client.run(token)
