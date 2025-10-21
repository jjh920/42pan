import os
import discord
from discord import app_commands
from discord.ui import View, Button, Select, Modal, TextInput
from typing import Dict, Any
from keep_alive import keep_alive

# ===== 설정: 역할/상수 =====
# "길드원"은 '역할 부여 없음' 처리
GRADE_CHOICES = ["길드원", "운영진", "관리자"]
GRADE_ROLE_NAMES = ["운영진", "관리자"]          # 실제로 서버에 존재해야 하는 등급 역할
INITIAL_ROLE_NAME = "가입자<"                    # 가입 직후 가진다고 가정. 완료 시 제거
SERVER_ROLE_NAMES = [f"{i}서버" for i in range(1, 11)]  # 1서버 ~ 10서버

# ===== 클라이언트/인텐트 =====
intents = discord.Intents.default()
intents.guilds = True
intents.members = True            # 멤버/닉 변경, 역할 변경에 필요
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# 유저별 진행 상태 저장
SIGNUP_STATE: Dict[int, Dict[str, Any]] = {}

# ===== 유틸 =====
def get_role_by_name(guild: discord.Guild, name: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=name)

async def ensure_roles_exist(guild: discord.Guild) -> bool:
    """필요한 역할(운영진/관리자 + 1~10서버)이 존재하는지 확인"""
    needed = GRADE_ROLE_NAMES + SERVER_ROLE_NAMES
    for rn in needed:
        if get_role_by_name(guild, rn) is None:
            return False
    return True  # INITIAL_ROLE_NAME 은 없어도 동작(있으면 제거)

async def apply_signup(guild: discord.Guild, member: discord.Member, grade_choice: str, server_choice: str, raw_nick: str):
    """닉네임/역할 실제 적용 + 가입자< 제거"""
    # 닉네임: "1서버/닉네임"
    new_nick = f"{server_choice}/{raw_nick}"

    # 목표 등급 역할(길드원은 None)
    add_grade_role = None
    if grade_choice in GRADE_ROLE_NAMES:
        add_grade_role = get_role_by_name(guild, grade_choice)
        if add_grade_role is None:
            raise RuntimeError(f"서버에 '{grade_choice}' 역할이 없습니다.")

    # 목표 서버 역할
    server_role = get_role_by_name(guild, server_choice)
    if server_role is None:
        raise RuntimeError(f"서버에 '{server_choice}' 역할이 없습니다.")

    # 제거할 '다른' 등급 역할들 (길드원 선택이면 운영진/관리자 전부 제거)
    to_remove_grade = [r for r in member.roles if r.name in GRADE_ROLE_NAMES and r != add_grade_role]
    # 제거할 '다른' 서버 역할들
    to_remove_server = [r for r in member.roles if r.name in SERVER_ROLE_NAMES and r != server_role]

    # 추가할 역할들
    to_add = []
    if add_grade_role and add_grade_role not in member.roles:
        to_add.append(add_grade_role)
    if server_role not in member.roles:
        to_add.append(server_role)

    # 초기 역할(가입자<) 제거 대상 포함(있을 때만)
    initial_role = get_role_by_name(guild, INITIAL_ROLE_NAME)
    to_remove_initial = [initial_role] if initial_role and initial_role in member.roles else []

    # 변경 적용
    # 닉네임
    await member.edit(nick=new_nick, reason="가입 봇 자동 설정")

    # 역할 제거 (등급/서버/가입자<)
    roles_to_remove = to_remove_grade + to_remove_server + to_remove_initial
    if roles_to_remove:
        await member.remove_roles(*roles_to_remove, reason="가입 봇 자동 설정: 기존 역할 정리")

    # 역할 추가
    if to_add:
        await member.add_roles(*to_add, reason="가입 봇 자동 설정: 신규 역할 부여")

# ===== UI 컴포넌트 =====
class GradeSelect(Select):
    def __init__(self):
        options = [discord.SelectOption(label=label, description=f"{label} 선택") for label in GRADE_CHOICES]
        super().__init__(
            placeholder="귀하의 등급은 무엇입니까? (목록에서 선택)",
            min_values=1, max_values=1, options=options, custom_id="grade_select"
        )

    async def callback(self, interaction: discord.Interaction):
        grade = self.values[0]
        user_id = interaction.user.id
        SIGNUP_STATE.setdefault(user_id, {})
        SIGNUP_STATE[user_id]["grade"] = grade

        # 다음 단계: 서버 선택
        view = View(timeout=180)
        view.add_item(ServerSelect())
        await interaction.response.edit_message(content="귀하의 서버숫자는 몇입니까? (목록에서 선택)", view=view)

class ServerSelect(Select):
    def __init__(self):
        options = [discord.SelectOption(label=rn, description=f"{rn} 선택") for rn in SERVER_ROLE_NAMES]
        super().__init__(
            placeholder="귀하의 서버숫자는 몇입니까? (목록에서 선택)",
            min_values=1, max_values=1, options=options, custom_id="server_select"
        )

    async def callback(self, interaction: discord.Interaction):
        server = self.values[0]
        user_id = interaction.user.id
        SIGNUP_STATE.setdefault(user_id, {})
        SIGNUP_STATE[user_id]["server"] = server

        # 다음 단계: 닉네임 입력 모달
        modal = NicknameModal()
        await interaction.response.send_modal(modal)

class NicknameModal(Modal, title="닉네임 입력"):
    nickname: TextInput

    def __init__(self):
        super().__init__(timeout=180)
        self.nickname = TextInput(
            label="귀하의 닉네임을 적어주세요",
            placeholder="예: 주현",
            max_length=32
        )
        self.add_item(self.nickname)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        state = SIGNUP_STATE.get(user_id, {})
        grade = state.get("grade")
        server = state.get("server")
        raw_nick = self.nickname.value.strip()

        if not (grade and server and raw_nick):
            await interaction.response.send_message("입력값이 누락되었습니다. 처음부터 다시 시도해주세요.", ephemeral=True)
            SIGNUP_STATE.pop(user_id, None)
            return

        # 진행 메시지
        await interaction.response.send_message("닉네임과 등급/서버를 변경중에 있습니다...", ephemeral=True)

        try:
            member = interaction.guild.get_member(user_id)
            if member is None:
                await interaction.followup.send("멤버 정보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.", ephemeral=True)
                return

            # 실제 적용 (길드원은 등급 역할 부여 없음)
            await apply_signup(interaction.guild, member, grade_choice=grade, server_choice=server, raw_nick=raw_nick)

            # 완료 안내
            await interaction.followup.send(
                content=(
                    "✅ 완료입니다.\n"
                    f"- 등급 설정: **{grade}** (길드원은 등급 역할 미부여)\n"
                    f"- 서버 설정: **{server}** (해당 서버 역할 자동부여)\n"
                    f"- 닉네임: **{server}/{raw_nick}**\n"
                    f"- 초기 역할 '**{INITIAL_ROLE_NAME}**'은 자동 해제되었습니다(있을 경우)."
                ),
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send("⚠️ 권한 부족: 봇에 '닉네임 변경'과 '역할 관리' 권한이 필요합니다.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ 처리 중 오류: {e}", ephemeral=True)
        finally:
            SIGNUP_STATE.pop(user_id, None)

class StartSignupView(View):
    def __init__(self, timeout=None):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="가입 시작", style=discord.ButtonStyle.primary, custom_id="start_signup_button")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 필수 역할(운영진/관리자 + 1~10서버)이 있는지 확인
        if not await ensure_roles_exist(interaction.guild):
            await interaction.response.send_message(
                "⚠️ 서버에 필요한 역할(운영진/관리자, 1서버~10서버)이 모두 존재해야 합니다.\n관리자에게 역할 생성 요청 후 다시 시도해주세요.",
                ephemeral=True
            )
            return

        # 1단계: 등급 선택
        view = View(timeout=180)
        view.add_item(GradeSelect())
        await interaction.response.send_message(
            content='귀하의 등급은 무엇입니까? (목록에서 선택)',
            view=view,
            ephemeral=True
        )

# ===== 명령어 =====
@tree.command(name="가입하기", description="이 채널에 가입 시작 버튼 메시지를 설치합니다. (관리자 전용)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_signup_message(interaction: discord.Interaction):
    view = StartSignupView()
    await interaction.response.send_message("아래 버튼을 눌러 가입 절차를 시작하세요.", view=view)
    # 필요하면 수동으로 메시지를 고정해 두세요.

# ===== 준비/동기화 =====
@client.event
async def on_ready():
    print(f"✅ 로그인: {client.user} (ID: {client.user.id})")
    try:
        await tree.sync()
        # 재시작 후에도 버튼이 동작하도록 View 재등록
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
