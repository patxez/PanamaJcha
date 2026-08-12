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
        "or-1": "OR-1, PC", "or-2": "OR-2, PEC", "or-3": "OR-3, CPL", "or-4": "OR-4, SGT", "or-5": "OR-5, SSG",
        "or-6": "OR-6/OR-7, SFC", "or-7": "OR-6/OR-7, SFC", "or-8": "OR-8/OR-9, MSG", "or-9": "OR-8/OR-9, MSG",
        "of-1a": "OF-1A, LTP", "of-1b": "OF-1B, 1LT", "of-2": "OF-2, CPT", "of-3": "OF-3, MAJ", "of-4": "OF-4, LTC",
        "of-5": "OF-5, COL", "of-6": "OF-6, SRCOL", "of-7": "OF-7, PMG", "of-8": "OF-8, MG", "of-9": "OF-9, GEN",
    },
}

DEVELOPER_IDS = [5711452462]
VERIFIED_EMOJI = "✅"

def load_settings():
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as file:
            saved = json.load(file)
            if isinstance(saved, dict):
                for key, value in saved.items():
                    if key == "role_ids" and isinstance(value, dict): settings["role_ids"].update(value)
                    elif key == "rank_prefixes" and isinstance(value, dict): settings["rank_prefixes"].update(value)
                    else: settings[key] = value
    except: pass
    return settings

def save_settings(settings):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as file: json.dump(settings, file, ensure_ascii=False, indent=2)

def parse_id(value):
    if value is None: return None
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None

# =========================
# DATABASE
# =========================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (discord_id TEXT PRIMARY KEY, roblox_id TEXT, roblox_username TEXT, verified INTEGER DEFAULT 0, pending_roblox_username TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS tickets (channel_id TEXT PRIMARY KEY, user_id TEXT, category TEXT, status TEXT DEFAULT 'open')")
    conn.commit(); conn.close()

def get_user(discord_id):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users WHERE discord_id = ?", (str(discord_id),)).fetchone()
    conn.close(); return row

def update_pending(discord_id, username):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO users (discord_id, pending_roblox_username, verified) VALUES (?, ?, 0) ON CONFLICT(discord_id) DO UPDATE SET pending_roblox_username = excluded.pending_roblox_username, verified = 0", (str(discord_id), str(username).strip().lower()))
    conn.commit(); conn.close()

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
        self.add_view(VerifyView()); self.add_view(ReVerifyView()); self.add_view(TicketPanelView())
        await self.tree.sync()
        print(f"Bot ready as {self.user}")

bot = MyBot()

def get_roblox_id_by_name(username):
    try:
        response = requests.post("https://users.roblox.com/v1/usernames/users", json={"usernames": [username], "excludeBannedUsers": True}, timeout=15)
        data = response.json()
        if data.get("data"): return data["data"][0]["id"]
    except: pass
    return None

def check_group_membership(roblox_id):
    settings = load_settings()
    try:
        response = requests.get(f"https://groups.roblox.com/v1/users/{roblox_id}/groups/roles", timeout=15)
        data = response.json()
        for group in data.get("data", []):
            if group["group"]["id"] == int(settings["roblox_group_id"]): return True, group["role"]["rank"], group["role"]["name"]
    except: pass
    return False, 0, None

def get_prefix_for_rank(rank_val, rank_name, settings):
    prefixes = settings.get("rank_prefixes", {})
    normalized_name = str(rank_name or "").strip().lower()
    for rank_key, prefix in prefixes.items():
        if str(rank_key).strip().lower() in normalized_name: return str(prefix).strip()
    fallback = {1: "OR-1, PC", 2: "OR-2, PEC", 3: "OR-3, CPL", 4: "OR-4, SGT", 5: "OR-5, SSG", 6: "OR-6/OR-7, SFC", 7: "OR-6/OR-7, SFC", 8: "OF-1A, LTP", 9: "OF-1B, 1LT", 10: "OF-2, CPT", 11: "OF-2, CPT", 12: "OF-3, MAJ", 13: "OF-4, LTC", 14: "OF-5, COL", 15: "OF-6, SRCOL", 16: "OF-7, PMG", 17: "OF-8, MG", 18: "OF-9, GEN"}
    return fallback.get(int(rank_val or 0), "")

async def update_member_status(discord_id, roblox_id, roblox_username, guild_id=None):
    settings = load_settings(); guild = bot.get_guild(int(guild_id)) if guild_id else (bot.guilds[0] if bot.guilds else None)
    if not guild: return None, None, None
    try:
        member = await guild.fetch_member(int(discord_id))
        is_in, rank_val, rank_name = check_group_membership(roblox_id); is_dev = int(roblox_id) in DEVELOPER_IDS
        manage = {parse_id(settings.get("verified_role_id")), parse_id(settings.get("developer_role_id")), parse_id(settings.get("ticket_role_id")), *[parse_id(r) for r in settings.get("role_ids", {}).values()]}
        manage.discard(None)
        to_add = [r for r in member.roles if r.id not in manage and r != guild.default_role]
        v_role = guild.get_role(parse_id(settings.get("verified_role_id")))
        if v_role: to_add.append(v_role)
        if is_dev:
            d_role = guild.get_role(parse_id(settings.get("developer_role_id")))
            if d_role: to_add.append(d_role)
            nick, disp = f"Dev | {roblox_username}", "Developer"
        elif is_in:
            if 1 <= rank_val <= 7: r_role = guild.get_role(parse_id(settings["role_ids"].get("or")))
            elif 8 <= rank_val <= 11: r_role = guild.get_role(parse_id(settings["role_ids"].get("of_low")))
            elif 12 <= rank_val <= 18: r_role = guild.get_role(parse_id(settings["role_ids"].get("of_high")))
            else: r_role = None
            if r_role: to_add.append(r_role)
            prefix = get_prefix_for_rank(rank_val, rank_name, settings)
            nick, disp = (f"{prefix} | {roblox_username}" if prefix else roblox_username), (rank_name or "Unknown")
        else:
            g_role = guild.get_role(parse_id(settings["role_ids"].get("guest")))
            if g_role: to_add.append(g_role)
            nick, disp = f"Guest | {roblox_username}", "Guest"
        await member.edit(roles=list(set(to_add)), nick=nick[:32])
        return rank_val if not is_dev else 999, member.display_name, disp
    except: return None, None, None

# =========================
# UI COMPONENTS
# =========================
class VerifyModal(discord.ui.Modal, title="ยืนยันตัวตน Roblox"):
    username = discord.ui.TextInput(label="ใส่ชื่อใน Roblox", placeholder="พิมพ์ชื่อที่นี่...", min_length=3, max_length=20)
    async def on_submit(self, interaction: discord.Interaction):
        name = self.username.value; rid = get_roblox_id_by_name(name)
        if not rid: return await interaction.response.send_message(f"❌ ไม่พบชื่อ: {name}", ephemeral=True)
        is_dev = int(rid) in DEVELOPER_IDS; is_in, _, _ = check_group_membership(rid); s = load_settings()
        if not is_in and not is_dev:
            em = discord.Embed(title="❌ กรุณาเข้ากลุ่ม Roblox", description=f"คุณยังไม่ได้เข้ากลุ่ม! [คลิกเพื่อเข้ากลุ่ม]({s['roblox_group_url']})", color=0xFF0000)
            return await interaction.response.send_message(embed=em, ephemeral=True)
        update_pending(interaction.user.id, name)
        em = discord.Embed(title="กรุณาเข้าแมพเพื่อยืนยันตัวตน", color=0x00FF00)
        em.add_field(name="Username", value=f"**{name}**"); em.add_field(name="Map", value=f"[คลิกเข้าเกม]({s['roblox_map_url']})")
        await interaction.response.send_message(embed=em, ephemeral=True)

class ReVerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="อัพเดทยศ", style=discord.ButtonStyle.success, custom_id="up_rank")
    async def up(self, it: discord.Interaction, b: discord.ui.Button):
        u = get_user(it.user.id)
        if not u or not u["verified"]: return await it.response.send_message("❌ กรุณายืนยันตัวตนก่อน", ephemeral=True)
        await it.response.defer(ephemeral=True)
        r, _, rn = await update_member_status(it.user.id, u["roblox_id"], u["roblox_username"], it.guild_id)
        await it.followup.send(f"✅ อัพเดทยศสำเร็จ: **{rn}**" if r else "❌ ล้มเหลว", ephemeral=True)
    @discord.ui.button(label="ยืนยันตัวตน", style=discord.ButtonStyle.primary, custom_id="st_v")
    async def st(self, it: discord.Interaction, b: discord.ui.Button): await it.response.send_modal(VerifyModal())

class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="ยืนยันตัวตน", style=discord.ButtonStyle.success, custom_id="v_main")
    async def v(self, it: discord.Interaction, b: discord.ui.Button): await it.response.send_modal(VerifyModal())

class TicketSelect(discord.ui.Select):
    def __init__(self):
        opts = [
            discord.SelectOption(label="แจ้งโปร", description="แจ้งคนใช้โปรแกรมช่วยเล่น", emoji="🚨", value="แจ้งโปร"),
            discord.SelectOption(label="แจ้งยศไม่เข้า", description="ยศในเกมกับดิสไม่ตรงกัน", emoji="⚠️", value="แจ้งยศไม่เข้า"),
            discord.SelectOption(label="ติดต่อแอดมินทั่วไป", description="สอบถามปัญหาทั่วไป", emoji="💬", value="ติดต่อแอดมิน"),
            discord.SelectOption(label="ติดต่อส่งเอกสาร", description="ส่งเอกสารต่างๆ แก่ทีมงาน", emoji="📄", value="ส่งเอกสาร"),
            discord.SelectOption(label="ติดต่อรับรางวัล", description="รับรางวัลจากตู้สุ่ม", emoji="🎁", value="รับรางวัล")
        ]
        super().__init__(placeholder="เลือกหัวข้อที่ต้องการติดต่อ", options=opts, custom_id="t_sel")
    async def callback(self, it: discord.Interaction):
        s = load_settings(); tid = parse_id(s.get("ticket_role_id", 1508479215908028544))
        ch_name = f"ticket-{self.values[0]}-{it.user.name}".lower()
        ov = {it.guild.default_role: discord.PermissionOverwrite(view_channel=False), it.user: discord.PermissionOverwrite(view_channel=True, send_messages=True), it.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
        if tid:
            r = it.guild.get_role(tid)
            if r: ov[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        ch = await it.guild.create_text_channel(name=ch_name, overwrites=ov)
        conn = sqlite3.connect(DB_PATH); conn.execute("INSERT INTO tickets (channel_id, user_id, category) VALUES (?, ?, ?)", (str(ch.id), str(it.user.id), self.values[0])); conn.commit(); conn.close()
        tag = f"<@&{tid}>" if tid else "@here"
        em = discord.Embed(title=f"🎫 Ticket: {self.values[0]}", description=f"สวัสดี {it.user.mention} กรุณาแจ้งรายละเอียด\nพิมพ์ `/ปิดช่อง` เพื่อปิด", color=0x3498DB)
        await ch.send(content=f"{tag} {it.user.mention}", embed=em)
        await it.response.send_message(f"✅ เปิดแล้วที่ {ch.mention}", ephemeral=True)

class TicketPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(TicketSelect())

class CustomizeModal(discord.ui.Modal, title="ปรับแต่งระบบทั้งหมด"):
    gid = discord.ui.TextInput(label="Roblox Group ID", required=True)
    vrole = discord.ui.TextInput(label="Verified Role ID", required=True)
    trole = discord.ui.TextInput(label="Ticket Role ID", required=True)
    gurl = discord.ui.TextInput(label="Group URL", required=True)
    murl = discord.ui.TextInput(label="Map URL", required=True)
    async def on_submit(self, it: discord.Interaction):
        s = load_settings()
        try:
            s["roblox_group_id"] = int(self.gid.value); s["verified_role_id"] = int(self.vrole.value)
            s["ticket_role_id"] = int(self.trole.value); s["roblox_group_url"] = self.gurl.value; s["roblox_map_url"] = self.murl.value
            save_settings(s); await it.response.send_message("✅ บันทึกแล้ว", ephemeral=True)
        except: await it.response.send_message("❌ ID ต้องเป็นตัวเลข", ephemeral=True)

# =========================
# SLASH COMMANDS
# =========================
@bot.tree.command(name="ยืนยันตัวตน", description="ตั้งค่าระบบยืนยันตัวตน")
@app_commands.default_permissions(administrator=True)
async def setup_v(it: discord.Interaction):
    await it.channel.send(embed=discord.Embed(title="ระบบยืนยันตัวตน", description="กดปุ่มด้านล่างเพื่อยืนยันตัวตน", color=0x2B2D31), view=VerifyView())
    await it.response.send_message("✅ ตั้งค่าสำเร็จ", ephemeral=True)

@bot.tree.command(name="ตั้งค่าทิกเก็ต", description="ส่งแผงควบคุม Ticket")
@app_commands.default_permissions(administrator=True)
async def setup_t(it: discord.Interaction):
    await it.channel.send(embed=discord.Embed(title="📬 ระบบติดต่อทีมงาน", description="เลือกหมวดหมู่ที่ต้องการติดต่อ", color=0x2B2D31), view=TicketPanelView())
    await it.response.send_message("✅ ส่งแผงควบคุมสำเร็จ", ephemeral=True)

@bot.tree.command(name="ปิดช่อง", description="ปิด Ticket (Admin Only)")
@app_commands.default_permissions(administrator=True)
async def close_t(it: discord.Interaction):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM tickets WHERE channel_id = ?", (str(it.channel.id),)).fetchone()
    if not row: return await it.response.send_message("❌ ไม่ใช่ช่อง Ticket", ephemeral=True)
    conn.execute("UPDATE tickets SET status = 'closed' WHERE channel_id = ?", (str(it.channel.id),)); conn.commit(); conn.close()
    m = it.guild.get_member(int(row["user_id"]))
    if m: await it.channel.set_permissions(m, send_messages=False, read_message_history=True, view_channel=True)
    await it.response.send_message("🔒 ปิด Ticket แล้ว (คุณยังดูประวัติได้)")

@bot.tree.command(name="ล้างข้อมูล", description="ลบข้อมูลยืนยันตัวตนทุกคน")
@app_commands.default_permissions(administrator=True)
async def clear_d(it: discord.Interaction):
    conn = sqlite3.connect(DB_PATH); conn.execute("DELETE FROM users"); conn.commit(); conn.close()
    await it.response.send_message("⚠️ ล้างข้อมูลสำเร็จ", ephemeral=True)

@bot.tree.command(name="ใส่โรล", description="ตั้งค่า Role")
@app_commands.default_permissions(administrator=True)
@app_commands.choices(ประเภท=[app_commands.Choice(name="Verified", value="verified"), app_commands.Choice(name="Developer", value="developer"), app_commands.Choice(name="Ticket", value="ticket"), app_commands.Choice(name="OR", value="or"), app_commands.Choice(name="OF Low", value="of_low"), app_commands.Choice(name="OF High", value="of_high"), app_commands.Choice(name="Guest", value="guest")])
async def set_r(it: discord.Interaction, ประเภท: app_commands.Choice[str], โรล: discord.Role):
    s = load_settings(); t = ประเภท.value
    if t in ["verified", "developer", "ticket"]: s[f"{t}_role_id"] = โรล.id
    else: s["role_ids"][t] = โรล.id
    save_settings(s); await it.response.send_message(f"✅ ตั้งค่า {ประเภท.name} เป็น {โรล.name}", ephemeral=True)

@bot.tree.command(name="ใส่คำนำหน้า", description="เพิ่มคำนำหน้ายศ")
@app_commands.default_permissions(administrator=True)
async def set_p(it: discord.Interaction, ยศ: str, คำนำหน้า: str):
    s = load_settings(); s["rank_prefixes"][ยศ.strip().lower()] = f"{ยศ.strip()}, {คำนำหน้า.strip()}"; save_settings(s)
    await it.response.send_message(f"✅ เพิ่มคำนำหน้า {ยศ} เรียบร้อย", ephemeral=True)

@bot.tree.command(name="ปรับแต่งทั้งหมด", description="เปิดหน้าต่างปรับแต่ง")
@app_commands.default_permissions(administrator=True)
async def cust(it: discord.Interaction): await it.response.send_modal(CustomizeModal())

@bot.tree.command(name="ดูการตั้งค่า", description="ดูการตั้งค่าปัจจุบัน")
@app_commands.default_permissions(administrator=True)
async def show_s(it: discord.Interaction):
    s = load_settings(); r = s["role_ids"]
    em = discord.Embed(title="การตั้งค่าระบบ", color=0x3498DB)
    em.add_field(name="Group ID", value=s["roblox_group_id"]); em.add_field(name="Ticket Role", value=s["ticket_role_id"])
    em.add_field(name="Roles", value=f"OR: {r['or']}\nOF Low: {r['of_low']}\nOF High: {r['of_high']}", inline=False)
    await it.response.send_message(embed=em, ephemeral=True)

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
async def v_api(req: Request):
    d = await req.json(); rid = d.get("robloxId"); rname = d.get("robloxUsername"); gid = d.get("guildId")
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT discord_id FROM users WHERE LOWER(pending_roblox_username) = ? ORDER BY rowid DESC LIMIT 1", (str(rname).lower(),)).fetchone(); conn.close()
    if not row: return {"ok": False, "message": "No pending"}
    r, dname, rn = await update_member_status(row["discord_id"], rid, rname, gid)
    if r:
        conn = sqlite3.connect(DB_PATH); conn.execute("UPDATE users SET roblox_id = ?, roblox_username = ?, verified = 1, pending_roblox_username = NULL WHERE discord_id = ?", (str(rid), rname, row["discord_id"])); conn.commit(); conn.close()
        return {"ok": True, "discord_username": dname, "current_rank": rn}
    return {"ok": False, "message": "Failed"}

if __name__ == "__ma
