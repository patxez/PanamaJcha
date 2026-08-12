# เครดิต
# By.ivzex
# By.patxez
# DEV.manpop79
# DEV.Fugus1234
# ฝากติดตามRoblox พวกผมด้วยนะค้าบ
# นำไปขายต่อได้ ให้เครดิตพวกผมด้วยนะค้าบ❤️
import os
import asyncio
import json
import re
import sqlite3
import requests
import discord
import uvicorn
from discord.ext import commands
from discord import app_commands
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

# =========================
# CONFIGURATION
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
PORT = int(os.getenv("PORT", 8888))
DB_PATH = os.getenv("DB_PATH", "database.db")
SETTINGS_PATH = os.getenv("SETTINGS_PATH", "settings.json")

DEFAULT_SETTINGS = {
    "roblox_group_id": 226834839,
    "roblox_group_url": "https://www.roblox.com/groups/226834839",
    "roblox_map_url": "https://www.roblox.com/th/games/78189317414125/By",
    "verified_role_id": 1479443343367995579,
    "developer_role_id": 1479469155399766129,
    "ticket_role_id": 1508479215908028544,
    "role_ids": {
        "or": 1479699133001629797,
        "of_low": 1479699314078122094,
        "of_high": 1479699471603470432,
        "guest": None,
    },
    "rank_prefixes": {
        "or-1": "OR-1, PC",
        "or-2": "OR-2, PEC",
        "or-3": "OR-3, CPL",
        "or-4": "OR-4, SGT",
        "or-5": "OR-5, SSG",
        "or-6": "OR-6/OR-7, SFC",
        "or-7": "OR-6/OR-7, SFC",
        "or-8": "OR-8/OR-9, MSG",
        "or-9": "OR-8/OR-9, MSG",
        "of-1a": "OF-1A, LTP",
        "of-1b": "OF-1B, 1LT",
        "of-2": "OF-2, CPT",
        "of-3": "OF-3, MAJ",
        "of-4": "OF-4, LTC",
        "of-5": "OF-5, COL",
        "of-6": "OF-6, SRCOL",
        "of-7": "OF-7, PMG",
        "of-8": "OF-8, MG",
        "of-9": "OF-9, GEN",
    },
}

DEVELOPER_IDS = [5711452462]
VERIFIED_EMOJI = "✅"


def _deep_copy_default_settings():
    return json.loads(json.dumps(DEFAULT_SETTINGS))


def load_settings():
    settings = _deep_copy_default_settings()
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as file:
            saved = json.load(file)
        if isinstance(saved, dict):
            for key, value in saved.items():
                if key == "role_ids" and isinstance(value, dict):
                    settings["role_ids"].update(value)
                elif key == "rank_prefixes" and isinstance(value, dict):
                    settings["rank_prefixes"].update(value)
                else:
                    settings[key] = value
    except FileNotFoundError:
        save_settings(settings)
    except (json.JSONDecodeError, OSError) as error:
        print(f"Settings load error: {error}")
    return settings


def save_settings(settings):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as file:
            json.dump(settings, file, ensure_ascii=False, indent=2)
    except OSError as error:
        print(f"Settings save error: {error}")


def parse_id(value):
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def get_role_id(settings, role_type):
    if role_type in {"verified", "developer", "ticket"}:
        return settings.get(f"{role_type}_role_id")
    return settings.get("role_ids", {}).get(role_type)


# =========================
# DATABASE
# =========================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            discord_id TEXT PRIMARY KEY,
            roblox_id TEXT,
            roblox_username TEXT,
            verified INTEGER DEFAULT 0,
            pending_roblox_username TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            channel_id TEXT PRIMARY KEY,
            user_id TEXT,
            category TEXT,
            status TEXT DEFAULT 'open'
        )
        """
    )
    conn.commit()
    conn.close()


def get_user(discord_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM users WHERE discord_id = ?", (str(discord_id),)
    ).fetchone()
    conn.close()
    return row


def update_pending(discord_id, username):
    conn = sqlite3.connect(DB_PATH)
    clean_name = str(username).strip().lower()
    conn.execute(
        """
        INSERT INTO users (discord_id, pending_roblox_username, verified)
        VALUES (?, ?, 0)
        ON CONFLICT(discord_id) DO UPDATE SET
            pending_roblox_username = excluded.pending_roblox_username,
            verified = 0
        """,
        (str(discord_id), clean_name),
    )
    conn.commit()
    conn.close()


# =========================
# BOT SETUP
# =========================
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(VerifyView())
        self.add_view(ReVerifyView())
        self.add_view(TicketPanelView())
        await self.tree.sync()
        print(f"Dev System v6 slash commands synced for {self.user}")


bot = MyBot()


def get_roblox_id_by_name(username):
    try:
        response = requests.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [username], "excludeBannedUsers": True},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("data"):
            return data["data"][0]["id"]
    except (requests.RequestException, ValueError) as error:
        print(f"Error fetching Roblox ID: {error}")
    return None


def check_group_membership(roblox_id):
    settings = load_settings()
    try:
        response = requests.get(
            f"https://groups.roblox.com/v1/users/{roblox_id}/groups/roles",
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        for group in data.get("data", []):
            if group["group"]["id"] == int(settings["roblox_group_id"]):
                return True, group["role"]["rank"], group["role"]["name"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        print(f"Error checking group membership: {error}")
    return False, 0, None


def get_prefix_for_rank(rank_val, rank_name, settings):
    prefixes = settings.get("rank_prefixes", {})
    normalized_name = str(rank_name or "").strip().lower()

    for rank_key, prefix in prefixes.items():
        if str(rank_key).strip().lower() in normalized_name:
            return str(prefix).strip()

    numeric_fallback = {
        1: "OR-1, PC", 2: "OR-2, PEC", 3: "OR-3, CPL", 4: "OR-4, SGT",
        5: "OR-5, SSG", 6: "OR-6/OR-7, SFC", 7: "OR-6/OR-7, SFC",
        8: "OF-1A, LTP", 9: "OF-1B, 1LT", 10: "OF-2, CPT", 11: "OF-2, CPT",
        12: "OF-3, MAJ", 13: "OF-4, LTC", 14: "OF-5, COL", 15: "OF-6, SRCOL",
        16: "OF-7, PMG", 17: "OF-8, MG", 18: "OF-9, GEN",
    }
    return numeric_fallback.get(int(rank_val or 0), "")


async def update_member_status(discord_id, roblox_id, roblox_username, guild_id=None):
    settings = load_settings()
    guild = bot.get_guild(int(guild_id)) if guild_id else None
    if guild is None and bot.guilds:
        guild = bot.guilds[0]
    if guild is None:
        return None, None, None

    try:
        member = await guild.fetch_member(int(discord_id))
        is_in_group, rank_val, rank_name = check_group_membership(roblox_id)
        is_dev = int(roblox_id) in DEVELOPER_IDS

        role_ids_to_manage = {
            parse_id(settings.get("verified_role_id")),
            parse_id(settings.get("developer_role_id")),
            parse_id(settings.get("ticket_role_id")),
            *{
                parse_id(role_id)
                for role_id in settings.get("role_ids", {}).values()
            },
        }
        role_ids_to_manage.discard(None)

        roles_to_add = [
            role for role in member.roles
            if role != guild.default_role and role.id not in role_ids_to_manage
        ]
        verified_role = guild.get_role(parse_id(settings.get("verified_role_id")))
        if verified_role:
            roles_to_add.append(verified_role)

        if is_dev:
            developer_role = guild.get_role(parse_id(settings.get("developer_role_id")))
            if developer_role:
                roles_to_add.append(developer_role)
            nickname = f"Dev | {roblox_username}"
            display_rank_name = "Developer"
        elif is_in_group:
            if 1 <= rank_val <= 7:
                rank_role = guild.get_role(parse_id(settings["role_ids"].get("or")))
            elif 8 <= rank_val <= 11:
                rank_role = guild.get_role(parse_id(settings["role_ids"].get("of_low")))
            elif 12 <= rank_val <= 18:
                rank_role = guild.get_role(parse_id(settings["role_ids"].get("of_high")))
            else:
                rank_role = None

            if rank_role:
                roles_to_add.append(rank_role)
            prefix = get_prefix_for_rank(rank_val, rank_name, settings)
            nickname = f"{prefix} | {roblox_username}" if prefix else roblox_username
            display_rank_name = rank_name or "ไม่ทราบชื่อยศ"
        else:
            guest_role = guild.get_role(parse_id(settings["role_ids"].get("guest")))
            if guest_role:
                roles_to_add.append(guest_role)
            nickname = f"Guest | {roblox_username}"
            display_rank_name = "Guest"

        unique_roles = list({role.id: role for role in roles_to_add}.values())
        await member.edit(roles=unique_roles, nick=nickname[:32])
        return rank_val if not is_dev else 999, member.display_name, display_rank_name
    except (discord.HTTPException, ValueError, TypeError) as error:
        print(f"Update Error: {error}")
        return None, None, None


# =========================
# UI COMPONENTS (VERIFY)
# =========================
class VerifyModal(discord.ui.Modal, title="ยืนยันตัวตน Roblox"):
    username = discord.ui.TextInput(
        label="ใส่ชื่อใน Roblox",
        placeholder="พิมพ์ชื่อของคุณที่นี่...",
        min_length=3,
        max_length=20,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        input_name = self.username.value
        roblox_id = get_roblox_id_by_name(input_name)
        if not roblox_id:
            await interaction.response.send_message(
                f"❌ ไม่พบชื่อ Roblox: **{input_name}** กรุณาตรวจสอบการสะกดชื่ออีกครั้ง",
                ephemeral=True,
            )
            return

        is_dev = int(roblox_id) in DEVELOPER_IDS
        is_in_group, _, _ = check_group_membership(roblox_id)
        settings = load_settings()
        if not is_in_group and not is_dev:
            embed_error = discord.Embed(
                title="❌ กรุณาเข้ากลุ่ม Roblox",
                description=(
                    "คุณยังไม่ได้เข้ากลุ่มของเรา! บอทได้ส่งลิงก์กลุ่มไปให้คุณทาง DM แล้วครับ\n\n"
                    f"**ลิงก์กลุ่ม:** [คลิกที่นี่เพื่อเข้ากลุ่ม]({settings['roblox_group_url']})"
                ),
                color=0xFF0000,
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            try:
                await interaction.user.send(
                    "สวัสดีครับ! กรุณาเข้ากลุ่ม Roblox ของเราก่อนยืนยันตัวตนนะครับ: "
                    f"{settings['roblox_group_url']}"
                )
            except discord.HTTPException:
                pass
            return

        update_pending(interaction.user.id, input_name)
        embed_success = discord.Embed(
            title="กรุณาเข้าแมพเพื่อยืนยันตัวตน", color=0x00FF00
        )
        embed_success.add_field(name="Username", value=f"**{input_name}**", inline=False)
        embed_success.add_field(
            name="Map", value=f"[คลิกที่นี่เพื่อเข้าเกม]({settings['roblox_map_url']})", inline=False
        )
        embed_success.set_footer(text="กรุณาเข้าเกมเพื่อให้ระบบยืนยันอัตโนมัติ")
        await interaction.response.send_message(embed=embed_success, ephemeral=True)


class ReVerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="อัพเดทยศ", style=discord.ButtonStyle.success, custom_id="update_rank")
    async def update_rank(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_row = get_user(interaction.user.id)
        if not user_row or not user_row["verified"] or not user_row["roblox_id"]:
            await interaction.response.send_message(
                "❌ คุณยังไม่เคยยืนยันตัวตน กรุณายืนยันตัวตนก่อนใช้ปุ่มนี้", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        rank, _, rank_name = await update_member_status(
            interaction.user.id, user_row["roblox_id"], user_row["roblox_username"], interaction.guild_id
        )
        if rank is not None:
            await interaction.followup.send(
                f"✅ อัพเดทยศสำเร็จ! ยศปัจจุบัน: **{rank_name}**", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ ไม่สามารถอัพเดทยศได้ กรุณาติดต่อแอดมินหรือลองใหม่อีกครั้ง", ephemeral=True
            )

    @discord.ui.button(label="ยืนยันตัวตน", style=discord.ButtonStyle.primary, custom_id="start_verify")
    async def start_verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VerifyModal())


class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ยืนยันตัวตน", style=discord.ButtonStyle.success, custom_id="verify_button_main")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VerifyModal())


# =========================
# TICKET SYSTEM COMPONENTS
# =========================
class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="แจ้งโปร",
                description="ใช้แจ้งคนใช้โปรแกรมช่วยเล่นหรือกระทำผิด",
                emoji="🚨",
                value="report_cheat"
            ),
            discord.SelectOption(
                label="แจ้งยศไม่เข้า",
                description="ใช้แจ้งปัญหากรณีศในเกมกับในดิสไม่ตรงกัน",
                emoji="⚠️",
                value="rank_issue"
            ),
            discord.SelectOption(
                label="ติดต่อแอดมินทั่วไป",
                description="สอบถามแอดมินเกี่ยวกับปัญหาทั่วไป",
                emoji="💬",
                value="general_admin"
            ),
            discord.SelectOption(
                label="ติดต่อส่งเอกสาร",
                description="ใช้สำหรับติดต่อส่งเอกสารต่างๆ แก่ทีมงาน",
                emoji="📄",
                value="submit_doc"
            ),
            discord.SelectOption(
                label="ติดต่อรับรางวัล",
                description="ใช้สำหรับติดต่อรับรางวัลจากตู้สุ่มของ",
                emoji="🎁",
                value="claim_reward"
            ),
        ]
        super().__init__(
            placeholder="เลือกหัวข้อที่ต้องการติดต่อ",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_category_select"
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return

        settings = load_settings()
        ticket_role_id = parse_id(settings.get("ticket_role_id", 1508479215908028544))
        
        category_name_map = {
            "report_cheat": "แจ้งโปร",
            "rank_issue": "แจ้งยศไม่เข้า",
            "general_admin": "ติดต่อแอดมิน",
            "submit_doc": "ส่งเอกสาร",
            "claim_reward": "รับรางวัล"
        }
        
        cat_key = self.values[0]
        cat_display = category_name_map.get(cat_key, "general")
        channel_name = f"ticket-{cat_display}-{interaction.user.name}".lower()

        # สร้าง Overwrites สำหรับช่อง Ticket
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }

        if ticket_role_id:
            role = guild.get_role(ticket_role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                topic=f"Ticket เปิดโดย {interaction.user} (ID: {interaction.user.id}) หมวดหมู่: {cat_display}"
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาดในการสร้างช่อง Ticket: {e}", ephemeral=True)
            return

        # บันทึกลง Database
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO tickets (channel_id, user_id, category, status) VALUES (?, ?, ?, 'open')",
            (str(ticket_channel.id), str(interaction.user.id), cat_display)
        )
        conn.commit()
        conn.close()

        # ส่งข้อความต้อนรับและแท็กเจ้าหน้าที่
        tag_mention = f"<@&{ticket_role_id}>" if ticket_role_id else "@here"
        embed = discord.Embed(
            title=f"🎫 Ticket: {cat_display}",
            description=(
                f"สวัสดีคุณ {interaction.user.mention}\n"
                f"คุณได้เปิด Ticket ในหมวดหมู่: **{cat_display}**\n\n"
                "กรุณาระบุรายละเอียดปัญหาหรือส่งหลักฐานให้เจ้าหน้าที่ทราบได้เลยครับ\n"
                "แอดมินจะทำการตรวจสอบและติดต่อกลับโดยเร็วที่สุด\n\n"
                "💡 *พิมพ์ `/ปิดช่อง` เพื่อปิด Ticket นี้*"
            ),
            color=0x3498DB
        )
        embed.set_footer(text="ระบบ Ticket อัตโนมัติ")

        await ticket_channel.send(content=f"{tag_mention} {interaction.user.mention}", embed=embed)
        await interaction.response.send_message(f"✅ เปิด Ticket ให้คุณแล้วที่: {ticket_channel.mention}", ephemeral=True)


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# =========================
# MODALS (CUSTOMIZE)
# =========================
class CustomizeAllModal(discord.ui.Modal, title="ปรับแต่งระบบทั้งหมด"):
    group_id = discord.ui.TextInput(
        label="Roblox Group ID", placeholder="เช่น 226834839", required=True
    )
    verified_role = discord.ui.TextInput(
        label="Verified Role ID", placeholder="เช่น 1479443343367995579", required=True
    )
    ticket_role = discord.ui.TextInput(
        label="Ticket Admin/Staff Role ID", placeholder="เช่น 1508479215908028544", required=True
    )
    group_url = discord.ui.TextInput(
        label="Roblox Group URL", placeholder="https://www.roblox.com/groups/...", required=True
    )
    map_url = discord.ui.TextInput(
        label="Roblox Map URL", placeholder="https://www.roblox.com/th/games/...", required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        settings = load_settings()
        try:
            settings["roblox_group_id"] = int(self.group_id.value.strip())
            settings["verified_role_id"] = int(self.verified_role.value.strip())
            settings["ticket_role_id"] = int(self.ticket_role.value.strip())
            settings["roblox_group_url"] = self.group_url.value.strip()
            settings["roblox_map_url"] = self.map_url.value.strip()
            save_settings(settings)
            await interaction.response.send_message("✅ บันทึกการตั้งค่าทั้งหมดเรียบร้อยแล้ว", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ ID ต้องเป็นตัวเลขเท่านั้น", ephemeral=True)


# =========================
# SLASH COMMANDS
# =========================
@bot.tree.command(name="ยืนยันตัวตน", description="ตั้งค่าระบบยืนยันตัวตน (Administrator Only)")
@app_commands.default_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="ระบบยืนยันตัวตนทหารไทย",
        description="กรุณากดปุ่มด้านล่างเพื่อเริ่มการยืนยันตัวตนกับ Roblox",
        color=0x2B2D31,
    )
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message("✅ ตั้งค่าระบบยืนยันตัวตนเรียบร้อยแล้ว", ephemeral=True)


@bot.tree.command(name="ตั้งค่าทิกเก็ต", description="ส่งแผงควบคุมระบบ Ticket (Administrator Only)")
@app_commands.default_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📬 ระบบติดต่อทีมงาน (Ticket)",
        description=(
            "กรุณาเลือกหัวข้อ/หมวดหมู่ที่คุณต้องการติดต่อจากเมนูด้านล่างนี้\n\n"
            "🚨 **แจ้งโปร:** แจ้งผู้เล่นใช้โปรแกรมช่วยเล่น\n"
            "⚠️ **แจ้งยศไม่เข้า:** แก้ไขปัญหายศในเกมกับดิสไม่ตรงกัน\n"
            "💬 **ติดต่อแอดมินทั่วไป:** สอบถามปัญหาทั่วไป\n"
            "📄 **ติดต่อส่งเอกสาร:** ส่งเอกสารให้ทีมงาน\n"
            "🎁 **ติดต่อรับรางวัล:** รับรางวัลจากตู้สุ่ม"
        ),
        color=0x2B2D31
    )
    embed.set_footer(text="ระบบ Ticket อัตโนมัติ")
    await interaction.channel.send(embed=embed, view=TicketPanelView())
    await interaction.response.send_message("✅ ส่งแผงควบคุม Ticket เรียบร้อยแล้ว", ephemeral=True)


@bot.tree.command(name="ปิดช่อง", description="ปิด Ticket ปัจจุบันและอนุญาตให้อดูประวัติย้อนหลังได้ (Admin Only)")
@app_commands.default_permissions(administrator=True)
async def close_ticket(interaction: discord.Interaction):
    channel = interaction.channel
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM tickets WHERE channel_id = ?", (str(channel.id),)).fetchone()
    
    if not row:
        conn.close()
        await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในช่อง Ticket เท่านั้น", ephemeral=True)
        return

    conn.execute("UPDATE tickets SET status = 'closed' WHERE channel_id = ?", (str(channel.id),))
    conn.commit()
    conn.close()

    user_id = int(row["user_id"])
    guild = interaction.guild
    member = guild.get_member(user_id)

    await interaction.response.send_message("🔒 กำลังปิด Ticket และอัปเดตสิทธิ์การเข้าถึง...")

    # ปรับสิทธิ์: ปิดการส่งข้อความของผู้ใช้ แต่ยังให้ดูประวัติย้อนหลังได้ (Read History = True, Send Messages = False)
    if member:
        try:
            await channel.set_permissions(member, send_messages=False, read_message_history=True, view_channel=True)
        except discord.HTTPException:
            pass

    embed_closed = discord.Embed(
        title="🔒 Ticket ถูกปิดแล้ว",
        description=f"Ticket นี้ถูกปิดโดย {interaction.user.mention}\nคุณยังสามารถดูประวัติการสนทนาย้อนหลังได้ แต่ไม่สามารถพิมพ์ข้อความเพิ่มได้แล้ว",
        color=0xE74C3C
    )
    embed_closed.set_footer(text="ประวัติ Ticket ถูกบันทึกไว้เรียบร้อย")
    await channel.send(embed=embed_closed)


async def clear_verification_data(interaction: discord.Interaction):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM users")
    conn.commit()
    conn.close()
    await interaction.response.send_message(
        "⚠️ [Admin] ล้างข้อมูลการยืนยันตัวตนทั้งหมดเรียบร้อยแล้ว ทุกคนต้องยืนยันใหม่!",
        ephemeral=True,
    )


@bot.tree.command(name="ล้างข้อมูล", description="ลบข้อมูลการยืนยันตัวตนทุกคน")
@app_commands.default_permissions(administrator=True)
async def reset_db_short(interaction: discord.Interaction):
    await clear_verification_data(interaction)


@bot.tree.command(name="ล้างข้อมูลทั้งหมด", description="ลบข้อมูลการยืนยันตัวตนทุกคน (คำสั่งเดิม)")
@app_commands.default_permissions(administrator=True)
async def reset_db_legacy(interaction: discord.Interaction):
    await clear_verification_data(interaction)


@bot.tree.command(name="ใส่โรล", description="ตั้งค่า Role ให้กับประเภทที่เลือก")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    ประเภท="verified, developer, ticket, or, of_low, of_high หรือ guest",
    โรล="เลือก Role ที่ต้องการให้ระบบใช้",
)
@app_commands.choices(
    ประเภท=[
        app_commands.Choice(name="ยืนยันตัวตน", value="verified"),
        app_commands.Choice(name="Developer", value="developer"),
        app_commands.Choice(name="Ticket Staff", value="ticket"),
        app_commands.Choice(name="OR", value="or"),
        app_commands.Choice(name="OF Low", value="of_low"),
        app_commands.Choice(name="OF High", value="of_high"),
        app_commands.Choice(name="Guest", value="guest"),
    ]
)
async def set_role(interaction: discord.Interaction, ประเภท: app_commands.Choice[str], โรล: discord.Role):
    settings = load_settings()
    role_type = ประเภท.value
    if role_type in {"verified", "developer", "ticket"}:
        settings[f"{role_type}_role_id"] = โรล.id
    else:
        settings["role_ids"][role_type] = โรล.id
    save_settings(settings)
    await interaction.response.send_message(
        f"✅ ตั้งค่าโรล **{โรล.name}** ให้กับประเภท **{ประเภท.name}** เรียบร้อยแล้ว",
        ephemeral=True,
    )


@bot.tree.command(name="ใส่คำนำหน้า", description="เพิ่มหรือแก้คำนำหน้าตามชื่อยศ Roblox")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    ยศ="รหัสยศ เช่น OF-3 หรือ OR-1 ต้องตรงหรือเป็นส่วนหนึ่งของชื่อยศ Roblox",
    คำนำหน้า="ชื่อคำนำหน้า เช่น MAJ หรือ PC",
)
async def set_prefix(interaction: discord.Interaction, ยศ: str, คำนำหน้า: str):
    rank_code = ยศ.strip()
    title = คำนำหน้า.strip()
    if not rank_code or not title:
        await interaction.response.send_message("❌ กรุณาระบุยศและคำนำหน้าให้ครบ", ephemeral=True)
        return

    settings = load_settings()
    settings["rank_prefixes"][rank_code.lower()] = f"{rank_code}, {title}"
    save_settings(settings)
    await interaction.response.send_message(
        f"✅ เพิ่มคำนำหน้า **{rank_code}, {title}** แล้ว\n"
        "สมาชิกจะเห็นผลเมื่อกดยืนยันใหม่หรือกดปุ่มอัพเดทยศ",
        ephemeral=True,
    )


@bot.tree.command(name="ปรับแต่งทั้งหมด", description="เปิดหน้าต่างปรับแต่งระบบกลุ่ม โรล และคำนำหน้า")
@app_commands.default_permissions(administrator=True)
async def customize_all(interaction: discord.Interaction):
    await interaction.response.send_modal(CustomizeAllModal())


@bot.tree.command(name="ดูการตั้งค่า", description="ดูค่าการตั้งค่าระบบปัจจุบัน (Administrator Only)")
@app_commands.default_permissions(administrator=True)
async def show_settings(interaction: discord.Interaction):
    settings = load_settings()
    role_ids = settings.get("role_ids", {})
    embed = discord.Embed(title="การตั้งค่าระบบปัจจุบัน", color=0x3498DB)
    embed.add_field(name="Group ID", value=str(settings.get("roblox_group_id")), inline=False)
    embed.add_field(name="Verified Role ID", value=str(settings.get("verified_role_id")), inline=False)
    embed.add_field(name="Ticket Role ID", value=str(settings.get("ticket_role_id")), inline=False)
    embed.add_field(
        name="Role IDs",
        value=(
            f"OR: `{role_ids.get('or')}`\n"
            f"OF Low: `{role_ids.get('of_low')}`\n"
            f"OF High: `{role_ids.get('of_high')}`\n"
            f"Guest: `{role_ids.get('guest')}`"
        ),
        inline=False,
    )
    embed.add_field(
        name="คำนำหน้าที่ตั้งไว้",
        value="\n".join(
            f"`{key}` → {value}" for key, value in settings.get("rank_prefixes", {}).items()
        )[:1024]
        or "ยังไม่มี",
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================
# FASTAPI WEBHOOK
# =========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    load_settings()
    asyncio.create_task(bot.start(DISCORD_TOKEN))
    yield
    await bot.close()


app = FastAPI(lifespan=lifespan)


@app.post("/verify")
async def verify_endpoint(request: Request):
    data = await request.json()
    roblox_id = data.get("robloxId")
    roblox_username = str(data.get("robloxUsername", "")).strip()
    guild_id = data.get("guildId")
    search_name = roblox_username.lower()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT discord_id FROM users
        WHERE LOWER(TRIM(pending_roblox_username)) = ?
        ORDER BY rowid DESC LIMIT 1
        """,
        (search_name,),
    ).fetchone()
    conn.close()

    if not row:
        return {
            "ok": False,
            "message": (
                f"ไม่พบชื่อ '{roblox_username}' ในรายการรอ "
                "(กรุณากดปุ่มยืนยันใน Discord ก่อน)"
            ),
        }

    rank, display_name, rank_name = await update_member_status(
        row["discord_id"], roblox_id, roblox_username, guild_id
    )
    if rank is not None:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """
            UPDATE users
            SET roblox_id = ?, roblox_username = ?, verified = 1,
                pending_roblox_username = NULL
            WHERE discord_id = ?
            """,
            (str(roblox_id), roblox_username, row["discord_id"]),
        )
        conn.commit()
        conn.close()
        return {
            "ok": True,
            "discord_username": display_name,
            "current_rank": rank_name,
        }

    return {"ok": False, "message": "บอทไม่มีสิทธิ์เปลี่ยนยศหรือไม่พบเซิร์ฟเวอร์ Discord"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", 
