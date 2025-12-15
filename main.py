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
                "## 환영합니다!\n\n"
                "### 아래 버튼을 눌러\n"
                "### **환영 채널로 이동해주세요** 👇"
            ),
            color=discord.Color.green()
        )

        await interaction.response.send_message(
            embed=embed,
            view=DoneView(welcome_channel),
            ephemeral=True
        )

        await welcome_channel.send(
            f"🎉 {member.mention} 님 환영합니다!\n"
            f"닉네임 변경은 운영진에게 문의해주세요."
        )

# ───────────────── 가입 View ─────────────────
class SignupView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=600)
        self.author_id = author_id

        self.position = None
        self.server_name = None
        self.server_channel = None

        # 직책
        self.position_select = discord.ui.Select(
            placeholder="직책 선택",
            options=[
                discord.SelectOption(label="길드원"),
                discord.SelectOption(label="운영진"),
                discord.SelectOption(label="관리자(서버관리자문의)")
            ],
            row=0
        )

        async def position_cb(interaction):
            await interaction.response.defer()
            self.position = self.position_select.values[0]

        self.position_select.callback = position_cb

        # 서버명
        self.server_name_select = discord.ui.Select(
            placeholder="서버명 선택",
            options=[discord.SelectOption(label=k, value=k) for k in SERVER_MAP],
            row=1
        )

        async def server_name_cb(interaction):
            await interaction.response.defer()
            self.server_name = self.server_name_select.values[0]
            self.server_channel = None

            # 서버채널 옵션 갱신 + 활성화
            self.server_channel_select.options = [
                discord.SelectOption(label=v, value=v)
                for v in SERVER_MAP[self.server_name]
            ]
            self.server_channel_select.disabled = False

            try:
                await interaction.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass

        self.server_name_select.callback = server_name_cb

        # 서버채널 (초기 비활성)
        self.server_channel_select = discord.ui.Select(
            placeholder="서버 채널 선택 (서버명을 먼저 선택하세요)",
            options=[discord.SelectOption(label="서버명을 먼저 선택하세요", value="_")],
            disabled=True,
            row=2
        )

        async def server_channel_cb(interaction):
            await interaction.response.defer()
            self.server_channel = self.server_channel_select.values[0]

        self.server_channel_select.callback = server_channel_cb

        # 다음 버튼
        self.next_button = discord.ui.Button(
            label="다음 (닉네임 입력)",
            style=discord.ButtonStyle.green,
            row=3
        )

        async def next_cb(interaction):
            if not all([self.position, self.server_name, self.server_channel]):
                await interaction.response.send_message(
                    "모든 항목을 선택해주세요.",
                    ephemeral=True
                )
                return

            await interaction.response.send_modal(
                NicknameModal(
                    self.position,
                    self.server_name,
                    self.server_channel
                )
            )

        self.next_button.callback = next_cb

        # 추가 (순서 고정)
        self.add_item(self.position_select)
        self.add_item(self.server_name_select)
        self.add_item(self.server_channel_select)
        self.add_item(self.next_button)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "본인만 진행할 수 있습니다.",
                ephemeral=True
            )
            return False
        return True

# ───────────────── 시작 버튼 ─────────────────
class StartSignupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)

    @discord.ui.button(label="가입하기", style=discord.ButtonStyle.green)
    async def start(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
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

# ───────────────── 자동 갱신 ─────────────────
async def refresh_signup_button():
    await client.wait_until_ready()
    guild = client.get_guild(GUILD_ID)

    async def update():
        channel = find_channel(guild, SIGNUP_CHANNEL_NAME)
        if not channel:
            return

        async for msg in channel.history(limit=10):
            if msg.author == client.user and msg.embeds:
                if msg.embeds[0].title == "▶️ 서버 가입 안내":
                    try:
                        await msg.delete()
                    except discord.NotFound:
                        pass

        embed = discord.Embed(
            title="▶️ 서버 가입 안내",
            description="아래 버튼을 눌러 가입하세요.",
            color=discord.Color.blurple()
        )
        await channel.send(embed=embed, view=StartSignupView())

    await update()
    while True:
        await asyncio.sleep(600)
        await update()

# ───────────────── 실행 ─────────────────
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN 환경변수가 없습니다.")
    keep_alive()
    client.run(token)
