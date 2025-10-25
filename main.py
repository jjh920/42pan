# main.py — 닉네임 확인 모달 통합버전 (완전 작동 확인)
import os
import asyncio
import datetime
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

SIGNUP_CHANNEL_NAME = "가입하기"
WELCOME_CHANNEL_NAME = "환영합니다"

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
    print(f"✅ {len(synced)}개 명령 동기화 완료 (guild={GUILD_ID})")
    client.loop.create_task(refresh_signup_button())
    print("♻️ 자동 가입버튼 갱신 루프 시작됨")

@client.event
async def on_disconnect():
    print("⚠️ Discord 연결 끊김 → 자동 재연결 시도 중...")

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
            print(f"⚠️ 역할 부여 실패: {e}")

# ── 닉네임 확인용 모달 ─────────────────────────
class NicknameConfirmModal(discord.ui.Modal, title="닉네임 확인"):
    nickname_info = discord.ui.TextInput(
        label="당신의 닉네임은 아래와 같습니다. 변경 시 운영진에게 문의하세요.",
        style=discord.TextStyle.short,
        required=False
    )

    def __init__(self, nickname: str):
        super().__init__()
        # ✅ 정적 필드에 기본값 세팅
        self.nickname_info.default = nickname

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ 확인되었습니다!", ephemeral=True)

# ── 닉네임 확인 버튼 뷰 ─────────────────────────
class NickCheckView(discord.ui.View):
    def __init__(self, nickname: str):
        super().__init__(timeout=None)
        self.nickname = nickname

    @discord.ui.button(label="내 닉네임 확인하기", style=discord.ButtonStyle.green)
    async def check_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = NicknameConfirmModal(self.nickname)
        await interaction.response.send_modal(modal)

# ── 환영채널 이동 버튼 ─────────────────────────
class DoneView(discord.ui.View):
    def __init__(self, welcome_channel: discord.TextChannel):
        super().__init__(timeout=None)
        url = f"https://discord.com/channels/{welcome_channel.guild.id}/{welcome_channel.id}"
        self.add_item(discord.ui.Button(
            label="환영합니다채널 바로가기",
            style=discord.ButtonStyle.link,
            url=url
        ))

# ── 가입 절차 뷰 ─────────────────────────────
class SignupView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=None)
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
        options=[
            discord.SelectOption(label="길드원"),
            discord.SelectOption(label="운영진"),
            discord.SelectOption(label="관리자(선택X!서버관리자문의)")
        ],
        row=0
    )
    async def select_position(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.position_value = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="당신의 서버를 선택하세요",
        options=[discord.SelectOption(label=f"{i}서버") for i in range(1, 11)],
        row=1
    )
    async def select_server(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.server_value = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="다음 (닉네임 입력)", style=discord.ButtonStyle.green, row=2)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.position_value or not self.server_value:
            await interaction.response.send_message("직위와 서버를 모두 선택해주세요.", ephemeral=True)
            return
        await interaction.response.send_modal(NicknameModal(self.position_value, self.server_value))

# ── 닉네임 입력 모달 ─────────────────────────
class NicknameModal(discord.ui.Modal, title="닉네임 입력"):
    nickname = discord.ui.TextInput(
        label="서버는 적지 말고 닉네임만 적어주세요!",
        placeholder="예) 싸이판은멋쟁이", max_length=32, required=True
    )

    def __init__(self, position_value: str, server_value: str):
        super().__init__()
        self.position_value = position_value
        self.server_value = server_value

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user
        new_nick = f"{self.server_value}/{self.nickname}"
        await member.edit(nick=new_nick)

        # 역할 처리
        roles_to_add = []
        if self.position_value in ("운영진", "서버관리자"):
            pos_role = find_role(guild, self.position_value)
            if pos_role:
                roles_to_add.append(pos_role)
        server_role = find_role(guild, self.server_value)
        if server_role:
            roles_to_add.append(server_role)
        if roles_to_add:
            await member.add_roles(*roles_to_add)
        join_role = find_role(guild, "가입자")
        if join_role and join_role in member.roles:
            await member.remove_roles(join_role)

        # ✅ 가입 완료 메시지 + 닉네임 확인 버튼 + 환영채널 이동 버튼
        welcome_channel = find_channel(guild, WELCOME_CHANNEL_NAME)
        view = NickCheckView(new_nick)
        embed = discord.Embed(
            title="✅ 가입이 완료되었습니다!",
            description="아래 버튼을 눌러 닉네임을 확인하거나 <#{welcome_channel.id}> 로 이동하세요.",
            color=discord.Color.green()
        )
        if welcome_channel:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            await welcome_channel.send(f"✅ {member.mention} 님! 환영합니다! 닉네임 변경시 운영진에게 문의하세요!")
        else:
            await interaction.response.send_message("가입 완료! (환영합니다채널을 찾을 수 없습니다.)", ephemeral=True)

# ── 가입 버튼 ───────────────────────────────
class StartSignupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="가입하기", style=discord.ButtonStyle.green)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = SignupView(author_id=interaction.user.id)
        await interaction.response.send_message(
            "안녕하세요, 가입봇 42판입니다.\n직위와 서버를 선택한 후 [다음] 버튼을 눌러 닉네임을 입력해주세요.",
            view=view,
            ephemeral=True
        )

# ── 관리자용 명령 ───────────────────────────
@tree.command(name="가입버튼", description="가입하기 버튼 메시지를 보냅니다.", guild=GUILD)
@app_commands.guild_only()
async def send_signup_button(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
        return
    await interaction.response.send_message("✅ 가입 버튼 메시지를 전송했습니다.", ephemeral=True)
    embed = discord.Embed(
        title="▶️ 서버 가입 절차 안내",
        description="아래 **[가입하기]** 버튼을 눌러 가입 절차를 시작하세요!",
        color=discord.Color.blurple()
    )
    await interaction.channel.send(embed=embed, view=StartSignupView())

# ── 🔁 10분 단위 갱신 ─────────────────────────
async def refresh_signup_button():
    await client.wait_until_ready()
    guild = client.get_guild(GUILD_ID)
    if not guild:
        return

    async def update_button():
        channel = find_channel(guild, SIGNUP_CHANNEL_NAME)
        if not channel:
            return
        embed = discord.Embed(
            title="▶️ 서버 가입 절차 안내",
            description="아래 **[가입하기]** 버튼을 눌러 가입 절차를 시작하세요!",
            color=discord.Color.blurple()
        )
        async for msg in channel.history(limit=10):
            if msg.author == client.user and msg.embeds:
                if msg.embeds[0].title == "▶️ 서버 가입 절차 안내":
                    await msg.delete()
        await channel.send(embed=embed, view=StartSignupView())
        print(f"♻️ [{datetime.datetime.now().strftime('%H:%M:%S')}] 가입 버튼 갱신됨")

    await update_button()
    while not client.is_closed():
        now = datetime.datetime.now()
        next_minute = ((now.minute // 10) + 1) * 10
        if next_minute >= 60:
            next_run = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
        else:
            next_run = now.replace(minute=next_minute, second=0, microsecond=0)
        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        await update_button()

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
