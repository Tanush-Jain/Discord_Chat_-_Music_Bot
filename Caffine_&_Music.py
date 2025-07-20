import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import re
import random
import aiohttp
from typing import Optional
import os

# --- Configuration --- #
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True
intents.voice_states = True

YTDL_FORMAT_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0"
}

FFMPEG_OPTIONS = {"options": "-vn"}
ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)

def time_to_seconds(time: str) -> int:
    """Convert mm:ss or hh:mm:ss or '90' (seconds) to total seconds."""
    if time.isdigit():
        return int(time)
    parts = [int(x) for x in time.split(":")]
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")
        self.url = data.get("url")
        self.webpage_url = data.get("webpage_url")
        self.duration = data.get("duration")  # in seconds
        self.uploader = data.get("uploader")
        self.artist = None
        self.extract_artist()
    def extract_artist(self):
        if self.title and "-" in self.title:
            parts = self.title.split("-")
            if len(parts) >= 2:
                self.artist = parts[0].strip()
        else:
            self.artist = self.uploader
    @classmethod
    async def from_url(cls, url: str, *, loop=None, stream=True, volume=0.5):
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        except Exception as ex:
            raise ex
        if data is None:
            raise ValueError("Could not retrieve data.")
        if "entries" in data:
            data = data["entries"][0]
            if data is None:
                raise ValueError("No video data.")
        url2 = data["url"] if stream else data["requested_download"]
        source = discord.FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
        return cls(source, data=data, volume=volume)

class Song:
    def __init__(self, source: YTDLSource, requester: discord.Member):
        self.source = source
        self.requester = requester
    def title(self): return self.source.title
    def artist(self): return self.source.artist
    def duration(self): return self.source.duration
    def url(self): return self.source.webpage_url

class GuildMusicState:
    def __init__(self, bot, guild):
        self.bot = bot
        self.guild = guild
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()
        self.voice_client: Optional[discord.VoiceClient] = None
        self.current: Optional[Song] = None
        self.loop = "off"  # off/song/queue
        self.volume = 0.5
        self.playback_task: Optional[asyncio.Task] = None
    async def audio_player_task(self):
        while True:
            self.next.clear()
            try:
                song = await self.queue.get()
            except asyncio.CancelledError:
                return
            self.current = song
            source = song.source
            source.volume = self.volume
            def after_playing(error):
                if error:
                    print(f"[Error] Player error: {error}")
                self.bot.loop.call_soon_threadsafe(self.next.set)
            if self.voice_client is None or not self.voice_client.is_connected():
                self.current = None
                return
            self.voice_client.play(source, after=after_playing)
            await self.next.wait()
            if self.loop == "song" and self.current is not None:
                await self.queue.put(self.current)
            elif self.loop == "queue" and self.current is not None:
                await self.queue.put(self.current)
            self.current = None
    def skip(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
            return True
        return False
    def stop(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
        self.clear_queue()
        self.current = None
    def clear_queue(self):
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except asyncio.QueueEmpty:
                break
    def is_playing(self):
        if self.voice_client is None:
            return False
        return self.voice_client.is_playing()
    def is_paused(self):
        if self.voice_client is None:
            return False
        return self.voice_client.is_paused()

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.music_states: dict[int, GuildMusicState] = {}
    def get_guild_state(self, guild: discord.Guild) -> GuildMusicState:
        state = self.music_states.get(guild.id)
        if state is None:
            state = GuildMusicState(self.bot, guild)
            self.music_states[guild.id] = state
        return state
    async def ensure_voice(self, interaction: discord.Interaction) -> Optional[discord.VoiceChannel]:
        if interaction.user.voice and interaction.user.voice.channel:
            return interaction.user.voice.channel
        else:
            await interaction.response.send_message("You must be in a voice channel.", ephemeral=True)
            return None

    # /join
    @app_commands.command(name="join", description="Join your voice channel")
    async def join(self, interaction: discord.Interaction):
        voice_channel = await self.ensure_voice(interaction)
        if voice_channel is None: return
        guild_state = self.get_guild_state(interaction.guild)
        try:
            if interaction.guild.voice_client is not None:
                if interaction.guild.voice_client.channel.id == voice_channel.id:
                    await interaction.response.send_message(f"I'm already in **{voice_channel}**.", ephemeral=True)
                    return
                else:
                    await interaction.guild.voice_client.move_to(voice_channel)
                    await interaction.response.send_message(f"Moved to **{voice_channel}**.")
            else:
                guild_state.voice_client = await voice_channel.connect()
                # Start player task
                if guild_state.playback_task is None or guild_state.playback_task.done():
                    guild_state.playback_task = self.bot.loop.create_task(guild_state.audio_player_task())
                await interaction.response.send_message(f"Joined **{voice_channel}**.")
        except Exception as e:
            await interaction.response.send_message(f"Failed to join: `{str(e)}`", ephemeral=True)

    # /leave
    @app_commands.command(name="leave", description="Leave the voice channel and clear queue")
    async def leave(self, interaction: discord.Interaction):
        guild_state = self.get_guild_state(interaction.guild)
        if not interaction.guild.voice_client:
            await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)
            return
        try:
            guild_state.clear_queue()
            guild_state.stop()
            await interaction.guild.voice_client.disconnect()
            guild_state.voice_client = None
            if guild_state.playback_task and not guild_state.playback_task.done():
                guild_state.playback_task.cancel()
            await interaction.response.send_message("Left the voice channel and cleared the queue.")
        except Exception as e:
            await interaction.response.send_message(f"Failed to leave: `{str(e)}`", ephemeral=True)

    # /play query
    @app_commands.command(name="play", description="Play a song (YouTube URL or search)")
    @app_commands.describe(query="Song title, artist, or YouTube/YT Music URL")
    async def play(self, interaction: discord.Interaction, query: str):
        voice_channel = await self.ensure_voice(interaction)
        if voice_channel is None: return
        guild_state = self.get_guild_state(interaction.guild)
        if interaction.guild.voice_client is None:
            try:
                guild_state.voice_client = await voice_channel.connect()
            except Exception as e:
                await interaction.response.send_message(
                    f"Failed to connect to `{voice_channel}`: `{str(e)}`", ephemeral=True)
                return
            if guild_state.playback_task is None or guild_state.playback_task.done():
                guild_state.playback_task = self.bot.loop.create_task(guild_state.audio_player_task())
        else:
            if interaction.guild.voice_client.channel != voice_channel:
                await interaction.guild.voice_client.move_to(voice_channel)
        # Defer for long operation
        await interaction.response.defer()
        try:
            source = await YTDLSource.from_url(query, loop=self.bot.loop, stream=True, volume=guild_state.volume)
            song = Song(source, requester=interaction.user)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)}")
            return
        if not guild_state.is_playing() and guild_state.queue.empty() and guild_state.current is None:
            await guild_state.queue.put(song)
            await interaction.followup.send(f"▶️ Now playing: **{song.title()}** (*requested by {song.requester.display_name}*)")
        else:
            await guild_state.queue.put(song)
            await interaction.followup.send(f"➕ Added to queue: **{song.title()}** (*requested by {song.requester.display_name}*)")

    # /pause
    @app_commands.command(name="pause", description="Pause playback")
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc is None or not vc.is_connected():
            await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)
            return
        if not vc.is_playing():
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        if vc.is_paused():
            await interaction.response.send_message("Already paused.", ephemeral=True)
            return
        vc.pause()
        await interaction.response.send_message("⏸️ Paused.")

    # /resume
    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc is None or not vc.is_connected():
            await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)
            return
        if not vc.is_paused():
            await interaction.response.send_message("Not paused.", ephemeral=True)
            return
        vc.resume()
        await interaction.response.send_message("▶️ Resumed.")

    # /stop
    @app_commands.command(name="stop", description="Stop and clear queue")
    async def stop(self, interaction: discord.Interaction):
        guild_state = self.get_guild_state(interaction.guild)
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_connected():
            await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)
            return
        if not guild_state.is_playing() and guild_state.queue.empty():
            await interaction.response.send_message("Nothing is playing and queue is empty.", ephemeral=True)
            return
        guild_state.stop()
        await interaction.response.send_message("⏹️ Stopped and cleared the queue.")

    # /skip
    @app_commands.command(name="skip", description="Skip the current song")
    async def skip(self, interaction: discord.Interaction):
        guild_state = self.get_guild_state(interaction.guild)
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_connected():
            await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)
            return
        if not guild_state.is_playing():
            await interaction.response.send_message("Nothing to skip.", ephemeral=True)
            return
        skipped = guild_state.skip()
        if skipped:
            await interaction.response.send_message("⏭️ Skipped.")
        else:
            await interaction.response.send_message("Failed to skip.", ephemeral=True)

    # /queue
    @app_commands.command(name="queue", description="Show song queue")
    async def queue(self, interaction: discord.Interaction):
        guild_state = self.get_guild_state(interaction.guild)
        if guild_state.current is None and guild_state.queue.empty():
            await interaction.response.send_message("Queue is empty.", ephemeral=True)
            return
        embed = discord.Embed(title="🎶 Queue", color=discord.Color.blurple())
        if guild_state.current:
            embed.add_field(name="Now Playing", value=f"**{guild_state.current.title()}**", inline=False)
        else:
            embed.add_field(name="Now Playing", value="Nothing", inline=False)
        if guild_state.queue.empty():
            embed.add_field(name="Up Next", value="Queue is empty.", inline=False)
        else:
            queue_items = list(guild_state.queue._queue)
            desc = ""
            for i, song in enumerate(queue_items[:10], start=1):
                desc += f"**{i}.** {song.title()} (*{song.requester.display_name}*)\n"
            if len(queue_items) > 10:
                desc += f"... and {len(queue_items)-10} more"
            embed.add_field(name="Up Next", value=desc, inline=False)
        await interaction.response.send_message(embed=embed)

    # /remove
    @app_commands.command(name="remove", description="Remove from queue (by position)")
    @app_commands.describe(pos="Position in the queue (1 = first up next)")
    async def remove(self, interaction: discord.Interaction, pos: int):
        guild_state = self.get_guild_state(interaction.guild)
        if pos < 1:
            await interaction.response.send_message("Position must be 1 or greater.", ephemeral=True)
            return
        if guild_state.queue.empty():
            await interaction.response.send_message("Queue is empty.", ephemeral=True)
            return
        queue_items = list(guild_state.queue._queue)
        if pos > len(queue_items):
            await interaction.response.send_message("No song at that queue position.", ephemeral=True)
            return
        removed_song = queue_items.pop(pos - 1)
        guild_state.clear_queue()
        for s in queue_items:
            await guild_state.queue.put(s)
        await interaction.response.send_message(f"🗑️ Removed **{removed_song.title()}**.")

    # /clearqueue
    @app_commands.command(name="clearqueue", description="Clear the song queue")
    async def clearqueue(self, interaction: discord.Interaction):
        guild_state = self.get_guild_state(interaction.guild)
        if guild_state.queue.empty():
            await interaction.response.send_message("Queue already empty.", ephemeral=True)
            return
        guild_state.clear_queue()
        await interaction.response.send_message("🗑️ Cleared the queue.")

    # /np
    @app_commands.command(name="nowplaying", description="Show currently playing song")
    async def nowplaying(self, interaction: discord.Interaction):
        guild_state = self.get_guild_state(interaction.guild)
        current = guild_state.current
        if current is None:
            await interaction.response.send_message("Nothing is currently playing.", ephemeral=True)
            return
        title = current.title() or "Unknown Title"
        artist = current.artist() or "Unknown Artist"
        duration_s = current.duration() or 0
        url = current.url() or ""
        def format_duration(duration: int):
            hours, remainder = divmod(duration, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"
        embed = discord.Embed(title="🎵 Now Playing",
                description=f"**{title}**\nArtist: {artist}\nDuration: {format_duration(duration_s)}\n[Source Link]({url})",
                color=discord.Color.green())
        await interaction.response.send_message(embed=embed)

    # /volume
    @app_commands.command(name="volume", description="Set playback volume (1-100%)")
    @app_commands.describe(vol="Volume percent (1-100)")
    async def volume(self, interaction: discord.Interaction, vol: int):
        guild_state = self.get_guild_state(interaction.guild)
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_connected():
            await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)
            return
        if not 0 < vol <= 100:
            await interaction.response.send_message("Volume must be 1-100.", ephemeral=True)
            return
        guild_state.volume = vol / 100
        if guild_state.current and guild_state.current.source:
            guild_state.current.source.volume = guild_state.volume
        await interaction.response.send_message(f"🔊 Volume set to {vol}%.")

    # /loop
    @app_commands.command(name="loop", description="Set loop mode")
    @app_commands.describe(mode="'song', 'queue', or 'off'")
    async def loop(self, interaction: discord.Interaction, mode: str):
        guild_state = self.get_guild_state(interaction.guild)
        mode_l = mode.lower()
        if mode_l not in ("song", "queue", "off"):
            await interaction.response.send_message("Mode should be one of: 'song', 'queue', 'off'", ephemeral=True)
            return
        guild_state.loop = mode_l
        if mode_l == "off":
            await interaction.response.send_message("Looping disabled.")
        elif mode_l == "song":
            await interaction.response.send_message("🔂 Loop current song.")
        elif mode_l == "queue":
            await interaction.response.send_message("🔁 Loop entire queue.")

    # /shuffle
    @app_commands.command(name="shuffle", description="Shuffle the music queue")
    async def shuffle(self, interaction: discord.Interaction):
        guild_state = self.get_guild_state(interaction.guild)
        if guild_state.queue.empty():
            await interaction.response.send_message("Queue is empty.", ephemeral=True)
            return
        queue_items = list(guild_state.queue._queue)
        random.shuffle(queue_items)
        guild_state.clear_queue()
        for s in queue_items:
            await guild_state.queue.put(s)
        await interaction.response.send_message("🔀 Shuffled the queue.")

    # /seek
    @app_commands.command(name="seek", description="Seek to specific time in song")
    @app_commands.describe(time="Time (mm:ss, hh:mm:ss, or seconds)")
    async def seek(self, interaction: discord.Interaction, time: str):
        guild_state = self.get_guild_state(interaction.guild)
        if guild_state.current is None or guild_state.voice_client is None:
            await interaction.response.send_message("Nothing is currently playing.", ephemeral=True)
            return
        try:
            seconds = time_to_seconds(time)
        except Exception:
            await interaction.response.send_message("Invalid time format. Use 'mm:ss', 'hh:mm:ss', or seconds.", ephemeral=True)
            return
        if seconds < 0 or (guild_state.current.duration and seconds > guild_state.current.duration):
            await interaction.response.send_message("Seek out of range.", ephemeral=True)
            return
        guild_state.voice_client.stop()
        try:
            ffmpeg_options_seek = {"options": f"-vn -ss {seconds}"}
            source_url = guild_state.current.source.data.get("url")
            if not source_url:
                await interaction.response.send_message("Cannot seek this source.", ephemeral=True)
                return
            audio_source = discord.FFmpegPCMAudio(source_url, **ffmpeg_options_seek)
            volume_source = discord.PCMVolumeTransformer(audio_source, volume=guild_state.volume)
            def after_playing(error):
                if error:
                    print(f"[Error] Seek error: {error}")
                self.bot.loop.call_soon_threadsafe(guild_state.next.set)
            guild_state.voice_client.play(volume_source, after=after_playing)
            await interaction.response.send_message(f"⏩ Seeked to {time}.")
        except Exception as e:
            await interaction.response.send_message(f"Failed to seek: `{str(e)}`", ephemeral=True)

    # /lyrics
    @app_commands.command(name="lyrics", description="Fetch lyrics for current (or specified) song")
    @app_commands.describe(query="Song title to fetch lyrics for (leave blank for current)")
    async def lyrics(self, interaction: discord.Interaction, query: Optional[str]=None):
        if query is None:
            guild_state = self.get_guild_state(interaction.guild)
            if guild_state.current:
                query = guild_state.current.title()
            else:
                await interaction.response.send_message("No song specified or playing.", ephemeral=True)
                return
        artist, title = "unknown", query
        if "-" in query:
            parts = query.split("-", 1)
            artist, title = parts[0].strip(), parts[1].strip()
        await interaction.response.defer()
        async with aiohttp.ClientSession() as session:
            try:
                url = f"https://api.lyrics.ovh/v1/{artist}/{title}"
                async with session.get(url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(f"Couldn't find lyrics for `{query}`.")
                        return
                    data = await resp.json()
                    lyrics = data.get("lyrics")
                    if not lyrics or lyrics.strip() == "":
                        await interaction.followup.send(f"No lyrics found for `{query}`.")
                        return
                    max_len = 2048
                    if len(lyrics) > max_len:
                        lyrics = lyrics[:max_len-3] + "..."
                    embed = discord.Embed(title=f"Lyrics: {query}", description=lyrics, color=discord.Color.purple())
                    await interaction.followup.send(embed=embed)
            except Exception as e:
                await interaction.followup.send(f"Error fetching lyrics: `{str(e)}`")

# Bot Setup

class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="/", intents=intents)
        self.tree.add_command(Music(self).join)
        self.tree.add_command(Music(self).leave)
        self.tree.add_command(Music(self).play)
        self.tree.add_command(Music(self).pause)
        self.tree.add_command(Music(self).resume)
        self.tree.add_command(Music(self).stop)
        self.tree.add_command(Music(self).skip)
        self.tree.add_command(Music(self).queue)
        self.tree.add_command(Music(self).remove)
        self.tree.add_command(Music(self).clearqueue)
        self.tree.add_command(Music(self).nowplaying)
        self.tree.add_command(Music(self).volume)
        self.tree.add_command(Music(self).loop)
        self.tree.add_command(Music(self).shuffle)
        self.tree.add_command(Music(self).seek)
        self.tree.add_command(Music(self).lyrics)
    async def setup_hook(self):
        await self.add_cog(Music(self))
        await self.tree.sync()

bot = MusicBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Game(name="Playing Music! Use /help"))
    print("------")

bot.run(TOKEN)
