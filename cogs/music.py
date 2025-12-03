import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from collections import deque
import random
import json

# Suppress noise from youtube_dl and fix bug with generic extractor
yt_dlp.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0' 
}

ffmpeg_options = {
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

    @classmethod
    async def search_source(cls, query, *, loop=None, stream=True):
        """Searches for a query and returns a list of (title, url, id) tuples for selection."""
        loop = loop or asyncio.get_event_loop()
        # 'ytsearch5:' gets top 5 results
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch5:{query}", download=False))
        
        if 'entries' not in data:
            return []
        
        results = []
        for entry in data['entries']:
            results.append({
                'title': entry.get('title'),
                'url': entry.get('webpage_url', entry.get('url')),
                'id': entry.get('id')
            })
        return results

class SearchSelect(discord.ui.Select):
    def __init__(self, ctx, results, music_cog):
        self.ctx = ctx
        self.music_cog = music_cog
        self.results = results
        options = []
        for i, res in enumerate(results):
            # Limit label size to 100 chars
            label = f"{i+1}. {res['title']}"[:100]
            options.append(discord.SelectOption(label=label, value=str(i)))

        super().__init__(placeholder="Select a song to play...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("This menu is not for you.", ephemeral=True)
        
        selection_index = int(self.values[0])
        selected_song = self.results[selection_index]
        
        # Add to queue via the music cog
        await interaction.response.defer() # Acknowledge interaction to prevent timeout
        
        # Add to queue logic (reusing play logic somewhat)
        self.music_cog.queue.append((selected_song['url'], self.ctx.author.id))
        await interaction.followup.send(f"Selected and queued: **{selected_song['title']}**")
        
        if not self.ctx.voice_client.is_playing():
            self.music_cog.play_next(self.ctx)

class SearchView(discord.ui.View):
    def __init__(self, ctx, results, music_cog):
        super().__init__(timeout=60)
        self.add_item(SearchSelect(ctx, results, music_cog))

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = deque()
        self.current_song = None
        self.is_looping = False
        self.is_shuffling = False
        self.autoplay = False
        self.playlist_dir = 'data/playlists'
        
        # Create playlist dir if not exists
        if not os.path.exists(self.playlist_dir):
            os.makedirs(self.playlist_dir)

        # Spotify Setup
        self.spotify = None
        client_id = os.getenv('SPOTIPY_CLIENT_ID')
        client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')
        if client_id and client_secret:
            try:
                self.spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
                print("Spotify integration enabled.")
            except Exception as e:
                print(f"Spotify integration failed: {e}")
        else:
            print("Spotify credentials not found. Spotify support disabled.")

    async def get_spotify_tracks(self, url):
        if not self.spotify:
            return []
        results = []
        try:
            if 'track' in url:
                track = self.spotify.track(url)
                results.append(f"{track['artists'][0]['name']} - {track['name']}")
            elif 'playlist' in url:
                playlist = self.spotify.playlist_items(url)
                for item in playlist['items']:
                    track = item['track']
                    if track:
                        results.append(f"{track['artists'][0]['name']} - {track['name']}")
            elif 'album' in url:
                album = self.spotify.album_tracks(url)
                for item in album['items']:
                    results.append(f"{item['artists'][0]['name']} - {item['name']}")
        except Exception as e:
            print(f"Error fetching Spotify tracks: {e}")
        return results

    async def play_next(self, ctx):
        if self.is_looping and self.current_song:
            # Re-queue the current song query
            self.queue.appendleft(self.current_song)

        if len(self.queue) > 0:
            if self.is_shuffling:
                # Shuffle logic remains simple for now
                pass 
            
            query, requester = self.queue.popleft()
            self.current_song = (query, requester)
            
            try:
                # Ensure we are still connected
                if not ctx.voice_client:
                    return

                source = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True)
                
                # Define the callback to run when the song finishes
                def after_playing(error):
                    if error:
                        print(f"Player error: {error}")
                        self.bot.loop.create_task(ctx.send(f"Player error: {error}"))
                    # Schedule the next song
                    self.bot.loop.create_task(self.play_next(ctx))

                ctx.voice_client.play(source, after=after_playing)
                await ctx.send(f'Now playing: **{source.title}**')
            
            except Exception as e:
                await ctx.send(f"Error playing **{query}**: {e}")
                print(f"Error playing {query}: {e}")
                # Recursively try the next song
                await self.play_next(ctx)
        else:
            self.current_song = None
            await ctx.send("Queue finished.")

    async def ensure_voice(self, ctx):
        if not ctx.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                return False
        return True

    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx, *, query):
        """Plays a song or adds to queue (URL or Search)."""
        if not await self.ensure_voice(ctx):
            return

        if 'spotify.com' in query:
            msg = await ctx.send("Processing Spotify link...")
            tracks = await self.get_spotify_tracks(query)
            if not tracks:
                return await msg.edit(content="Could not load Spotify tracks.")
            for track in tracks:
                self.queue.append((track, ctx.author.id))
            await msg.edit(content=f"Queued {len(tracks)} tracks from Spotify.")
        else:
            self.queue.append((query, ctx.author.id))
            await ctx.send(f"Added to queue: {query}")

        if not ctx.voice_client.is_playing():
            await self.play_next(ctx)

    @commands.command(name='search')
    async def search(self, ctx, *, query):
        """Searches YouTube and lets you select a song."""
        if not await self.ensure_voice(ctx):
            return

        msg = await ctx.send(f"Searching for **{query}**...")
        try:
            results = await YTDLSource.search_source(query, loop=self.bot.loop)
        except Exception as e:
             return await msg.edit(content=f"Error searching: {e}")
        
        if not results:
            return await msg.edit(content="No results found.")
        
        view = SearchView(ctx, results, self)
        await msg.edit(content="Select a song to play:", view=view)

    # --- Playlist Commands ---
    @commands.group(name='playlist', invoke_without_command=True)
    async def playlist(self, ctx):
        """Playlist management commands."""
        await ctx.send("Available commands: create, add, remove, list, load, delete, show")

    @playlist.command(name='create')
    async def pl_create(self, ctx, name: str):
        """Creates a new empty playlist."""
        filepath = os.path.join(self.playlist_dir, f"{name}.json")
        if os.path.exists(filepath):
            return await ctx.send(f"Playlist **{name}** already exists.")
        
        with open(filepath, 'w') as f:
            json.dump([], f)
        await ctx.send(f"Playlist **{name}** created.")

    @playlist.command(name='add')
    async def pl_add(self, ctx, name: str, *, song: str):
        """Adds a song (URL/Query) to a playlist."""
        filepath = os.path.join(self.playlist_dir, f"{name}.json")
        if not os.path.exists(filepath):
            return await ctx.send(f"Playlist **{name}** not found.")
        
        with open(filepath, 'r') as f:
            tracks = json.load(f)
        
        tracks.append(song)
        
        with open(filepath, 'w') as f:
            json.dump(tracks, f)
        await ctx.send(f"Added **{song}** to playlist **{name}**.")

    @playlist.command(name='list')
    async def pl_list(self, ctx):
        """Lists all saved playlists."""
        files = [f[:-5] for f in os.listdir(self.playlist_dir) if f.endswith('.json')]
        if not files:
            return await ctx.send("No playlists found.")
        await ctx.send(f"**Saved Playlists:**\n" + "\n".join(files))

    @playlist.command(name='load')
    async def pl_load(self, ctx, name: str):
        """Loads a playlist into the queue."""
        filepath = os.path.join(self.playlist_dir, f"{name}.json")
        if not os.path.exists(filepath):
            return await ctx.send(f"Playlist **{name}** not found.")
        
        if not await self.ensure_voice(ctx):
            return

        with open(filepath, 'r') as f:
            tracks = json.load(f)
        
        for track in tracks:
            self.queue.append((track, ctx.author.id))
        
        await ctx.send(f"Loaded {len(tracks)} songs from **{name}**.")
        if not ctx.voice_client.is_playing():
            await self.play_next(ctx)

    @playlist.command(name='delete')
    async def pl_delete(self, ctx, name: str):
        """Deletes a playlist."""
        filepath = os.path.join(self.playlist_dir, f"{name}.json")
        if not os.path.exists(filepath):
            return await ctx.send(f"Playlist **{name}** not found.")
        os.remove(filepath)
        await ctx.send(f"Playlist **{name}** deleted.")

    # --- Standard Controls ---
    @commands.command(name='skip', aliases=['s'])
    async def skip(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Skipped.")

    @commands.command(name='stop')
    async def stop(self, ctx):
        self.queue.clear()
        if ctx.voice_client:
            ctx.voice_client.stop()
        await ctx.send("Stopped.")

    @commands.command(name='queue', aliases=['q'])
    async def queue_info(self, ctx):
        if len(self.queue) == 0:
            return await ctx.send("Queue is empty.")
        msg = "**Queue:**\n"
        for i, (query, _) in enumerate(list(self.queue)[:10]):
            msg += f"{i+1}. {query}\n"
        if len(self.queue) > 10:
            msg += f"...and {len(self.queue) - 10} more."
        await ctx.send(msg)

    @commands.command(name='shuffle')
    async def shuffle(self, ctx):
        if len(self.queue) < 2:
            return await ctx.send("Not enough songs.")
        temp = list(self.queue)
        random.shuffle(temp)
        self.queue = deque(temp)
        await ctx.send("Queue shuffled.")

    @commands.command(name='loop')
    async def loop(self, ctx):
        self.is_looping = not self.is_looping
        await ctx.send(f"Loop: **{self.is_looping}**")

    @commands.command(name='radio')
    async def radio(self, ctx, *, genre="lofi"):
        query = f"{genre} radio live"
        await self.play(ctx, query=query)

    @commands.command(name='leave')
    async def leave(self, ctx):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()

async def setup(bot):
    await bot.add_cog(Music(bot))

