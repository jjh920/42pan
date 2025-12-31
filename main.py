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

# ───────────────── 서버 목록 (단일 구조) ─────────────────
SERVER_LIST = [
    "엘드리히1",
    "엘드리히2",
    "로웨인",
    "아퀼라",
    "마레크",
    "모리안",
    "칼리온"
]

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

    if not hasattr(client, "signup_task") or client.signup_task.done():
        client.signup_task = client.loop.create_task(refresh_signup_button())
        print("🔁 refresh_signup_button started")

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
        label="* 제발!! * 닉네임만 입력해주세요",
        placeholder="예) 싸이판",
        max_length=20,
        required=True
    )

    def __init__(self, position, server_name):
        super().__init__()
        self.position = position
        self.server_name = server_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            guild = interaction.guild
            member = interaction.user

            # 닉네임 설정
            await member.edit(
                nick=f"{self.server_name}/{self.nickname}"
            )

            # 역할 부여
            roles = []
            for name in (self.server_name, self.position):
                role = find_role(guild, name)
                if role:
                    roles.append(role)

            if roles:
                await member.add_roles(*roles)

            join_role = find_role(guild, "가입자")
            if join_role:
                await member.remove_roles(join_role)

            welcome_channel = find_channel(guild, WELCOME_CHANNEL_NAME)

            embed = discord.Embed(
                title="✅ 가입이 완료되었습니다!",
                description=(
                    "# 환영합니다!\n\n"
                    "# 아래 버튼을 눌러\n"
                    "# 👇환영 채널로 이동해주세요."
                ),
                color=discord.Color.green()
            )

            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(
                embed=embed,
                view=DoneView(welcome_channel),
                ephemeral=True
            )

            await welcome_channel.send(
                f"✅ {member.mention} 님 가입을 환영합니다! 닉네임 변경 시 운영진 및 관리자에게 문의하세요!"
            )

        except Exception as e:
            print("❌ NicknameModal error:", e)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "처리 중 오류가 발생했습니다. 운영진에게 문의해주세요.",
                    ephemeral=True
                )

# ───────────────── 가입 View ─────────────────
class SignupView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.position = None
        self.server_name = None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "본인만 진행할 수 있습니다.",
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
            discord.SelectOption(
                label="관리자 (선택 X)",
                description="서버관리자에게 문의하세요 (링꼬)"
            )
        ],
        row=0
    )
    async def select_position(self, interaction, select):
        self.position = select.values[0]
        for opt in self.select_position.options:
            opt.default = (opt.label == self.position)
        await interaction.response.defer()

    # 서버 선택
    @discord.ui.select(
        placeholder="서버 선택",
        options=[discord.SelectOption(label=s) for s in SERVER_LIST],
        row=1
    )
    async def select_server(self, interaction, select):
        self.server_name = select.values[0]
        for opt in self.select_server.options:
            opt.default = (opt.label == self.server_name)
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="다음 (닉네임 입력)", style=discord.ButtonStyle.green, row=2)
    async def next_button(self, interaction, button):
        if not all([self.position, self.server_name]):
            await interaction.response.send_message(
                "직책과 서버를 모두 선택해주세요.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            NicknameModal(self.position, self.server_name)
        )

# ───────────────── 시작 버튼 ─────────────────
class StartSignupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="가입하기", style=discord.ButtonStyle.green)
    async def start(self, interaction, button):
        await interaction.response.send_message(
            "직책 → 서버 → 닉네임 순서로 진행하세요.",
            view=SignupView(interaction.user.id),
            ephemeral=True
        )

# ───────────────── 자동 갱신 ─────────────────
async def refresh_signup_button():
    await client.wait_until_ready()
    guild = client.get_guild(GUILD_ID)

    while not client.is_closed():
        try:
            channel = find_channel(guild, SIGNUP_CHANNEL_NAME)
            if not channel:
                await asyncio.sleep(300)
                continue

            async for msg in channel.history(limit=10):
                if (
                    msg.author == client.user
                    and msg.embeds
                    and msg.embeds[0].title == "▶️ 서버 가입 안내"
                ):
                    await msg.delete()

            embed = discord.Embed(
                title="▶️ 서버 가입 안내",
                description="아래 버튼을 눌러 가입하세요.",
                color=discord.Color.blurple()
            )
            await channel.send(embed=embed, view=StartSignupView())

        except Exception as e:
            print("❌ refresh_signup_button error:", e)

        await asyncio.sleep(300)

# ───────────────── 실행 ─────────────────
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN 환경변수가 없습니다.")
    keep_alive()
    client.run(token)
