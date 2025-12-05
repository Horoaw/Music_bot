# 🎵 Discord Music Bot (CN) / 音乐机器人

一款基于 Python, `discord.py` 和 `yt-dlp` 构建的功能强大、稳定可靠的 Discord 音乐机器人。

> **[Go to English Documentation (英文文档)](README.md)**

## 🚀 v2.0 重大更新：稳定性和缓存系统

**此版本彻底解决了 YouTube "403 Forbidden" 播放错误问题。**

我们引入了全新的 **“混合播放架构 (Hybrid Playback Engine)”**：
1.  **智能回退机制**：机器人会优先尝试流式播放 (Streaming)。如果遇到网络限制或 403 错误，机器人会**自动**切换到“下载模式”，将歌曲下载到服务器后再播放。这保证了**100% 的播放成功率**。
2.  **本地缓存系统**：下载的歌曲会保存在服务器的 `data/music_cache/` 目录中。
    *   **去重**：如果一首歌已经被下载过，下次点播时会直接秒开本地文件，不再消耗流量下载。
    *   **自动清理**：系统会自动清理超过 **7天** 未被访问的缓存文件，防止占用过多硬盘空间。
3.  **环境增强**：集成了 Node.js 环境，解决了受保护音乐视频（如 Vevo）无法签名验证的问题。

---

## ✨ 核心功能特性

*   **🎶 高品质播放**: 支持 YouTube, SoundCloud 和直链音频源。
*   **🛡️ 403 防御**: 内置多层防御机制（HTTP 头注入、IPv4 强制、智能下载回退），彻底告别播放失败。
*   **🟢 Spotify 支持**: 完美支持 Spotify 单曲、专辑和歌单链接（自动转换为 YouTube 搜索源）。
*   **🤖 斜杠命令 (Slash Commands)**: 全面支持 `/play`, `/search` 等命令，并带有丝滑的自动补全建议。
*   **📂 歌单管理**: 支持创建、保存、加载自定义歌单，甚至支持直接导入 YouTube 播放列表或 Spotify 歌单。
*   **📻 电台模式**: 支持 24/7 直播电台 (Lofi, Jazz 等)。
*   **🌐 双语支持**: 帮助菜单提供中文和英文说明。

## 🛠️ 安装与部署

### 1. 前置要求

*   **Python 3.10+**
*   **FFmpeg**: 音频处理的核心组件。
    *   Linux: `sudo apt install ffmpeg`
*   **Node.js**: **(v2.0 新增)** 用于解密 YouTube 签名。
    *   Linux: `sudo apt install nodejs`

### 2. 安装步骤

1.  **克隆代码:**
    ```bash
    git clone <repository_url>
    cd discord_song_bot
    ```

2.  **安装依赖:**
    
    推荐使用 Conda (已包含 Python, FFmpeg, Node.js):
    ```bash
    conda env create -f environment.yml
    conda activate discord_music_bot
    ```
    
    或者使用 pip (需手动安装 FFmpeg 和 Node.js):
    ```bash
    pip install discord.py[voice] yt-dlp spotipy python-dotenv aiohttp
    ```

3.  **配置文件 (.env):**
    在项目根目录创建 `.env` 文件:
    ```env
    DISCORD_TOKEN=你的_Discord_机器人_Token
    SPOTIPY_CLIENT_ID=你的_Spotify_ID  # 可选
    SPOTIPY_CLIENT_SECRET=你的_Spotify_Secret # 可选
    ```

4.  **Cookies 配置 (关键):**
    *   从浏览器导出 YouTube 的 `cookies.txt` 文件。
    *   将其放置在项目**根目录**下。这是绕过年龄限制和高级反爬虫的关键。

### 3. 运行

```bash
python main.py
```

## 🎮 使用方法

### 常用命令

| 命令 | 描述 |
| :--- | :--- |
| **`/play <链接或歌名>`** | 播放歌曲。支持 URL 或直接搜索（带自动补全）。 |
| **`/search <关键词>`** | 搜索 YouTube 并列出前 5 个结果供选择。 |
| **`/stop`** | 停止播放并清空队列。 |
| **`/skip`** | 跳过当前歌曲。 |
| **`/queue`** | 显示当前播放队列。 |
| **`/shuffle`** | 随机打乱队列。 |
| **`/loop`** | 切换当前歌曲的单曲循环模式。 |
| **`/radio [流派]`** | 播放直播电台（默认：lofi）。 |
| **`/playlist`** | 强大的歌单管理命令组（详见下文）。 |

### 播放列表命令 (Playlist)

*   `/playlist create <名字>`: 创建一个新歌单。
*   `/playlist add <名字> <内容>`: 向歌单添加歌曲。
    *   支持单曲 URL。
    *   支持关键词搜索。
    *   支持一次添加多首（用逗号 `,` 或竖线 `|` 分隔）。
    *   **支持直接粘贴 YouTube 播放列表链接或 Spotify 链接！**
*   `/playlist load <名字>`: 将整个歌单加载到当前播放队列。
*   `/playlist list`: 列出所有已保存的歌单。
*   `/playlist show <名字>`: 查看歌单里的所有歌曲。
*   `/playlist delete <名字>`: 删除一个歌单。

## 🏗️ 架构工作流 (Technical Workflow)

当用户输入 `/play` 时，机器人内部的工作流程如下：

1.  **检查缓存**: 检查 `data/music_cache/` 下是否已有该歌曲文件。
    *   ✅ 有 -> **直接播放本地文件** (秒开)。
    *   ❌ 无 -> 进入下一步。
2.  **尝试流式播放 (Streaming)**: 尝试从 YouTube 获取流媒体链接。
    *   ✅ 成功 -> 开始播放流。
    *   ❌ 失败 (如 403 禁止访问) -> **自动触发回退机制**。
3.  **回退下载 (Failover Download)**: 
    *   机器人提示 "Downloading..."。
    *   将歌曲完整下载到服务器缓存目录。
    *   下载完成后播放本地文件。

此机制确保了极高的播放稳定性。

---

## ⚠️ 故障排除

*   **403 Forbidden 错误**:
    *   通常已被 v2.0 自动修复。如果仍然出现，请检查 `cookies.txt` 是否过期。
*   **PrivilegedIntentsRequired**:
    *   请在 Discord 开发者门户开启 "Message Content Intent"。
*   **Node.js Warning**:
    *   启动时如果看到 "WARNING: Node.js NOT found"，请务必安装 Node.js，否则部分歌曲无法播放。
