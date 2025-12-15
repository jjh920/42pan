# main.py
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

# ── 서버명 ↔ 서버 번호 매핑 ─────────────────
SERVER_MAP = {
    "라엘": [5, 8, 9],
    "모리안": [3, 4, 9, 10],
    "엘드리히": [1, 2, 3, 5],
    "마레크": [4, 7],
}

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
    print(f"✅ {len(synced)}개 명령 동기화 완료")
    client.loop.create_task(refresh_signup_button())

@client.event
async def on_member_join(member: discord.Member):
    if member.guild.id != GUILD_ID:
        return
    role = find_role(member.guild, "가입자")
    if role:
        await member.add_roles(role)

# ── 닉네임 입력 모달 ─────────────────────────
class NicknameModal(discord.ui.Modal, title="닉네임 입력"):
    nickname = discord.ui.TextInput(
        label="닉네임만 입력해주세요",
        placeholder="예) 싸이판",
        max_length=32,
        required=True
    )

    def __init__(self, position, server_name, server_number):
        super().__init__()
        self.position = position
        self.server_name = server_name
        self.server_number = server_number

    async def on_submit(self, interaction: discord.Interaction):
        member = interaction.user
        guild = interaction.guild

        new_nick = f"{self.server_name}/{self.server_number}/{self.nickname}"
        try:
            await member.edit(nick=new_nick)
        except Exception:
            pass

        roles = []
        if self.position in ("운영진", "서버관리자"):
            role = find_role(guild, self.position)
            if role:
                roles.append(role)

        server_role = find_role(guild, self.server_name)
        if server_role:
            roles.append(server_role)

        if roles:
            await member.add_roles(*roles)

        join_role = find_role(guild, "가입자")
        if join_role in member.roles:
            await member.remove_roles(join_role)

        welcome_channel = find_channel(guild, WELCOME_CHANNEL_NAME)
        if welcome_channel:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="✅ 가입 완료!",
                    description=f"<#{welcome_channel.id}> 로 이동하세요.",
                    color=discord.Color.green()
                ),
                view=DoneView(welcome_channel),
                ephemeral=True
            )
            await welcome_channel.send(f"🎉 {member.mention} 님 환영합니다!")

# ── 완료 버튼 ──────────────────────────────
class DoneView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        url = f"https://discord.com/channels/{channel.guild.id}/{channel.id}"
        self.add_item(discord.ui.Button(label="환영 채널로 이동", url=url))

# ── 가입 절차 뷰 ───────────────────────────
class SignupView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.position = None
        self.server_name = None
        self.server_number = None

    async def interaction_check(self, interaction):
        return interaction.user.id == self.author_id

    @discord.ui.select(
        placeholder="직위를 선택하세요",
        options=[
            discord.SelectOption(label="길드원"),
            discord.SelectOption(label="운영진"),
            discord.SelectOption(label="서버관리자"),
        ],
        row=0
    )
    async def select_position(self, interaction, select):
        self.position = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="서버 이름 선택",
        options=[discord.SelectOption(label=k) for k in SERVER_MAP.keys()],
        row=1
    )
    async def select_server_name(self, interaction, select):
        self.server_name = select.values[0]
        self.select_server.options = [
            discord.SelectOption(label=f"{i}서버") for i in SERVER_MAP[self.server_name]
        ]
        await interaction.response.edit_message(view=self)

    @discord.ui.select(
        placeholder="서버 선택",
        options=[],
        row=2
    )
    async def select_server(self, interaction, select):
        self.server_number = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="다음 (닉네임 입력)", style=discord.ButtonStyle.green, row=3)
    async def next(self, interaction, button):
        if not all([self.position, self.server_name, self.server_number]):
            await interaction.response.send_message("모든 항목을 선택해주세요.", ephemeral=True)
            return

        await interaction.response.send_modal(
            NicknameModal(self.position, self.server_name, self.server_number)
        )

# ── 시작 버튼 ──────────────────────────────
class StartSignupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="가입하기", style=discord.ButtonStyle.green)
    async def start(self, interaction, button):
        await interaction.response.send_message(
            "가입 절차를 시작합니다.",
            view=SignupView(interaction.user.id),
            ephemeral=True
        )

# ── 관리자 명령 ────────────────────────────
@tree.command(name="가입버튼", guild=GUILD)
async def signup_button(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("관리자 전용입니다.", ephemeral=True)
        return

    embed = discord.Embed(
        title="▶️ 서버 가입 안내",
        description="아래 버튼을 눌러 가입하세요.",
        color=discord.Color.blurple()
    )
    await interaction.channel.send(embed=embed, view=StartSignupView())
    await interaction.response.send_message("가입 버튼 전송 완료", ephemeral=True)

# ── 자동 갱신 ──────────────────────────────
async def refresh_signup_button():
    await client.wait_until_ready()
    guild = client.get_guild(GUILD_ID)
    if not guild:
        return

    while True:
        channel = find_channel(guild, SIGNUP_CHANNEL_NAME)
        if channel:
            async for msg in channel.history(limit=5):
                if msg.author == client.user:
                    await msg.delete()
            embed = discord.Embed(
                title="▶️ 서버 가입 안내",
                description="아래 버튼을 눌러 가입하세요.",
                color=discord.Color.blurple()
            )
            await channel.send(embed=embed, view=StartSignupView())
        await asyncio.sleep(600)

# ── 실행 ───────────────────────────────────
if __name__ == "__main__":
    keep_alive()
    client.run(os.getenv("DISCORD_TOKEN"))
