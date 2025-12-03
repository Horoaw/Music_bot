# 🎵 Discord Music Bot / 音乐机器人

A feature-rich, open-source Discord music bot built with Python, `discord.py`, and `yt-dlp`.  
基于 Python, `discord.py` 和 `yt-dlp` 构建的功能丰富的开源 Discord 音乐机器人。

## ✨ Features / 功能特性

*   **🎶 High Quality Playback**: Streams audio from YouTube, SoundCloud, and direct URL sources.
*   **🟢 Spotify Support**: Seamlessly handles Spotify Track, Album, and Playlist links (auto-converts to YouTube queries).
*   **🤖 Slash Commands**: Full support for `/play`, `/search`, and more with autocomplete suggestions.
*   **🔍 Smart Search**: 
    *   `/play`: Type to get real-time search suggestions from YouTube.
    *   `/search`: Select from top 5 results with video duration displayed.
*   **📂 Playlist Management**: Create, save, and load your own custom playlists.
*   **📻 Radio Mode**: Listen to live 24/7 radio streams (Lofi, Jazz, etc.).
*   **🌐 Bilingual Support**: Help command available in both English and Chinese.

## 🛠️ Setup / 安装指南

### Prerequisites / 前置要求

1.  **Python 3.10+**
2.  **FFmpeg**: Essential for audio processing.
    *   **Linux**: `sudo apt install ffmpeg`
    *   **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to your PATH.

### Installation / 安装步骤

1.  **Clone the repository / 克隆仓库:**
    ```bash
    git clone <repository_url>
    cd discord_song_bot
    ```

2.  **Install Dependencies / 安装依赖:**
    
    Using Conda (Recommended):
    ```bash
    conda env create -f environment.yml
    conda activate discord_music_bot
    ```
    
    Or using pip:
    ```bash
    pip install discord.py[voice] yt-dlp spotipy python-dotenv aiohttp
    ```

3.  **Configuration / 配置:**
    Create a `.env` file in the project root:
    ```env
    DISCORD_TOKEN=your_discord_bot_token
    SPOTIPY_CLIENT_ID=your_spotify_client_id  # Optional / 可选
    SPOTIPY_CLIENT_SECRET=your_spotify_client_secret # Optional / 可选
    ```

4.  **Permissions / 权限设置:**
    *   Go to Discord Developer Portal -> Bot.
    *   Enable **Message Content Intent** (Required for traditional `!` commands to work).
    *   Ensure the bot invite includes `applications.commands` scope.

### Running the Bot / 运行机器人

```bash
python main.py
```

## 🎮 Usage / 使用方法

### 🔄 First Time Setup / 首次设置
After starting the bot, run this command in your server to register Slash Commands immediately:
```
!sync ~
```

### 📜 Commands / 命令列表

| Command / 命令 | Description / 描述 |
| :--- | :--- |
| **`/play <query>`** | Play a song via URL or search term (with autocomplete). <br> 播放链接或搜索关键词（支持自动补全）。 |
| **`/search <query>`** | Search YouTube and select from a list (shows duration). <br> 搜索 YouTube 并选择歌曲（显示时长）。 |
| **`/stop`** | Stop playback and clear queue. <br> 停止播放并清空队列。 |
| **`/skip`** | Skip the current song. <br> 跳过当前歌曲。 |
| **`/queue`** | Show the current play queue. <br> 显示当前播放队列。 |
| **`/shuffle`** | Shuffle the queue. <br> 随机打乱队列。 |
| **`/loop`** | Toggle loop for current song. <br> 切换单曲循环。 |
| **`/radio [genre]`** | Play a live radio (default: lofi). <br> 播放电台（默认：lofi）。 |
| **`/help`** | Show bilingual help menu. <br> 显示双语帮助菜单。 |
| **`/leave`** | Disconnect from voice channel. <br> 断开语音连接。 |

### 📂 Playlist Commands / 播放列表

*   `/playlist create <name>`: Create a new playlist. <br> 创建一个新歌单。
*   `/playlist add <name> <song>`: Add current song/url to playlist. <br> 添加当前歌曲/链接到歌单。
*   `/playlist show <name>`: Show all songs in a playlist with indices. <br> 显示歌单所有歌曲（带序号）。
*   `/playlist remove <name> <index>`: Remove a song from a playlist by index. <br> 根据序号从歌单中移除歌曲。
*   `/playlist load <name>`: Load playlist to queue. <br> 将歌单加载到播放队列。
*   `/playlist list`: List all playlists. <br> 列出所有歌单。
*   `/playlist delete <name>`: Delete a playlist. <br> 删除整个歌单。

## ⚠️ Troubleshooting / 故障排除

*   **"PrivilegedIntentsRequired" Error**:
    *   Go to Discord Developer Portal -> Bot -> Privileged Gateway Intents -> Enable "Message Content Intent".
*   **Slash commands not appearing?**:
    *   Run `!sync ~` in your server.
    *   Re-invite the bot using the URL printed in the console at startup.
*   **Spotify links not working?**:
    *   Ensure `SPOTIPY_CLIENT_ID` and `SPOTIPY_CLIENT_SECRET` are set in your `.env` file.
