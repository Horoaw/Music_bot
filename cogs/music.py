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
import traceback
import re

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

# Ensure Node.js is in PATH for yt-dlp
def ensure_node_path():
    # Force add standard system paths to PATH
    extra_paths = ['/usr/bin', '/usr/local/bin']
    current_path = os.environ.get("PATH", "")
    
    # Ensure system paths are at the VERY front
    new_path = os.pathsep.join(extra_paths + [current_path])
    os.environ["PATH"] = new_path
    
    print(f"DEBUG: Updated PATH for yt-dlp: {os.environ['PATH']}")
    
    import shutil
    node_path = shutil.which("node")
    print(f"DEBUG: shutil.which('node') returns: {node_path}")

    # Verify if the found node actually works
    if node_path:
        try:
            node_version = subprocess.check_output([node_path, "--version"], stderr=subprocess.STDOUT, text=True).strip()
            print(f"DEBUG: Node.js at {node_path} is version: {node_version}")
            
            # AGGRESSIVE FIX:
            # If we detect Conda's node, FORCE switch to System Node.
            if "anaconda" in node_path or "envs" in node_path:
                print("DEBUG: Detected Conda/Env Node.js. Forcing switch to System Node to fix yt-dlp issues.")
                
                # Remove that Conda directory from PATH
                broken_dir = os.path.dirname(node_path)
                env_paths = os.environ["PATH"].split(os.pathsep)
                clean_paths = [p for p in env_paths if os.path.abspath(p) != os.path.abspath(broken_dir)]
                # Re-add system paths just in case
                clean_paths = extra_paths + clean_paths
                os.environ["PATH"] = os.pathsep.join(clean_paths)
                print(f"DEBUG: Cleaned PATH: {os.environ['PATH']}")
                
                # Re-check
                new_node = shutil.which("node")
                print(f"DEBUG: New shutil.which('node'): {new_node}")

        except Exception as e:
            print(f"WARNING: Node.js check failed: {e}")

ensure_node_path()

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
    'outtmpl': os.path.join(cache_dir, '%(id)s.%(ext)s'),
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'force_ipv4': True,
    'cachedir': cache_dir,
    'ignore_no_formats_error': True,
    'sleep_interval': 1,
    'max_sleep_interval': 3,
    'socket_timeout': 30,
    'retries': 10,
    'extract_flat': 'in_playlist',
}

ffmpeg_options = {
    'options': '-vn',
}

# Separate options for streaming vs downloading
ffmpeg_streaming_options = {
    'options': '-vn',
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
    async def from_url(cls, url, *, loop=None, stream=True, ctx=None, source_type='youtube', ytdl_instance=None):
        loop = loop or asyncio.get_event_loop()
        
        if not ytdl_instance:
             # Fallback if no instance provided, though Music cog should provide it
             ytdl_instance = yt_dlp.YoutubeDL(ytdl_format_options)

        # Extract info. If stream=False, this might download the file if not present.
        try:
            data = await loop.run_in_executor(None, lambda: ytdl_instance.extract_info(url, download=not stream))
        except Exception as e:
            err_msg = str(e).strip().split('\n')[-1]
            print(f"ERROR: Failed to extract info for {url}: {err_msg}")
            raise e

        if 'entries' in data:
            # take first item from a playlist
            if not data['entries']:
                raise Exception("No search results found.")
            data = data['entries'][0]

        if not data:
            raise Exception("Failed to extract any data from the provided URL/query.")

        # Ensure we have a title and a playable URL/id
        if 'title' not in data:
            data['title'] = "Unknown Title"
        
        # Robust URL extraction
        filename = data.get('url')
        if not filename and 'formats' in data:
            # Sort formats to find best audio
            try:
                # Filter for audio-only formats
                audio_formats = [f for f in data['formats'] if f.get('vcodec') == 'none' and f.get('url')]
                if not audio_formats:
                    # Fallback to any format with a URL if no audio-only found
                    audio_formats = [f for f in data['formats'] if f.get('url')]
                
                if audio_formats:
                    # Sort by quality (abr)
                    audio_formats.sort(key=lambda x: x.get('abr', 0) or 0, reverse=True)
                    filename = audio_formats[0]['url']
            except Exception as e:
                print(f"DEBUG: Format sorting failed: {e}")

        if not stream:
            filename = ytdl_instance.prepare_filename(data)

        if not filename:
             raise Exception("The extracted data does not contain a valid URL or filename for playback.")
        
        _ffmpeg_options = {}
        
        if stream:
            _ffmpeg_options = ffmpeg_streaming_options.copy()
            current_ua = random.choice(USER_AGENTS)
            
            # Inject headers for streaming to avoid 403
            headers = data.get('http_headers', {})
            # Only override User-Agent if not already specific or if we want rotation
            headers['User-Agent'] = current_ua
            
            # Bilibili specific: Needs Referer
            if source_type == 'bilibili':
                headers['Referer'] = 'https://www.bilibili.com/'
            
            header_items = [f"{key}: {value}" for key, value in headers.items()]
            header_str = "\r\n".join(header_items) + "\r\n"
            
            if 'before_options' in _ffmpeg_options:
                 _ffmpeg_options['before_options'] = f'-headers "{header_str}" ' + _ffmpeg_options['before_options']
            else:
                 _ffmpeg_options['before_options'] = f'-headers "{header_str}"'

            _ffmpeg_options['before_options'] += f' -user_agent "{current_ua}"'
        else:
            _ffmpeg_options = ffmpeg_options.copy()

        return cls(discord.FFmpegPCMAudio(filename, executable=ffmpeg_executable, **_ffmpeg_options), data=data, filename=filename)

    def cleanup(self):
        super().cleanup()

    @classmethod
    async def search_source(cls, query, *, loop=None, ytdl_instance=None):
        loop = loop or asyncio.get_event_loop()
        if not ytdl_instance:
            return []
        data = await loop.run_in_executor(None, lambda: ytdl_instance.extract_info(f"ytsearch5:{query}", download=False))
        
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
            description = f"{duration_str}"
            options.append(discord.SelectOption(label=label, description=description, value=str(i)))

        super().__init__(placeholder="Select a song to play...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("This menu is not for you.", ephemeral=True)
        
        selection_index = int(self.values[0])
        selected_song = self.results[selection_index]
        
        await interaction.response.defer()
        
        self.music_cog.queue.append((selected_song['url'], self.ctx.author.id))
        
        if self.ctx.voice_client and not self.ctx.voice_client.is_playing():
            await self.music_cog.play_next(self.ctx)
        else:
            await interaction.followup.send(f"SUCCESS: Queued **{selected_song['title']}**")
            await self.music_cog.update_player(self.ctx)

class SearchView(discord.ui.View):
    def __init__(self, ctx, results, music_cog):
        super().__init__(timeout=60)
        self.add_item(SearchSelect(ctx, results, music_cog))

class PlayerView(discord.ui.View):
    def __init__(self, music_cog, ctx):
        super().__init__(timeout=None)
        self.music_cog = music_cog
        self.ctx = ctx

    @discord.ui.button(label="PLAY / PAUSE", style=discord.ButtonStyle.secondary)
    async def play_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.ctx.voice_client:
            return await interaction.response.send_message("Bot is not connected.", ephemeral=True)
        
        if self.ctx.voice_client.is_playing():
            self.ctx.voice_client.pause()
            await interaction.response.send_message("Paused.", ephemeral=True)
        elif self.ctx.voice_client.is_paused():
            self.ctx.voice_client.resume()
            await interaction.response.send_message("Resumed.", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing playing.", ephemeral=True)
        
        await self.music_cog.update_player(self.ctx)

    @discord.ui.button(label="SKIP", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.ctx.voice_client:
            self.ctx.voice_client.stop()
            await interaction.response.send_message("Skipped.", ephemeral=True)
        else:
            await interaction.response.send_message("Bot is not connected.", ephemeral=True)

    @discord.ui.button(label="STOP", style=discord.ButtonStyle.secondary)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.music_cog.queue.clear()
        if self.ctx.voice_client:
            self.ctx.voice_client.stop()
        await interaction.response.send_message("Stopped and cleared queue.", ephemeral=True)
        await self.music_cog.update_player(self.ctx)

    @discord.ui.button(label="SHUFFLE", style=discord.ButtonStyle.secondary)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.music_cog.is_shuffling = not self.music_cog.is_shuffling
        status = "enabled" if self.music_cog.is_shuffling else "disabled"
        await interaction.response.send_message(f"Shuffle {status}.", ephemeral=True)
        await self.music_cog.update_player(self.ctx)

    @discord.ui.button(label="LOOP", style=discord.ButtonStyle.secondary)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.music_cog.is_looping = not self.music_cog.is_looping
        status = "enabled" if self.music_cog.is_looping else "disabled"
        await interaction.response.send_message(f"Loop {status}.", ephemeral=True)
        await self.music_cog.update_player(self.ctx)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # YouTube specific options
        yt_opts = ytdl_format_options.copy()
        yt_opts.update({
            'format': 'bestaudio/best',
            'cookiefile': cookie_path,
            # Aggressive client rotation to avoid 403
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'android', 'mweb'],
                    'player_skip': ['webpage', 'configs'],
                }
            },
            'geo_bypass': True,
            'nocheckcertificate': True,
            'prefer_insecure': True,
        })
        self.ytdl_yt = yt_dlp.YoutubeDL(yt_opts)

        # Bilibili specific options
        bili_opts = ytdl_format_options.copy()
        bili_opts.update({
            'format': 'bestaudio/best',
            'http_headers': {
                'Referer': 'https://www.bilibili.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        })
        self.ytdl_bili = yt_dlp.YoutubeDL(bili_opts)

        self.queue = deque()
        self.current_song = None
        self.current_source = None
        self.player_messages = {} # guild_id -> Message
        self.is_looping = False
        self.is_shuffling = False
        self.autoplay = False
        self.playlist_dir = 'data/playlists'
        self.bili_retries = set()     # Track clean titles that were already fallbacked
        
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

    def create_player_embed(self, source, ctx):
        embed = discord.Embed(
            title="NOW PLAYING",
            description=f"**[{source.title}]({source.url})**",
            color=0x1DB954 # Spotify Green
        )
        
        if source.data.get('thumbnail'):
            embed.set_thumbnail(url=source.data['thumbnail'])
        
        duration = source.data.get('duration')
        if duration:
            m, s = divmod(duration, 60)
            duration_str = f"{int(m)}:{int(s):02d}"
            embed.add_field(name="DURATION", value=duration_str, inline=True)
        
        status = "PLAYING"
        if ctx.voice_client:
            if ctx.voice_client.is_paused():
                status = "PAUSED"
            elif not ctx.voice_client.is_playing():
                status = "STOPPED"
        
        embed.add_field(name="STATUS", value=status, inline=True)
        
        loop_status = "ON" if self.is_looping else "OFF"
        shuffle_status = "ON" if self.is_shuffling else "OFF"
        embed.add_field(name="LOOP", value=loop_status, inline=True)
        embed.add_field(name="SHUFFLE", value=shuffle_status, inline=True)

        if len(self.queue) > 0:
            next_song = self.queue[0][0]
            embed.add_field(name="NEXT SONG", value=next_song[:50] + ("..." if len(next_song) > 50 else ""), inline=False)

        embed.set_footer(text="SPOTIFY INTERACTIVE PLAYER")
        return embed

    async def update_player(self, ctx, source=None):
        if source:
            self.current_source = source
        
        if not self.current_source:
            return

        embed = self.create_player_embed(self.current_source, ctx)
        view = PlayerView(self, ctx)
        
        guild_id = ctx.guild.id
        old_msg = self.player_messages.get(guild_id)

        # Delete old message to keep chat clean and ensure player is at the bottom
        if old_msg:
            try:
                await old_msg.delete()
            except:
                pass

        try:
            new_msg = await ctx.send(embed=embed, view=view)
            self.player_messages[guild_id] = new_msg
        except Exception as e:
            print(f"ERROR: Could not send player message: {e}")

    async def trigger_bili_fallback(self, ctx, query, requester_id):
        """Fallback to Bilibili for YouTube failures."""
        if query in self.bili_retries:
            return await self.play_next(ctx)

        self.bili_retries.add(query)
        
        search_query = query
        if query.startswith('http'):
            try:
                # Try to get info to extract title
                info = await self.bot.loop.run_in_executor(None, lambda: self.ytdl_yt.extract_info(query, download=False, process=False))
                search_query = info.get('title', query)
            except:
                search_query = re.sub(r'https?://(www\.)?(youtube\.com/watch\?v=|youtu\.be/|bilibili\.com/video/)', '', query)
                search_query = re.sub(r'[^\w\s]', ' ', search_query)
                search_query = ' '.join(search_query.split()).strip()

        # Clean search query by removing common junk
        clean_query = search_query
        junk_patterns = [
            r"\(Official Video\)", r"\[Official Video\]", r"Official Video",
            r"\(Official Audio\)", r"\[Official Audio\]", r"Official Audio",
            r"\(MV\)", r"\[MV\]", r"\bMV\b",
            r"\(HD\)", r"\[HD\]", r"\bHD\b",
            r"\(1080p\)", r"\[1080p\]", r"1080p",
            r"\(4K\)", r"\[4K\]", r"4K",
            r"\(Lyrics\)", r"\[Lyrics\]", r"Lyrics"
        ]
        for pattern in junk_patterns:
            clean_query = re.sub(pattern, "", clean_query, flags=re.IGNORECASE)
        
        clean_query = ' '.join(clean_query.split()).strip()
        search_query_bili = f"{clean_query} music"
        
        await self.safe_send(ctx, f"FALLBACK: YouTube restricted this content. Searching Bilibili for: {clean_query}...")
        
        try:
            # Use bilisearch1: as requested
            data = await self.bot.loop.run_in_executor(None, lambda: self.ytdl_bili.extract_info(f"bilisearch1:{search_query_bili}", download=False))
            
            if 'entries' in data and data['entries']:
                entry = data['entries'][0]
                url = entry.get('webpage_url', entry.get('url'))
                # Prepend to queue for immediate playback
                self.queue.appendleft((url, requester_id))
            else:
                await self.safe_send(ctx, "ERROR: No results found on Bilibili.")
        except Exception:
            await self.safe_send(ctx, "ERROR: Bilibili search failed.")
        
        await self.play_next(ctx)

    async def play_next(self, ctx):
        if self.is_looping and self.current_song:
            self.queue.appendleft(self.current_song)

        if len(self.queue) > 0:
            query, requester_id = self.queue.popleft()
            self.current_song = (query, requester_id)
            
            is_bili = "bilibili.com" in query or "b23.tv" in query
            is_yt_url = "youtube.com" in query or "youtu.be" in query
            
            # Determine source_type and ytdl_instance
            if is_bili:
                source_type = 'bilibili'
                ytdl_inst = self.ytdl_bili
                search_query = query
            else:
                source_type = 'youtube'
                ytdl_inst = self.ytdl_yt
                # If it's not a URL, it's a search term
                search_query = query if is_yt_url else f"ytsearch:{query}"

            try:
                if not ctx.voice_client:
                    guild = ctx.guild
                    requester = guild.get_member(requester_id)
                    if requester and requester.voice:
                         await requester.voice.channel.connect(self_deaf=True)
                    else:
                         self.queue.clear()
                         return

                await self.safe_send(ctx, f"⏳ Loading: **{query[:50]}...**")
                source = await YTDLSource.from_url(search_query, loop=self.bot.loop, stream=True, ctx=ctx, source_type=source_type, ytdl_instance=ytdl_inst)
                
                def after_playing(error):
                    if error:
                        print(f"ERROR: Playback error for {query}: {error}")
                        async def handle_error():
                            await self.safe_send(ctx, f"❌ Playback error: {error}")
                            if source_type == 'youtube':
                                 await self.trigger_bili_fallback(ctx, query, requester_id)
                            else:
                                 if query in self.bili_retries:
                                     self.bili_retries.remove(query)
                                 await self.play_next(ctx)
                        self.bot.loop.create_task(handle_error())
                        return
                    
                    if query in self.bili_retries:
                        self.bili_retries.remove(query)
                    self.bot.loop.create_task(self.play_next(ctx))

                ctx.voice_client.play(source, after=after_playing)
                await self.update_player(ctx, source)
            
            except Exception as e:
                err_msg = str(e).strip().split('\n')[-1]
                await self.safe_send(ctx, f"❌ Failed to load: **{query[:50]}**\n`{err_msg}`")
                
                if source_type == 'youtube':
                    await self.trigger_bili_fallback(ctx, query, requester_id)
                else:
                    if query in self.bili_retries:
                        self.bili_retries.remove(query)
                    await self.play_next(ctx)
        else:
            self.current_song = None
            self.bili_retries.clear() # Clear all retries when queue is done
            await self.safe_send(ctx, "INFO: Queue empty.")

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

    @commands.hybrid_command(name='play', aliases=['p'], description="Plays a song or adds to queue.")
    @app_commands.describe(query="Song URL or search term.")
    @app_commands.autocomplete(query=play_autocomplete)
    async def play(self, ctx: commands.Context, *, query: str):
        await ctx.defer() 
        
        query = query.strip()
        if not query:
            return await ctx.send("ERROR: Provide a song name or URL.")
        
        if not await self.ensure_voice(ctx):
            return
            
        if not ctx.voice_client:
            return await ctx.send("ERROR: Voice connection failed.")

        # Sanitize YouTube URL
        if 'youtube.com/watch' in query and 'list=' in query:
            try:
                import urllib.parse as urlparse
                parsed = urlparse.urlparse(query)
                params = urlparse.parse_qs(parsed.query)
                if 'v' in params:
                    query = f"https://www.youtube.com/watch?v={params['v'][0]}"
            except Exception:
                pass

        if 'spotify.com' in query:
            msg = await ctx.send("INFO: Loading Spotify tracks...")
            tracks = await self.get_spotify_tracks(query)
            if not tracks:
                return await msg.edit(content="ERROR: Failed to load Spotify tracks.")
            for track in tracks:
                self.queue.append((track, ctx.author.id))
            
            if ctx.voice_client and not ctx.voice_client.is_playing():
                await msg.delete()
                await self.play_next(ctx)
            else:
                await msg.edit(content=f"SUCCESS: Queued {len(tracks)} tracks.")
                await self.update_player(ctx)
        else:
            self.queue.append((query, ctx.author.id))
            if ctx.voice_client and not ctx.voice_client.is_playing():
                try:
                    await self.play_next(ctx)
                except Exception as e:
                    await ctx.send(f"ERROR: Initial search failed: {e}")
            else:
                display_query = query if query.startswith('http') else f"SEARCH: {query}"
                await ctx.send(f"SUCCESS: Queued {display_query}")
                await self.update_player(ctx)

    @commands.hybrid_command(name='search', description="Searches YouTube and lets you select a song.")
    @app_commands.describe(query="The search term for YouTube.")
    async def search(self, ctx: commands.Context, *, query: str):
        await ctx.defer() 
        if not await self.ensure_voice(ctx):
            return

        msg = await ctx.send(f"SEARCHING: **{query}**...")
        try:
            results = await YTDLSource.search_source(query, loop=self.bot.loop, ytdl_instance=self.ytdl_yt)
        except Exception as e:
             return await msg.edit(content=f"ERROR: Error searching: {e}")
        
        if not results:
            return await msg.edit(content="ERROR: No results found.")
        
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
            return await ctx.send(f"ERROR: Playlist **{name}** already exists.")
        
        with open(filepath, 'w') as f:
            json.dump([], f)
        await ctx.send(f"SUCCESS: Playlist **{name}** created.")

    @playlist.command(name='add', description="Adds songs to a playlist. Supports URLs, search terms (comma-separated), or playlists.")
    @app_commands.describe(name="The name of the playlist.", song_query="URLs/Terms (separate with comma for multiple), or a Playlist URL.")
    @app_commands.autocomplete(name=playlist_autocomplete)
    async def pl_add(self, ctx: commands.Context, name: str, *, song_query: str):
        await ctx.defer() 
        filepath = os.path.join(self.playlist_dir, f"{name}.json")
        if not os.path.exists(filepath):
            return await ctx.send(f"ERROR: Playlist **{name}** not found.")
        
        with open(filepath, 'r') as f:
            tracks = json.load(f)

        added_count = 0
        if 'list=' in song_query and ('youtube.com/playlist' in song_query or 'youtube.com/watch' in song_query): 
            msg = await ctx.send("INFO: Processing YouTube playlist...")
            try:
                loop = self.bot.loop or asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: self.ytdl_yt.extract_info(song_query, download=False, process_info=False)) 

                if 'entries' in data:
                    for entry in data['entries']:
                        song_info = await loop.run_in_executor(None, lambda: self.ytdl_yt.extract_info(entry['url'], download=False))
                        tracks.append(song_info.get('webpage_url', song_info.get('url', song_info.get('title'))))
                        added_count += 1
                await msg.edit(content=f"SUCCESS: Added {added_count} songs from YouTube playlist to **{name}**.")
            except Exception as e:
                await msg.edit(content=f"ERROR: Error processing YouTube playlist: {e}")
                print(f"Error processing YouTube playlist: {e}")
                return
        elif 'spotify.com' in song_query:
            msg = await ctx.send("INFO: Processing Spotify link...")
            spotify_tracks = await self.get_spotify_tracks(song_query)
            if not spotify_tracks:
                await msg.edit(content="ERROR: Could not load Spotify tracks.")
                return
            for track_title in spotify_tracks:
                tracks.append(track_title)
                added_count += 1
            await msg.edit(content=f"SUCCESS: Added {added_count} songs from Spotify link to **{name}**.")
        else:
            songs_to_add = [s.strip() for s in song_query.replace('|', ',').split(',') if s.strip()]
            
            for song in songs_to_add:
                tracks.append(song)
                added_count += 1
            
            if added_count > 1:
                await ctx.send(f"SUCCESS: Added {added_count} songs to playlist **{name}**:\n" + ", ".join(songs_to_add)[:1900])
            elif added_count == 1:
                await ctx.send(f"SUCCESS: Added **{songs_to_add[0]}** to playlist **{name}**.")
            else:
                await ctx.send("ERROR: No valid songs found to add.")

        with open(filepath, 'w') as f:
            json.dump(tracks, f)


    @playlist.command(name='list', description="Lists all saved playlists.")
    async def pl_list(self, ctx: commands.Context):
        files = [f[:-5] for f in os.listdir(self.playlist_dir) if f.endswith('.json')]
        if not files:
            return await ctx.send("INFO: No playlists found.")
        await ctx.send(f"**SAVED PLAYLISTS:**\n" + "\n".join(files))

    @playlist.command(name='load', description="Loads a playlist into the queue.")
    @app_commands.describe(name="The name of the playlist to load.")
    @app_commands.autocomplete(name=playlist_autocomplete)
    async def pl_load(self, ctx: commands.Context, name: str):
        await ctx.defer() 
        filepath = os.path.join(self.playlist_dir, f"{name}.json")
        if not os.path.exists(filepath):
            return await ctx.send(f"ERROR: Playlist **{name}** not found.")
        
        if not await self.ensure_voice(ctx):
            return

        with open(filepath, 'r') as f:
            tracks = json.load(f)
        
        for track in tracks:
            self.queue.append((track, ctx.author.id))

        if ctx.voice_client and not ctx.voice_client.is_playing():
            await self.play_next(ctx)
        else:
            await ctx.send(f"SUCCESS: Loaded {len(tracks)} songs from **{name}**.")
            await self.update_player(ctx)
    @playlist.command(name='delete', description="Deletes a playlist.")
    @app_commands.describe(name="The name of the playlist to delete.")
    @app_commands.autocomplete(name=playlist_autocomplete)
    async def pl_delete(self, ctx: commands.Context, name: str):
        filepath = os.path.join(self.playlist_dir, f"{name}.json")
        if not os.path.exists(filepath):
            return await ctx.send(f"ERROR: Playlist **{name}** not found.")
        os.remove(filepath)
        await ctx.send(f"SUCCESS: Playlist **{name}** deleted.")

    @playlist.command(name='show', description="Shows the songs in a playlist.")
    @app_commands.describe(name="The name of the playlist.")
    @app_commands.autocomplete(name=playlist_autocomplete)
    async def pl_show(self, ctx: commands.Context, name: str):
        filepath = os.path.join(self.playlist_dir, f"{name}.json")
        if not os.path.exists(filepath):
            return await ctx.send(f"ERROR: Playlist **{name}** not found.")
        
        with open(filepath, 'r') as f:
            tracks = json.load(f)
        
        if not tracks:
            return await ctx.send(f"INFO: Playlist **{name}** is empty.")
        
        msg = f"**PLAYLIST {name}:**\n"
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
            return await ctx.send(f"ERROR: Playlist **{name}** not found.")
        
        with open(filepath, 'r') as f:
            tracks = json.load(f)
        
        if index < 1 or index > len(tracks):
            return await ctx.send(f"ERROR: Invalid index. Use `/playlist show {name}` to check indices.")
        
        removed = tracks.pop(index - 1)
        
        with open(filepath, 'w') as f:
            json.dump(tracks, f)
        await ctx.send(f"SUCCESS: Removed **{removed}** from playlist **{name}**.")

    # --- Standard Controls ---
    @commands.hybrid_command(name='nowplaying', aliases=['np'], description="Shows the current playing song with controls.")
    async def nowplaying(self, ctx: commands.Context):
        if not self.current_source:
            return await ctx.send("Nothing is playing.")
        
        # Clear existing player message reference for this guild to force a new message if desired, 
        # or just update it. Here we update.
        await self.update_player(ctx)

    @commands.hybrid_command(name='skip', aliases=['s'], description="Skips the current song.")
    async def skip(self, ctx: commands.Context):
        if ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
            ctx.voice_client.stop()
            await ctx.send("Skipped.")
        else:
            await ctx.send("Nothing to skip.")

    @commands.hybrid_command(name='stop', description="Stops playback and clears the queue.")
    async def stop(self, ctx: commands.Context):
        self.queue.clear()
        if ctx.voice_client:
            ctx.voice_client.stop()
        await ctx.send("Stopped.")
        await self.update_player(ctx)

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
            return await ctx.send("Not enough songs to shuffle.")
        temp = list(self.queue)
        random.shuffle(temp)
        self.queue = deque(temp)
        await ctx.send("Queue shuffled.")
        await self.update_player(ctx)

    @commands.hybrid_command(name='loop', description="Toggles loop mode for the current song.")
    async def loop(self, ctx: commands.Context):
        self.is_looping = not self.is_looping
        status = "On" if self.is_looping else "Off"
        await ctx.send(f"Loop: **{status}**")
        await self.update_player(ctx)

    @commands.hybrid_command(name='radio', description="Plays a radio stream.")
    @app_commands.describe(genre="The genre of the radio to play (e.g., lofi, jazz).")
    async def radio(self, ctx: commands.Context, *, genre: str = "lofi"):
        await ctx.defer() # Defer immediately
        query = f"{genre} radio live"
        await self.play(ctx, query=query)

    @commands.hybrid_command(name='volume', description="Changes the player's volume (0-100).")
    @app_commands.describe(volume="Volume level from 0 to 100.")
    async def volume(self, ctx: commands.Context, volume: int):
        if not ctx.voice_client:
            return await ctx.send("Not connected to a voice channel.")

        if 0 <= volume <= 100:
            ctx.voice_client.source.volume = volume / 100
            await ctx.send(f"Volume changed to **{volume}%**")
        else:
            await ctx.send("Please enter a volume between 0 and 100.")

    @commands.hybrid_command(name='status', description="Reports the current status of the bot's environment.")
    async def status(self, ctx: commands.Context):
        import yt_dlp
        import platform
        import shutil
        
        ytdlp_version = yt_dlp.version.__version__
        ffmpeg_path = ffmpeg_executable
        python_version = platform.python_version()
        
        cookie_info = "Not found"
        if os.path.exists(cookie_path):
            size = os.path.getsize(cookie_path)
            cookie_info = f"Exists ({size} bytes)"
            
        node_path = shutil.which("node")
        node_version = "N/A"
        if node_path:
            try:
                node_version = subprocess.check_output([node_path, "--version"], text=True).strip()
            except:
                node_version = "Error"

        # Check cache size
        cache_size_bytes = 0
        for f in os.listdir(cache_dir):
            cache_size_bytes += os.path.getsize(os.path.join(cache_dir, f))
        cache_size_mb = cache_size_bytes / (1024 * 1024)

        report = (
            f"**ENVIRONMENT STATUS**\n"
            f"YT-DLP: `{ytdlp_version}`\n"
            f"FFmpeg: `{ffmpeg_path}`\n"
            f"Node.js: `{node_version}`\n"
            f"Python: `{python_version}`\n"
            f"Cookies: `{cookie_info}`\n"
            f"Cache Size: `{cache_size_mb:.2f} MB`"
        )
        await ctx.send(report)

    @commands.hybrid_command(name='update_ytdlp', description="Updates yt-dlp to the latest version.")
    @commands.has_permissions(administrator=True)
    async def update_ytdlp(self, ctx: commands.Context):
        await ctx.defer()
        try:
            # Run pip upgrade
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "-U", "yt-dlp",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Re-import or check version
                import importlib
                import yt_dlp
                importlib.reload(yt_dlp)
                new_version = yt_dlp.version.__version__
                await ctx.send(f"SUCCESS: yt-dlp updated to `{new_version}`. Please restart the bot to ensure all changes take effect.")
            else:
                await ctx.send(f"ERROR: Update failed: {stderr.decode()}")
        except Exception as e:
            await ctx.send(f"ERROR: An exception occurred: {e}")

    @commands.hybrid_command(name='leave', description="Disconnects the bot from the voice channel.")
    async def leave(self, ctx: commands.Context):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()

    @commands.hybrid_command(name='help', description="Shows available commands.")
    async def help(self, ctx: commands.Context):
        embed = discord.Embed(
            title="MUSIC BOT HELP",
            description="Available commands:",
            color=0x1DB954 # Spotify Green
        )

        # General Commands
        embed.add_field(
            name="**!play / !p <url|query>**",
            value="Plays a song from URL or search term.",
            inline=False
        )
        embed.add_field(
            name="**!search <query>**",
            value="Searches YouTube and lets you select a song.",
            inline=False
        )
        embed.add_field(
            name="**!skip / !s**",
            value="Skips the current song.",
            inline=False
        )
        embed.add_field(
            name="**!stop**",
            value="Stops playback and clears the queue.",
            inline=False
        )
        embed.add_field(
            name="**!queue / !q**",
            value="Displays the current song queue.",
            inline=False
        )
        embed.add_field(
            name="**!shuffle**",
            value="Shuffles the current queue.",
            inline=False
        )
        embed.add_field(
            name="**!loop**",
            value="Toggles loop mode for the current song.",
            inline=False
        )
        embed.add_field(
            name="**!radio [genre]**",
            value="Plays a live radio stream (default: lofi).",
            inline=False
        )
        embed.add_field(
            name="**!playlist**",
            value="Playlist commands: `create`, `add`, `remove`, `list`, `load`, `delete`.",
            inline=False
        )
        embed.add_field(
            name="**!volume <0-100>**",
            value="Changes the player's volume.",
            inline=False
        )
        embed.add_field(
            name="**!status**",
            value="Shows environment status (yt-dlp, ffmpeg, node, cache).",
            inline=False
        )
        embed.add_field(
            name="**!update_ytdlp**",
            value="Admin only: Updates yt-dlp to the latest version.",
            inline=False
        )
        embed.add_field(
            name="**!leave**",
            value="Disconnects the bot from the voice channel.",
            inline=False
        )

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Music(bot))