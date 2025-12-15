import os
import asyncio
import discord
from discord import app_commands
from keep_alive import keep_alive

# ───────────────── 기본 설정 ─────────────────
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

GUILD_ID = int(os.getenv("GUILD_ID", "0"))
GUILD = discord.Object(id=GUILD_ID)

SIGNUP_CHANNEL_NAME = "가입하기"
WELCOME_CHANNEL_NAME = "환영합니다"

# ───────────────── 서버 매핑 ─────────────────
SERVER_MAP = {
    "라엘": ["5서버", "8서버", "9서버"],
    "모리안": ["3서버", "4서버", "9서버", "10서버"],
    "엘드리히": ["1서버", "2서버", "3서버", "5서버"],
    "마레크": ["4서버", "7서버"]
}

# ───────────────── 유틸 ──────────────────────
def find_role(guild: discord.Guild, name: str):
    return discord.utils.get(guild.roles, name=name)

def find_channel(guild: discord.Guild, name: str):
    return discord.utils.get(guild.text_channels, name=name)

# ───────────────── Ready ─────────────────────
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    try:
        tree.copy_global_to(guild=GUILD)
    except Exception:
        pass
    await tree.sync(guild=GUILD)
    client.loop.create_task(refresh_signup_button())

# ───────────────── 신규 입장 ─────────────────
@client.event
async def on_member_join(member: discord.Member):
    if member.guild.id != GUILD_ID:
        return
    role = find_role(member.guild, "가입자")
    if role:
        await member.add_roles(role)

# ───────────────── 완료 버튼 View ─────────────────
class DoneView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=300)
        self.add_item(
            discord.ui.Button(
                label="환영 채널로 이동하기 👈",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/channels/{channel.guild.id}/{channel.id}"
            )
        )

# ───────────────── 닉네임 모달 ─────────────────
class NicknameModal(discord.ui.Modal, title="닉네임 입력"):
    nickname = discord.ui.TextInput(
        label="닉네임만 입력해주세요",
        placeholder="예) 싸이판",
        max_length=20,
        required=True
    )

    def __init__(self, position, server_name, server_channel):
        super().__init__()
        self.position = position
        self.server_name = server_name
        self.server_channel = server_channel

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user

        try:
            await member.edit(
                nick=f"{self.server_name}/{self.server_channel}/{self.nickname}"
            )
        except Exception:
            pass

        roles = []
        for name in (
            self.server_name,
            f"{self.server_name} {self.server_channel}",
            self.position
        ):
            r = find_role(guild, name)
            if r:
                roles.append(r)

        if roles:
            await member.add_roles(*roles)

        join_role = find_role(guild, "가입자")
        if join_role:
            await member.remove_roles(join_role)

        welcome_channel = find_channel(guild, WELCOME_CHANNEL_NAME)

        embed = discord.Embed(
            title="✅ 가입 완료!",
            description=(
                "# 환영합니다!\n\n"
                "# 아래 버튼을 눌러\n"
                "#👇 **환영 채널로 이동해주세요** "
            ),
            color=discord.Color.green()
        )

        await interaction.response.send_message(
            embed=embed,
            view=DoneView(welcome_channel),
            ephemeral=True
        )

        await welcome_channel.send(
            f"✅ {member.mention} 님 환영합니다!\n"
            f"닉네임 변경은 닉네임변경요청방이나 운영진에게 문의해주세요."
        )

# ───────────────── 가입 View ─────────────────
class SignupView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=600)
        self.author_id = author_id

        self.position = None
        self.server_name = None
        self.server_channel = None

        self.position_select = self.make_position_select()
        self.server_name_select = self.make_server_name_select()
        self.server_channel_select = None
        self.next_button = self.make_next_button()

        self.add_item(self.position_select)
        self.add_item(self.server_name_select)
        self.add_item(self.next_button)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "본인만 진행할 수 있습니다.",
                ephemeral=True
            )
            return False
        return True

    # ── 직책 Select ──
    def make_position_select(self):
        select = discord.ui.Select(
            placeholder="직책 선택",
            options=[
                discord.SelectOption(label="길드원"),
                discord.SelectOption(label="운영진"),
                discord.SelectOption(label="관리자(서버관리자문의)")
            ],
            row=0
        )

        async def callback(interaction: discord.Interaction):
            await interaction.response.defer()
            self.position = select.values[0]

        select.callback = callback
        return select

    # ── 서버명 Select ──
    def make_server_name_select(self):
        select = discord.ui.Select(
            placeholder="서버명 선택",
            options=[discord.SelectOption(label=k, value=k) for k in SERVER_MAP],
            row=1
        )

        async def callback(interaction: discord.Interaction):
            await interaction.response.defer()

            self.server_name = select.values[0]
            self.server_channel = None

            # 기존 서버채널 제거
            if self.server_channel_select:
                self.remove_item(self.server_channel_select)

            # ⚠️ 다음 버튼 제거 (row 순서 보장)
            self.remove_item(self.next_button)

            # 서버채널 추가 (row=2)
            self.server_channel_select = self.make_server_channel_select()
            self.add_item(self.server_channel_select)

            # 다음 버튼 재추가 (row=3)
            self.add_item(self.next_button)

            try:
                await interaction.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass

        select.callback = callback
        return select

    # ── 서버채널 Select ──
    def make_server_c
