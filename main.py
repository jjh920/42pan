# main.py
import os
import discord
from keep_alive import keep_alive

# 인텐트 설정
intents = discord.Intents.default()
intents.members = True              # 멤버 이벤트 감지를 위해 반드시 필요
intents.message_content = True      # on_message용
client = discord.Client(intents=intents)

INITIAL_ROLE_NAME = "가입자"  # 새로 들어온 멤버에게 자동 부여할 역할 이름


# 봇 준비 완료 시
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")


# 새 멤버가 서버에 들어왔을 때
@client.event
async def on_member_join(member: discord.Member):
    """멤버가 서버에 들어온 순간 '가입자' 역할 자동 부여"""
    role = discord.utils.get(member.guild.roles, name=INITIAL_ROLE_NAME)
    if not role:
        print(f"⚠️ '{INITIAL_ROLE_NAME}' 역할을 찾을 수 없습니다.")
        return
    try:
        # 이미 역할이 없을 때만 추가
        if role not in member.roles:
            await member.add_roles(role, reason="자동 가입자 역할 부여 (on_member_join)")
            print(f"✅ {member.name} 에게 '{INITIAL_ROLE_NAME}' 역할 부여 완료")
    except discord.Forbidden:
        print("🚫 권한 오류: 봇의 역할이 '가입자'보다 위에 있거나 Manage Roles 권한이 있어야 합니다.")
    except Exception as e:
        print(f"⚠️ 오류 발생: {e}")


# 메세지에 👍 반응 (기존 기능 유지)
@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    try:
        await message.add_reaction("👍")
    except Exception as e:
        print(f"⚠️ add_reaction 실패: {e}")


def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN 환경변수가 없습니다.")
    keep_alive()         # Render Web Service용 HTTP keep-alive
    client.run(token)    # 봇 실행


if __name__ == "__main__":
    main()
