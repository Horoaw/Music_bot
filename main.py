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
            help_command=None,
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
        print("Note: Global slash commands may take up to an hour to appear.")
        print(f"Invite URL (Ensure 'applications.commands' is checked!):")
        print(f"https://discord.com/api/oauth2/authorize?client_id={self.user.id}&permissions=8&scope=bot%20applications.commands")
        print('------')

    @commands.command(name='sync', description="Syncs slash commands.")
    @commands.has_permissions(administrator=True)
    async def sync_commands(self, ctx: commands.Context, spec: str = "~"):
        await ctx.send(f"🔄 Processing sync request with spec: `{spec}`...")
        print(f"Sync triggered by {ctx.author} (Spec: {spec})")
        
        try:
            if spec == "~": # Sync to current guild
                if not ctx.guild:
                    return await ctx.send("❌ Can only sync to a guild.")
                
                # Clear existing guild commands first to ensure a clean slate
                self.tree.clear_commands(guild=ctx.guild)
                
                # Copy global commands to this guild
                self.tree.copy_global_to(guild=ctx.guild)
                
                # Sync
                synced = await self.tree.sync(guild=ctx.guild)
                await ctx.send(f"✅ Successfully synced {len(synced)} commands to this server (Instant).")
                print(f"Synced {len(synced)} commands to guild {ctx.guild.id}.")
                
            elif spec == "global": # Sync globally
                synced = await self.tree.sync()
                await ctx.send(f"✅ Synced {len(synced)} commands globally (May take 1 hour).")
                
            elif spec == "^": # Clear
                self.tree.clear_commands(guild=ctx.guild)
                await self.tree.sync(guild=ctx.guild)
                await ctx.send("✅ Cleared guild commands.")
            
            else:
                await ctx.send("❓ Unknown spec. Use `~` (Guild) or `global`.")

        except Exception as e:
            print(f"Sync Error: {e}")
            await ctx.send(f"❌ Sync failed: {e}")

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
