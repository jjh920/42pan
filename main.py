# main.py — 최소작동 버전 (길드 전용 /핑)
import os
import discord
from discord import app_commands
from keep_alive import keep_alive  # 없으면 try/except로 무시됨

intents = discord.Intents.default()
intents.guilds = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

GUILD_ID = int(os.getenv("GUILD_ID", "0"))  # .env에 GUILD_ID=1234567890
GUILD = discord.Object(id=GUILD_ID)

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    # 글로벌을 길드로 복사(선택) 후 해당 길드 동기화
    try:
        tree.copy_global_to(guild=GUILD)
    except Exception:
        pass
    synced = await tree.sync(guild=GUILD)
    print(f"✅ {len(synced)}개 길드 명령 동기화 완료 (guild={GUILD_ID})")

# 길드 범위로 명령을 정의해야 즉시 반영됨
@tree.command(name="핑", description="슬래시 테스트", guild=GUILD)
@app_commands.guild_only()
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("퐁! ✅", ephemeral=True)

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN 환경변수가 없습니다.")
    try:
        keep_alive()
    except Exception:
        pass
    client.run(token)
