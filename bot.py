# bot.py (디버그/안정화 패치)
import os
import discord
from discord import app_commands
from discord.ui import View, Button, Select, Modal, TextInput
from typing import Dict, Any
from keep_alive import keep_alive

SIGNUP_CHANNEL_NAME = "가입하기"
INITIAL_ROLE_NAME = "가입자<"

GRADE_CHOICES = ["길드원", "운영진", "관리자"]     # 길드원은 역할 미부여
GRADE_ROLE_NAMES = ["운영진", "관리자"]            # 실제로 존재해야 함
SERVER_ROLE_NAMES = [f"{i}서버" for i in range(1, 11)]

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

SIGNUP_STATE: Dict[int, Dict[str, Any]] = {}

def get_role_by_name(guild: discord.Guild, name: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=name)

async def ensure_roles_exist(guild: discord.Guild) -> bool:
    for rn in GRADE_ROLE_NAMES + SERVER_ROLE_NAMES:
        if get_role_by_name(guild, rn) is None:
            print(f"[WARN] 역할 없음: {rn}")
            return False
    return True

def bot_perm_check(guild: discord.Guild, channel: discord.abc.GuildChannel | None = None) -> str | None:
    """필수 권한/역할순서 체크. 문제가 없으면 None."""
    me: discord.Member = guild.me  # 봇 자신
    if not me:
        return "봇 멤버 정보를 가져오지 못했습니다."
    # 권한
    perms = channel.permissions_for(me) if channel else guild.me.guild_permissions
    if not perms.manage_roles:
        return "봇에 'Manage Roles(역할 관리)' 권한이 필요합니다."
    if not perms.change_nickname:
        return "봇에 'Change Nickname(닉네임 변경)' 권한이 필요합니다."
    # 역할 순서(봇 역할이 더 위여야 함)
    bot_top_pos = max((r.position for r in me.roles), default=-1)
    for rn in GRADE_ROLE_NAMES + SERVER_ROLE_NAMES + [INITIAL_ROLE_NAME]:
        r = get_role_by_name(guild, rn)
        if r and r.position >= bot_top_pos:
            return f"봇 역할이 '{rn}' 역할보다 위에 있어야 합니다. (서버 설정 → 역할 순서 조정)"
    return None

async def apply_signup(guild: discord.Guild, member: discord.Member, grade_choice: str, server_choice: str, raw_nick: str):
    new_nick = f"{server_choice}/{raw_nick}"
    add_grade_role = None
    if grade_choice in GRADE_ROLE_NAMES:
        add_grade_role = get_role_by_name(guild, grade_choice)
        if not add_grade_role:
            raise RuntimeError(f"서버에 '{grade_choice}' 역할이 없습니다.")
    server_role = get_role_by_name(guild, server_choice)
    if not server_role:
        raise RuntimeError(f"서버에 '{server_choice}' 역할이 없습니다.")

    to_remove_grade = [r for r in member.roles if r.name in GRADE_ROLE_NAMES and r != add_grade_role]
    to_remove_server = [r for r in member.roles if r.name in SERVER_ROLE_NAMES and r != server_role]
    initial_role = get_role_by_name(guild, INITIAL_ROLE_NAME)
    to_remove_initial = [initial_role] if initial_role and initial_role in member.roles else []

    to_add = []
    if add_grade_role and add_grade_role not in member.roles:
        to_add.append(add_grade_role)
    if server_role not in member.roles:
        to_add.append(server_role)

    # 변경 적용
    print(f"[INFO] 닉 '{member}' -> '{new_nick}', 등급 '{grade_choice}', 서버 '{server_choice}'")
    await member.edit(nick=new_nick, reason="가입 봇 자동 설정")
    roles_to_remove = to_remove_grade + to_remove_server + to_remove_initial
    if roles_to_remove:
        await member.remove_roles(*roles_to_remove, reason="가입 봇 자동 설정: 기존 역할 정리")
    if to_add:
        await member.add_roles(*to_add, reason="가입 봇 자동 설정: 신규 역할 부여")

# ===== UI =====
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

        # 권한/역할순서 사전 점검
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
                    f"- 초기 역할 '**{INITIAL_ROLE_NAME}**'은 자동 해제되었습니다(있을 경우)."
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
        if not await ensure_roles_exist(interaction.guild):
            await interaction.response.send_message(
                "⚠️ 필요한 역할(운영진/관리자, 1서버~10서버)이 모두 존재해야 합니다.\n관리자에게 역할 생성 요청 후 다시 시도해주세요.",
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

# ---- 명령어들 ----

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # 슬래시 커맨드 에러 로깅
    print(f"[CMD ERROR] {interaction.command} in {interaction.guild}: {error}")

@tree.command(name="가입하기설치", description=f"'{SIGNUP_CHANNEL_NAME}' 채널에 가입 시작 버튼 메시지 설치 (관리자)")
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
    print(f"[INFO] 설치 완료 by {interaction.user} in {interaction.guild} -> {ch}")

# 현재 채널에 바로 설치하는 빠른 명령(디버그용)
@tree.command(name="가입버튼", description="(디버그) 현재 채널에 가입 버튼 메시지를 생성")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def install_here(interaction: discord.Interaction):
    view = StartSignupView()
    await interaction.response.send_message("아래 버튼을 눌러 **가입 절차**를 시작하세요.", view=view)
    print(f"[INFO] 현재 채널 설치 by {interaction.user} in {interaction.channel}")

@client.event
async def on_ready():
    print(f"✅ 로그인: {client.user} (ID: {client.user.id})")
    try:
        # 길드별 즉시 동기화(전파 지연 방지)
        total = 0
        for guild in client.guilds:
            synced = await tree.sync(guild=guild)
            total += len(synced)
            print(f"   - {guild.name}: {len(synced)}개 동기화")
        print(f"✅ 슬래시 커맨드 총 {total}개 동기화 완료")
        # 재시작 후에도 버튼 동작하도록 View 재등록
        client.add_view(StartSignupView())
    except Exception as e:
        print("슬래시 동기화 오류:", e)

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("환경변수 DISCORD_TOKEN 이 설정되어 있지 않습니다.")
        raise SystemExit(1)
    keep_alive()
    client.run(token)
