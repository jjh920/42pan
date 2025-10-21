# main.py
import os
import discord
from keep_alive import keep_alive  # UptimeRobot 핑 받는 미니 웹서버 (Flask)

# ─────────────────────────────────────────────────────────
# 인텐트 설정 (Developer Portal > Bot 에서도 동일하게 ON)
# - SERVER MEMBERS INTENT: 멤버 이벤트/역할 부여를 위해 필수
# - MESSAGE CONTENT INTENT: on_message 사용 시 권장
# ─────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

client = discord.Client(intents=intents)

# 새 멤버에게 자동 부여할 역할명
INITIAL_ROLE_NAME = "가입자"


# ─────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────
def get_role_by_name(guild: discord.Guild, name: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=name)


async def safe_add_role(member: discord.Member, role_name: str, reason: str):
    role = get_role_by_name(member.guild, role_name)
    if not role:
        print(f"⚠️ 역할 없음: '{role_name}' (서버에 역할을 먼저 만들어 두세요)")
        return
    # 권한/역할 순서 체크: 봇 역할이 대상 역할보다 위에 있어야 함
    me = member.guild.me
    if me is None:
        print("⚠️ 봇 멤버 정보를 가져오지 못했습니다.")
        return
    bot_top_pos = max((r.position for r in me.roles), default=-1)
    if role.position >= bot_top_pos:
        print(f"🚫 역할 순서 문제: 봇 역할이 '{role.name}' 보다 위에 있어야 합니다. (서버 설정 → 역할 순서)")
        return

    if role in member.roles:
        print(f"ℹ️ {member} 은(는) 이미 '{role.name}' 역할을 가지고 있습니다.")
        return

    try:
        await member.add_roles(role, reason=reason)
        print(f"✅ {member} 에게 '{role.name}' 역할 부여 완료 ({reason})")
    except discord.Forbidden:
        print("🚫 권한 부족: 봇에 'Manage Roles' 권한이 있나요?")
    except Exception as e:
        print(f"⚠️ add_roles 예외: {e}")


# ─────────────────────────────────────────────────────────
# 이벤트
# ─────────────────────────────────────────────────────────
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    # 봇이 참가한 길드/권한 간단 점검
    for g in client.guilds:
        me = g.me
        if me:
            perms = me.guild_permissions
            print(
                f"• Guild: {g.name} | ManageRoles={'Y' if perms.manage_roles else 'N'} "
                f"| ChangeNickname={'Y' if perms.change_nickname else 'N'}"
            )


@client.event
async def on_member_join(member: discord.Member):
    """
    새 멤버 입장 시 '가입자' 역할 자동 부여.
    ※ 멤버십 스크리닝(규칙 동의)이 켜진 서버는 pending=True 상태에서 실패할 수 있으므로
      아래 on_member_update 에서도 보완합니다.
    """
    print(f"👋 on_member_join: {member} (pending={getattr(member, 'pending', None)})")
    await safe_add_role(member, INITIAL_ROLE_NAME, "자동 가입자 역할 (on_member_join)")


@client.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """
    멤버십 스크리닝(규칙 동의) 활성 서버 보완:
    pending=True → False (규칙 동의 완료) 순간에 '가입자' 역할 부여
    """
    try:
        before_pending = getattr(before, "pending", None)
        after_pending = getattr(after, "pending", None)
        if before_pending and (after_pending is False):
            print(f"✅ Screening passed: {after}")
            await safe_add_role(after, INITIAL_ROLE_NAME, "자동 가입자 역할 (screening passed)")
    except Exception as e:
        print(f"⚠️ on_member_update 예외: {e}")


@client.event
async def on_message(message: discord.Message):
    # 봇/자기 자신 메시지 무시
    if message.author.bot:
        return
    try:
        await message.add_reaction("👍")
    except Exception as e:
        print(f"⚠️ add_reaction 실패: {e}")


# ─────────────────────────────────────────────────────────
# 엔트리포인트
# ─────────────────────────────────────────────────────────
def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN 환경변수가 없습니다. Render → Environment에 토큰을 넣어주세요.")
    # Render에서 sleep 방지용 웹서버 가동 (UptimeRobot이 5분마다 체크)
    keep_alive()
    # 디스코드 봇 실행
    client.run(token)


if __name__ == "__main__":
    main()
