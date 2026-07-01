import discord
from discord.ext import commands
from discord import app_commands
import os
import static_ffmpeg
import yt_dlp
from server import keep_alive

# 初始化 FFMPEG
static_ffmpeg.add_paths()

# ===== 啟動 Web 服務 =====
keep_alive()

# ===== Intents 設定 =====
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True 

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ===== 音訊與 YT 設定 =====
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'cookiefile': 'cookies.txt',  
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}

# ===== 事件監聽：無人時自動離開 =====
@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id: return
    voice_client = member.guild.voice_client
    if voice_client and voice_client.channel == before.channel:
        members = [m for m in voice_client.channel.members if not m.bot]
        if len(members) == 0:
            await voice_client.disconnect()

@bot.event
async def on_ready():
    await tree.sync()
    print(f"機器人已啟動：{bot.user}")

# ===== 指令區 =====

@tree.command(name="播放", description="播放 YT 音樂")
async def play_audio(interaction: discord.Interaction, 關鍵字: str):
    await interaction.response.defer(thinking=True)
    
    if not interaction.guild.voice_client:
        if not interaction.user.voice: return await interaction.followup.send("請先進入語音頻道")
        vc = await interaction.user.voice.channel.connect(self_deaf=True)
    else:
        vc = interaction.guild.voice_client

    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(關鍵字, download=False)
            if 'entries' in info: info = info['entries'][0]
            url = info.get('url')
            title = info.get('title', '未知標題')
        
        if not hasattr(vc, 'queue'): vc.queue = []
        vc.queue.append((url, title))
        
        if not vc.is_playing():
            def play_next(e):
                if vc.queue:
                    next_url, next_title = vc.queue.pop(0)
                    source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(next_url, **FFMPEG_OPTIONS), volume=0.5)
                    vc.play(source, after=play_next)
            
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS), volume=0.5)
            vc.play(source, after=play_next)
            await interaction.followup.send(f"開始播放: {title}")
        else:
            await interaction.followup.send(f"已加入清單: {title}")
    except Exception as e:
        await interaction.followup.send("播放失敗，請檢查連結或 Cookie 是否有效。")
        print(f"Error: {e}")

@tree.command(name="離開", description="退出語音")
async def leave_vc(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("已離開語音頻道")

@tree.command(name="狀態", description="查看延遲 (Ping)")
async def sys_info(interaction: discord.Interaction):
    ping = round(bot.latency * 1000)
    await interaction.response.send_message(f"目前延遲: {ping}ms")

token = os.environ.get("DISCORD_TOKEN")
if token: bot.run(token)
