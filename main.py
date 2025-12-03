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
        await self.tree.sync() 

    async def on_command_error(self, ctx, error):
        """Global error handler."""
        if isinstance(error, commands.CommandNotFound):
            return # Ignore unknown commands
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Missing required arguments.")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send(f"Error executing command: {error.original}")
            print(f"Command Error: {error}")
        else:
            await ctx.send(f"An error occurred: {error}")
            print(f"Unhandled Error: {error}")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

    @commands.command(name='sync', description="Syncs slash commands. Use `!sync ~` to sync to current guild, `!sync *` to copy all global app commands to current guild and sync, `!sync ^` to clear all commands from the current guild and sync.")
    @commands.is_owner() # Only bot owner can use this
    async def sync_commands(self, ctx: commands.Context, guild_id: int = None, spec: str = "~"):
        guild = None
        if guild_id:
            guild = self.get_guild(guild_id)
            if not guild:
                return await ctx.send(f"Guild with ID {guild_id} not found.")

        if spec == "~": # Sync to current guild
            if not ctx.guild:
                return await ctx.send("Cannot sync to current guild outside a guild.")
            self.tree.copy_global_to(guild=ctx.guild)
            synced = await self.tree.sync(guild=ctx.guild)
        elif spec == "*": # Copy global to current guild and sync
            if not ctx.guild:
                return await ctx.send("Cannot sync to current guild outside a guild.")
            self.tree.copy_global_to(guild=ctx.guild)
            synced = await self.tree.sync(guild=ctx.guild)
        elif spec == "^": # Clear commands from current guild and sync
            if not ctx.guild:
                return await ctx.send("Cannot clear commands from current guild outside a guild.")
            self.tree.clear_commands(guild=ctx.guild)
            await self.tree.sync(guild=ctx.guild)
            synced = []
        elif spec == "global": # Sync globally
            synced = await self.tree.sync()
        else:
            await ctx.send("Invalid sync spec. Use `~` for current guild sync, `*` for global copy+current guild sync, `^` for current guild clear+sync, or `global` for global sync.")
            return

        await ctx.send(f"Synced {len(synced)} commands {'globally' if spec == 'global' else f'to {guild.name if guild else ctx.guild.name}'}.")

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
