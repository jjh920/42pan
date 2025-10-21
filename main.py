# main.py — 최소작동 버전 (+ 가입자 자동 부여, /가입하기 가입절차)
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

# ── 유틸 ───────────────────────────────────
def find_role(guild: discord.Guild, name: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=name)

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
    role = find_role(member.guild, "가입자")
    if role:
        try:
            await member.add_roles(role, reason="신규 입장 자동 부여")
            print(f"👋 {member}에게 '가입자' 역할 부여 완료")
        except Exception as e:
            print(f"⚠️ {member}에게 역할 부여 실패: {e}")
    else:
        print("❌ '가입자' 역할을 찾을 수 없습니다. 서버에 역할이 있는지 확인하세요.")

# ── 가입 절차용 뷰/모달 ─────────────────────
class SignupView(discord.ui.View):
    def __init__(self, author_id: int, timeout: float | None = 180):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.position_value: str | None = None
        self.server_value: str | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # 자기 것만 조작 가능
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("이 가입 절차는 본인만 진행할 수 있어요.", ephemeral=True)
            return False
        return True

    @discord.ui.select(
        placeholder="당신의 직위를 선택하세요",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="길드원"),
            discord.SelectOption(label="운영진"),
            discord.SelectOption(label="관리자"),
        ],
        row=0
    )
    async def select_position(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.position_value = select.values[0]
        await interaction.response.defer()  # 조용히 선택만 반영

    @discord.ui.select(
        placeholder="당신의 서버를 선택하세요",
        min_values=1,
        max_values=1,
        options=[discord.SelectOption(label=f"{i}서버") for i in range(1, 11)],
        row=1
    )
    async def select_server(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.server_value = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="다음 (닉네임 입력)", style=discord.ButtonStyle.primary, row=2)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.position_value or not self.server_value:
            await interaction.response.send_message("직위와 서버를 모두 선택해주세요.", ephemeral=True)
            return
        await interaction.response.send_modal(NicknameModal(self.position_value, self.server_value))

class NicknameModal(discord.ui.Modal, title="닉네임 입력"):
    nickname = discord.ui.TextInput(
        label="당신의 닉네임은 무엇인가요?",
        placeholder="예) 주현",
        max_length=32,
        required=True
    )

    def __init__(self, position_value: str, server_value: str):
        super().__init__()
        self.position_value = position_value
        self.server_value = server_value

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user if isinstance(interaction.user, discord.Member) else guild.get_member(interaction.user.id)
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("멤버 정보를 불러올 수 없습니다. 잠시 후 다시 시도해주세요.", ephemeral=True)
            return

        # 역할 계산
        roles_to_add: list[discord.Role] = []
        # 직위 역할 (길드원은 별도 역할 없음)
        if self.position_value in ("운영진", "관리자"):
            pos_role = find_role(guild, self.position_value)
            if pos_role:
                roles_to_add.append(pos_role)
            else:
                await interaction.response.send_message(f"'{self.position_value}' 역할을 찾을 수 없습니다. 관리자에게 문의하세요.", ephemeral=True)
                return

        # 서버 역할 (1서버~10서버)
        server_role = find_role(guild, self.server_value)
        if not server_role:
            await interaction.response.send_message(f"'{self.server_value}' 역할을 찾을 수 없습니다. 관리자에게 문의하세요.", ephemeral=True)
            return
        roles_to_add.append(server_role)

        # 닉네임 구성: {서버}/{닉네임}
        new_nick = f"{self.server_value}/{str(self.nickname)}"

        # 진행 메시지
        await interaction.response.send_message("가입 승인중입니다…", ephemeral=True)

        # 역할 부여 & 닉네임 설정 & '가입자' 제거
        errors = []
        try:
            if roles_to_add:
                await member.add_roles(*roles_to_add, reason="가입 절차 완료 - 역할 부여")
        except Exception as e:
            errors.append(f"역할 부여 오류: {e}")

        try:
            await member.edit(nick=new_nick, reason="가입 절차 완료 - 닉네임 설정")
        except Exception as e:
            errors.append(f"닉네임 변경 오류: {e}")

        try:
            join_role = find_role(guild, "가입자")
            if join_role and join_role in member.roles:
                await member.remove_roles(join_role, reason="가입 절차 완료 - 가입자 제거")
        except Exception as e:
            errors.append(f"'가입자' 역할 제거 오류: {e}")

        # 완료 안내
        base_msg = f"가입이 완료되었습니다! 🎉\n부여된 역할: {', '.join([r.name for r in roles_to_add])}\n닉네임: {new_nick}"
        if errors:
            err_msg = "\n".join(errors)
            await interaction.followup.send(f"{base_msg}\n\n⚠️ 일부 작업에서 문제가 발생했습니다:\n```{err_msg}```", ephemeral=True)
        else:
            await interaction.followup.send(base_msg, ephemeral=True)

# ── 명령어들 ────────────────────────────────
@tree.command(name="핑", description="슬래시 테스트", guild=GUILD)
@app_commands.guild_only()
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("퐁! ✅", ephemeral=True)

@tree.command(name="가입하기", description="가입 절차를 시작합니다.", guild=GUILD)
@app_commands.guild_only()
async def signup(interaction: discord.Interaction):
    view = SignupView(author_id=interaction.user.id)
    await interaction.response.send_message(
        "안녕하세요, 가입봇 42판입니다.\n아래에서 **직위**와 **서버**를 선택한 뒤 **[다음]** 버튼을 눌러 닉네임을 입력해주세요.",
        view=view,
        ephemeral=True
    )

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
