# 🎵 Discord Music Bot

**Date:** Sunday, July 20, 2025, 12:59 PM IST

## Overview

**Discord Music Bot** is an advanced open-source music bot built with Python and `discord.py` (slash command/interaction version). It streams high-quality audio from YouTube and YouTube Music, providing rich controls for queued music playback within any Discord server.

### ✨ Why Is It Unique?

- **Full Slash Command Support:** All actions use `/` commands for seamless Discord integration and autocomplete.
- **Independent Server Queues:** Each server gets its own queue, loop state, and volume—no cross-server interference.
- **Robust Feature Set:** Includes looping (song/queue), shuffling, time-seek, lyrics search, volume, and clear command feedback.
- **Fast & Reliable:** Plays audio through `yt-dlp` and `FFmpeg` for reliable quality and performance.
- **Modern Python & Discord:** Uses discord.py 2.x's interaction API for future-proof, responsive command handling.

---

## 📜 Commands & Examples

All commands are used directly as `/commands` in chat; Discord will suggest available arguments.

| Command                     | Example                                         | Description                                            |
|-----------------------------|-------------------------------------------------|--------------------------------------------------------|
| `/join`                     | `/join`                                         | Bot joins your current voice channel                   |
| `/leave`                    | `/leave`                                        | Bot leaves and clears the queue                        |
| `/play query`               | `/play Believer`/play https://youtu.be/...  | Play song from title, artist, or YouTube URL           |
| `/pause`                    | `/pause`                                        | Pause the current song                                 |
| `/resume`                   | `/resume`                                       | Resume paused song                                     |
| `/stop`                     | `/stop`                                         | Stop playback and clear the queue                      |
| `/skip`                     | `/skip`                                         | Skip the currently playing song                        |
| `/queue`                    | `/queue`                                        | View upcoming queue                                    |
| `/remove pos`               | `/remove 2`                                     | Remove song at position (1=next in queue)              |
| `/clearqueue`               | `/clearqueue`                                   | Removes all songs from the queue                       |
| `/nowplaying`               | `/nowplaying`                                   | Show details for the song currently playing            |
| `/volume vol`               | `/volume 70`                                    | Sets volume (1–100, session only)                      |
| `/loop mode`                | `/loop song``/loop queue``/loop off`    | Loop song, queue, or turn off looping                  |
| `/shuffle`                  | `/shuffle`                                      | Shuffle the queue order                                |
| `/seek time`                | `/seek 1:30``/seek 90`                      | Go to a specific time in the current song              |
| `/lyrics query`             | `/lyrics Numb`/lyrics                       | Show lyrics (uses current song if no query given)      |

---

## 🚀 Getting Started

1. **Invite your bot** with the `bot` and `application.commands` scopes.
2. **Install dependencies:**
    ```
    pip install -U discord.py yt-dlp PyNaCl aiohttp
    ```
3. **Insert your bot token** in the Python code (`TOKEN = "..."`).
4. **Run the bot script:**  
    ```
    python bot.py
    ```
5. **Use `/` in a text channel.** Discord may take a minute to register all slash commands after first run.

---

## 📝 Notes

- **FFmpeg** must be installed and available in your system path.
- **Permissions:** For full function, the bot needs "Connect", "Speak", "Embed Links", and "Send Messages".
- Command registration is automatic via the interaction API, but new commands may need a Discord client restart/refresh to appear.

---

## 🤝 Contributing & Extending

- Fork and PR on new features welcome!
- Want more music platforms or custom settings? Edit the code—it's modular and clean.

---

Built with ❤️ and Python for modern Discord music fans[1].
