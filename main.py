# main.py — 가입채널 제한 + 환영채널 안내 + 버튼 상호작용 수정 + Unknown interaction 해결 버전
import os
import discord
from discord import app_commands
from keep_alive import keep_alive

# ── 기본 설정 ──────────────────────────────
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

GUILD_ID = int(os.getenv("GUILD_ID", "0"))
GUILD = discord.Object(id=GUILD_ID)

# ── 채널 이름 설정 ─────────────────────────
SIGNUP_CHANNEL_NAME = "가입하기"       # 명령 사용 가능 채널 이름
WELCOME_CHANNEL_NAME = "환영합니다"    # 완료 후 안내 채널 이름

# ── 유틸 ───────────────────────────────────
def find_role(guild: discord.Guild, name: str):
    return discord.utils.get(guild.roles, name=name)

def find_channel(guild: discord.Guild, name: str):
    return discord.utils.get(guild.text_channels, name=name)

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

# ── 새로 들어온 멤버에게 '가입자' 역할만 부여 ─────────────────────────
@client.event
async def on_member_join(member: discord.Member):
    if member.guild.id != GUILD_ID:
        return

    role = find_role(member.guild, "가입자")
    if role:
        try:
            await member.add_roles(role, reason="신규 입장 자동 부여")
            print(f"👋 {member}에게 '가입자' 역할 부여 완료")
        except Exception as e:
            print(f"⚠️ {member}에게 역할 부여 실패: {e}")
    else:
        print("❌ '가입자' 역할을 찾을 수 없습니다.")

# ── 가입 절차용 뷰/모달 ─────────────────────
class SignupView(discord.ui.View):
    def __init__(self, author_id: int, timeout: float | None = 180):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.position_value = None
        self.server_value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
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
            discord.SelectOption(label="관리자(선택X!서버관리자문의)"),
        ],
        row=0
    )
    async def select_position(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.position_value = select.values[0]
        await interaction.response.defer()

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
        label="닉네임만 적어주세요!(서버 적지 마세요!!)",
        placeholder="예) 싸이판은멋쟁이",
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
            await interaction.response.send_message("멤버 정보를 불러올 수 없습니다.", ephemeral=True)
            return

        roles_to_add = []
        if self.position_value in ("운영진", "서버관리자"):
            pos_role = find_role(guild, self.position_value)
            if pos_role:
                roles_to_add.append(pos_role)
        server_role = find_role(guild, self.server_value)
        if server_role:
            roles_to_add.append(server_role)

        new_nick = f"{self.server_value}/{str(self.nickname)}"
        await interaction.response.send_message("가입 승인중입니다…", ephemeral_
