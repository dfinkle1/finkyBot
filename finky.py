import discord
from discord.ext import commands,tasks
import youtube_dl
import asyncio
import gtts
import config

secret_key = config.SECRET_KEY

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
    'source_address': '0.0.0.0',
}

ffmpeg_options = {
    'options': '-vn',
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_idle.start()

    def cog_unload(self):
        self.check_idle.cancel()
    
    @commands.command()
    async def tts(self, ctx, *, text):
        """Converts text to speech and plays it"""

        voice_channel = ctx.author.voice.channel if ctx.author.voice else None
        voice_client = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)

        if not voice_channel:
            await ctx.send("You are not connected to a voice channel.")
            return

        if not voice_client:
            await voice_channel.connect()
            voice_client = ctx.voice_client

        tts = gtts.gTTS(text)
        tts.save("tts.mp3")

        voice_client.play(discord.FFmpegPCMAudio("tts.mp3"))

        # Wait for the TTS to finish playing
        while voice_client.is_playing():
            await asyncio.sleep(0.5)

        await voice_client.disconnect()
    
    @tasks.loop(minutes=3.0)
    async def check_idle(self):
        if not self.bot.voice_clients:
            return

        for voice_client in self.bot.voice_clients:
            if voice_client.guild.voice_client and voice_client.guild.voice_client.is_playing():
                continue

            if voice_client.idle():
                await voice_client.disconnect()

    @commands.command()
    async def join(self, ctx, *, channel: discord.VoiceChannel = None):
        """Joins a voice channel"""

        if not channel:
            if ctx.author.voice and ctx.author.voice.channel:
                channel = ctx.author.voice.channel
            else:
                await ctx.send("You are not connected to a voice channel.")
                return

        if ctx.voice_client and ctx.voice_client.is_connected():
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()

    @commands.command()
    async def leave(self, ctx):
        """Leaves the voice channel"""

        if ctx.voice_client and ctx.voice_client.is_connected():
            await ctx.voice_client.disconnect()
        else:
            await ctx.send("I am not connected to a voice channel.")

    @commands.command()
    async def play(self, ctx, *, song):
        """Plays a song by name from YouTube"""

        if not ctx.voice_client or not ctx.voice_client.is_connected():
            await ctx.invoke(self.join)

        async with ctx.typing():
            player = await YTDLSource.from_url(f"ytsearch:{song}", loop=self.bot.loop)
            ctx.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)

        await ctx.send(f'Now playing: {player.title}')

    @commands.command()
    async def stop(self, ctx):
        """Stops playing and clears the queue"""

        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()

    @commands.command()
    async def skip(self, ctx):
        """Skips the currently playing song"""

        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Skipped the current song.")
        else:
            await ctx.send("No song is currently playing.")

    @commands.command()
    async def queue(self, ctx):
        """Displays the current song queue"""

        if ctx.voice_client and ctx.voice_client.is_playing():
            queue = [f'{i + 1}. {song.title}' for i, song in enumerate(ctx.voice_client.source.queue)]
            queue_message = '\n'.join(queue)
            await ctx.send(f"Current Song Queue:\n{queue_message}")
        else:
            await ctx.send("No song is currently playing.")

    @commands.command()
    async def clear(self, ctx):
        """Clears the song queue"""

        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()

        if ctx.voice_client and ctx.voice_client.source:
            ctx.voice_client.source.queue.clear()
            await ctx.send("Song queue cleared.")
        else:
            await ctx.send("No song queue to clear.")


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("$"),
    description='Finky bot',
    intents=intents,
)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')


async def main():
    async with bot:
        await bot.add_cog(Music(bot))
        await bot.start(secret_key)


asyncio.run(main())