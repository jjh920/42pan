# main.py — 최종 통합 가입봇 (에러 수정 완료)

import os
import asyncio
import datetime
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
    print("♻️ 가입 버튼 자동 갱신 시작")

# ───────────────── 신규 입장 ─────────────────
@client.event
async def on_member_join(member: discord.Member):
    if member.guild.id != GUILD_ID:
        return
    role = find_role(member.guild, "가입자")
    if role:
        await member.add_roles(role, reason="신규 입장")

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

        # 닉네임 설정
        new_nick = f"{self.server_name}/{self.server_channel}/{self.nickname}"
        try:
            await member.edit(nick=new_nick)
        except Exception:
            pass

        roles_to_add = []

        # 1️⃣ 서버명 역할
        r = find_role(guild, self.server_name)
        if r:
            roles_to_add.append(r)

        # 2️⃣ 서버명 + 서버채널 역할
        combined = f"{self.server_name} {self.server_channel}"
        r = find_role(guild, combined)
        if r:
            roles_to_add.append(r)

        # 3️⃣ 직책 역할
        r = find_role(guild, self.position)
        if r:
            roles_to_add.append(r)

        if roles_to_add:
            await member.add_roles(*roles_to_add)

        # 가입자 역할 제거
        join_role = find_role(guild, "가입자")
        if join_role:
            await member.remove_roles(join_role)

        # 완료 메시지
        welcome = find_channel(guild, WELCOME_CHANNEL_NAME)
        embed = discord.Embed(
            title="✅ 가입 완료!",
            description=f"<#{welcome.id}> 채널로 이동해주세요.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(
            embed=embed,
            view=DoneView(welcome),
            ephemeral=True
        )
        await welcome.send(f"🎉 {member.mention} 님 환영합니다!")

# ───────────────── 완료 버튼 ──────────────────
class DoneView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="환영 채널 이동",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/channels/{channel.guild.id}/{channel.id}"
            )
        )

# ───────────────── 가입 뷰 ────────────────────
class SignupView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.position = None
        self.server_name = None
        self.server_channel = None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "이 가입 절차는 본인만 진행할 수 있습니다.",
                ephemeral=True
            )
            return False
        return True

    # 직책 선택
    @discord.ui.select(
        placeholder="직책 선택",
        options=[
            discord.SelectOption(label="길드원"),
            discord.SelectOption(label="운영진"),
            discord.SelectOption(label="서버관리자")
        ],
        row=0
    )
    async def select_position(self, interaction, select):
        self.position = select.values[0]
        await interaction.response.defer()

    # 서버명 선택
    @discord.ui.select(
        placeholder="서버명 선택",
        options=[discord.SelectOption(label=k) for k in SERVER_MAP],
        row=1
    )
    async def select_server_name(self, interaction, select):
        self.server_name = select.values[0]
        self.server_channel_select.options = [
            discord.SelectOption(label=v, value=v)
            for v in SERVER_MAP[self.server_name]
        ]
        await interaction.response.edit_message(view=self)

    # 서버채널 선택 (더미 옵션 필수)
    @discord.ui.select(
        placeholder="서버 채널 선택",
        options=[discord.SelectOption(label="서버명을 먼저 선택하세요", value="__dummy__")],
        row=2
    )
    async def server_channel_select(self, interaction, select):
        if select.values[0] == "__dummy__":
            await interaction.response.send_message(
                "서버명을 먼저 선택해주세요.",
                ephemeral=True
            )
            return
        self.server_channel = select.values[0]
        await interaction.response.defer()

    # 다음 버튼
    @discord.ui.button(label="다음 (닉네임 입력)", style=discord.ButtonStyle.green, row=3)
    async def next_button(self, interaction, button):
        if not all([self.position, self.server_name, self.server_channel]):
            await interaction.response.send_message(
                "모든 항목을 선택해주세요.",
                ephemeral=True
            )
            return
        await interaction.response.send_modal(
            NicknameModal(self.position, self.server_name, self.server_channel)
        )

# ───────────────── 시작 버튼 ──────────────────
class StartSignupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="가입하기", style=discord.ButtonStyle.green)
    async def start(self, interaction, button):
        await interaction.response.send_message(
            "직책 → 서버명 → 서버채널 → 닉네임 순서로 진행하세요.",
            view=SignupView(interaction.user.id),
            ephemeral=True
        )

# ───────────────── 관리자 명령 ─────────────────
@tree.command(name="가입버튼", description="가입 버튼 생성", guild=GUILD)
@app_commands.guild_only()
async def signup_button(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "관리자만 사용할 수 있습니다.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "✅ 가입 버튼을 생성했습니다.",
        ephemeral=True
    )

    embed = discord.Embed(
        title="▶️ 서버 가입 안내",
        description="아래 버튼을 눌러 가입 절차를 시작하세요.",
        color=discord.Color.blurple()
    )
    await interaction.channel.send(embed=embed, view=StartSignupView())

# ───────────────── 자동 갱신 ──────────────────
async def refresh_signup_button():
    await client.wait_until_ready()
    guild = client.get_guild(GUILD_ID)
    if not guild:
        return

    async def update():
        channel = find_channel(guild, SIGNUP_CHANNEL_NAME)
        if not channel:
            return

        async for msg in channel.history(limit=10):
            if msg.author == client.user and msg.embeds:
                if msg.embeds[0].title == "▶️ 서버 가입 안내":
                    await msg.delete()

        embed = discord.Embed(
            title="▶️ 서버 가입 안내",
            description="아래 버튼을 눌러 가입하세요.",
            color=discord.Color.blurple()
        )
        await channel.send(embed=embed, view=StartSignupView())
        print("♻️ 가입 버튼 갱신")

    await update()
    while True:
        await asyncio.sleep(600)
        await update()

# ───────────────── 실행 ──────────────────────
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN 환경변수가 없습니다.")
    keep_alive()
    client.run(token)
