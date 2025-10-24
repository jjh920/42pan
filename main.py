# main.py — 가입채널 제한 + 환영채널 안내 버전
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

# ── 새로 들어온 멤버에게 "가입자" 역할 부여 ─────────────────
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
            discord.SelectOption(label="관리자(서버관리자문의)"),
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
        label="당신의 닉네임은 무엇인가요?",
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
        await interaction.response.send_message("가입 승인중입니다…", ephemeral=True)

        # 역할 부여 / 닉네임 변경 / 가입자 제거
        if roles_to_add:
            await member.add_roles(*roles_to_add, reason="가입 절차 완료 - 역할 부여")
        await member.edit(nick=new_nick, reason="가입 절차 완료 - 닉네임 설정")
        join_role = find_role(guild, "가입자")
        if join_role and join_role in member.roles:
            await member.remove_roles(join_role, reason="가입 절차 완료 - 가입자 제거")

        # 환영 채널 안내
        welcome_channel = find_channel(guild, WELCOME_CHANNEL_NAME)
        if welcome_channel:
            await interaction.followup.send(
                f"가입이 완료되었습니다! 🎉\n {welcome_channel.mention} <<<<<<<버튼을 눌러서 닉네임이 잘 변경되었는지 확인!!",
                ephemeral=True
            )
            await welcome_channel.send(f"🎉 {member.mention} 님! 환영합니다! 🎊 닉네임 변경시 운영진 및 관리자에게 문의하세요!!")
        else:
            await interaction.followup.send("가입이 완료되었습니다! (환영 채널을 찾을 수 없습니다)", ephemeral=True)

# ── 명령어들 ────────────────────────────────
@tree.command(name="가입하기", description="가입 절차를 시작합니다.", guild=GUILD)
@app_commands.guild_only()
async def signup(interaction: discord.Interaction):
    # ✅ 특정 채널(#가입하기)에서만 허용
    if interaction.channel.name != SIGNUP_CHANNEL_NAME:
        await interaction.response.send_message(
            f"이 명령은 #{SIGNUP_CHANNEL_NAME} 채널에서만 사용할 수 있습니다.",
            ephemeral=True
        )
        return

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
