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
import io
import datetime
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
    "transcript_channel_id": None,
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
        # ทำให้ปุ่มที่สร้างไว้ก่อนบอทรีสตาร์ตยังใช้งานได้
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
            *{parse_id(role_id) for role_id in settings.get("role_ids", {}).values()},
        }
        role_ids_to_manage.discard(None)
        roles_to_add = [role for role in member.roles if role != guild.default_role and role.id not in role_ids_to_manage]
        verified_role = guild.get_role(parse_id(settings.get("verified_role_id")))
        if verified_role: roles_to_add.append(verified_role)
        if is_dev:
            developer_role = guild.get_role(parse_id(settings.get("developer_role_id")))
            if developer_role: roles_to_add.append(developer_role)
            nickname = f"Dev | {roblox_username}"
            display_rank_name = "Developer"
        elif is_in_group:
            if 1 <= rank_val <= 7: rank_role = guild.get_role(parse_id(settings["role_ids"].get("or")))
            elif 8 <= rank_val <= 11: rank_role = guild.get_role(parse_id(settings["role_ids"].get("of_low")))
            elif 12 <= rank_val <= 18: rank_role = guild.get_role(parse_id(settings["role_ids"].get("of_high")))
            else: rank_role = None
            if rank_role: roles_to_add.append(rank_role)
            prefix = get_prefix_for_rank(rank_val, rank_name, settings)
            nickname = f"{prefix} | {roblox_username}" if prefix else roblox_username
            display_rank_name = rank_name or "ไม่ทราบชื่อยศ"
        else:
            guest_role = guild.get_role(parse_id(settings["role_ids"].get("guest")))
            if guest_role: roles_to_add.append(guest_role)
            nickname = f"Guest | {roblox_username}"
            display_rank_name = "Guest"
        unique_roles = list({role.id: role for role in roles_to_add}.values())
        await member.edit(roles=unique_roles, nick=nickname[:32])
        return rank_val if not is_dev else 999, member.display_name, display_rank_name
    except (discord.HTTPException, ValueError, TypeError) as error:
        print(f"Update Error: {error}")
        return None, None, None

# =========================
# UI COMPONENTS
# =========================
class VerifyModal(discord.ui.Modal, title="ยืนยันตัวตน Roblox"):
    username = discord.ui.TextInput(label="ใส่ชื่อใน Roblox", placeholder="พิมพ์ชื่อของคุณที่นี่...", min_length=3, max_length=20, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        input_name = self.username.value
        roblox_id = get_roblox_id_by_name(input_name)
        if not roblox_id:
            await interaction.response.send_message(f"❌ ไม่พบชื่อ Roblox: **{input_name}** กรุณาตรวจสอบการสะกดชื่ออีกครั้ง", ephemeral=True)
            return
        is_dev = int(roblox_id) in DEVELOPER_IDS
        is_in_group, _, _ = check_group_membership(roblox_id)
        settings = load_settings()
        if not is_in_group and not is_dev:
            embed_error = discord.Embed(title="❌ กรุณาเข้ากลุ่ม Roblox", description=f"คุณยังไม่ได้เข้ากลุ่มของเรา! [คลิกที่นี่เพื่อเข้ากลุ่ม]({settings['roblox_group_url']})", color=0xFF0000)
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return
        update_pending(interaction.user.id, input_name)
        embed_success = discord.Embed(title="กรุณาเข้าแมพเพื่อยืนยันตัวตน", color=0x00FF00)
        embed_success.add_field(name="Username", value=f"**{input_name}**", inline=False)
        embed_success.add_field(name="Map", value=f"[คลิกที่นี่เพื่อเข้าเกม]({settings['roblox_map_url']})", inline=False)
        await interaction.response.send_message(embed=embed_success, ephemeral=True)

class ReVerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="อัพเดทยศ", style=discord.ButtonStyle.success, custom_id="update_rank")
    async def update_rank(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_row = get_user(interaction.user.id)
        if not user_row or not user_row["verified"]:
            await interaction.response.send_message("❌ คุณยังไม่เคยยืนยันตัวตน กรุณายืนยันตัวตนก่อนใช้ปุ่มนี้", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        rank, _, rank_name = await update_member_status(interaction.user.id, user_row["roblox_id"], user_row["roblox_username"], interaction.guild_id)
        await interaction.followup.send(f"✅ อัพเดทยศสำเร็จ! ยศปัจจุบัน: **{rank_name}**" if rank is not None else "❌ ไม่สามารถอัพเดทยศได้", ephemeral=True)
    @discord.ui.button(label="ยืนยันตัวตน", style=discord.ButtonStyle.primary, custom_id="start_verify")
    async def start_verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VerifyModal())

class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="ยืนยันตัวตน", style=discord.ButtonStyle.success, custom_id="verify_button_main")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VerifyModal())

class CustomizeAllModal(discord.ui.Modal, title="ปรับแต่งระบบทั้งหมด"):
    group_id = discord.ui.TextInput(label="Roblox Group ID", required=True)
    verified_role = discord.ui.TextInput(label="Verified Role ID", required=True)
    group_url = discord.ui.TextInput(label="Roblox Group URL", required=True)
    map_url = discord.ui.TextInput(label="Roblox Map URL", required=True)
    prefixes = discord.ui.TextInput(label="คำนำหน้า (เช่น OF-3=MAJ; OF-4=LTC)", style=discord.TextStyle.paragraph, required=False)
    async def on_submit(self, interaction: discord.Interaction):
        settings = load_settings()
        try:
            settings["roblox_group_id"] = int(self.group_id.value.strip())
            settings["verified_role_id"] = int(self.verified_role.value.strip())
            settings["roblox_group_url"] = self.group_url.value.strip()
            settings["roblox_map_url"] = self.map_url.value.strip()
            if self.prefixes.value.strip():
                for item in self.prefixes.value.split(";"):
                    if "=" in item:
                        code, title = item.split("=", 1)
                        settings["rank_prefixes"][code.strip().lower()] = f"{code.strip()}, {title.strip()}"
            save_settings(settings)
            await interaction.response.send_message("✅ บันทึกการตั้งค่าเรียบร้อยแล้ว", ephemeral=True)
        except: await interaction.response.send_message("❌ ID ต้องเป็นตัวเลขเท่านั้น", ephemeral=True)

# =========================
# TICKET & TRANSCRIPT
# =========================
async def generate_transcript(channel, ticket_user, closed_by, category):
    messages = []
    async for msg in channel.history(limit=None, oldest_first=True): messages.append(msg)
    html = f"<html><head><meta charset='utf-8'><title>Transcript - {channel.name}</title><style>body{{background:#36393f;color:#dcddde;font-family:sans-serif;padding:20px;}}.info{{background:#2f3136;padding:15px;border-radius:8px;margin-bottom:20px;border-left:5px solid #7289da;}}.msg{{display:flex;margin-bottom:15px;}}.av{{width:40px;height:40px;border-radius:50%;margin-right:15px;}}.auth{{font-weight:bold;color:#fff;}}.time{{font-size:0.75rem;color:#72767d;margin-left:10px;}}.txt{{margin-top:5px;white-space:pre-wrap;}}.att{{margin-top:10px;max-width:400px;border-radius:4px;}}</style></head><body><div class='info'><h2>Ticket Transcript</h2><p><b>หมวดหมู่:</b> {category}</p><p><b>ผู้เปิด:</b> {ticket_user}</p><p><b>ผู้ปิด:</b> {closed_by}</p><p><b>วันที่:</b> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p></div>"
    for m in messages:
        if m.author.bot and not m.embeds: continue
        html += f"<div class='msg'><img class='av' src='{m.author.display_avatar.url}'><div><span class='auth'>{m.author.display_name}</span><span class='time'>{m.created_at.strftime('%Y-%m-%d %H:%M')}</span><div class='txt'>{m.clean_content}</div>"
        for att in m.attachments:
            if any(att.filename.lower().endswith(e) for e in ['.png','.jpg','.jpeg','.gif','.webp']): html += f"<img class='att' src='{att.url}'>"
            else: html += f"<div class='txt'><a href='{att.url}' style='color:#00aff4;'>ไฟล์: {att.filename}</a></div>"
        html += "</div></div>"
    return html + "</body></html>"

class TicketSelect(discord.ui.Select):
    def __init__(self):
        opts = [discord.SelectOption(label=l, emoji=e, value=l) for l, e in [("แจ้งโปร","🚨"),("แจ้งยศไม่เข้า","⚠️"),("ติดต่อแอดมิน","💬"),("ส่งเอกสาร","📄"),("รับรางวัล","🎁")]]
        super().__init__(placeholder="เลือกหัวข้อที่ต้องการติดต่อ", options=opts, custom_id="ticket_select_main")
    async def callback(self, it: discord.Interaction):
        s = load_settings(); tid = parse_id(s.get("ticket_role_id", 1508479215908028544))
        name = f"ticket-{self.values[0]}-{it.user.name}".lower(); g = it.guild
        ov = {g.default_role: discord.PermissionOverwrite(view_channel=False), it.user: discord.PermissionOverwrite(view_channel=True, send_messages=True), g.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
        if tid:
            r = g.get_role(tid)
            if r: ov[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        ch = await g.create_text_channel(name=name, overwrites=ov)
        conn = sqlite3.connect(DB_PATH); conn.execute("INSERT INTO tickets (channel_id, user_id, category) VALUES (?, ?, ?)", (str(ch.id), str(it.user.id), self.values[0])); conn.commit(); conn.close()
        tag = f"<@&{tid}>" if tid else "@here"
        em = discord.Embed(title=f"🎫 Ticket: {self.values[0]}", description=f"สวัสดีคุณ {it.user.mention}\nกรุณาแจ้งรายละเอียด\n\n💡 *พิมพ์ `/ปิดช่อง` เพื่อปิด*", color=0x3498DB)
        await ch.send(content=f"{tag} {it.user.mention}", embed=em)
        await it.response.send_message(f"✅ เปิด Ticket แล้วที่ {ch.mention}", ephemeral=True)

class TicketPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(TicketSelect())

# =========================
# SLASH COMMANDS
# =========================
@bot.tree.command(name="ยืนยันตัวตน", description="ตั้งค่าระบบยืนยันตัวตน (Administrator Only)")
@app_commands.default_permissions(administrator=True)
async def setup_verify(interaction: discord.Interaction):
    embed = discord.Embed(title="ระบบยืนยันตัวตนทหารไทย", description="กรุณากดปุ่มด้านล่างเพื่อเริ่มการยืนยันตัวตนกับ Roblox", color=0x2B2D31)
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message("✅ ตั้งค่าระบบยืนยันตัวตนเรียบร้อยแล้ว", ephemeral=True)

@bot.tree.command(name="ตั้งค่าทิกเก็ต", description="ส่งแผงควบคุม Ticket (Admin Only)")
@app_commands.default_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction):
    embed = discord.Embed(title="📬 ระบบติดต่อทีมงาน (Ticket)", description="เลือกหมวดหมู่ที่ต้องการติดต่อจากเมนูด้านล่าง", color=0x2B2D31)
    await interaction.channel.send(embed=embed, view=TicketPanelView())
    await interaction.response.send_message("✅ ส่งแผงควบคุม Ticket เรียบร้อยแล้ว", ephemeral=True)

@bot.tree.command(name="ปิดช่อง", description="ปิด Ticket ปัจจุบัน (Admin Only)")
@app_commands.default_permissions(administrator=True)
async def close_ticket(interaction: discord.Interaction):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM tickets WHERE channel_id = ?", (str(interaction.channel.id),)).fetchone()
    if not row: return await interaction.response.send_message("❌ ไม่ใช่ช่อง Ticket", ephemeral=True)
    await interaction.response.send_message("🔒 กำลังบันทึกประวัติและปิด Ticket...")
    s = load_settings(); u = interaction.guild.get_member(int(row["user_id"]))
    html = await generate_transcript(interaction.channel, u or row["user_id"], interaction.user, row["category"])
    file = discord.File(io.BytesIO(html.encode()), filename=f"transcript-{interaction.channel.name}.html")
    ts_id = parse_id(s.get("transcript_channel_id"))
    if ts_id:
        ts_ch = interaction.guild.get_channel(ts_id)
        if ts_ch:
            em = discord.Embed(title="📄 Ticket Transcript", color=0x2B2D31, timestamp=datetime.datetime.now())
            em.add_field(name="หมวดหมู่", value=row["category"]); em.add_field(name="ผู้เปิด", value=f"<@{row['user_id']}>"); em.add_field(name="ผู้ปิด", value=interaction.user.mention)
            await ts_ch.send(embed=em, file=file)
    conn.execute("UPDATE tickets SET status = 'closed' WHERE channel_id = ?", (str(interaction.channel.id),)); conn.commit(); conn.close()
    if u: await interaction.channel.set_permissions(u, send_messages=False, read_message_history=True, view_channel=True)
    await interaction.channel.send("✅ บันทึกประวัติเรียบร้อยแล้ว ช่องนี้ถูกล็อกการพิมพ์")

@bot.tree.command(name="ตั้งช่องประวัติ", description="ตั้งค่าช่องสำหรับส่งประวัติ Ticket (Admin Only)")
@app_commands.default_permissions(administrator=True)
async def set_transcript_channel(interaction: discord.Interaction, ช่อง: discord.TextChannel):
    s = load_settings(); s["transcript_channel_id"] = ช่อง.id; save_settings(s)
    await interaction.response.send_message(f"✅ ตั้งค่าช่องประวัติเป็น {ช่อง.mention} เรียบร้อยแล้ว", ephemeral=True)

@bot.tree.command(name="ล้างข้อมูล", description="ลบข้อมูลการยืนยันตัวตนทุกคน")
@app_commands.default_permissions(administrator=True)
async def reset_db(interaction: discord.Interaction):
    conn = sqlite3.connect(DB_PATH); conn.execute("DELETE FROM users"); conn.commit(); conn.close()
    await interaction.response.send_message("⚠️ ล้างข้อมูลสำเร็จ", ephemeral=True)

@bot.tree.command(name="ใส่โรล", description="ตั้งค่า Role ให้กับประเภทที่เลือก")
@app_commands.default_permissions(administrator=True)
@app_commands.choices(ประเภท=[app_commands.Choice(name="Verified", value="verified"), app_commands.Choice(name="Developer", value="developer"), app_commands.Choice(name="Ticket", value="ticket"), app_commands.Choice(name="OR", value="or"), app_commands.Choice(name="OF Low", value="of_low"), app_commands.Choice(name="OF High", value="of_high"), app_commands.Choice(name="Guest", value="guest")])
async def set_role(interaction: discord.Interaction, ประเภท: app_commands.Choice[str], โรล: discord.Role):
    s = load_settings(); t = ประเภท.value
    if t in ["verified", "developer", "ticket"]: s[f"{t}_role_id"] = โรล.id
    else: s["role_ids"][t] = โรล.id
    save_settings(s); await interaction.response.send_message(f"✅ ตั้งค่า {ประเภท.name} เป็น {โรล.name}", ephemeral=True)

@bot.tree.command(name="ใส่คำนำหน้า", description="เพิ่มหรือแก้คำนำหน้าตามชื่อยศ Roblox")
@app_commands.default_permissions(administrator=True)
async def set_prefix(interaction: discord.Interaction, ยศ: str, คำนำหน้า: str):
    s = load_settings(); s["rank_prefixes"][ยศ.strip().lower()] = f"{ยศ.strip()}, {คำนำหน้า.strip()}"; save_settings(s)
    await interaction.response.send_message(f"✅ เพิ่มคำนำหน้า {ยศ} เรียบร้อย", ephemeral=True)

@bot.tree.command(name="ปรับแต่งทั้งหมด", description="เปิดหน้าต่างปรับแต่งระบบทั้งหมด")
@app_commands.default_permissions(administrator=True)
async def customize_all(interaction: discord.Interaction): await interaction.response.send_modal(CustomizeAllModal())

@bot.tree.command(name="ดูการตั้งค่า", description="ดูค่าการตั้งค่าระบบปัจจุบัน")
@app_commands.default_permissions(administrator=True)
async def show_settings(interaction: discord.Interaction):
    s = load_settings(); r = s.get("role_ids", {})
    em = discord.Embed(title="การตั้งค่าระบบปัจจุบัน", color=0x3498DB)
    em.add_field(name="Group ID", value=str(s.get("roblox_group_id"))); em.add_field(name="Ticket Role", value=str(s.get("ticket_role_id")))
    em.add_field(name="Roles", value=f"OR: {r.get('or')}\nOF Low: {r.get('of_low')}\nOF High: {r.get('of_high')}", inline=False)
    await interaction.response.send_message(embed=em, ephemeral=True)

# =========================
# FASTAPI WEBHOOK
# =========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(); load_settings(); asyncio.create_task(bot.start(DISCORD_TOKEN))
    yield
    await bot.close()

app = FastAPI(lifespan=lifespan)

@app.post("/verify")
async def verify_endpoint(request: Request):
    data = await request.json(); rid, rname, gid = data.get("robloxId"), data.get("robloxUsername"), data.get("guildId")
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT discord_id FROM users WHERE LOWER(pending_roblox_username) = ? ORDER BY rowid DESC LIMIT 1", (str(rname).lower(),)).fetchone(); conn.close()
    if not row: return {"ok": False, "message": "No pending"}
    r, dname, rn = await update_member_status(row["discord_id"], rid, rname, gid)
    if r:
        conn = sqlite3.connect(DB_PATH); conn.execute("UPDATE users SET roblox_id = ?, roblox_username = ?, verified = 1, pending_roblox_username = NULL WHERE discord_id = ?", (str(rid), rname, row["discord_id"])); conn.commit(); conn.close()
        return {"ok": True, "discord_username": dname, "current_rank": rn}
    return {"ok": False}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
