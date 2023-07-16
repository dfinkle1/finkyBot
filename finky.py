import discord
from discord.ext import commands,tasks
import youtube_dl
import asyncio
import gtts
from async_timeout import timeout
from dotenv import load_dotenv
import os

load_dotenv()
secret_key = os.getenv('SECRET_KEY')

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
    def __init__(self, source, *, data, volume=0.20):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, download=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=download))

        if 'entries' in data:
            data = data['entries'][0]

        filename = ytdl.prepare_filename(data) if download else data['url']
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class MusicPlayer:
    def __init__(self,ctx):
        self.bot = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel

        self.np = None #now playing message
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self.player_loop())


    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()
        
            try:
                async with timeout(120):
                    source = await self.queue.get()
            except asyncio.TimeoutError:
                return self.bot.voice_client.disconnect()
        
            self._guild.voice_client.play(source, after=lambda _: self.next.set())
            self.np = await self._channel.send(f'**Now Playing:** `{source.title}`')
            await self.next.wait()

            try:
                # We are no longer playing this song...
                await self.np.delete()
            except discord.HTTPException:
                pass
        # call the cleanup to remove the downloaded file after playing
                
    def start_loop(self):
        self.loop.run_forever()


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        
    def get_player(self,ctx):
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            print("hi")
            print(ctx.guild.id)
            player = MusicPlayer(ctx)
            print("hi!!!")
            self.players[ctx.guild.id]=player
            print(self.players)
            print(player)

        return player

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
    async def test(self,ctx):
        print(ctx.guild.id)
        # print(player)
        print("hello")

    @commands.command()
    async def play(self, ctx, *, song):
        """Plays a song by name from YouTube"""

        if not ctx.voice_client or not ctx.voice_client.is_connected():
            await ctx.invoke(self.join)

        # async with ctx.typing():
        player = self.get_player(ctx)
        source = await YTDLSource.from_url(f"ytsearch:{song}", loop=self.bot.loop,download=False)
        await player.queue.put(source)

        player.start_loop()
        # await ctx.voice_client.play(source)
    
    @commands.command()
    async def stop(self,ctx):
        ctx.voice_client.stop()
        await ctx.send("u has skipped jajaa")

    @commands.command()
    async def skip(self, ctx):
        """Skips the currently playing song"""
        
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await self.play_next(ctx)

    async def play_next(self,ctx,error=None):
            
            print(f'wubalubadubdub')

            if self.queue:
                next_song=self.queue.pop(0)
                await ctx.send(f"Now playing:{next_song.title}")
                await ctx.voice_client.play(next_song, after = lambda e: self.play_next(ctx,e))
                
            else:
                await ctx.voice_client.disconnect()
                await ctx.send("No songs left in queue")

    @commands.command()
    async def leave(self, ctx):
        """Leaves the voice channel"""

        if ctx.voice_client and ctx.voice_client.is_connected():
            await ctx.voice_client.disconnect()
        else:
            await ctx.send("I am not connected to a voice channel.")

    # @commands.command()
    # async def stop(self, ctx):
    #     """Stops playing and clears the queue"""

    #     if ctx.voice_client and ctx.voice_client.is_playing():
    #         ctx.voice_client.stop()

    @commands.command()
    async def queue(self, ctx):
        """Displays the current song queue"""

        if ctx.voice_client and ctx.voice_client.is_playing():
            queue = [f'{i + 1}. {song.title}' for i, song in enumerate(self.queue)]
            queue_message = '\n'.join(queue)
            await ctx.send(f"Current Song Queue:\n{queue_message}")
        else:
            await ctx.send("No song is currently playing.")
    
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
            await asyncio.sleep(3.0)

        await voice_client.disconnect()

    


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