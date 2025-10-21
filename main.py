# main.py — 최소작동 버전 (+ 가입자 역할 자동 부여)
import os
import discord
from discord import app_commands
from keep_alive import keep_alive  # 없으면 try/except로 무시됨

# ── 기본 설정 ──────────────────────────────
intents = discord.Intents.default()
intents.guilds = True
intents.members = True  # ✅ 새 멤버 join 이벤트를 위해 꼭 필요
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

GUILD_ID = int(os.getenv("GUILD_ID", "0"))
GUILD = discord.Object(id=GUILD_ID)

# ── 봇 준비 완료 ───────────────────────────
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    try:
        tree.copy_global_to(guild=GUILD)
    except Exception:
        pass
    synced = await tree.sync(guild=GUILD)
    print(f"✅ {len(synced)}개 길드 명령 동기화 완료 (guild={GUILD_ID})")

# ── 새로 들어온 멤버에게 "가입자" 역할 부여 ─────────────────
@client.event
async def on_member_join(member: discord.Member):
    if member.guild.id != GUILD_ID:
        return  # 다른 서버는 무시
    role = discord.utils.get(member.guild.roles, name="가입자")
    if role:
        try:
            await member.add_roles(role)
            print(f"👋 {member.name}에게 '가입자' 역할 부여 완료")
        except Exception as e:
            print(f"⚠️ {member.name}에게 역할 부여 실패: {e}")
    else:
        print("❌ '가입자' 역할을 찾을 수 없습니다. 서버에 역할이 있는지 확인하세요.")

# ── 테스트용 슬래시 명령 (/핑) ───────────────────────────────
@tree.command(name="핑", description="슬래시 테스트", guild=GUILD)
@app_commands.guild_only()
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("퐁! ✅", ephemeral=True)

# ── 실행 ────────────────────────────────────
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN 환경변수가 없습니다.")
    try:
        keep_alive()
    except Exception:
        pass
    client.run(token)
