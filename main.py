# ================================================================
# บอท Discord ยืนยันตัวตนแบบไฟล์เดียว
#
# วิธีใช้แบบสั้น:
# 1) ติดตั้งไลบรารี: pip install -U discord.py
# 2) แก้ค่าตรงส่วน "ตั้งค่าตรงนี้" ด้านล่าง โดยเฉพาะ TOKEN
# 3) รันไฟล์นี้: python บอทดิสคอร์ดยืนยันตัวตน.py
# 4) ในเซิร์ฟเวอร์ ใช้คำสั่ง !setup เพื่อสร้างปุ่มยืนยันตัวตน
#
# หมายเหตุ: ห้ามเผยแพร่ TOKEN ของบอทให้ผู้อื่นเห็น
# ================================================================

import asyncio
import re
import secrets
import sqlite3
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands


# ================================================================
# ตั้งค่าตรงนี้
# ================================================================

# ใส่ Bot Token ที่คัดลอกจาก Discord Developer Portal ระหว่างเครื่องหมาย " "
TOKEN = "MTUzNTI4MDI4NjY4ODg3MDUzNA.G-Aloa.Hh-lE0kJsRpMuFLpaenL_BsfwS9IzwUfW5lJRc"

# ใส่ Role ID ที่ต้องการให้สมาชิกได้รับหลังยืนยันสำเร็จ
# ค่าเริ่มต้นนี้คือ Role ID ที่คุณส่งมา
ROLE_ID = 1508479215908028543

# ใส่ Category ID ที่ต้องการให้บอทสร้างห้องยืนยันไว้ข้างใน
# ถ้าไม่ต้องการใช้ Category ให้ใส่ 0
CATEGORY_ID = 0

# ใส่ Channel ID ของห้องแอดมินที่ต้องการรับ Log การยืนยันตัวตน
# ถ้าไม่ใช้ Log ให้ใส่ 0
LOG_CHANNEL_ID = 1535263918929223700

# ชื่อไฟล์ฐานข้อมูล ไม่ต้องแก้ก็ได้
DATABASE_FILE = "verification_data.sqlite3"

# จำนวนตัวอักษรของคีย์ที่บอทจะสุ่มให้แต่ละครั้ง
KEY_LENGTH = 12


# ตรวจสอบว่าผู้ใช้ใส่ Token แล้วหรือยัง
if not TOKEN or TOKEN == "ใส่โทเคนบอทตรงนี้":
    raise RuntimeError(
        "ยังไม่ได้ใส่ TOKEN กรุณาเปิดไฟล์นี้ แล้วแก้ TOKEN = \"...\" ตรงส่วนตั้งค่า"
    )


# เปิดสิทธิ์พื้นฐานที่บอทต้องใช้
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
# จำเป็นสำหรับการอ่านคำสั่งข้อความ เช่น !setup
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ================================================================
# ส่วนจัดการฐานข้อมูลคีย์
# ================================================================

def connect_database():
    """เปิดฐานข้อมูล SQLite ซึ่งจะถูกสร้างอัตโนมัติในโฟลเดอร์เดียวกับไฟล์นี้"""
    database = sqlite3.connect(DATABASE_FILE)
    database.row_factory = sqlite3.Row
    return database


def prepare_database():
    """สร้างตารางเก็บข้อมูล ถ้ายังไม่มี"""
    with connect_database() as database:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS verification_sessions (
                user_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                display_name TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'EN',
                verify_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                verified INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # รองรับฐานข้อมูลเดิมที่สร้างจากไฟล์เวอร์ชันก่อนหน้า
        try:
            database.execute("ALTER TABLE verification_sessions ADD COLUMN language TEXT NOT NULL DEFAULT 'EN'")
        except sqlite3.OperationalError:
            pass
        database.commit()


def create_unique_key():
    """สุ่มคีย์ใหม่และตรวจสอบไม่ให้ซ้ำกับคีย์เก่า"""
    ตัวอักษรที่ใช้ = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    while True:
        new_key = "".join(secrets.choice(ตัวอักษรที่ใช้) for _ in range(KEY_LENGTH))
        with connect_database() as database:
            found = database.execute(
                "SELECT 1 FROM verification_sessions WHERE verify_key = ?",
                (new_key,),
            ).fetchone()

        if found is None:
            return new_key


def save_verification_session(user_id, guild_id, channel_id, display_name, language, verify_key):
    """บันทึกคีย์ล่าสุดของผู้ใช้คนนี้"""
    with connect_database() as database:
        # ถ้าผู้ใช้เคยเริ่มยืนยันไว้ ให้ลบข้อมูลเก่าก่อนสร้างชุดใหม่
        database.execute(
            "DELETE FROM verification_sessions WHERE user_id = ?", (user_id,)
        )
        database.execute(
            """
            INSERT INTO verification_sessions
            (user_id, guild_id, channel_id, display_name, language, verify_key, created_at, verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                user_id,
                guild_id,
                channel_id,
                display_name,
                language,
                verify_key,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        database.commit()


def find_session_by_key(verify_key):
    """ค้นหาคีย์ที่ยังไม่ถูกใช้"""
    with connect_database() as database:
        return database.execute(
            """
            SELECT * FROM verification_sessions
            WHERE verify_key = ? AND verified = 0
            """,
            (verify_key.upper(),),
        ).fetchone()


def mark_session_as_verified(user_id):
    """ทำเครื่องหมายว่าคีย์นี้ถูกใช้งานแล้ว"""
    with connect_database() as database:
        database.execute(
            "UPDATE verification_sessions SET verified = 1 WHERE user_id = ?",
            (user_id,),
        )
        database.commit()


def clear_verification_by_name(guild_id, display_name):
    """ลบข้อมูลยืนยันของชื่อที่ระบุในเซิร์ฟเวอร์นี้ และคืนจำนวนรายการที่ลบ"""
    normalized_name = " ".join(display_name.strip().split()).casefold()
    with connect_database() as database:
        rows = database.execute(
            "SELECT user_id, display_name, channel_id, verified FROM verification_sessions WHERE guild_id = ?",
            (guild_id,),
        ).fetchall()

        matched_user_ids = [
            row["user_id"]
            for row in rows
            if " ".join(str(row["display_name"]).strip().split()).casefold() == normalized_name
        ]

        if matched_user_ids:
            placeholders = ",".join("?" for _ in matched_user_ids)
            database.execute(
                f"DELETE FROM verification_sessions WHERE guild_id = ? AND user_id IN ({placeholders})",
                (guild_id, *matched_user_ids),
            )
        database.commit()

    return len(matched_user_ids)


def is_name_already_used(display_name):
    """ตรวจว่าชื่อนี้เคยถูกยืนยันสำเร็จโดยสมาชิกคนอื่นหรือไม่

    เปรียบเทียบแบบไม่สนใจตัวพิมพ์เล็ก/ใหญ่และช่องว่างหัวท้าย
    เช่น John, john และ JOHN ถือเป็นชื่อเดียวกัน
    """
    normalized_name = " ".join(display_name.strip().split()).casefold()
    with connect_database() as database:
        rows = database.execute(
            "SELECT display_name FROM verification_sessions WHERE verified = 1"
        ).fetchall()

    return any(
        " ".join(str(row["display_name"]).strip().split()).casefold() == normalized_name
        for row in rows
    )


# คำที่ไม่อนุญาตในชื่อ รวมถึงคำหยาบและคำคาราโอเกะที่มักใช้แทนคำหยาบ
# เพิ่มคำได้เองในรายการนี้ หากต้องการกรองคำเพิ่มเติม
คำต้องห้าม = {
    "fuck", "fucking", "shit", "bitch", "asshole", "bastard", "dick",
    "pussy", "penis", "sex", "porn", "nude", "nigger", "niga",
    "kuy", "kuวย", "hee", "hia", "sat", "satt", "heekuy", "kut",
    "tadz", "taad", "เหี้ย", "ควย", "กู", "มึง", "สัส", "เย็ด",
}


def validate_english_name(name):
    """คืนข้อความผิดพลาด ถ้าชื่อไม่ผ่านกฎ หรือคืน None ถ้าชื่อผ่าน"""
    cleaned = " ".join(name.strip().split())

    # อนุญาตเฉพาะ A-Z, a-z, ตัวเลข, เว้นวรรค, _ และ - เท่านั้น
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{1,23}", cleaned):
        return "Name must use English letters only (A-Z). Numbers, spaces, - and _ are allowed."

    words = set(re.findall(r"[a-z0-9]+", cleaned.lower()))
    if words.intersection(คำต้องห้าม):
        return "This name contains a blocked or inappropriate word. Please choose another name."

    # กันการต่อคำหยาบติดกัน เช่น heekuy หรือ kutheekuy
    lower_name = re.sub(r"[^a-z0-9]", "", cleaned.lower())
    blocked_joined = ("fuck", "shit", "bitch", "asshole", "heekuy", "kutheekuy", "kuy")
    if any(word in lower_name for word in blocked_joined):
        return "This name contains a blocked or inappropriate word. Please choose another name."

    return None


# ================================================================
# ส่วนหน้าต่างกรอกชื่อและปุ่มต่าง ๆ
# ================================================================

async def create_verification(interaction: discord.Interaction, name: str, language: str):
    """สร้างห้องและส่งข้อความ โดยใช้ภาษาที่ผู้ใช้เลือก"""
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server." if language == "EN" else "คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์เท่านั้น",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    name = " ".join(name.strip().split())
    name_error = validate_english_name(name)
    if name_error:
        if language == "TH":
            name_error = "ชื่อต้องเป็นภาษาอังกฤษเท่านั้น และห้ามมีคำหยาบหรือคำคาราโอเกะ กรุณาเปลี่ยนชื่อใหม่"
        await interaction.followup.send(name_error, ephemeral=True)
        return

    # ห้ามใช้ชื่อที่สมาชิกคนอื่นยืนยันสำเร็จไปแล้วซ้ำ
    if is_name_already_used(name):
        duplicate_message = (
            "ชื่อนี้ถูกใช้ยืนยันตัวตนไปแล้ว กรุณาเลือกชื่ออื่น"
            if language == "TH"
            else "This name has already been used for verification. Please choose another name."
        )
        await interaction.followup.send(duplicate_message, ephemeral=True)
        return

    guild = interaction.guild
    member = interaction.user
    verify_key = create_unique_key()
    category = None
    if CATEGORY_ID != 0:
        selected_channel = guild.get_channel(CATEGORY_ID)
        if isinstance(selected_channel, discord.CategoryChannel):
            category = selected_channel

    permission_overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, manage_messages=True),
    }

    try:
        private_channel = await guild.create_text_channel(
            name=make_channel_name(name, member.id),
            category=category,
            overwrites=permission_overwrites,
            topic=f"Verification channel for {member.id}",
            reason="Create verification channel",
        )
    except discord.Forbidden:
        message = "บอทสร้างห้องไม่ได้ กรุณาให้บอทมีสิทธิ์ Manage Channels" if language == "TH" else "I cannot create the private channel. Please give me Manage Channels permission."
        await interaction.followup.send(message, ephemeral=True)
        return

    save_verification_session(member.id, guild.id, private_channel.id, name, language, verify_key)

    if language == "TH":
        await interaction.followup.send(
            f"สร้างห้องส่วนตัวแล้ว: {private_channel.mention}\nคีย์ยืนยันของคุณคือ `{verify_key}`\nห้ามส่งคีย์นี้ให้ผู้อื่น",
            ephemeral=True,
        )
        title = "🔍 ยืนยันตัวตน"
        description = f"ชื่อของคุณ: **{discord.utils.escape_markdown(name)}**\n\nพิมพ์ `/verify` พร้อมคีย์ของคุณ แล้วกดปุ่ม **✅ ยืนยันตัวตน**"
        verify_button = "✅ ยืนยันตัวตน"
    else:
        await interaction.followup.send(
            f"Private verification channel created: {private_channel.mention}\nYour key is `{verify_key}`\nDo not share this key.",
            ephemeral=True,
        )
        title = "🔍 Verify"
        description = f"Your name: **{discord.utils.escape_markdown(name)}**\n\nType `/verify` with your key, then click **✅ Verify**"
        verify_button = "✅ Verify"

    await private_channel.send(
        content=member.mention,
        embed=discord.Embed(title=title, description=description, color=discord.Color.green()),
        view=VerifyInstructionView(member.id, verify_button, language),
    )


class NameModal(discord.ui.Modal, title="Enter your English name"):
    display_name = discord.ui.TextInput(label="English name only", placeholder="Example: John_Smith or User123", min_length=1, max_length=32, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await create_verification(interaction, str(self.display_name), "EN")


class ThaiNameModal(discord.ui.Modal, title="กรอกชื่อภาษาอังกฤษ"):
    display_name = discord.ui.TextInput(label="ชื่อภาษาอังกฤษเท่านั้น", placeholder="ตัวอย่าง: John_Smith หรือ User123", min_length=1, max_length=32, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await create_verification(interaction, str(self.display_name), "TH")


def make_channel_name(name, user_id):
    """ทำชื่อห้องให้ไม่ใส่อักขระที่ Discord ไม่รองรับ"""
    cleaned_name = re.sub(r"[^a-zA-Z0-9ก-๙_-]+", "-", name.lower()).strip("-")
    cleaned_name = cleaned_name[:65] or "user"
    return f"verify-{cleaned_name}-{str(user_id)[-4:]}"


class VerifyInstructionView(discord.ui.View):
    """ปุ่มคำสั่ง verify ในห้องส่วนตัว ให้ข้อความและปุ่มเป็นภาษาที่เลือก"""

    def __init__(self, owner_id, button_text, language):
        super().__init__(timeout=None)
        self.owner_id = owner_id
        self.language = language
        self.add_item(VerifyHelpButton(owner_id, button_text, language))


class VerifyHelpButton(discord.ui.Button):
    def __init__(self, owner_id, button_text, language):
        super().__init__(label=button_text, style=discord.ButtonStyle.success)
        self.owner_id = owner_id
        self.language = language

    async def callback(self, interaction: discord.Interaction):
        message = "พิมพ์ `/verify` แล้วใส่คีย์ที่ได้รับในข้อความส่วนตัว" if self.language == "TH" else "Type `/verify` and enter the key you received privately."
        await interaction.response.send_message(message, ephemeral=True)


class StartVerificationView(discord.ui.View):
    """ปุ่มเริ่มกรอกชื่อ"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔍 Verify",
        style=discord.ButtonStyle.primary,
        custom_id="verification:start",
    )
    async def start_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="🌐 Choose your language / เลือกภาษา",
            description="Select one option below. / กรุณาเลือกภาษาด้านล่าง",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=LanguageView(), ephemeral=True)


class LanguageView(discord.ui.View):
    """เมนูเลือกภาษา โดยตั้งค่าเริ่มต้นของหน้าจอเป็น EN"""

    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="🇬🇧 EN • English", style=discord.ButtonStyle.primary)
    async def english_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NameModal())

    @discord.ui.button(label="🇹🇭 TH • ภาษาไทย", style=discord.ButtonStyle.secondary)
    async def thai_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ThaiNameModal())


class ConfirmVerificationView(discord.ui.View):
    """ปุ่มยืนยันขั้นสุดท้ายและรับโรล"""

    def __init__(self, owner_id, verify_key, language="TH"):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.verify_key = verify_key
        self.language = language
        # เปลี่ยนข้อความปุ่มตามภาษาที่เลือก
        self.children[0].label = "✅ ยืนยันตัวตน" if language == "TH" else "✅ Verify"

    @discord.ui.button(
        label="ยืนยันและรับโรล",
        style=discord.ButtonStyle.success,
    )
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # ป้องกันคนอื่นมากดปุ่มของเจ้าของคีย์
        if interaction.user.id != self.owner_id:
            message = "ปุ่มนี้ใช้ได้เฉพาะเจ้าของคีย์เท่านั้น" if self.language == "TH" else "This button is only for the key owner."
            await interaction.response.send_message(message, ephemeral=True)
            return

        session = find_session_by_key(self.verify_key)
        if session is None or session["user_id"] != interaction.user.id:
            message = "คีย์ไม่ถูกต้อง หมดอายุ หรือถูกใช้ไปแล้ว" if self.language == "TH" else "This key is invalid, expired, or already used."
            await interaction.response.send_message(message, ephemeral=True)
            return

        role = interaction.guild.get_role(ROLE_ID)
        if role is None:
            message = f"ไม่พบโรล ID {ROLE_ID} ในเซิร์ฟเวอร์" if self.language == "TH" else f"Role ID {ROLE_ID} was not found in this server."
            await interaction.response.send_message(message, ephemeral=True)
            return

        try:
            await interaction.user.add_roles(role, reason="ยืนยันตัวตนสำเร็จ")
        except discord.Forbidden:
            message = "บอทมอบโรลไม่ได้ ให้ตรวจสอบ Manage Roles และลำดับโรล" if self.language == "TH" else "I cannot add the role. Check Manage Roles and the bot role hierarchy."
            await interaction.response.send_message(message, ephemeral=True)
            return

        # เปลี่ยนชื่อสมาชิกในเซิร์ฟเวอร์เป็นชื่อภาษาอังกฤษที่กรอกไว้
        try:
            await interaction.user.edit(
                nick=session["display_name"],
                reason="เปลี่ยนชื่อหลังยืนยันตัวตนสำเร็จ",
            )
        except discord.Forbidden:
            # ถ้าบอทไม่มีสิทธิ์ Manage Nicknames ให้ยืนยันต่อได้ แต่ไม่เปลี่ยนชื่อ
            pass

        mark_session_as_verified(interaction.user.id)

        # ส่ง Log ไปยังห้องแอดมินหลังยืนยันสำเร็จ
        if LOG_CHANNEL_ID != 0:
            log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
            if isinstance(log_channel, discord.TextChannel):
                log_embed = discord.Embed(
                    title="✅ ยืนยันตัวตนสำเร็จ",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc),
                )
                log_embed.add_field(name="สมาชิก", value=f"{interaction.user.mention}\n`{interaction.user}`", inline=False)
                log_embed.add_field(name="User ID", value=str(interaction.user.id), inline=True)
                log_embed.add_field(name="ชื่อที่ยืนยัน", value=session["display_name"], inline=True)
                log_embed.add_field(name="โรลที่ได้รับ", value=f"{role.mention} (`{role.id}`)", inline=False)
                log_embed.add_field(name="ภาษา", value="ไทย (TH)" if self.language == "TH" else "English (EN)", inline=True)
                log_embed.add_field(name="ห้องยืนยัน", value=f"`{interaction.channel.name}`", inline=True)
                log_embed.set_footer(text="Verification Log")
                try:
                    await log_channel.send(embed=log_embed)
                except (discord.Forbidden, discord.HTTPException):
                    # ถ้าส่ง Log ไม่ได้ จะไม่ขัดขวางการยืนยันของสมาชิก
                    pass

        button.disabled = True

        success_message = (
            f"ยืนยันตัวตนสำเร็จ คุณได้รับโรล **{role.name}** แล้ว ห้องนี้จะถูกลบใน 3 วินาที"
            if self.language == "TH"
            else f"Verification complete. Role **{role.name}** added and nickname updated to **{session['display_name']}**. This channel will be deleted in 3 seconds."
        )
        await interaction.response.edit_message(content=success_message, view=self)

        # รอให้ผู้ใช้เห็นข้อความสำเร็จสั้น ๆ แล้วลบห้องยืนยัน
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason="ลบห้องหลังยืนยันตัวตนสำเร็จ")
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass


# ================================================================
# คำสั่ง Discord
# ================================================================

@bot.event
async def on_ready():
    prepare_database()
    bot.add_view(StartVerificationView())
    await bot.tree.sync()
    print(f"บอทออนไลน์แล้ว: {bot.user}")
    print("ใช้คำสั่ง !setup ในเซิร์ฟเวอร์เพื่อส่งปุ่มยืนยันตัวตน")


@bot.command(name="setup")
@commands.has_guild_permissions(manage_guild=True)
async def setup_verify(ctx: commands.Context):
    """ใช้ !setup แล้วลบข้อความคำสั่ง ก่อนส่งแผงยืนยันแบบสาธารณะ"""
    try:
        # ลบข้อความ !setup ทันที จึงไม่เหลือชื่อคนสั่งอยู่ด้านบน
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        # ถ้าบอทไม่มี Manage Messages จะลบข้อความไม่ได้ แต่ยังส่งแผงได้
        pass

    embed = discord.Embed(
        title="🔍 ยืนยันตัวตนสมาชิก",
        description="กดปุ่มด้านล่าง แล้วกรอกชื่อเพื่อเริ่มยืนยันตัวตน",
        color=discord.Color.green(),
    )
    await ctx.send(embed=embed, view=StartVerificationView())


@bot.tree.command(
    name="verify",
    description="ตรวจสอบคีย์ยืนยันตัวตน",
)
@app_commands.describe(key="คีย์ที่บอทส่งให้คุณ เช่น ABCD2345XYZ9")
async def verify(interaction: discord.Interaction, key: str):
    key = key.strip().upper()
    session = find_session_by_key(key)

    if session is None:
        await interaction.response.send_message(
            "คีย์ไม่ถูกต้อง หมดอายุ หรือถูกใช้ไปแล้ว",
            ephemeral=True,
        )
        return

    # บังคับให้ใช้คีย์ในห้องของเจ้าของเท่านั้น
    language = session["language"] or "EN"
    if (
        session["user_id"] != interaction.user.id
        or session["channel_id"] != interaction.channel_id
    ):
        message = "คีย์นี้ใช้ได้เฉพาะเจ้าของคีย์และห้องส่วนตัวของเจ้าของเท่านั้น" if language == "TH" else "This key can only be used by its owner in the private verification channel."
        await interaction.response.send_message(message, ephemeral=True)
        return

    message = "ตรวจสอบคีย์ผ่านแล้ว กรุณากดปุ่มด้านล่างเพื่อรับโรล" if language == "TH" else "Key accepted. Click the button below to receive your role."
    await interaction.response.send_message(
        message,
        view=ConfirmVerificationView(interaction.user.id, key, language),
        ephemeral=True,
    )


@bot.tree.command(
    name="clear-verification",
    description="ล้างข้อมูลการยืนยันของชื่อสมาชิก เพื่อให้สามารถใช้ชื่อเดิมยืนยันใหม่ได้",
)
@app_commands.describe(username="ชื่อที่ต้องการล้างข้อมูล เช่น User123")
@app_commands.checks.has_permissions(manage_guild=True)
async def clear_verification(interaction: discord.Interaction, username: str):
    """คำสั่งแอดมินสำหรับล้างข้อมูลชื่อที่ยืนยันไปแล้ว

    Discord ไม่รองรับชื่อ Slash Command ภาษาไทยในทุกกรณี จึงใช้
    /clear-verification แทน และมีคำอธิบายภาษาไทยกำกับไว้
    """
    if interaction.guild is None:
        await interaction.response.send_message("คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    # จำกัดให้ใช้ในห้องแอดมินที่ตั้งไว้เท่านั้น
    if LOG_CHANNEL_ID == 0:
        await interaction.response.send_message(
            "ยังไม่ได้ตั้งค่า LOG_CHANNEL_ID ให้ใส่ Channel ID ของห้องแอดมินในไฟล์บอทก่อน",
            ephemeral=True,
        )
        return

    if interaction.channel_id != LOG_CHANNEL_ID:
        await interaction.response.send_message(
            "คำสั่งนี้ใช้ได้เฉพาะในห้องแอดมินที่ตั้งไว้เท่านั้น",
            ephemeral=True,
        )
        return

    username = " ".join(username.strip().split())
    if not username:
        await interaction.response.send_message("กรุณาใส่ชื่อที่ต้องการล้างข้อมูล", ephemeral=True)
        return

    deleted_count = clear_verification_by_name(interaction.guild.id, username)
    if deleted_count == 0:
        await interaction.response.send_message(
            f"ไม่พบข้อมูลการยืนยันของชื่อ `{username}` ในเซิร์ฟเวอร์นี้",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"ล้างข้อมูลการยืนยันของชื่อ `{username}` แล้ว จำนวน {deleted_count} รายการ ชื่อนี้สามารถนำไปยืนยันใหม่ได้",
        ephemeral=True,
    )


@setup_verify.error
async def setup_verify_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingGuildPermissions):
        await ctx.send("คำสั่งนี้ใช้ได้เฉพาะแอดมินหรือคนที่มีสิทธิ์ Manage Server", delete_after=5)
    else:
        await ctx.send(f"เกิดข้อผิดพลาด: {error}", delete_after=5)


# เริ่มบอท
if __name__ == "__main__":
    bot.run(TOKEN)
