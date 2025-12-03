# Discord Music Bot

A robust, open-source Discord music bot built with Python, `discord.py`, and `yt-dlp`.

## Features

*   **Multi-Source Support:** YouTube, SoundCloud, Direct URLs (MP3/FLAC/etc.).
*   **Spotify Integration:** Paste Spotify Track/Album/Playlist links (Bot searches for them on YouTube automatically).
*   **Radio Mode:** Play live radio streams.
*   **Queue System:** Enqueue, skip, stop, shuffle, loop.
*   **24/7 Capability:** The bot stays in the channel until you explicitly disconnect it.

## Setup

### Prerequisites

1.  **Python 3.9+** or **Conda**.
2.  **FFmpeg** installed and added to your system PATH.
    *   Linux: `sudo apt install ffmpeg`
    *   Windows: Download and add `bin` folder to Path.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone git@github.com:Horoaw/Music_bot.git
    cd Music_bot
    ```

2.  **Set up Environment:**

    *   **Using Conda:**
        ```bash
        conda env create -f environment.yml
        conda activate discord_music_bot
        ```
    
    *   **Using Pip:**
        ```bash
        pip install discord.py yt-dlp spotipy python-dotenv PyNaCl
        ```

3.  **Configuration:**
    *   Rename `.env` (or create it) and fill in your credentials:
        ```env
        DISCORD_TOKEN=your_bot_token_here
        SPOTIPY_CLIENT_ID=your_spotify_id (Optional)
        SPOTIPY_CLIENT_SECRET=your_spotify_secret (Optional)
        ```

### Running the Bot

```bash
python main.py
```

## Commands

*   `!play <url|search>`: Play a song or add to queue. Supports Spotify links.
*   `!skip`: Skip current song.
*   `!stop`: Stop playing and clear queue.
*   `!queue`: Show current queue.
*   `!shuffle`: Shuffle the queue.
*   `!loop`: Toggle loop mode.
*   `!radio <genre>`: Play a radio stream (default: lofi).
*   `!leave`: Disconnect the bot.

## Disclaimer

This bot uses `yt-dlp` to stream audio. Ensure you comply with the Terms of Service of the platforms you access.
