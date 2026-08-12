# เครดิต: By.ivzex, By.patxez, DEV.manpop79, DEV.Fugus1234
import os, asyncio, json, re, sqlite3, requests, discord, uvicorn
from discord.ext import commands
from discord import app_commands
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

# =========================
# CONFIGURATION
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
PORT = int(os.getenv("PORT", 8888))
DB_PATH = "database.db"
SETTINGS_PATH = "settings.json"

DEFAULT_SETTINGS = {
    "roblox_group_id": 226834839,
    "roblox_group_url": "https://www.roblox.com/groups/226834839",
    "roblox_map_url": "https://www.roblox.com/th/games/78189317414125/By",
    "verified_role_id": 1479443343367995579,
    "developer_role_id": 1479469155399766129,
    "ticket_role_id": 1508479215908028544,
    "role_ids": {"or": 1479699133001629797, "of_low": 1479699314078122094, "of_high": 1479699471603470432, "guest": None},
    "rank_prefixes": {
        "or-1": "OR-1, PC", "or-2": "OR-2, PEC", "or-3": "OR-3, CPL", "or-4": "OR-4, SGT", "or-5": "OR-5, SSG",
        "or-6": "OR-6/OR-7, SFC", "or-7": "OR-6/OR-7, SFC", "or-8": "OR-8/OR-9, MSG", "or-9": "OR-8/OR-9, MSG",
        "of-1a": "OF-1A, LTP", "of-1b": "OF-1B, 1LT", "of-2": "OF-2, CPT", "of-3": "OF-3, MAJ", "of-4": "OF-4, LTC",
        "of-5": "OF-5, COL", "of-6": "OF-6, SRCOL", "of-7": "OF-7, PMG", "of-8": "OF-8, MG", "of-9": "OF-9, GEN"
    }
}

DEVELOPER_IDS = [5711452462]

def load_settings():
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    for k, v in saved.items():
                        if k == "role_ids" and isinstance(v, dict): settings["role_ids"].update(v)
                        elif k == "rank_prefixes" and isinstance(v, dict): settings["rank_prefixes"].update(v)
                        else: settings[k] = v
    except: pass
    return settings

def save_settings(s):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f: json.dump(s, f, ensure_ascii=False, indent=2)

def parse_id(v):
    if v is None: return None
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None

# =========================
# DATABASE
# =========================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (discord_id TEXT PRIMARY KEY, roblox_id TEXT, roblox_username TEXT, verified INTEGER DEFAULT 0, pending_roblox_username TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS tickets (channel_id TEXT PRIMARY KEY, user_id TEXT, category TEXT, status TEXT DEFAULT 'open')")
    conn.commit()
    conn.close()

def get_user(did):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users WHERE discord_id = ?", (str(did),)).fetchone()
    conn.close(); return row

def update_pending(did, user):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO users (discord_id, pending_roblox_username, verified) VALUES (?, ?, 0) ON CONFLICT(discord_id) DO UPDATE SET pending_roblox_username = excluded.pending_roblox_username, verified = 0", (str(did), str(user).strip().lower()))
    conn.commit(); conn.close()

# =========================
# BOT CORE
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

bot = MyBot()

def get_roblox_id(name):
    try:
        r = requests.post("https://users.roblox.com/v1/usernames/users", json={"usernames": [name], "excludeBannedUsers": True}, timeout=10)
        d = r.json()
        if d.get("data"): return d["data"][0]["id"]
    except: pass
    return None

def check_group(rid):
    s = load_settings()
    try:
        r = requests.get(f"https://groups.roblox.com/v1/users/{rid}/groups/roles", timeout=10)
        d = r.json()
        for g in d.get("data", []):
            if g["group"]["id"] == int(s["roblox_group_id"]): return True, g["role"]["rank"], g["role"]["name"]
    except: pass
    return False, 0, None

async def update_status(did, rid, rname, gid=None):
    s = load_settings(); guild = bot.get_guild(int(gid)) if gid else (bot.guilds[0] if bot.guilds else None)
    if not guild: return None, None, None
    try:
        m = await guild.fetch_member(int(did))
        in_g, rval, rn = check_group(rid); is_dev = int(rid) in DEVELOPER_IDS
        manage_roles = {parse_id(s.get("verified_role_id")), parse_id(s.get("developer_role_id")), parse_id(s.get("ticket_role_id")), *[parse_id(x) for x in s["role_ids"].values()]}
        manage_roles.discard(None)
        to_add = [r for r in m.roles if r.id not in manage_roles and r != guild.default_role]
        v_role = guild.get_role(parse_id(s.get("verified_role_id")))
        if v_role: to_add.append(v_role)
        if is_dev:
            d_role = guild.get_role(parse_id(s.get("developer_role_id")))
            if d_role: to_add.append(d_role)
            nick, disp = f"Dev | {rname}", "Developer"
        elif in_g:
            if 1 <= rval <= 7: r_role = guild.get_role(parse_id(s["role_ids"].get("or")))
            elif 8 <= rval <= 11: r_role = guild.get_role(parse_id(s["role_ids"].get("of_low")))
            elif 12 <= rval <= 18: r_role = guild.get_role(parse_id(s["role_ids"].get("of_high")))
            else: r_role = None
            if r_role: to_add.append(r_role)
            p = next((v for k, v in s["rank_prefixes"].items() if k.lower() in rn.lower()), "")
            nick, disp = (f"{p} | {rname}" if p else rname), (rn or "Unknown")
        else:
            g_role = guild.get_role(parse_id(s["role_ids"].get("guest")))
            if g_role: to_add.append(g_role)
            nick, disp = f"Guest | {rname}", "Guest"
        await m.edit(roles=list(set(to_add)), nick=nick[:32])
        return rval if not is_dev else 999, m.display_name, disp
    except: return None, None, None

# =========================
# UI (VERIFY & TICKET)
# =========================
class VerifyModal(discord.ui.Modal, title="ยืนยันตัวตน Roblox"):
    user = discord.ui.TextInput(label="ชื่อ Roblox", placeholder="พิมพ์ชื่อที่นี่...", min_length=3, max_length=20)
    async def on_submit(self, it: discord.Interaction):
        name = self.user.value; rid = get_roblox_id(name)
        if not rid: return await it.response.send_message(f"❌ ไม่พบชื่อ: {name}", ephemeral=True)
        in_g, _, _ = check_group(rid); is_dev = int(rid) in DEVELOPER_IDS; s = load_settings()
        if not in_g and not is_dev:
            return await it.response.send_message(f"❌ กรุณาเข้ากลุ่มก่อน: {s['roblox_group_url']}", ephemeral=True)
        update_pending(it.user.id, name)
        em = discord.Embed(title="ยืนยันตัวตน", description=f"ชื่อ: **{name}**\n[คลิกเข้าแมพเพื่อยืนยัน]({s['roblox_map_url']})", color=0x00FF00)
        await it.response.send_message(embed=em, ephemeral=True)

class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="ยืนยันตัวตน", style=discord.ButtonStyle.success, custom_id="v_btn")
    async def v(self, it: discord.Interaction, b: discord.ui.Button): await it.response.send_modal(VerifyModal())

class ReVerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="อัพเดทยศ", style=discord.ButtonStyle.success, custom_id="up_btn")
    async def up(self, it: discord.Interaction, b: discord.ui.Button):
        u = get_user(it.user.id)
        if not u or not u["verified"]: return await it.response.send_message("❌ กรุณายืนยันตัวตนก่อน", ephemeral=True)
        await it.response.defer(ephemeral=True)
        r, _, rn = await update_status(it.user.id, u["roblox_id"], u["roblox_username"], it.guild_id)
        await it.followup.send(f"✅ อัพเดทยศสำเร็จ: **{rn}**" if r else "❌ ล้มเหลว", ephemeral=True)
    @discord.ui.button(label="ยืนยันตัวตน", style=discord.ButtonStyle.primary, custom_id="v_btn_re")
    async def v(self, it: discord.Interaction, b: discord.ui.Button): await it.response.send_modal(VerifyModal())

class TicketSelect(discord.ui.Select):
    def __init__(self):
        opts = [
            discord.SelectOption(label="แจ้งโปร", emoji="🚨", value="report"),
            discord.SelectOption(label="แจ้งยศไม่เข้า", emoji="⚠️", value="rank"),
            discord.SelectOption(label="ติดต่อแอดมินทั่วไป", emoji="💬", value="admin"),
            discord.SelectOption(label="ติดต่อส่งเอกสาร", emoji="📄", value="doc"),
            discord.SelectOption(label="ติดต่อรับรางวัล", emoji="🎁", value="reward")
        ]
        super().__init__(placeholder="เลือกหัวข้อที่ต้องการติดต่อ", options=opts, custom_id="t_sel")
    async def callback(self, it: discord.Interaction):
        s = load_settings(); tid = parse_id(s.get("ticket_role_id", 1508479215908028544))
        name = f"ticket-{self.values[0]}-{it.user.name}".lower()
        ov = {it.guild.default_role: discord.PermissionOverwrite(view_channel=False), it.user: discord.PermissionOverwrite(view_channel=True, send_messages=True), it.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
        if tid:
            r = it.guild.get_role(tid)
            if r: ov[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        ch = await it.guild.create_text_channel(name=name, overwrites=ov)
        conn = sqlite3.connect(DB_PATH); conn.execute("INSERT INTO tickets (channel_id, user_id, category) VALUES (?, ?, ?)", (str(ch.id), str(it.user.id), self.values[0])); conn.commit(); conn.close()
        tag = f"<@&{tid}>" if tid else "@here"
        em = discord.Embed(title=f"Ticket: {self.values[0]}", description=f"สวัสดี {it.user.mention} กรุณาแจ้งรายละเอียด\nพิมพ์ `/ปิดช่อง` เพื่อปิด", color=0x3498DB)
        await ch.send(content=f"{tag} {it.user.mention}", embed=em)
        await it.response.send_message(f"✅ เปิดแล้วที่ {ch.mention}", ephemeral=True)

class TicketPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(TicketSelect())

# =========================
# COMMANDS
# =========================
@bot.tree.command(name="ยืนยันตัวตน")
@app_commands.default_permissions(administrator=True)
async def setup_v(it: discord.Interaction):
    await it.channel.send(embed=discord.Embed(title="ระบบยืนยันตัวตน", description="กดปุ่มด้านล่าง", color=0x2B2D31), view=VerifyView())
    await it.response.send_message("✅ OK", ephemeral=True)

@bot.tree.command(name="ตั้งค่าทิกเก็ต")
@app_commands.default_permissions(administrator=True)
async def setup_t(it: discord.Interaction):
    await it.channel.send(embed=discord.Embed(title="📬 ติดต่อทีมงาน", description="เลือกหมวดหมู่ด้านล่าง", color=0x2B2D31), view=TicketPanelView())
    await it.response.send_message("✅ OK", ephemeral=True)

@bot.tree.command(name="ปิดช่อง")
@app_commands.default_permissions(administrator=True)
async def close_t(it: discord.Interaction):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM tickets WHERE channel_id = ?", (str(it.channel.id),)).fetchone()
    if not row: return await it.response.send_message("❌ ไม่ใช่ช่อง Ticket", ephemeral=True)
    conn.execute("UPDATE tickets SET status = 'closed' WHERE channel_id = ?", (str(it.channel.id),)); conn.commit(); conn.close()
    m = it.guild.get_member(int(row["user_id"]))
    if m: await it.channel.set_permissions(m, send_messages=False, read_message_history=True, view_channel=True)
    await it.response.send_message("🔒 ปิด Ticket แล้ว (ดูประวัติได้)")

@bot.tree.command(name="ใส่โรล")
@app_commands.default_permissions(administrator=True)
@app_commands.choices(ประเภท=[app_commands.Choice(name="ยืนยัน", value="verified"), app_commands.Choice(name="Dev", value="developer"), app_commands.Choice(name="Ticket", value="ticket")])
async def set_r(it: discord.Interaction, ประเภท: app_commands.Choice[str], โรล: discord.Role):
    s = load_settings(); s[f"{ประเภท.value}_role_id"] = โรล.id; save_settings(s)
    await it.response.send_message(f"✅ ตั้งค่า {ประเภท.name} เป็น {โรล.name}", ephemeral=True)

# =========================
# WEBHOOK & START
# =========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(); asyncio.create_task(bot.start(DISCORD_TOKEN))
    yield
    await bot.close()

app = FastAPI(lifespan=lifespan)

@app.post("/verify")
async def v_api(req: Request):
    d = await req.json(); rid = d.get("robloxId"); rname = d.get("robloxUsername"); gid = d.get("guildId")
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT discord_id FROM users WHERE LOWER(pending_roblox_username) = ? ORDER BY rowid DESC LIMIT 1", (str(rname).lower(),)).fetchone(); conn.close()
    if not row: return {"ok": False, "message": "No pending"}
    r, dname, rn = await update_status(row["discord_id"], rid, rname, gid)
    if r:
        conn = sqlite3.connect(DB_PATH); conn.execute("UPDATE users SET roblox_id = ?, roblox_username = ?, verified = 1, pending_roblox_username = NULL WHERE discord_id = ?", (str(rid), rname, row["discord_id"])); conn.commit(); conn.close()
        return {"ok": True, "discord_username": dname, "current_rank": rn}
    return {"ok": False, "message": "Failed"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
