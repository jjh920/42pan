# main.py
import os
import discord
from keep_alive import keep_alive

# 인텐트 설정
intents = discord.Intents.default()
intents.message_content = True  # on_message 사용 시 필요 (Developer Portal에서도 활성화)

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")

@client.event
async def on_message(message: discord.Message):
    # 자신/봇 메시지는 무시 (루프/권한오류 예방)
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
