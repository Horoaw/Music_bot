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
import aiohttp
import sys
import subprocess

# Suppress noise from youtube_dl and fix bug with generic extractor
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ''

# Helper to find ffmpeg executable in current environment
def get_ffmpeg_exe():
    # Check inside the current Python environment (e.g., Conda/Venv bin directory)
    possible_path = os.path.join(os.path.dirname(sys.executable), 'ffmpeg')
    if os.path.exists(possible_path) and os.access(possible_path, os.X_OK):
        return possible_path
    # Fallback to system PATH
    return 'ffmpeg'

ffmpeg_executable = get_ffmpeg_exe()
print(f"Using FFmpeg executable: {ffmpeg_executable}")

# Check for Node.js (Crucial for yt-dlp signature decryption)
try:
    node_version = subprocess.check_output(["node", "--version"], text=True).strip()
    print(f"Node.js found: {node_version}")
except (FileNotFoundError, subprocess.CalledProcessError):
    print("WARNING: Node.js NOT found in PATH. Protected videos (e.g., Vevo) will likely FAIL with 403 errors.")

cookie_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cookies.txt')
print(f"Looking for cookies at: {cookie_path}")
if os.path.exists(cookie_path):
    print(f"Cookies found! Size: {os.path.getsize(cookie_path)} bytes")
else:
    print("WARNING: cookies.txt NOT FOUND at expected path!")

# Set cachedir to a specific persistent directory
cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'music_cache')
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)

ytdl_format_options = {
    'format': 'bestaudio/best',
    # Save to cache directory using video ID to avoid duplicates
    'outtmpl': os.path.join(cache_dir, '%(id)s.%(ext)s'),
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    # DEBUGGING ENABLED: Verbose logging to find why formats are missing
    'logtostderr': True,
    'quiet': False,
    'no_warnings': False,
    'verbose': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'cookiefile': cookie_path,
    # Enable yt-dlp caching to avoid re-downloading if file exists
    'cachedir': cache_dir, 
}

ffmpeg_options = {
    'options': '-vn',
    # Reconnect options are good for streaming, harmless for local files usually, 
    # but let's keep them in a separate dict for streaming mode
}

# Separate options for streaming vs downloading
ffmpeg_streaming_options = {
    'options': '-vn',
    # Aggressive reconnect options to handle 403s and resets
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_on_network_error 1 -reconnect_at_eof 1'
}

# Pool of User-Agents to rotate
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1"
]

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, filename=None, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.filename = filename
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.is_live = data.get('is_live', False)

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        
        # Extract info. If stream=False, this might download the file if not present.
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        
        _ffmpeg_options = {}
        
        if stream:
            _ffmpeg_options = ffmpeg_streaming_options.copy()
            
            # Select a random User-Agent for this session
            current_ua = random.choice(USER_AGENTS)
            
            # Inject headers for streaming to avoid 403
            if 'http_headers' in data:
                headers = data['http_headers']
                # Override or add User-Agent
                headers['User-Agent'] = current_ua
                
                header_items = []
                for key, value in headers.items():
                    header_items.append(f"{key}: {value}")
                
                header_str = "\r\n".join(header_items) + "\r\n"
                
                if 'before_options' in _ffmpeg_options:
                     _ffmpeg_options['before_options'] = f'-headers "{header_str}" ' + _ffmpeg_options['before_options']
                else:
                     _ffmpeg_options['before_options'] = f'-headers "{header_str}"'

                # Also add -user_agent flag explicitly for protocols that use it directly
                _ffmpeg_options['before_options'] += f' -user_agent "{current_ua}"'
                
                print(f"DEBUG: Streaming with UA: {current_ua}")
            else:
                # If no headers from yt-dlp, just inject our UA
                _ffmpeg_options['before_options'] += f' -user_agent "{current_ua}"'
        else:
            _ffmpeg_options = ffmpeg_options.copy()
            print(f"DEBUG: Playing local file: {filename}")

        return cls(discord.FFmpegPCMAudio(filename, executable=ffmpeg_executable, **_ffmpeg_options), data=data, filename=filename)

    def cleanup(self):
        # We do NOT delete the file if it's a local download (filename exists and is not a URL)
        # This satisfies "I don't want to repeat downloading the same song"
        # Only cleanup if we are strictly streaming and have temp artifacts (rare for FFmpegPCMAudio)
        super().cleanup()

    @classmethod
    async def search_source(cls, query, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch5:{query}", download=False))
        
        if 'entries' not in data:
            return []
        
        results = []
        for entry in data['entries']:
            results.append({
                'title': entry.get('title'),
                'url': entry.get('webpage_url', entry.get('url')),
                'id': entry.get('id'),
                'duration': entry.get('duration', 0)
            })
        return results

class SearchSelect(discord.ui.Select):
    def __init__(self, ctx, results, music_cog):
        self.ctx = ctx
        self.music_cog = music_cog
        self.results = results
        options = []
        for i, res in enumerate(results):
            seconds = res.get('duration', 0)
            if seconds:
                m, s = divmod(seconds, 60)
                if m >= 60:
                    h, m = divmod(m, 60)
                    duration_str = f"{int(h)}:{int(m):02d}:{int(s):02d}"
                else:
                    duration_str = f"{int(m)}:{int(s):02d}"
            else:
                duration_str = "N/A"

            label = f"{i+1}. {res['title']}"[:90] 
            description = f"⏱️ {duration_str}"
            options.append(discord.SelectOption(label=label, description=description, value=str(i)))

        super().__init__(placeholder="Select a song to play...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("This menu is not for you.", ephemeral=True)
        
        selection_index = int(self.values[0])
        selected_song = self.results[selection_index]
        
        await interaction.response.defer()
        
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
        self.download_retries = set() # Track songs that failed streaming and need downloading
        
        if not os.path.exists(self.playlist_dir):
            os.makedirs(self.playlist_dir)

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

    async def safe_send(self, ctx, content):
        """Safely send a message, ignoring errors if the channel is unknown/gone."""
        try:
            return await ctx.send(content)
        except (discord.NotFound, discord.HTTPException) as e:
            print(f"Warning: Could not send message to channel {ctx.channel.id}: {e}")
            return None

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
            self.queue.appendleft(self.current_song)

        if len(self.queue) > 0:
            if self.is_shuffling:
                pass 
            
            query, requester_id = self.queue.popleft()
            self.current_song = (query, requester_id)
            
            try:
                if not ctx.voice_client:
                    guild = ctx.guild
                    requester = guild.get_member(requester_id)
                    if requester and requester.voice:
                         await requester.voice.channel.connect(self_deaf=True)
                    else:
                         await self.safe_send(ctx, f"Skipped **{query}**: Bot is not connected to voice and cannot reconnect.")
                         self.queue.clear()
                         return

                # FAILOVER LOGIC:
                # If query is in download_retries, use stream=False (Download)
                # Else use stream=True (Stream)
                should_download = query in self.download_retries
                
                if should_download:
                     print(f"Retry Mode: Downloading {query}...")
                     await self.safe_send(ctx, f"⬇️ Downloading **{query}** to server cache (Streaming failed)...")
                
                source = await YTDLSource.from_url(query, loop=self.bot.loop, stream=not should_download)
                
                def after_playing(error):
                    if error:
                        print(f"Player error: {error}")
                        # Check if it was a 403 or streaming error
                        # If we were streaming, try downloading next time
                        if not should_download:
                            if source.is_live:
                                print(f"Live stream {query} failed. Retrying stream (re-extract URL)...")
                                # Live streams should NOT be downloaded. Just retry streaming.
                                self.queue.appendleft((query, requester_id))
                            else:
                                print(f"Streaming failed for {query}. Retrying with download.")
                                self.download_retries.add(query)
                                self.queue.appendleft((query, requester_id))
                            
                            self.bot.loop.create_task(self.play_next(ctx))
                            return
                        else:
                             # If download failed or playing downloaded file failed
                             if source.is_live:
                                  print(f"Live stream retry failed for {query}. Retrying...")
                                  self.queue.appendleft((query, requester_id))
                                  self.bot.loop.create_task(self.play_next(ctx))
                                  return

                             self.bot.loop.create_task(self.safe_send(ctx, f"Player error: {error}"))
                    
                    # If successful (or failed download), remove from retries and move on
                    if query in self.download_retries:
                        self.download_retries.remove(query)
                        
                    self.bot.loop.create_task(self.play_next(ctx))

                ctx.voice_client.play(source, after=after_playing)
                await self.safe_send(ctx, f'Now playing: **{source.title}**')
            
            except Exception as e:
                error_msg = f"Error playing **{query}**: {e}"
                str_e = str(e)
                if "Sign in to confirm your age" in str_e or "Sign in to confirm you’re not a bot" in str_e:
                    error_msg += "\n⚠️ **Authentication Required**: Please upload a valid `cookies.txt` file to the server root directory to play this video."
                
                await self.safe_send(ctx, error_msg)
                print(f"Error playing {query}: {e}")
                # If extraction fails, maybe try downloading?
                if not should_download:
                     # Caution: We can't know if it's live if extraction failed. 
                     # Safe bet: Try download unless we already know it's a retry.
                     self.download_retries.add(query)
                     self.queue.appendleft((query, requester_id))
                await self.play_next(ctx)
        else:
            self.current_song = None
            await self.safe_send(ctx, "Queue finished.")

    async def ensure_voice(self, ctx):
        if not ctx.voice_client:
            if ctx.author.voice:
                try:
                    await ctx.author.voice.channel.connect(self_deaf=True, timeout=60.0)
                except asyncio.TimeoutError:
                    await ctx.send("Error: Connection to voice channel timed out. (Discord Voice Server might be unreachable)")
                    return False
                except Exception as e:
                    await ctx.send(f"Error connecting to voice channel: {e}")
                    return False
            else:
                await ctx.send("You are not connected to a voice channel.")
                return False
        return True

    async def play_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if not current:
            return []
        
        url = f"http://suggestqueries.google.com/complete/search?client=youtube&ds=yt&q={current}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    pass # Simplified for brevity
                
        url = f"http://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q={current}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = json.loads(await response.text())
                    suggestions = data[1]
                    return [
                        app_commands.Choice(name=suggestion, value=suggestion)
                        for suggestion in suggestions[:25] 
                    ]
        return []

    @commands.hybrid_command(name='play', aliases=['p'], description="Plays a song or adds to queue (URL or Search).")
    @app_commands.describe(query="The song URL or search term.")
    @app_commands.autocomplete(query=play_autocomplete)
    async def play(self, ctx: commands.Context, *, query: str):
        await ctx.defer() 
        
        if not await self.ensure_voice(ctx):
            return
            
        if not ctx.voice_client:
            return await ctx.send("Error: Failed to verify voice connection.")

        # Sanitize YouTube URL: If it has v= and list=, strip the list part to avoid yt-dlp Mix errors
        if 'youtube.com/watch' in query and 'list=' in query:
            try:
                # Basic parsing to keep only v=...
                import urllib.parse as urlparse
                parsed = urlparse.urlparse(query)
                params = urlparse.parse_qs(parsed.query)
                if 'v' in params:
                    video_id = params['v'][0]
                    query = f"https://www.youtube.com/watch?v={video_id}"
                    print(f"Sanitized Mix URL to: {query}")
            except Exception as e:
                print(f"Error sanitizing URL: {e}")

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

    @commands.hybrid_command(name='search', description="Searches YouTube and lets you select a song.")
    @app_commands.describe(query="The search term for YouTube.")
    async def search(self, ctx: commands.Context, *, query: str):
        await ctx.defer() 
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
    @commands.hybrid_group(name='playlist', description="Playlist management commands.")
    async def playlist(self, ctx: commands.Context):
        await ctx.send("Available commands: create, add, remove, list, load, delete, show")

    async def playlist_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        playlists = [f[:-5] for f in os.listdir(self.playlist_dir) if f.endswith('.json')]
        return [
            app_commands.Choice(name=pl, value=pl)
            for pl in playlists if current.lower() in pl.lower()
        ][:25]

    async def playlist_song_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
        playlist_name = interaction.namespace.name
        if not playlist_name:
            return []
        
        filepath = os.path.join(self.playlist_dir, f"{playlist_name}.json")
        if not os.path.exists(filepath):
            return []
        
        try:
            with open(filepath, 'r') as f:
                tracks = json.load(f)
        except:
            return []
            
        choices = []
        for i, song in enumerate(tracks):
            label = f"{i+1}. {song}"[:100]
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=i+1))
        
        return choices[:25]

    @playlist.command(name='create', description="Creates a new empty playlist.")
    @app_commands.describe(name="The name of the playlist to create.")
    async def pl_create(self, ctx: commands.Context, name: str):
        filepath = os.path.join(self.playlist_dir, f"{name}.json")
        if os.path.exists(filepath):
            return await ctx.send(f"Playlist **{name}** already exists.")
        
        with open(filepath, 'w') as f:
            json.dump([], f)
        await ctx.send(f"Playlist **{name}** created.")

    @playlist.command(name='add', description="Adds songs to a playlist. Supports URLs, search terms (comma-separated), or playlists.")
    @app_commands.describe(name="The name of the playlist.", song_query="URLs/Terms (separate with comma for multiple), or a Playlist URL.")
    @app_commands.autocomplete(name=playlist_autocomplete)
    async def pl_add(self, ctx: commands.Context, name: str, *, song_query: str):
        await ctx.defer() 
        filepath = os.path.join(self.playlist_dir, f"{name}.json")
        if not os.path.exists(filepath):
            return await ctx.send(f"Playlist **{name}** not found.")
        
        with open(filepath, 'r') as f:
            tracks = json.load(f)

        added_count = 0
        if 'list=' in song_query and ('youtube.com/playlist' in song_query or 'youtube.com/watch' in song_query): 
            msg = await ctx.send("Processing YouTube playlist...")
            try:
                loop = self.bot.loop or asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(song_query, download=False, process_info=False)) 

                if 'entries' in data:
                    for entry in data['entries']:
                        song_info = await loop.run_in_executor(None, lambda: ytdl.extract_info(entry['url'], download=False))
                        tracks.append(song_info.get('webpage_url', song_info.get('url', song_info.get('title'))))
                        added_count += 1
                await msg.edit(content=f"Added {added_count} songs from YouTube playlist to **{name}**.")
            except Exception as e:
                await msg.edit(content=f"Error processing YouTube playlist: {e}")
                print(f"Error processing YouTube playlist: {e}")
                return
        elif 'spotify.com' in song_query:
            msg = await ctx.send("Processing Spotify link...")
            spotify_tracks = await self.get_spotify_tracks(song_query)
            if not spotify_tracks:
                await msg.edit(content="Could not load Spotify tracks.")
                return
            for track_title in spotify_tracks:
                tracks.append(track_title)
                added_count += 1
            await msg.edit(content=f"Added {added_count} songs from Spotify link to **{name}**.")
        else:
            songs_to_add = [s.strip() for s in song_query.replace('|', ',').split(',') if s.strip()]
            
            for song in songs_to_add:
                tracks.append(song)
                added_count += 1
            
            if added_count > 1:
                await ctx.send(f"Added {added_count} songs to playlist **{name}**:\n" + ", ".join(songs_to_add)[:1900])
            elif added_count == 1:
                await ctx.send(f"Added **{songs_to_add[0]}** to playlist **{name}**.")
            else:
                await ctx.send("No valid songs found to add.")

        with open(filepath, 'w') as f:
            json.dump(tracks, f)

    async def play_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if current.startswith(('http://', 'https://')):
            return []
        if not current:
            return []
        # ... (rest of the play_autocomplete logic)


    @playlist.command(name='list', description="Lists all saved playlists.")
    async def pl_list(self, ctx: commands.Context):
        files = [f[:-5] for f in os.listdir(self.playlist_dir) if f.endswith('.json')]
        if not files:
            return await ctx.send("No playlists found.")
        await ctx.send(f"**Saved Playlists:**\n" + "\n".join(files))

    @playlist.command(name='load', description="Loads a playlist into the queue.")
    @app_commands.describe(name="The name of the playlist to load.")
    @app_commands.autocomplete(name=playlist_autocomplete)
    async def pl_load(self, ctx: commands.Context, name: str):
        await ctx.defer() 
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

    @playlist.command(name='delete', description="Deletes a playlist.")
    @app_commands.describe(name="The name of the playlist to delete.")
    @app_commands.autocomplete(name=playlist_autocomplete)
    async def pl_delete(self, ctx: commands.Context, name: str):
        filepath = os.path.join(self.playlist_dir, f"{name}.json")
        if not os.path.exists(filepath):
            return await ctx.send(f"Playlist **{name}** not found.")
        os.remove(filepath)
        await ctx.send(f"Playlist **{name}** deleted.")

    @playlist.command(name='show', description="Shows the songs in a playlist.")
    @app_commands.describe(name="The name of the playlist.")
    @app_commands.autocomplete(name=playlist_autocomplete)
    async def pl_show(self, ctx: commands.Context, name: str):
        filepath = os.path.join(self.playlist_dir, f"{name}.json")
        if not os.path.exists(filepath):
            return await ctx.send(f"Playlist **{name}** not found.")
        
        with open(filepath, 'r') as f:
            tracks = json.load(f)
        
        if not tracks:
            return await ctx.send(f"Playlist **{name}** is empty.")
        
        msg = f"**Playlist {name}:**\n"
        for i, song in enumerate(tracks):
            msg += f"{i+1}. {song}\n"
            if len(msg) > 1900:
                msg += "...(truncated)"
                break
        await ctx.send(msg)

    @playlist.command(name='remove', description="Removes a song from a playlist by index.")
    @app_commands.describe(name="The name of the playlist.", index="The index of the song to remove.")
    @app_commands.autocomplete(name=playlist_autocomplete, index=playlist_song_autocomplete)
    async def pl_remove_song(self, ctx: commands.Context, name: str, index: int):
        filepath = os.path.join(self.playlist_dir, f"{name}.json")
        if not os.path.exists(filepath):
            return await ctx.send(f"Playlist **{name}** not found.")
        
        with open(filepath, 'r') as f:
            tracks = json.load(f)
        
        if index < 1 or index > len(tracks):
            return await ctx.send(f"Invalid index. Use `/playlist show {name}` to check indices.")
        
        removed = tracks.pop(index - 1)
        
        with open(filepath, 'w') as f:
            json.dump(tracks, f)
        await ctx.send(f"Removed **{removed}** from playlist **{name}**.")

    # --- Standard Controls ---
    @commands.hybrid_command(name='skip', aliases=['s'], description="Skips the current song.")
    async def skip(self, ctx: commands.Context):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Skipped.")

    @commands.hybrid_command(name='stop', description="Stops playback and clears the queue.")
    async def stop(self, ctx: commands.Context):
        self.queue.clear()
        if ctx.voice_client:
            ctx.voice_client.stop()
        await ctx.send("Stopped.")

    @commands.hybrid_command(name='queue', aliases=['q'], description="Displays the current queue.")
    async def queue_info(self, ctx: commands.Context):
        if len(self.queue) == 0:
            return await ctx.send("Queue is empty.")
        msg = "**Queue:**\n"
        for i, (query, _) in enumerate(list(self.queue)[:10]):
            msg += f"{i+1}. {query}\n"
        if len(self.queue) > 10:
            msg += f"...and {len(self.queue) - 10} more."
        await ctx.send(msg)

    @commands.hybrid_command(name='shuffle', description="Shuffles the current queue.")
    async def shuffle(self, ctx: commands.Context):
        if len(self.queue) < 2:
            return await ctx.send("Not enough songs.")
        temp = list(self.queue)
        random.shuffle(temp)
        self.queue = deque(temp)
        await ctx.send("Queue shuffled.")

    @commands.hybrid_command(name='loop', description="Toggles loop mode for the current song.")
    async def loop(self, ctx: commands.Context):
        self.is_looping = not self.is_looping
        await ctx.send(f"Loop: **{self.is_looping}**")

    @commands.hybrid_command(name='radio', description="Plays a radio stream.")
    @app_commands.describe(genre="The genre of the radio to play (e.g., lofi, jazz).")
    async def radio(self, ctx: commands.Context, *, genre: str = "lofi"):
        await ctx.defer() # Defer immediately
        query = f"{genre} radio live"
        await self.play(ctx, query=query)

    @commands.hybrid_command(name='leave', description="Disconnects the bot from the voice channel.")
    async def leave(self, ctx: commands.Context):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()

    @commands.hybrid_command(name='help', description="Shows available commands (English/Chinese). | 显示可用命令 (中/英).")
    async def help(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🎵 Music Bot Help / 音乐机器人帮助",
            description="Here are the available commands / 以下是可用命令:",
            color=discord.Color.blue()
        )

        # General Commands
        embed.add_field(
            name="▶️ **!play / !p <url|query>**",
            value="Plays a song from URL or search term.\n播放链接或搜索关键词对应的歌曲。",
            inline=False
        )
        embed.add_field(
            name="🔍 **!search <query>**",
            value="Searches YouTube and lets you select a song.\n搜索 YouTube 并让你选择一首歌曲。",
            inline=False
        )
        embed.add_field(
            name="⏭️ **!skip / !s**",
            value="Skips the current song.\n跳过当前播放的歌曲。",
            inline=False
        )
        embed.add_field(
            name="⏹️ **!stop**",
            value="Stops playback and clears the queue.\n停止播放并清空播放队列。",
            inline=False
        )
        embed.add_field(
            name="📜 **!queue / !q**",
            value="Displays the current song queue.\n显示当前的播放队列。",
            inline=False
        )
        embed.add_field(
            name="🔀 **!shuffle**",
            value="Shuffles the current queue.\n随机打乱播放队列。",
            inline=False
        )
        embed.add_field(
            name="🔁 **!loop**",
            value="Toggles loop mode for the current song.\n切换当前歌曲的循环模式。",
            inline=False
        )
        embed.add_field(
            name="📻 **!radio [genre]**",
            value="Plays a live radio stream (default: lofi).\n播放直播电台 (默认: lofi)。",
            inline=False
        )
        embed.add_field(
            name="📂 **!playlist**",
            value="Playlist commands: `create`, `add`, `remove`, `list`, `load`, `delete`.\n播放列表命令: `create`, `add`, `remove`, `list`, `load`, `delete`。",
            inline=False
        )
        embed.add_field(
            name="🚪 **!leave**",
            value="Disconnects the bot from the voice channel.\n断开机器人与语音频道的连接。",
            inline=False
        )

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Music(bot))