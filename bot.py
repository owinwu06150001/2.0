import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import time
import asyncio
import datetime
import psutil
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
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ===== 資料儲存 =====
stay_channels = {}
stay_since = {}
tag_targets = {}
stats_channels = {}
queues = {}
welcome_channels = {}
filter_configs = {}

# ===== 不雅語言預設詞庫 =====
COMMON_PROFANITY = [
    "幹", "靠", "屁", "垃圾", "智障", "腦癱", "死全家", "孤兒", 
    "廢物", "去死", "操你媽", "你媽死了", "尼哥", "畜生", "雜種", 
    "低能兒", "白癡", "腦殘", "傻逼", "機掰", "雞掰", "賤人", "賤貨",
    "操", "肏", "幹你娘", "靠北", "靠腰", "三小", "幹林娘", "機歪",
    "支那", "下流", "無恥", "欠幹", "狗娘養的", "尼瑪"
]

# ===== 播放音檔設定 =====
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'cookiefile': 'cookies.txt',  # 必須確保檔案存在
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}
# ===== 審核日誌對照表 =====
AUDIT_LOG_ACTIONS_CN = {
    "guild_update": "更新伺服器", "channel_create": "建立頻道", "channel_update": "更新頻道",
    "channel_delete": "刪除頻道", "member_kick": "踢出成員", "member_ban": "封鎖成員",
    "member_unban": "解除封鎖", "member_update": "更新成員", "member_role_update": "更新成員身分組",
    "role_create": "建立身分組", "role_update": "更新身分組", "role_delete": "刪除身分組",
    "message_delete": "刪除訊息", "message_bulk_delete": "批量刪除訊息",
}

def get_help_text(bot_mention):
    return (
        f"## {bot_mention} 使用手冊\n"
        "本機器人為 24/7 語音掛機設計 具備30秒自動重連機制。\n\n"
        "### 指令列表\n"
        "* /加入 [頻道]：進入語音頻道掛機。\n"
        "* /設定統計頻道：建立自動更新人數的統計頻道。\n"
        "* /播放 [連結或關鍵字]：播放 YT 或上傳音檔。\n"
        "* /系統狀態：查看硬體資訊。\n"
        "* /停止播放：中斷目前的音樂。\n"
        "* /離開：退出頻道並停止掛機。\n"
        "* /開始標註 [成員] [內容] [次數]：執行標註轟炸。\n"
        "* /停止標註：結束轟炸。\n"
        "* /設定過濾器：開啟/關閉不雅語言禁言系統。\n"
        "* /新增過濾詞彙：手動加入關鍵字。\n"
        "* /狀態：查看掛機時間與延遲。\n"
        "* /移除身分組 / /給予身分組：管理成員權限。\n"
        "* /建立身分組面板 [身分組] [圖片網址]：發送按鈕面板。\n"
        "* /設定歡迎頻道 [頻道]：設定歡迎訊息發送位置。\n"
        "* /查看審核日誌：查看操作紀錄。\n"
        "* /使用方式：顯示本手冊。"
    )

class RoleButtonView(discord.ui.View):
    def __init__(self, role_id):
        super().__init__(timeout=None)
        self.role_id = role_id

    @discord.ui.button(label="取得身分組", style=discord.ButtonStyle.success, custom_id="role_add_persistent")
    async def add_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(self.role_id)
        if role:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"已獲取 {role.name} 身分組", ephemeral=True)

    @discord.ui.button(label="移除身分組", style=discord.ButtonStyle.danger, custom_id="role_remove_persistent")
    async def remove_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(self.role_id)
        if role:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"已移除 {role.name} 身分組", ephemeral=True)

class MusicManager:
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.queue = []
        self.current = None
        self.volume = 0.5
        self.vc = None

    def get_status_embed(self):
        status = "播放中" if self.vc and self.vc.is_playing() else "已暫停"
        embed = discord.Embed(title="音樂控制面板", color=0xaa96da)
        embed.add_field(name="當前歌曲", value=self.current[1] if self.current else "無", inline=False)
        embed.add_field(name="狀態", value=status, inline=True)
        embed.set_footer(text=f"待播清單剩餘: {len(self.queue)} 首")
        return embed

    def play_next(self, error=None):
        if not self.vc or not self.vc.is_connected(): return
        if not self.queue:
            self.current = None
            return
        self.current = self.queue.pop(0)
        
        url = self.current[0]
        if "http" in url:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(url, download=False)
                url = info['url']
        
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS), volume=self.volume)
        self.vc.play(source, after=lambda e: bot.loop.call_soon_threadsafe(self.play_next, e))

async def tag_logic(channel, target, content, times):
    for i in range(times):
        if not tag_targets.get(target.id, False): break
        try: await channel.send(f"{target.mention} {content}")
        except: break
        await asyncio.sleep(0.8)

@bot.event
async def on_message(message):
    if message.author.bot: return
    if bot.user.mentioned_in(message) and not message.mention_everyone:
        await message.channel.send(get_help_text(bot.user.mention))

    config = filter_configs.get(message.guild.id, {"enabled": False, "keywords": COMMON_PROFANITY})
    if config.get("enabled") and any(word in message.content for word in config.get("keywords")):
        try:
            await message.delete()
            await message.author.timeout(datetime.timedelta(seconds=60), reason="使用不雅詞彙")
        except: pass
    await bot.process_commands(message)

@bot.event
async def on_ready():
    await tree.sync()
    update_member_stats.start()
    check_connection.start()
    print(f"機器人已啟動：{bot.user}")

@bot.event
async def on_member_join(member):
    cid = welcome_channels.get(member.guild.id)
    if cid:
        ch = bot.get_channel(cid)
        if ch:
            await ch.send(f"歡迎 {member.mention} 加入，你是本伺服器第 {member.guild.member_count} 位成員！")

@tree.command(name="播放", description="播放YT連結或搜尋音樂")
async def play_audio(interaction: discord.Interaction, 關鍵字: str):
    await interaction.response.defer(thinking=True)
    gid = interaction.guild_id
    if gid not in queues: queues[gid] = MusicManager(gid)
    mgr = queues[gid]
    
    if not interaction.guild.voice_client:
        if not interaction.user.voice: return await interaction.followup.send("請先進入語音")
        mgr.vc = await interaction.user.voice.channel.connect(self_deaf=True)
    else: mgr.vc = interaction.guild.voice_client

    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            # 確保傳入的是正確的搜尋查詢格式
            query = 關鍵字 if "http" in 關鍵字 else f"ytsearch:{關鍵字}"
            info = ydl.extract_info(query, download=False)
            
            # 如果是搜尋結果，取第一個
            if 'entries' in info:
                info = info['entries'][0]
            
            url = info.get('url') or info.get('webpage_url')
            title = info.get('title', '未知標題')
            
            # 若自動取得的 URL 是網頁頁面而非串流檔，需再次提取真實串流
            if "youtube.com" in url or "youtu.be" in url:
                stream_info = ydl.extract_info(url, download=False)
                url = stream_info['url']

        mgr.queue.append((url, title))
        if not mgr.vc.is_playing(): 
            mgr.play_next()
            await interaction.followup.send(f"開始播放: {title}")
        else:
            await interaction.followup.send(f"已加入清單: {title}")
            
    except Exception as e:
        await interaction.followup.send(f"播放失敗：無法取得該影片的串流連結。請嘗試其他連結。")
        print(f"播放錯誤: {e}")

@tree.command(name="停止播放", description="停止音樂")
async def stop_play(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("音樂已停止")

@tree.command(name="加入", description="進入語音頻道掛機")
async def join_vc(interaction: discord.Interaction, 頻道: discord.VoiceChannel = None):
    頻道 = 頻道 or (interaction.user.voice.channel if interaction.user.voice else None)
    if not 頻道: return await interaction.response.send_message("請先進入頻道", ephemeral=True)
    await 頻道.connect(self_deaf=True)
    stay_channels[interaction.guild.id] = 頻道.id
    stay_since[interaction.guild.id] = time.time()
    await interaction.response.send_message(f"已連接至：{頻道.name}")

@tree.command(name="離開", description="退出語音")
async def leave_vc(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        stay_channels.pop(interaction.guild.id, None)
        await interaction.response.send_message("已離開語音頻道")

@tree.command(name="設定統計頻道", description="建立人數統計頻道")
@app_commands.checks.has_permissions(manage_channels=True)
async def stats_setup(interaction: discord.Interaction):
    guild = interaction.guild
    cat = await guild.create_category("伺服器數據")
    c = await guild.create_voice_channel(f"人數: {guild.member_count}", category=cat)
    stats_channels[guild.id] = {"total": c.id}
    await interaction.response.send_message("統計頻道建立完成")

@tree.command(name="建立身分組面板", description="發送身分組按鈕面板")
@app_commands.checks.has_permissions(manage_roles=True)
async def setup_role_panel(interaction: discord.Interaction, 身分組: discord.Role, 圖片網址: str = None):
    view = RoleButtonView(身分組.id)
    embed = discord.Embed(title="身分組", description=f"點擊按鈕獲取 {身分組.mention}", color=0xaa96da)
    if 圖片網址: embed.set_thumbnail(url=圖片網址)
    bot.add_view(view)
    await interaction.response.send_message(embed=embed, view=view)

@tree.command(name="設定歡迎頻道", description="設定歡迎訊息發送位置")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_welcome_channel(interaction: discord.Interaction, 頻道: discord.TextChannel):
    welcome_channels[interaction.guild.id] = 頻道.id
    await interaction.response.send_message(f"歡迎頻道已設定為：{頻道.mention}")

@tree.command(name="設定過濾器", description="開啟/關閉禁言系統")
@app_commands.checks.has_permissions(manage_guild=True)
async def filter_set(interaction: discord.Interaction, 開啟: bool, 記錄頻道: discord.TextChannel):
    filter_configs[interaction.guild.id] = {"enabled": 開啟, "log_channel_id": 記錄頻道.id, "keywords": COMMON_PROFANITY.copy()}
    await interaction.response.send_message(f"過濾系統：{'開啟' if 開啟 else '關閉'}")

@tree.command(name="開始標註", description="對成員執行轟炸")
async def start_bomb(interaction: discord.Interaction, 成員: discord.Member, 內容: str, 次數: int):
    tag_targets[成員.id] = True
    await interaction.response.send_message(f"開始轟炸 {成員.mention}")
    await tag_logic(interaction.channel, 成員, 內容, min(次數, 20))
    tag_targets[成員.id] = False

@tree.command(name="停止標註", description="停止轟炸")
async def stop_bomb(interaction: discord.Interaction, 成員: discord.Member):
    tag_targets[成員.id] = False
    await interaction.response.send_message(f"已停止對 {成員.mention} 的動作")

@tree.command(name="系統狀態", description="硬體監控")
async def sys_info(interaction: discord.Interaction):
    await interaction.response.send_message(f"CPU: {psutil.cpu_percent()}% | RAM: {psutil.virtual_memory().percent}%")

@tree.command(name="查看審核日誌", description="查看操作紀錄")
async def show_logs(interaction: discord.Interaction, 筆數: int = 5):
    await interaction.response.defer()
    log_text = "### 最近審核日誌\n"
    async for entry in interaction.guild.audit_logs(limit=min(筆數, 20)):
        log_text += f"* {entry.action} | {entry.user}\n"
    await interaction.followup.send(log_text)

@tasks.loop(seconds=1)
async def check_connection():
    for gid, cid in list(stay_channels.items()):
        guild = bot.get_guild(gid)
        if guild and (not guild.voice_client or not guild.voice_client.is_connected()):
            ch = bot.get_channel(cid)
            if ch: await ch.connect(self_deaf=True)

@tasks.loop(minutes=10)
async def update_member_stats():
    for guild in bot.guilds:
        if guild.id in stats_channels:
            ch = bot.get_channel(stats_channels[guild.id]["total"])
            if ch: await ch.edit(name=f"總人數: {guild.member_count}")

token = os.environ.get("DISCORD_TOKEN")
if token: bot.run(token)
