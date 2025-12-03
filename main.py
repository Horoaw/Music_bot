import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Define intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            help_command=commands.DefaultHelpCommand(),
            case_insensitive=True
        )

    async def setup_hook(self):
        # Load extensions (cogs)
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await self.load_extension(f'cogs.{filename[:-3]}')
                print(f'Loaded extension: {filename[:-3]}')
        
        # Sync slash commands (optional, useful for hybrid commands)
        # await self.tree.sync() 

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

async def main():
    bot = MusicBot()
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found in .env file.")
    else:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            pass
