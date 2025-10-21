# main.py
import os
import discord
from discord import app_commands
from discord.ui import View, Button, Select, Modal, TextInput
from typing import Dict, Any, Optional
from keep_alive import keep_alive  # Flask keep-alive 서버 (UptimeRobot 핑용)

# ========= 설정 =========
SIGNUP_CHANNEL_NAME = "가입하기"  # 이 채널에 가입 버튼을 깔고, 여기서 누르면 절차 시작

# 입장 직후 자동 부여/제거 대상 초기 역할들
INITIAL_ROLE_NAMES = ["가입자", "가입자<"]  # 둘 다 지원 (서버에 있는 것만 사용/제거)

# 등급 선택 (길드원은 등급 역할 부여 X)
GRADE_CHOICES = ["길드원", "운영진", "관리자"]
GRADE_ROLE_NAMES = ["운영진", "관리자"]  # 실제로 서버에 있어야 하는 등급 역할

# 서버 역할 목록 (단일 선택/단일 보유)
SERVER_ROLE_NAMES = [f"{i}서버" for i in range(1, 11)]

# ========= 클라이언트/인텐트 =========
intents = discord.Intents.default()
intents.guilds = True
intents.members = True            # on_member_join / 역할 변경에 필수
intents.message_content = True    # on_message 쓰면 권장
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# 유저별 가입 진행 상태 저장
SIGNUP_STATE: Dict[int, Dict[str, Any]] = {}


# ========= 유틸 =========
def get_role_by_name(guild: discord.Guild, name: str) -> Optional[discord.Role]:
    return discord.utils.get(guild.roles, name=name)

def top_position(member: discord.Member) -> int:
    return max((r.position for r in member.roles), default=-1)

def first_existing_roles(guild: discord.Guild, names: list[str]) -> list[discord.Role]:
    """리스트 중 서버에 실제로 존재하는 역할만 반환"""
    out = []
    for n in names:
        r = get_role_by_name(guild, n)
        if r:
            out.append(r)
    return out

def bot_perm_check(guild: discord.Guild, channel: Optional[discord.abc.GuildChannel] = None) -> Optional[str]:
    """봇 권한/역할 순서 점검. 문제가 없으면 None."""
    me: Optional[discord.Member] = guild.me
    if not me:
        return "봇 멤버 정보를 가져오지 못했습니다."
    perms = channel.permissions_for(me) if channel else me.guild_permissions
    if not perms.manage_roles:
        return "봇에 'Manage Roles(역할 관리)' 권한이 필요합니다."
    if not perms.change_nickname:
        return "봇에 'Change Nickname(닉 변경)' 권한이 필요합니다."
    # 봇 역할 순서: 모든 대상 역할보다 위에 있어야 함
    bot_top = top_position(me)
    targets = GRADE_ROLE_NAMES + SERVER_ROLE_NAMES + INITIAL_ROLE_NAMES
    for rn in targets:
        r = get_role_by_name(guild, rn)
        if r and r.position >= bot_top:
            return f"봇 역할이 '{rn}' 역할보다 위에 있어야 합니다. (서버 설정 → 역할 순서)"
    return None


async def safe_add_initial_role(member: discord.Member, reason: str):
    """입장 직후 초기 역할(리스트 중 존재하는 첫 역할)을 부여 시도."""
    guild = member.guild
    me = guild.me
    if not me:
        print("⚠️ 봇 멤버 정보를 가져오지 못했습니다.")
        return
    bot_top = top_position(me)

    for name in INITIAL_ROLE_NAMES:
        role = get_role_by_name(guild, name)
        if not role:
            continue
        if role.position >= bot_top:
            print(f"🚫 역할 순서 문제: 봇 역할이 '{role.name}' 보다 위여야 합니다.")
            return
        if role in member.roles:
            print(f"ℹ️ {member} 은(는) 이미 '{role.name}' 보유.")
            return
        try:
            await member.add_roles(role, reason=reason)
            print(f"✅ {member} 에게 초기 역할 '{role.name}' 부여 완료")
            return
        except discord.Forbidden:
            print("🚫 권한 부족: Manage Roles/역할 순서 확인.")
            return
        except Exception as e:
            print(f"⚠️ 초기 역할 부여 예외: {e}")
            return
    print("ℹ️ 초기 역할(INITIAL_ROLE_NAMES) 중 서버에 존재하는 역할이 없습니다.")


async def apply_signup(guild: discord.Guild, member: discord.Member, grade_choice: str, server_choice: str, raw_nick: str):
    """닉네임/역할 실제 적용 + 초기 역할 제거"""
    new_nick = f"{server_choice}/{raw_nick}"

    # 등급 역할 (길드원은 None)
    add_grade_role = None
    if grade_choice in GRADE_ROLE_NAMES:
        add_grade_role = get_role_by_name(guild, grade_choice)
        if not add_grade_role:
            raise RuntimeError(f"서버에 '{grade_choice}' 역할이 없습니다.")

    # 서버 역할
    server_role = get_role_by_name(guild, server_choice)
    if not server_role:
        raise RuntimeError(f"서버에 '{server_choice}' 역할이 없습니다.")

    # 제거할 등급/서버 역할들
    to_remove_grade = [r for r in member.roles if r.name in GRADE_ROLE_NAMES and r != add_grade_role]
    to_remove_server = [r for r in member.roles if r.name in SERVER_ROLE_NAMES and r != server_role]
    # 초기 역할 제거(여러 개 있을 수 있음)
    existing_initials = first_existing_roles(guild, INITIAL_ROLE_NAMES)
    to_remove_initial = [r for r in existing_initials if r in member.roles]

    # 추가할 역할
    to_add = []
    if add_grade_role and add_grade_role not in member.roles:
        to_add.append(add_grade_role)
    if server_role not in member.roles:
        to_add.append(server_role)

    # 닉네임 변경
    print(f"[APPLY] {member} -> 닉 '{new_nick}', 등급 '{grade_choice}', 서버 '{server_choice}'")
    await member.edit(nick=new_nick, reason="가입 봇 자동 설정")

    # 역할 제거 → 추가 순
    if to_remove_grade or to_remove_server or to_remove_initial:
        await member.remove_roles(*to_remove_grade, *to_remove_server, *to_remove_initial, reason="가입 봇: 기존 역할 정리")
    if to_add:
        await member.add_roles(*to_add, reason="가입 봇: 신규 역할 부여")


# ========= UI 컴포넌트 =========
class GradeSelect(Select):
    def __init__(self):
        options = [discord.SelectOption(label=label, description=f"{label} 선택") for label in GRADE_CHOICES]
        super().__init__(placeholder="귀하의 등급은 무엇입니까?", min_values=1, max_values=1,
                         options=options, custom_id="grade_select")

    async def callback(self, interaction: discord.Interaction):
        grade = self.values[0]
        uid = interaction.user.id
        SIGNUP_STATE.setdefault(uid, {})
        SIGNUP_STATE[uid]["grade"] = grade

        view = View(timeout=180)
        view.add_item(ServerSelect())
        await interaction.response.edit_message(content="귀하의 서버숫자는 몇입니까?", view=view)


class ServerSelect(Select):
    def __init__(self):
        options = [discord.SelectOption(label=rn, description=f"{rn} 선택") for rn in SERVER_ROLE_NAMES]
        super().__init__(placeholder="귀하의 서버숫자를 선택하세요", min_values=1, max_values=1,
                         options=options, custom_id="server_select")

    async def callback(self, interaction: discord.Interaction):
        server = self.values[0]
        uid = interaction.user.id
        SIGNUP_STATE.setdefault(uid, {})
        SIGNUP_STATE[uid]["server"] = server

        await interaction.response.send_modal(NicknameModal())


class NicknameModal(Modal, title="닉네임 입력"):
    nickname: TextInput
    def __init__(self):
        super().__init__(timeout=180)
        self.nickname = TextInput(label="귀하의 닉네임을 적어주세요", placeholder="예: 주현", max_length=32)
        self.add_item(self.nickname)

    async def on_submit(self, interaction: discord.Interaction):
        uid = interaction.user.id
        state = SIGNUP_STATE.get(uid, {})
        grade = state.get("grade")
        server = state.get("server")
        raw_nick = self.nickname.value.strip()

        if not (grade and server and raw_nick):
            await interaction.response.send_message("입력값이 누락되었습니다. 처음부터 다시 시도해주세요.", ephemeral=True)
            SIGNUP_STATE.pop(uid, None)
            return

        problem = bot_perm_check(interaction.guild, interaction.channel)
        if problem:
            await interaction.response.send_message(f"⚠️ 설정 문제: {problem}", ephemeral=True)
            return

        await interaction.response.send_message("닉네임과 등급/서버를 변경중에 있습니다...", ephemeral=True)

        try:
            member = interaction.guild.get_member(uid)
            if not member:
                await interaction.followup.send("멤버 정보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.", ephemeral=True)
                return

            await apply_signup(interaction.guild, member, grade_choice=grade, server_choice=server, raw_nick=raw_nick)

            await interaction.followup.send(
                content=(
                    "✅ 완료입니다.\n"
                    f"- 등급: **{grade}** (길드원은 등급 역할 미부여)\n"
                    f"- 서버: **{server}** (해당 서버 역할 부여)\n"
                    f"- 닉네임: **{server}/{raw_nick}**\n"
                    f"- 초기 역할은 자동 해제되었습니다(있을 경우)."
                ),
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send("🚫 권한 부족: 봇에 '닉네임 변경'과 '역할 관리' 권한이 필요합니다.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ 처리 중 오류: {e}", ephemeral=True)
            raise
        finally:
            SIGNUP_STATE.pop(uid, None)


class StartSignupView(View):
    def __init__(self, timeout=None):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="가입 시작", style=discord.ButtonStyle.primary, custom_id="start_signup_button")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 필수 역할 있는지
        for rn in GRADE_ROLE_NAMES + SERVER_ROLE_NAMES:
            if get_role_by_name(interaction.guild, rn) is None:
                await interaction.response.send_message(
                    f"⚠️ 역할 누락: '{rn}' 역할이 서버에 필요합니다. 관리자에게 역할 생성 요청 후 다시 시도해주세요.",
                    ephemeral=True
                )
                return
        problem = bot_perm_check(interaction.guild, interaction.channel)
        if problem:
            await interaction.response.send_message(f"⚠️ 설정 문제: {problem}", ephemeral=True)
            return

        view = View(timeout=180)
        view.add_item(GradeSelect())
        await interaction.response.send_message(
            content="귀하의 등급은 무엇입니까? (목록에서 선택)",
            view=view,
            ephemeral=True
        )


# ========= 슬래시 명령 =========
@tree.command(name="가입하기설치", description=f"'{SIGNUP_CHANNEL_NAME}' 채널에 가입 시작 버튼 메시지를 설치 (관리자)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def install_in_signup_channel(interaction: discord.Interaction):
    ch = discord.utils.get(interaction.guild.text_channels, name=SIGNUP_CHANNEL_NAME)
    if not ch:
        await interaction.response.send_message(
            f"⚠️ '{SIGNUP_CHANNEL_NAME}' 채널을 찾지 못했습니다. 채널을 먼저 만들고 다시 실행하세요.",
            ephemeral=True
        )
        return
    view = StartSignupView()
    await ch.send("아래 버튼을 눌러 **가입 절차**를 시작하세요.", view=view)
    await interaction.response.send_message(f"✅ 설치 완료: {ch.mention} 에 메시지를 생성했습니다. 고정(핀)해 두세요.", ephemeral=True)


# ========= 이벤트 =========
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    # 길드별로 슬래시 커맨드 즉시 동기화(전파 지연 방지)
    try:
        total = 0
        for guild in client.guilds:
            synced = await tree.sync(guild=guild)
            total += len(synced)
            print(f"   - {guild.name}: {len(synced)}개 동기화")
        print(f"✅ 슬래시 커맨드 총 {total}개 동기화 완료")
        # 재시작 후에도 버튼이 살아있도록 View 재등록
        client.add_view(StartSignupView())
    except Exception as e:
        print("슬래시 동기화 오류:", e)

@client.event
async def on_member_join(member: discord.Member):
    """새 멤버 입장 시 초기 역할 자동 부여(스크리닝 꺼진 서버)."""
    print(f"👋 on_member_join: {member} (pending={getattr(member, 'pending', None)})")
    await safe_add_initial_role(member, "자동 초기 역할 (on_member_join)")

@client.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """스크리닝 켜진 서버: pending -> False 순간에 초기 역할 부여."""
    try:
        if getattr(before, "pending", None) and (before.pending is True) and (after.pending is False):
            print(f"✅ Screening passed: {after}")
            await safe_add_initial_role(after, "자동 초기 역할 (screening passed)")
    except Exception as e:
        print(f"⚠️ on_member_update 예외: {e}")

@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    try:
        await message.add_reaction("👍")
    except Exception as e:
        print(f"⚠️ add_reaction 실패: {e}")


# ========= 엔트리포인트 =========
def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN 환경변수가 없습니다. Render → Environment에 토큰을 넣어주세요.")
    keep_alive()      # Render 무료 플랜 유지 (UptimeRobot 5분 핑)
    client.run(token) # 디스코드 봇 실행

if __name__ == "__main__":
    main()
