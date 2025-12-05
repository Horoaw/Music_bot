# 🎵 Discord Music Bot

A feature-rich, robust, and open-source Discord music bot built with Python, `discord.py`, and `yt-dlp`.

> **[中文文档 (Chinese Documentation)](README_CN.md)**

## 🚀 v2.0 Release: Hybrid Architecture & Smart Caching

**This release permanently resolves the persistent YouTube "403 Forbidden" playback errors.**

We have introduced a new **"Hybrid Playback Engine"**:
1.  **Smart Failover**: The bot prioritizes **Streaming** for speed. If YouTube blocks the stream (403 error), the bot **automatically** switches to **"Download Mode"**, downloads the track to the server, and plays it locally. This guarantees **100% playback success**.
2.  **Smart Caching System**: Downloaded songs are saved in `data/music_cache/`.
    *   **No Duplicates**: If a song is requested again, the bot plays the cached local file immediately without re-downloading.
    *   **Auto Cleanup**: A maintenance script automatically deletes cached files older than **7 days** to save disk space.
3.  **Enhanced Environment**: Integrated Node.js support to handle signature decryption for protected videos (e.g., Vevo).

---

## ✨ Key Features

*   **🎶 High Quality Playback**: Streams/Downloads audio from YouTube, SoundCloud, and direct URLs.
*   **🛡️ 403 Protection**: Multi-layer defense (Header Injection, IPv4 Enforcement, Failover Downloading).
*   **🟢 Spotify Support**: Seamlessly handles Spotify Track, Album, and Playlist links (auto-converts to YouTube queries).
*   **🤖 Slash Commands**: Full support for `/play`, `/search` with rich autocomplete suggestions.
*   **📂 Playlist Management**: Create, save, and load custom playlists. Supports importing from YouTube/Spotify playlists.
*   **📻 Radio Mode**: Listen to live 24/7 radio streams (Lofi, Jazz, etc.).
*   **🌐 Bilingual Support**: Help command available in both English and Chinese.

## 🛠️ Installation & Setup

### 1. Prerequisites

*   **Python 3.10+**
*   **FFmpeg**: Essential for audio processing.
    *   Linux: `sudo apt install ffmpeg`
*   **Node.js**: **(New in v2.0)** Required for yt-dlp signature decryption.
    *   Linux: `sudo apt install nodejs`

### 2. Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd discord_song_bot
    ```

2.  **Install Dependencies:**
    
    Using Conda (Recommended - includes Python, FFmpeg, Node.js):
    ```bash
    conda env create -f environment.yml
    conda activate discord_music_bot
    ```
    
    Or using pip (Manual FFmpeg/Node.js install required):
    ```bash
    pip install discord.py[voice] yt-dlp spotipy python-dotenv aiohttp
    ```

3.  **Configuration (.env):**
    Create a `.env` file in the project root:
    ```env
    DISCORD_TOKEN=your_discord_bot_token
    SPOTIPY_CLIENT_ID=your_spotify_client_id  # Optional
    SPOTIPY_CLIENT_SECRET=your_spotify_client_secret # Optional
    ```

4.  **Cookies (Crucial):**
    *   Export your YouTube `cookies.txt` using a browser extension.
    *   Place it in the project **root directory**. This is required to bypass age restrictions and 403 errors.

### 3. Running the Bot

```bash
python main.py
```

## 🎮 Commands

### Common Commands

| Command | Description |
| :--- | :--- |
| **`/play <query>`** | Play a song via URL or search term (with autocomplete). |
| **`/search <query>`** | Search YouTube and select from the top 5 results. |
| **`/stop`** | Stop playback and clear the queue. |
| **`/skip`** | Skip the current song. |
| **`/queue`** | Display the current play queue. |
| **`/shuffle`** | Shuffle the queue. |
| **`/loop`** | Toggle loop mode for the current song. |
| **`/radio [genre]`** | Play a live radio stream (default: lofi). |
| **`/playlist`** | Manage saved playlists (see below). |

### Playlist Management

*   `/playlist create <name>`: Create a new playlist.
*   `/playlist add <name> <content>`: Add songs to a playlist.
    *   Supports single URLs or Search terms.
    *   Supports multiple songs (comma `,` or pipe `|` separated).
    *   **Supports importing full YouTube Playlists or Spotify links!**
*   `/playlist load <name>`: Load a saved playlist into the queue.
*   `/playlist list`: List all saved playlists.
*   `/playlist show <name>`: Show songs in a playlist.
*   `/playlist delete <name>`: Delete a playlist.

## 🏗️ Technical Workflow

How the bot decides how to play a song:

```mermaid
graph TD
    A[User Command /play] --> B{Is file in Cache?}
    B -- Yes --> C[Play Local File (Instant)]
    B -- No --> D[Attempt Streaming]
    D -- Success --> E[Stream from YouTube]
    D -- Failure (403/Error) --> F[Download Mode]
    F --> G[Download to Server]
    G --> C
```

This ensures that **if streaming fails, the bot simply tries harder (downloads it)** instead of giving up.

---

## ⚠️ Troubleshooting

*   **"PrivilegedIntentsRequired" Error**:
    *   Go to Discord Developer Portal -> Bot -> Privileged Gateway Intents -> Enable "Message Content Intent".
*   **Slash commands not appearing?**:
    *   Run `!sync ~` in your server or re-invite the bot.
*   **Node.js Warning**:
    *   If you see "WARNING: Node.js NOT found" at startup, please install Node.js. Protected videos will fail without it.