import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from collections import deque
import random

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
    'source_address': '0.0.0.0' # Bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5' # Reconnect on stream drop
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
        # If it's a search query (not a URL), ytdl handles it via default_search
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist/search result
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = deque() # Stores tuples: (query_or_url, requester_id)
        self.current_song = None
        self.is_looping = False
        self.is_shuffling = False
        self.autoplay = False
        
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
        """Extracts track(s) from a Spotify URL and returns a list of search queries."""
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

    def play_next(self, ctx):
        if self.is_looping and self.current_song:
            # If looping, add the current song back to the front (or just replay it)
            # To keep it simple, we'll re-queue the *query* of the current song
            self.queue.appendleft(self.current_song)

        if len(self.queue) > 0:
            if self.is_shuffling:
                # Randomly pick a song from queue
                # Note: deque doesn't support random access efficiently, so we convert to list temporarily
                # A better shuffle implementation would shuffle the deque once on command
                pass # Basic shuffle implemented in command, here we just take next
            
            query, requester = self.queue.popleft()
            self.current_song = (query, requester)
            
            # Resolve source
            coro = YTDLSource.from_url(query, loop=self.bot.loop, stream=True)
            future = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
            
            try:
                player = future.result()
                ctx.voice_client.play(player, after=lambda e: self.play_next(ctx))
                asyncio.run_coroutine_threadsafe(ctx.send(f'Now playing: **{player.title}**'), self.bot.loop)
            except Exception as e:
                print(f"Error playing {query}: {e}")
                self.play_next(ctx) # Skip faulty song
        else:
            self.current_song = None
            if self.autoplay:
                # TODO: Implement autoplay logic here (fetch related from last song)
                pass
            # Disconnect logic could go here if 24/7 mode is off

    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx, *, query):
        """Plays a song from YouTube, Spotify, or URL."""
        
        if not ctx.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                return await ctx.send("You are not connected to a voice channel.")

        # Check for Spotify
        if 'spotify.com' in query:
            msg = await ctx.send("Processing Spotify link...")
            tracks = await self.get_spotify_tracks(query)
            if not tracks:
                return await msg.edit(content="Could not load Spotify tracks. Check URL or Bot Config.")
            
            for track in tracks:
                self.queue.append((track, ctx.author.id))
            
            await msg.edit(content=f"Queued {len(tracks)} tracks from Spotify.")
            
            if not ctx.voice_client.is_playing():
                self.play_next(ctx)
        else:
            # Regular YouTube/URL
            self.queue.append((query, ctx.author.id))
            if not ctx.voice_client.is_playing():
                self.play_next(ctx)
            else:
                await ctx.send(f'Added to queue: {query}')

    @commands.command(name='queue', aliases=['q'])
    async def queue_info(self, ctx):
        """Displays the current queue."""
        if len(self.queue) == 0:
            return await ctx.send("Queue is empty.")
        
        msg = "**Queue:**\n"
        for i, (query, _) in enumerate(list(self.queue)[:10]): # Show top 10
            msg += f"{i+1}. {query}\n"
        
        if len(self.queue) > 10:
            msg += f"...and {len(self.queue) - 10} more."
        
        await ctx.send(msg)

    @commands.command(name='skip', aliases=['s'])
    async def skip(self, ctx):
        """Skips the current song."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Skipped.")

    @commands.command(name='stop')
    async def stop(self, ctx):
        """Stops playback and clears queue."""
        self.queue.clear()
        if ctx.voice_client:
            ctx.voice_client.stop()
        await ctx.send("Stopped and queue cleared.")

    @commands.command(name='leave', aliases=['disconnect'])
    async def leave(self, ctx):
        """Disconnects the bot."""
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("Disconnected.")

    @commands.command(name='loop')
    async def loop(self, ctx):
        """Toggles loop mode (repeats the current song)."""
        self.is_looping = not self.is_looping
        await ctx.send(f"Looping is now **{'ON' if self.is_looping else 'OFF'}**.")

    @commands.command(name='shuffle')
    async def shuffle(self, ctx):
        """Shuffles the current queue."""
        if len(self.queue) < 2:
            return await ctx.send("Not enough songs to shuffle.")
        
        # Create a list from deque, shuffle, recreate deque
        temp_list = list(self.queue)
        random.shuffle(temp_list)
        self.queue = deque(temp_list)
        await ctx.send("Queue shuffled.")

    @commands.command(name='radio')
    async def radio(self, ctx, *, genre="lofi"):
        """Plays a radio stream (defaults to Lofi Girl or searches genre)."""
        # Basic implementation: Search for "genre radio live" on YouTube
        query = f"{genre} radio live"
        await self.play(ctx, query=query)

    @commands.command(name='save')
    async def save_playlist(self, ctx, name: str):
        """Saves the current queue to a playlist."""
        if not self.queue:
            return await ctx.send("Queue is empty, nothing to save.")
        
        import json
        playlist_data = list(self.queue)
        # We only save the query/url, not the requester for simplicity in this prototype
        tracks = [q[0] for q in playlist_data]
        
        filepath = os.path.join('data', f'{name}.json')
        try:
            with open(filepath, 'w') as f:
                json.dump(tracks, f)
            await ctx.send(f"Playlist **{name}** saved with {len(tracks)} songs.")
        except Exception as e:
            await ctx.send(f"Error saving playlist: {e}")

    @commands.command(name='load')
    async def load_playlist(self, ctx, name: str):
        """Loads a playlist into the queue."""
        filepath = os.path.join('data', f'{name}.json')
        if not os.path.exists(filepath):
            return await ctx.send(f"Playlist **{name}** not found.")
        
        import json
        try:
            with open(filepath, 'r') as f:
                tracks = json.load(f)
            
            for track in tracks:
                self.queue.append((track, ctx.author.id))
            
            await ctx.send(f"Loaded {len(tracks)} songs from **{name}**.")
            
            if not ctx.voice_client or not ctx.voice_client.is_playing():
                 # If bot is idle, start playing
                if ctx.author.voice:
                     if not ctx.voice_client:
                         await ctx.author.voice.channel.connect()
                     self.play_next(ctx)
        except Exception as e:
            await ctx.send(f"Error loading playlist: {e}")

async def setup(bot):
    await bot.add_cog(Music(bot))
