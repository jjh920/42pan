# main.py  — 최소작동 버전 (슬래시 /핑 만)
import os
import discord
from discord import app_commands
from keep_alive import keep_alive  # UptimeRobot 핑용(있으면 사용, 없으면 이 줄 제거해도 됨)

# ── 기본 클라이언트/인텐트 ─────────────────
intents = discord.Intents.default()
intents.guilds = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ── 봇 준비 완료 ──────────────────────────
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    # 길드마다 즉시 동기화(슬래시가 바로 뜨게)
    total = 0
    for g in client.guilds:
        synced = await tree.sync(guild=g)
        total += len(synced)
        print(f"   - {g.name}: {len(synced)}개 동기화")
    print(f"✅ 슬래시 커맨드 총 {total}개 동기화 완료")

# ── 테스트용 슬래시 명령 (/핑) ─────────────
@tree.command(name="핑", description="슬래시 테스트")
@app_commands.guild_only()
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("퐁! ✅", ephemeral=True)

# ── 엔트리 포인트 ─────────────────────────
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN 환경변수가 없습니다.")
    # keep_alive()가 있다면 사용
    try:
        keep_alive()
    except Exception:
        pass
    client.run(token)
