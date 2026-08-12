# Credits: By.ivzex, By.patxez, DEV.manpop79, DEV.Fugus1234
import os, asyncio, json, re, sqlite3, requests, discord, uvicorn
from discord.ext import commands
from discord import app_commands
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
PORT = int(os.getenv("PORT", 8888))
DB_PATH, SETTINGS_PATH = "database.db", "settings.json"

DEFAULT_SETTINGS = {
    "roblox_group_id": 226834839, "roblox_group_url": "https://www.roblox.com/groups/226834839",
    "roblox_map_url": "https://www.roblox.com/th/games/78189317414125/By",
    "verified_role_id": 1479443343367995579, "developer_role_id": 1479469155399766129, "ticket_role_id": 1508479215908028544,
    "role_ids": {"or": 1479699133001629797, "of_low": 1479699314078122094, "of_high": 1479699471603470432, "guest": None},
    "rank_prefixes": {"or-1": "OR-1, PC", "or-2": "OR-2, PEC", "or-3": "OR-3, CPL", "or-4": "OR-4, SGT", "or-5": "OR-5, SSG", "or-6": "OR-6/OR-7, SFC", "or-7": "OR-6/OR-7, SFC", "or-8": "OR-8/OR-9, MSG", "or-9": "OR-8/OR-9, MSG", "of-1a": "OF-1A, LTP", "of-1b": "OF-1B, 1LT", "of-2": "OF-2, CPT", "of-3": "OF-3, MAJ", "of-4": "OF-4, LTC", "of-5": "OF-5, COL", "of-6": "OF-6, SRCOL", "of-7": "OF-7, PMG", "of-8": "OF-8, MG", "of-9": "OF-9, GEN"}
}

def load_s():
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    for k, v in saved.items():
                        if k in ["role_ids", "rank_prefixes"] and isinstance(v, dict): s[k].update(v)
                        else: s[k] = v
    except: pass
    return s

def save_s(s):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f: json.dump(s, f, ensure_ascii=False, indent=2)

def parse_id(v):
    if v is None: return None
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (discord_id TEXT PRIMARY KEY, roblox_id TEXT, roblox_username TEXT, verified INTEGER DEFAULT 0, pending_roblox_username TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS tickets (channel_id TEXT PRIMARY KEY, user_id TEXT, category TEXT, status TEXT DEFAULT 'open')")
    conn.commit(); conn.close()

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default(); intents.members = True; intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
    async def setup_hook(self):
        self.add_view(VerifyView()); self.add_view(ReVerifyView()); self.add_view(TicketPanelView())
        await self.tree.sync()

bot = MyBot()

def get_rid(n):
    try:
        r = requests.post("https://users.roblox.com/v1/usernames/users", json={"usernames": [n], "excludeBannedUsers": True}, timeout=10)
        d = r.json()
        if d.get("data"): return d["data"][0]["id"]
    except: return None

def check_g(rid):
    s = load_s()
    try:
        r = requests.get(f"https://groups.roblox.com/v1/users/{rid}/groups/roles", timeout=10)
        d = r.json()
        for g in d.get("data", []):
            if g["group"]["id"] == int(s["roblox_group_id"]): return True, g["role"]["rank"], g["role"]["name"]
    except: pass
    return False, 0, None

async def up_stat(did, rid, rn, gid=None):
    s = load_s(); g = bot.get_guild(int(gid)) if gid else (bot.guilds[0] if bot.guilds else None)
    if not g: return None, None, None
    try:
        m = await g.fetch_member(int(did)); in_g, rv, rname = check_g(rid); is_d = int(rid) in [5711452462]
        m_roles = {parse_id(s.get("verified_role_id")), parse_id(s.get("developer_role_id")), parse_id(s.get("ticket_role_id")), *[parse_id(x) for x in s["role_ids"].values()]}
        m_roles.discard(None)
        to_a = [r for r in m.roles if r.id not in m_roles and r != g.default_role]
        vr = g.get_role(parse_id(s.get("verified_role_id")))
        if vr: to_a.append(vr)
        if is_d:
            dr = g.get_role(parse_id(s.get("developer_role_id")))
            if dr: to_a.append(dr)
            nk, dp = f"Dev | {rn}", "Developer"
        elif in_g:
            if 1 <= rv <= 7: rr = g.get_role(parse_id(s["role_ids"].get("or")))
            elif 8 <= rv <= 11: rr = g.get_role(parse_id(s["role_ids"].get("of_low")))
            elif 12 <= rv <= 18: rr = g.get_role(parse_id(s["role_ids"].get("of_high")))
            else: rr = None
            if rr: to_a.append(rr)
            p = next((v for k, v in s["rank_prefixes"].items() if k.lower() in rname.lower()), "")
            nk, dp = (f"{p} | {rn}" if p else rn), (rname or "Unknown")
        else:
            gr = g.get_role(parse_id(s["role_ids"].get("guest")))
            if gr: to_a.append(gr)
            nk, dp = f"Guest | {rn}", "Guest"
        await m.edit(roles=list(set(to_a)), nick=nk[:32])
        return rv if not is_d else 999, m.display_name, dp
    except: return None, None, None

class VerifyModal(discord.ui.Modal, title="ยืนยันตัวตน Roblox"):
    u = discord.ui.TextInput(label="ชื่อ Roblox", min_length=3, max_length=20)
    async def on_submit(self, it: discord.Interaction):
        n = self.u.value; rid = get_rid(n); s = load_s()
        if not rid: return await it.response.send_message(f"❌ ไม่พบชื่อ: {n}", ephemeral=True)
        in_g, _, _ = check_g(rid); is_d = int(rid) in [5711452462]
        if not in_g and not is_d: return await it.response.send_message(f"❌ กรุณาเข้ากลุ่มก่อน: {s['roblox_group_url']}", ephemeral=True)
        conn = sqlite3.connect(DB_PATH); conn.execute("INSERT INTO users (discord_id, pending_roblox_username, verified) VALUES (?, ?, 0) ON CONFLICT(discord_id) DO UPDATE SET pending_roblox_username = excluded.pending_roblox_username, verified = 0", (str(it.user.id), n.strip().lower())); conn.commit(); conn.close()
        em = discord.Embed(title="ยืนยันตัวตน", description=f"ชื่อ: **{n}**\n[คลิกเข้าแมพเพื่อยืนยัน]({s['roblox_map_url']})", color=0x00FF00)
        await it.response.send_message(embed=em, ephemeral=True)

class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="ยืนยันตัวตน", style=discord.ButtonStyle.success, custom_id="v_btn")
    async def v(self, it: discord.Interaction, b: discord.ui.Button): await it.response.send_modal(VerifyModal())

class ReVerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="อัพเดทยศ", style=discord.ButtonStyle.success, custom_id="up_btn")
    async def up(self, it: discord.Interaction, b: discord.ui.Button):
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; u = conn.execute("SELECT * FROM users WHERE discord_id = ?", (str(it.user.id),)).fetchone(); conn.close()
        if not u or not u["verified"]: return await it.response.send_message("❌ กรุณายืนยันตัวตนก่อน", ephemeral=True)
        await it.response.defer(ephemeral=True)
        r, _, rn = await up_stat(it.user.id, u["roblox_id"], u["roblox_username"], it.guild_id)
        await it.followup.send(f"✅ อัพเดทยศสำเร็จ: **{rn}**" if r else "❌ ล้มเหลว", ephemeral=True)
    @discord.ui.button(label="ยืนยันตัวตน", style=discord.ButtonStyle.primary, custom_id="v_btn_re")
    async def v(self, it: discord.Interaction, b: discord.ui.Button): await it.response.send_modal(VerifyModal())

class TicketSelect(discord.ui.Select):
    def __init__(self):
        opts = [discord.SelectOption(label=l, emoji=e, value=l) for l, e in [("แจ้งโปร", "🚨"), ("แจ้งยศไม่เข้า", "⚠️"), ("ติดต่อแอดมินทั่วไป", "💬"), ("ติดต่อส่งเอกสาร", "📄"), ("ติดต่อรับรางวัล", "🎁")]]
        super().__init__(placeholder="เลือกหัวข้อที่ต้องการติดต่อ", options=opts, custom_id="t_sel")
    async def callback(self, it: discord.Interaction):
        s = load_s(); tid = parse_id(s.get("ticket_role_id", 1508479215908028544)); name = f"ticket-{self.values[0]}-{it.user.name}".lower()
        ov = {it.guild.default_role: discord.PermissionOverwrite(view_channel=False), it.user: discord.PermissionOverwrite(view_channel=True, send_messages=True), it.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
        if tid:
            r = it.guild.get_role(tid)
            if r: ov[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        ch = await it.guild.create_text_channel(name=name, overwrites=ov)
        conn = sqlite3.connect(DB_PATH); conn.execute("INSERT INTO tickets (channel_id, user_id, category) VALUES (?, ?, ?)", (str(ch.id), str(it.user.id), self.values[0])); conn.commit(); conn.close()
        tag = f"<@&{tid}>" if tid else "@here"
        em = discord.Embed(title=f"🎫 Ticket: {self.values[0]}", description=f"สวัสดี {it.user.mention} กรุณาแจ้งรายละเอียด\nพิมพ์ `/ปิดช่อง` เพื่อปิด", color=0x3498DB)
        await ch.send(content=f"{tag} {it.user.mention}", embed=em)
        await it.response.send_message(f"✅ เปิดแล้วที่ {ch.mention}", ephemeral=True)

class TicketPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(TicketSelect())

@bot.tree.command(name="ยืนยันตัวตน")
@app_commands.default_permissions(administrator=True)
async def setup_v(it: discord.Interaction):
    await it.channel.send(embed=discord.Embed(title="ระบบยืนยันตัวตน", description="กดปุ่มด้านล่าง", color=0x2B2D31), view=VerifyView())
    await it.response.send_message("✅ OK", ephemeral=True)

@bot.tree.command(name="ตั้งค่าทิกเก็ต")
@app_commands.default_permissions(administrator=True)
async def setup_t(it: discord.Interaction):
    await it.channel.send(embed=discord.Embed(title="📬 ติดต่อทีมงาน", description="เลือกหมวดหมู่", color=0x2B2D31), view=TicketPanelView())
    await it.response.send_message("✅ OK", ephemeral=True)

@bot.tree.command(name="ปิดช่อง")
@app_commands.default_permissions(administrator=True)
async def close_t(it: discord.Interaction):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; row = conn.execute("SELECT * FROM tickets WHERE channel_id = ?", (str(it.channel.id),)).fetchone()
    if not row: return await it.response.send_message("❌ ไม่ใช่ช่อง Ticket", ephemeral=True)
    conn.execute("UPDATE tickets SET status = 'closed' WHERE channel_id = ?", (str(it.channel.id),)); conn.commit(); conn.close()
    m = it.guild.get_member(int(row["user_id"]))
    if m: await it.channel.set_permissions(m, send_messages=False, read_message_history=True, view_channel=True)
    await it.response.send_message("🔒 ปิด Ticket แล้ว (ดูประวัติได้)")

@bot.tree.command(name="ใส่โรล")
@app_commands.default_permissions(administrator=True)
async def set_r(it: discord.Interaction, ประเภท: str, โรล: discord.Role):
    s = load_s(); t = ประเภท.lower()
    if t in ["verified", "developer", "ticket"]: s[f"{t}_role_id"] = โรล.id
    else: s["role_ids"][t] = โรล.id
    save_s(s); await it.response.send_message(f"✅ ตั้งค่า {ประเภท} เป็น {โรล.name}", ephemeral=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(); asyncio.create_task(bot.start(DISCORD_TOKEN))
    yield
    await bot.close()

app = FastAPI(lifespan=lifespan)

@app.post("/verify")
async def v_api(req: Request):
    d = await req.json(); rid, rname, gid = d.get("robloxId"), d.get("robloxUsername"), d.get("guildId")
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; row = conn.execute("SELECT discord_id FROM users WHERE LOWER(pending_roblox_username) = ? ORDER BY rowid DESC LIMIT 1", (str(rname).lower(),)).fetchone(); conn.close()
    if not row: return {"ok": False}
    r, dname, rn = await up_stat(row["discord_id"], rid, rname, gid)
    if r:
        conn = sqlite3.connect(DB_PATH); conn.execute("UPDATE users SET roblox_id = ?, roblox_username = ?, verified = 1, pending_roblox_username = NULL WHERE discord_id = ?", (str(rid), rname, row["discord_id"])); conn.commit(); conn.close()
        return {"ok": True, "discord_username": dname, "current_rank": rn}
    return {"ok": False}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
