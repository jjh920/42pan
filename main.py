# main.py — 닉네임 확인 버튼 초록색 + 클릭 시 창 닫기 + 세션 무제한 + 10분 자동 갱신 + 자동 재연결 로그 포함
import os
import asyncio
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

    # 🔁 자동 버튼 갱신 루프 시작
    client.loop.create_task(refresh_signup_button())
    print("♻️ 자동 가입버튼 갱신 루프 시작됨")

# ── 연결 끊김 감지 로그 ───────────────────────────
@client.event
async def on_disconnect():
    print("⚠️ Discord 연결 끊김 → 자동 재연결 시도 중...")

# ── 새로 들어온 멤버에게 '가입자' 역할 부여 ─────────────────────────
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

# ── 닉네임 확인 버튼 뷰 ───────────────────────────
class DoneView(discord.ui.View):
    def __init__(self, welcome_channel: discord.TextChannel):
        super().__init__(timeout=None)  # ✅ 세션 무제한
        self.welcome_channel = welcome_channel

    @discord.ui.button(label="닉네임 확인하기", style=discord.ButtonStyle.green)
    async def check_nick(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # ✅ 현재 메시지(가입 완료) 닫기
            await interaction.message.delete()
            # ✅ 새 안내 메시지 표시
            await interaction.response.send_message(
                f"🔎 {self.welcome_channel.mention} 채널로 이동해서 닉네임을 확인해주세요!",
                ephemeral=True
            )
        except discord.errors.NotFound:
            pass

# ── 가입 절차용 뷰/모달 ─────────────────────
class SignupView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=None)  # ✅ 세션 무제한
        self.author_id = author_id
        self.position_value = None
        self.server_value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            try:
                await interaction.response.send_message(
                    "이 가입 절차는 본인만 진행할 수 있어요.", ephemeral=True
                )
            except Exception:
                pass
            return False
        return True

    @discord.ui.select(
        placeholder="당신의 직위를 선택하세요",
        min_values=1, max_values=1,
        options=[
            discord.SelectOption(label="길드원"),
            discord.SelectOption(label="운영진"),
            discord.SelectOption(label="관리자(선택X!서버관리자문의)")
        ],
        row=0
    )
    async def select_position(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.position_value = select.values[0]
        try:
            await interaction.response.defer()
        except Exception:
            pass

    @discord.ui.select(
        placeholder="당신의 서버를 선택하세요",
        min_values=1, max_values=1,
        options=[discord.SelectOption(label=f"{i}서버") for i in range(1, 11)],
        row=1
    )
    async def select_server(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.server_value = select.values[0]
        try:
            await interaction.response.defer()
        except Exception:
            pass

    @discord.ui.button(label="다음 (닉네임 입력)", style=discord.ButtonStyle.primary, row=2)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.position_value or not self.server_value:
            try:
                await interaction.response.send_message(
                    "직위와 서버를 모두 선택해주세요.", ephemeral=True
                )
            except Exception:
                pass
            return
        try:
            await interaction.response.send_modal(NicknameModal(self.position_value, self.server_value))
        except Exception:
            pass

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
        member = (
            interaction.user
            if isinstance(interaction.user, discord.Member)
            else guild.get_member(interaction.user.id)
        )
        if not isinstance(member, discord.Member):
            try:
                await interaction.response.send_message("멤버 정보를 불러올 수 없습니다.", ephemeral=True)
            except Exception:
                pass
            return

        new_nick = f"{self.server_value}/{str(self.nickname)}"
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        roles_to_add = []
        if self.position_value in ("운영진", "서버관리자"):
            pos_role = find_role(guild, self.position_value)
            if pos_role:
                roles_to_add.append(pos_role)
        server_role = find_role(guild, self.server_value)
        if server_role:
            roles_to_add.append(server_role)

        try:
            if roles_to_add:
                await member.add_roles(*roles_to_add, reason="가입 절차 완료 - 역할 부여")
            await member.edit(nick=new_nick, reason="가입 절차 완료 - 닉네임 설정")

            join_role = find_role(guild, "가입자")
            if join_role and join_role in member.roles:
                await member.remove_roles(join_role, reason="가입 절차 완료 - 가입자 제거")
        except Exception:
            pass

        welcome_channel = find_channel(guild, WELCOME_CHANNEL_NAME)
        try:
            if welcome_channel:
                view = DoneView(welcome_channel)
                await interaction.followup.send(
                    "✅가입이 완료되었습니다! \n아래 버튼을 눌러 닉네임을 확인해주세요!",
                    view=view,
                    ephemeral=True
                )
                await welcome_channel.send(
                    f"✅ {member.mention} 님! 환영합니다! 닉네임 변경시 운영진에게 문의하세요!"
                )
            else:
                await interaction.followup.send(
                    "가입이 완료되었습니다! (환영 채널을 찾을 수 없습니다)", ephemeral=True
                )
        except (discord.errors.InteractionResponded, discord.errors.NotFound):
            pass

# ── 가입 버튼 클릭 시 절차 실행 ───────────────────
class StartSignupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # ✅ 세션 무제한

    @discord.ui.button(label="가입하기", style=discord.ButtonStyle.green)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            view = SignupView(author_id=interaction.user.id)
            await interaction.followup.send(
                "안녕하세요, 가입봇 42판입니다.\n"
                "아래에서 **직위**와 **서버**를 선택한 뒤 **[다음]** 버튼을 눌러 닉네임을 입력해주세요.",
                view=view,
                ephemeral=True
            )
        except (discord.errors.InteractionResponded, discord.errors.NotFound):
            pass

# ── 관리자용 명령: 가입 버튼 메시지 보내기 ─────────────────────────────
@tree.command(name="가입버튼", description="가입하기 버튼 메시지를 보냅니다.", guild=GUILD)
@app_commands.guild_only()
async def send_signup_button(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        try:
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
        except Exception:
            pass
        return

    try:
        await interaction.response.send_message("✅ 가입 버튼 메시지를 전송했습니다.", ephemeral=True)
        embed = discord.Embed(
            title="▶️ 서버 가입 절차 안내",
            description="아래 **[가입하기]** 버튼을 눌러 가입 절차를 시작하세요!",
            color=discord.Color.blurple()
        )
        await interaction.channel.send(embed=embed, view=StartSignupView())
    except (discord.errors.InteractionResponded, discord.errors.NotFound):
        pass

# ── 🔁 자동으로 10분마다 가입 버튼 메시지 갱신 ─────────────────────────
async def refresh_signup_button():
    await client.wait_until_ready()
    while not client.is_closed():
        guild = client.get_guild(GUILD_ID)
        if guild:
            channel = find_channel(guild, SIGNUP_CHANNEL_NAME)
            if channel:
                embed = discord.Embed(
                    title="▶️ 서버 가입 절차 안내",
                    description="아래 **[가입하기]** 버튼을 눌러 가입 절차를 시작하세요!",
                    color=discord.Color.blurple()
                )
                try:
                    async for msg in channel.history(limit=10):
                        if msg.author == client.user and msg.embeds:
                            if msg.embeds[0].title == "▶️ 서버 가입 절차 안내":
                                await msg.delete()
                    await channel.send(embed=embed, view=StartSignupView())
                    print("♻️ 가입 버튼 갱신됨 (이전 메시지 삭제 후 재등록)")
                except Exception as e:
                    print(f"⚠️ 자동 갱신 실패: {e}")
        await asyncio.sleep(600)

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
