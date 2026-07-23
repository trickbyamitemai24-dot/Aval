"""GOD-LEVEL ULTIMATE message templates for Aurora Checker.

Design system:
  - ꧁꧂ decorative frames for titles
  - Small caps for all labels (ᴄᴄ, ɢᴀᴛᴇᴡᴀʏ, ʀᴇsᴘᴏɴsᴇ)
  - Small caps for responses (sᴜᴄᴄᴇᴇᴅᴇᴅ, ᴄᴀʀᴅ_ᴅᴇᴄʟɪɴᴇᴅ)
  - Grouped card digits (4798 5106 2905 1356)
  - 20-char progress bar with percentage
  - 10-char ratio bars per stat (▰▰▰▱▱▱▱▱▱▱)
  - Premium emoji on every element (28 custom IDs)
  - Consistent header/footer with ꧁꧂
"""

from templates.emojis import (
    e_lightning, e_warning, e_card, e_cart, e_memo, e_money,
    e_globe, e_globe_flag, e_heart, e_free, e_chart, e_gem, e_gem_plans,
    e_fire, e_mobile, e_check, e_mailbox,
    e_bronze, e_silver, e_gold, e_crown,
    e_cross, e_refresh, e_check_done, e_clipboard,
    e_hourglass, e_smile, e_hourglass_v2, e_calendar, e_warning_alt,
    e_gift,
)

D  = "━━━━━━━━━━━━━━━━━━━━━━"
DS = "━━━━━━━━━━━━━━━━━━"

B  = lambda s: f"<b>{s}</b>"
C  = lambda s: f"<code>{s}</code>"
I  = lambda s: f"<i>{s}</i>"


# ── Small caps converter ──────────────────────────────────────────
_SC = {
    'a':'ᴀ','b':'ʙ','c':'ᴄ','d':'ᴅ','e':'ᴇ','f':'ғ','g':'ɢ','h':'ʜ','i':'ɪ',
    'j':'ᴊ','k':'ᴋ','l':'ʟ','m':'ᴍ','n':'ɴ','o':'ᴏ','p':'ᴘ','q':'ǫ','r':'ʀ',
    's':'s','t':'ᴛ','u':'ᴜ','v':'ᴠ','w':'ᴡ','x':'x','y':'ʏ','z':'ᴢ',
}

def sc(s: str) -> str:
    """Convert to small caps."""
    return ''.join(_SC.get(c.lower(), c) for c in s)


def frame(t: str) -> str:
    """꧁꧂ decorative frame."""
    return f"꧁  {B(t)}  ꧂"


def hdr() -> str:
    """Standard header."""
    return f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n{D}"


def ftr() -> str:
    """Standard footer."""
    return f"{D}\n{e_mailbox()} {I('Owner: @rayzenqx')}"


def grp(n: str) -> str:
    """Group 16-digit card: 4798 5106 2905 1356"""
    return f"{n[:4]} {n[4:8]} {n[8:12]} {n[12:]}" if len(n) == 16 else n


def grp_masked(card) -> str:
    """Masked grouped card."""
    n = card.number
    return f"{n[:4]} {n[4:6]}** **** {n[-4:]}" if len(n) == 16 else card.masked


def bar(pct: float, w: int = 20) -> str:
    """Progress bar."""
    return "█" * int(pct * w) + "░" * (w - int(pct * w))


def ratio(part: int, total: int, w: int = 10) -> str:
    """Ratio bar."""
    p = (part / total) if total > 0 else 0
    return "▰" * int(p * w) + "▱" * (w - int(p * w))


# ═════════════════════════════════════════════════════════════════════════
# START
# ═════════════════════════════════════════════════════════════════════════
def format_start(tier, card_limit, checks=0, charged=0, live=0):
    stats_section = ""
    if checks > 0:
        stats_section = (
            f"\n{e_chart()} 𝒀𝑶𝑼𝑹 𝑺𝑻𝑨𝑻𝑺 {e_chart()}\n{DS}\n"
            f"{e_card()}  {B('ᴄʜᴇᴄᴋs')}   : {checks}\n"
            f"{e_heart()}  {B('ᴄʜᴀʀɢᴇᴅ')} : {charged}\n"
            f"{e_smile()}  {B('ʟɪᴠᴇ')}    : {live}\n\n"
        )

    return (
        f"{hdr()}\n\n"
        f"{frame('𝑾𝑬𝑳𝑪𝑶𝑴𝑬')}\n\n"
        f"{e_free()}  {B('ᴛɪᴇʀ')}    : {tier}\n"
        f"{e_chart()} {B('ʟɪᴍɪᴛ')}   : {card_limit} ᴄᴀʀᴅs /ʀᴜɴ\n"
        f"{e_gem()}  {B('ʀᴇᴅᴇᴇᴍ')}  : /redeem &lt;key&gt;\n\n"
        f"{stats_section}"
        f"{e_fire()} 𝑪𝑶𝑴𝑴𝑨𝑵𝑫𝑺 {e_fire()}\n{DS}\n"
        f"{e_card()}  /sh {I('cc')}     — Single Check (Shopify)\n"
        f"{e_card()}  /st {I('cc')}     — Single Check (Stripe)\n"
        f"{e_card()}  /amz {I('cc')}    — Single Check (Amazon)\n"
        f"{e_card()}  /bin {I('bin')}   — BIN Lookup\n"
        f"{e_card()}  /ccgen           — Generate valid cards\n"
        f"{e_memo()}  /chk      — Mass Check (.txt)\n"
        f"{e_memo()}  /massamz  — Mass Amazon (.txt)\n"
        f"{e_check()} /resume   — Resume interrupted\n\n"
        f"{e_mobile()} 𝑷𝑹𝑶𝑿𝑰𝑶𝑺 {e_mobile()}\n{DS}\n"
        f"{e_check()}  /addproxy   — Add proxies\n"
        f"{e_check()}  /proxy      — Check &amp; clean\n"
        f"{e_check()}  /clearproxy — Clear all\n\n"
        f"{e_cart()} 𝑨𝑴𝑨𝒁𝑶𝑵 𝑪𝑶𝑶𝑲𝑰𝑬𝑺 {e_cart()}\n{DS}\n"
        f"{e_check()}  /setcookies — Set cookies\n"
        f"{e_check()}  /cookies    — View status\n"
        f"{e_check()}  /clearcookies — Clear\n\n"
        f"{ftr()}"
    )


# ═════════════════════════════════════════════════════════════════════════
# SINGLE CHECK
# ═════════════════════════════════════════════════════════════════════════
def format_single_check(status, card, gateway, response, price, bin_info, flag=""):
    sm = {
        "CHARGED":  (e_heart(),     "𝑪𝑯𝑨𝑹𝑮𝑬𝑫"),
        "LIVE":     (e_check_done(),"𝑳𝑰𝑽𝑶 𝑪𝑨𝑹𝑫"),
        "LIVE_3DS": (e_check_done(),"𝑳𝑰𝑽𝑶 3DS"),
        "DEAD":     (e_warning(),   "𝑫𝑬𝑨𝑫 𝑪𝑨𝑹𝑫"),
    }
    ei, label = sm.get(status, (e_warning(), "𝑫𝑬𝑨𝑫 𝑪𝑨𝑹𝑫"))

    if status in ("CHARGED", "LIVE", "LIVE_3DS"):
        cc_show = grp(card.number)
        cc_full = f"{cc_show}|{card.month}|{card.year}|{card.cvv}"
    else:
        cc_full = card.masked

    bn = f"{bin_info.get('brand','?')} − {bin_info.get('type','?')} − {bin_info.get('level','?')}"

    return (
        f"{hdr()}\n\n"
        f"{frame(label)}\n"
        f"   {ei} {ei} {ei}\n\n"
        f"{e_card()}   {B('ᴅᴄ')}       : {C(cc_full)}\n"
        f"{e_cart()}   {B('ɢᴀᴛᴇᴡᴀʏ')}  : {gateway}\n"
        f"{e_memo()}   {B('ʀᴇsᴘᴏɴsᴇ')} : {sc(response)}\n"
        f"{e_money()}  {B('ᴘʀɪᴄᴇ')}    : ${price}\n\n"
        f"{DS}\n"
        f"{e_card()}   {B('ʙɪɴ')}      : {bn}\n"
        f"{e_globe()}  {B('ʙᴀɴᴋ')}     : {bin_info.get('bank','?')}\n"
        f"{e_globe_flag()} {B('ᴄᴏᴜɴᴛʀʏ')} : {bin_info.get('country','?')} {flag}\n\n"
        f"{ftr()}"
    )


# ═════════════════════════════════════════════════════════════════════════
# BIN
# ═════════════════════════════════════════════════════════════════════════
def format_bin(bin_info, flag=""):
    return (
        f"{hdr()}\n\n{frame('ʙɪɴ ʟᴏᴏᴋᴜᴘ')}\n\n"
        f"{e_card()}      {B('ʙɪɴ')}     : {bin_info.get('bin','?')}\n"
        f"🏦      {B('ʙᴀɴᴋ')}   : {bin_info.get('bank','?')}\n"
        f"{e_card()}      {B('ʙʀᴀɴᴅ')}  : {bin_info.get('brand','?')}\n"
        f"{e_chart()}     {B('ᴛʏᴘᴇ')}   : {bin_info.get('type','?')}\n"
        f"{e_clipboard()} {B('ʟᴇᴠᴇʟ')}  : {bin_info.get('level','?')}\n"
        f"{e_globe_flag()} {B('ᴄᴏᴜɴᴛʀʏ')} : {bin_info.get('country','?')} {flag}\n\n"
        f"{ftr()}"
    )


def format_bin_usage():
    return f"{e_cross()} {B('ᴜsᴀɢᴇ:')}\n{C('/bin 444488')}\nOr reply with {C('/bin')}"


# ═════════════════════════════════════════════════════════════════════════
# HELP
# ═════════════════════════════════════════════════════════════════════════
def format_help():
    return (
        f"{hdr()}\n\n"
        f"{e_fire()} 𝑪𝑶𝑴𝑴𝑨𝑵𝑫𝑺 {e_fire()}\n{DS}\n"
        f"{e_card()}  /sh {I('cc')}      — Single Check (Shopify)\n"
        f"{e_card()}  /st {I('cc')}      — Single Check (Stripe)\n"
        f"{e_card()}  /amz {I('cc')}     — Single Check (Amazon)\n"
        f"{e_card()}  /bin {I('bin')}    — BIN Lookup\n"
        f"{e_card()}  /ccgen            — Generate Luhn-valid cards\n"
        f"{e_memo()}  /chk       — Mass Check (.txt)\n"
        f"{e_memo()}  /massamz   — Mass Amazon Check (.txt)\n"
        f"{e_check()} /resume    — Resume interrupted\n"
        f"{e_gem()}  /redeem {I('key')}  — Redeem a key\n"
        f"{e_clipboard()} /plans     — View pricing\n\n"
        f"{e_mobile()} 𝑷𝑹𝑶𝑿𝑰𝑶𝑺 {e_mobile()}\n{DS}\n"
        f"   /addproxy   — Add proxies\n"
        f"   /proxy      — Check &amp; clean\n"
        f"   /clearproxy — Clear all\n\n"
        f"{e_cart()} 𝑨𝑴𝑨𝒁𝑶𝑵 𝑪𝑶𝑶𝑲𝑰𝑬𝑺 {e_cart()}\n{DS}\n"
        f"   /setcookies {I('cookies')} — Set Amazon cookies\n"
        f"   /cookies             — View cookie status\n"
        f"   /clearcookies        — Clear cookies\n\n"
        f"{ftr()}"
    )


# ═════════════════════════════════════════════════════════════════════════
# ERRORS
# ═════════════════════════════════════════════════════════════════════════
def format_error(msg="An error occurred. Try again."):
    return f"{e_cross()} {msg}"

def format_banned():
    return f"{e_cross()} {B('You are banned.')}\nContact: @rayzenqx"

def format_card_error():
    return (
        f"{e_cross()} {B('ɪɴᴠᴀʟɪᴅ ᴄᴀʀᴅ ғᴏʀᴍᴀᴛ.')}\n\n{B('sᴜᴘᴘᴏʀᴛᴇᴅ:')}\n"
        f"• {C('4798510629051356|12|2028|893')}\n"
        f"• {C('4798510629051356:12:2028:893')}\n"
        f"• {C('4798510629051356 12 2028 893')}\n"
        f"• {C('4798510629051356,12,2028,893')}"
    )

def format_usage_sh():
    return f"{e_cross()} {B('ᴜsᴀɢᴇ:')}\n{C('/sh 4798510629051356|12|2028|893')}\n\nOr reply with {C('/sh')}"

def format_usage_st():
    return f"{e_cross()} {B('ᴜsᴀɢᴇ:')}\n{C('/st 4798510629051356|12|2028|893')}\n\nOr reply with {C('/st')}"

def format_tier_exceeded(tier, limit):
    return f"{e_cross()} ᴛɪᴇʀ ({tier}) ᴍᴀx {B(str(limit))} ᴄᴀʀᴅs.\n{e_gem()} Upgrade: /plans"


# ═════════════════════════════════════════════════════════════════════════
# CHECKING
# ═════════════════════════════════════════════════════════════════════════
def format_checking(card):
    return (
        f"{hdr()}\n\n"
        f"{e_refresh()} {B('ᴄʜᴇᴄᴋɪɴɢ ᴄᴀʀᴅ...')}\n"
        f"{e_card()} {C(grp_masked(card))}\n\n"
        f"{e_hourglass()} {I('ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...')}\n\n{D}"
    )


# ═════════════════════════════════════════════════════════════════════════
# MASS CHECK OPTIONS
# ═════════════════════════════════════════════════════════════════════════
def format_mass_check_options(c5, c10, call, cc, warn="", chq=0, cv40=0, csureship=0, call_combined=0):
    t = (
        f"{hdr()}\n\n{frame('ᴍᴀss ᴄʜᴇᴄᴋ')}\n\n"
        f"📦  {B('sᴏᴜʀᴄᴇ')} : Global Sites\n"
        f"sᴇʟᴇᴄᴛ sɪᴛᴇs ᴘʀɪᴄᴇ ʀᴀɴɢᴇ:\n\n"
        f"   • $1 − $5        ({c5})\n"
        f"   • $1 − $10       ({c10})\n"
        f"   • Working         ({call})\n"
        f"   • {e_check_done()} HQ            ({chq})\n"
        f"   • {e_lightning()} V40            ({cv40})\n"
        f"   • {e_lightning()} Sureship     ({csureship})\n"
        f"   • {e_globe()} ALL Sites    ({call_combined})\n\n"
        f"{e_card()}  {B('ᴄᴀʀᴅs')}  : {cc}\n"
    )
    if warn:
        t += f"\n{warn}"
    return t


def format_mass_check_limit_warning(total, limit):
    lbl = "Free" if limit == 500 else "Tier"
    return f"🫦 {B(str(total))} ᴄᴀʀᴅs — {lbl} ʟɪᴍɪᴛ {B(str(limit))}. Checking first {B(str(limit))}."


# ═════════════════════════════════════════════════════════════════════════
# MASS CHECK PROGRESS
# ═════════════════════════════════════════════════════════════════════════
def format_mass_check_progress(pr, total, checked, duration, charged, live, dead):
    pct = (checked / total) if total > 0 else 0
    pct_num = int(pct * 100)

    eta_str = ""
    if checked > 0 and duration:
        parts = duration.split("m ")
        if len(parts) == 2:
            try:
                mins = int(parts[0])
                secs = int(parts[1].rstrip("s"))
                elapsed_s = mins * 60 + secs
                rate = elapsed_s / checked
                remaining = int((total - checked) * rate)
                eta_m = remaining // 60
                eta_s = remaining % 60
                eta_str = f" | ᴇᴛᴀ: {eta_m}m {eta_s}s"
            except (ValueError, ZeroDivisionError):
                pass

    return (
        f"{hdr()}\n\n{frame('ᴍᴀss ᴄʜᴇᴄᴋ')}\n\n"
        f"{e_cart()}   {B('ɢᴀᴛᴇᴡᴀʏ')}    : #Mass_Shopify\n"
        f"{e_money()}  {B('ʀᴀɴɢᴇ')}      : {pr}\n"
        f"{e_card()}   {B('ᴛᴏᴛᴀʟ')}      : {total}\n\n"
        f"{bar(pct)}\n"
        f"   {checked}/{total} ({pct_num}%)\n"
        f"{e_hourglass()} {B('ᴅᴜʀᴀᴛɪᴏɴ')}    : {duration}{eta_str}\n\n"
        f"{DS}\n"
        f"{e_heart()}   {B('ᴄʜᴀʀɢᴇᴅ')} : {charged}  {ratio(charged, total)}\n"
        f"{e_smile()}   {B('ʟɪᴠᴇ')}    : {live}  {ratio(live, total)}\n"
        f"{e_warning()} {B('ᴅᴇᴀᴅ')}    : {dead}  {ratio(dead, total)}\n\n"
        f"{D}"
    )


# ═════════════════════════════════════════════════════════════════════════
# MASS CHECK COMPLETE
# ═════════════════════════════════════════════════════════════════════════
def format_mass_check_complete(pr, total, duration, charged, live, dead):
    success = charged + live
    rate = int((success / total * 100)) if total > 0 else 0
    return (
        f"{hdr()}\n\n{frame('ᴄʜᴇᴄᴋ ᴄᴏᴍᴘʟᴇᴛᴇ')}\n\n"
        f"{e_cart()}   {B('ɢᴀᴛᴇᴡᴀʏ')}    : #Mass_Shopify\n"
        f"{e_money()}  {B('ʀᴀɴɢᴇ')}      : {pr}\n"
        f"{e_card()}   {B('ᴛᴏᴛᴀʟ')}      : {total}\n"
        f"{e_hourglass()} {B('ᴅᴜʀᴀᴛɪᴏɴ')}    : {duration}\n\n"
        f"{DS}\n"
        f"{e_heart()}   {B('ᴄʜᴀʀɢᴇᴅ')} : {charged}  {ratio(charged, total)}\n"
        f"{e_smile()}   {B('ʟɪᴠᴇ')}    : {live}  {ratio(live, total)}\n"
        f"{e_warning()} {B('ᴅᴇᴀᴅ')}    : {dead}  {ratio(dead, total)}\n\n"
        f"{DS}\n"
        f"📈  {B('sᴜᴄᴄᴇss')}  : {rate}%  {ratio(success, total, 12)}\n\n"
        f"{ftr()}"
    )


# ═════════════════════════════════════════════════════════════════════════
# CARD LISTS
# ═════════════════════════════════════════════════════════════════════════
def format_charged_cards_list(cards):
    lines = [f"{hdr()}\n\n{frame(f'ᴄʜᴀʀɢᴇᴅ ({len(cards)})')}\n"]
    for i, (card, r) in enumerate(cards, 1):
        lines.append(f"{e_heart()} {i}. {C(card.raw)}")
        lines.append(f"   {r.gateway} | ${r.price}")
    lines.append(f"\n{ftr()}")
    return "\n".join(lines)


def format_live_cards_list(cards):
    lines = [f"{hdr()}\n\n{frame(f'ʟɪᴠᴇ ({len(cards)})')}\n"]
    for i, (card, r) in enumerate(cards, 1):
        lines.append(f"{e_check_done()} {i}. {C(card.raw)}")
        lines.append(f"   {sc(r.message)}")
    lines.append(f"\n{ftr()}")
    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# PLANS
# ═════════════════════════════════════════════════════════════════════════
def format_plans():
    return (
        f"{e_gem_plans()} 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐏𝐋𝐀𝐍𝐒 {e_gem_plans()}\n{D}\n\n"
        f"{e_free()} {B('FREE')}\n├─ ᴡᴏʀᴋᴇʀs: 10\n├─ sᴘᴇᴇᴅ: ʟᴏᴡ\n└─ ғʀᴇᴇ ᴛʀɪᴀʟ\n\n"
        f"{e_bronze()} {B('BASIC')}\n├─ ʟɪᴍɪᴛ: 1,000/ʀᴜɴ\n├─ ᴡᴏʀᴋᴇʀs: 20\n├─ sᴘᴇᴇᴅ: ᴅᴇᴄᴇɴᴛ\n"
        f"├─ 7ᴅ → $2\n├─ 15ᴅ → $5\n└─ 30ᴅ → $7 {e_gem()} {B('BEST')}\n\n"
        f"{e_silver()} {B('PRO')}\n├─ ʟɪᴍɪᴛ: 5,000/ʀᴜɴ\n├─ ᴡᴏʀᴋᴇʀs: 30\n├─ sᴘᴇᴇᴅ: ᴍᴇᴅɪᴜᴍ\n"
        f"├─ 7ᴅ → $5\n├─ 15ᴅ → $7\n└─ 30ᴅ → $10 {e_gem()} {B('BEST')}\n\n"
        f"{e_gold()} {B('MAX')}\n├─ ʟɪᴍɪᴛ: 10,000/ʀᴜɴ\n├─ ᴡᴏʀᴋᴇʀs: 50\n├─ sᴘᴇᴇᴅ: ғᴀsᴛ\n"
        f"├─ 7ᴅ → $5\n├─ 15ᴅ → $10\n└─ 30ᴅ → $15 {e_gem()} {B('BEST')}\n\n"
        f"{e_crown()} {B('ULTRA')}\n├─ ʟɪᴍɪᴛ: 50,000/ʀᴜɴ\n├─ ᴡᴏʀᴋᴇʀs: 200\n├─ sᴘᴇᴇᴅ: ᴜʟᴛʀᴀ\n"
        f"├─ 7ᴅ → $12\n├─ 15ᴅ → $30\n└─ 30ᴅ → $50 {e_gem()} {B('BEST')}\n\n"
        f"{DS}\n"
        f"{e_check()} ᴜɴʟɪᴍɪᴛᴇᴅ ʀᴜɴs ᴅᴜʀɪɴɢ ᴀᴄᴛɪᴠᴇ ᴘʟᴀɴ\n"
        f"{e_check()} ᴄʜᴇᴄᴋ ʟɪᴍɪᴛ = ᴍᴀx ᴘᴇʀ sɪɴɢʟᴇ ʀᴜɴ\n"
        f"{e_check()} ᴡᴏʀᴋᴇʀs = ᴍᴀx ᴀᴄᴛɪᴠᴇ ᴛʜʀᴇᴀᴅs\n"
        f"{e_lightning()} ғᴀsᴛ ᴄʜᴇᴄᴋɪɴɢ\n"
        f"{e_lightning()} sᴛᴀʙʟᴇ ᴀᴄᴄᴇss\n"
        f"{e_lightning()} ʀᴇɢᴜʟᴀʀ ᴜᴘᴅᴀᴛᴇs\n"
        f"{DS}\n\n{B('ᴅᴍ')}: @rayzenqx {e_heart()}"
    )


# ═════════════════════════════════════════════════════════════════════════
# KEY REDEEMED
# ═════════════════════════════════════════════════════════════════════════
def format_key_redeemed(tier, expiry, limit, workers):
    return (
        f"{hdr()}\n\n{frame('ᴋᴇʏ ʀᴇᴅᴇᴇᴍᴇᴅ')}\n\n"
        f"{e_gem()}      {B('ᴛɪᴇʀ')}      : {tier}\n"
        f"{e_calendar()}      {B('ᴇxᴘɪʀᴇs')}   : {expiry}\n"
        f"{e_chart()}     {B('ʟɪᴍɪᴛ')}     : {limit}/ʀᴜɴ\n"
        f"{e_lightning()}     {B('ᴡᴏʀᴋᴇʀs')}  : {workers}\n\n"
        f"{ftr()}"
    )


def format_key_error():
    return f"{e_cross()} {B('ɪɴᴠᴀʟɪᴅ ᴋᴇʏ ᴏʀ ᴀʟʀᴇᴀᴅʏ ʀᴇᴅᴇᴇᴍᴇᴅ.')}\n\n{B('ᴜsᴀɢᴇ')}: {C('/redeem AURORA-XXXX-XXXX-XXXX-XXXX')}"


# ═════════════════════════════════════════════════════════════════════════
# BATCH KEY GENERATION (Evelyn-style)
# ═════════════════════════════════════════════════════════════════════════
def format_batch_keys_generated(tier, quantity, duration, keys, card_limit):
    """Format the batch key generation message — Evelyn style.
    
    Uses plain ``` code block for COPY button.
    Card limit formatted with commas (5,000).
    """
    # Format limit with commas
    limit_str = f"{card_limit:,}"

    # Keys in plain code block (triple backtick) — Telegram shows COPY button
    keys_text = "\n".join(keys)

    return (
        f"{e_gift()} <b>Generated {quantity} {tier} key(s)</b>\n"
        f"{e_card()} Limit: <b>{limit_str}</b> cards/chk · {duration} day(s) each\n\n"
        f"<code>{keys_text}</code>\n\n"
        f"Redeem: <code>/redeem KEY</code> or reply to this message with /redeem"
    )


def format_batch_redeem_success(tier, duration, expires_str, key, position, card_limit):
    """Format successful redemption from a batch (Evelyn-style with premium emoji)."""
    return (
        f"{e_check_done()} {B('Key redeemed!')}\n"
        f"{e_gem()} {B('Tier')}: {tier} ({card_limit} cards/chk)\n"
        f"{e_hourglass_v2()} {B('Duration')}: {duration} day(s)\n"
        f"{e_calendar()} {B('Expires')}: {expires_str}\n"
        f"{e_gem()} {B('Key')}: {C(key)} ({position})"
    )


def format_batch_all_redeemed():
    """All keys in batch are redeemed."""
    return f"{e_warning_alt()} {B('All keys in that message are already redeemed.')}"


def format_redeem_cooldown(cooldown_str):
    """Redeem cooldown active."""
    return (
        f"{e_hourglass_v2()} {B('Cooldown active.')}\n"
        f"You can redeem another key in {B(cooldown_str)}."
    )


def format_key_not_found():
    """Key not found in system."""
    return f"{e_cross()} {B('Key not found or invalid.')}"


def format_key_already_redeemed():
    """Key already redeemed by someone."""
    return f"{e_warning_alt()} {B('This key has already been redeemed.')}"


def format_genkey_usage():
    """Usage for /genkey."""
    return (
        f"{e_cross()} {B('Usage:')}\n"
        f"{C('/genkey <plan> <quantity> <duration_days>')}\n\n"
        f"{B('Example')}: {C('/genkey Pro 50 1')}\n\n"
        f"{B('Plans')}: FREE, BASIC, PRO, MAX, ULTRA"
    )


def format_status_user(tier, expires, expired, card_limit, workers):
    """User's /status showing active tier + remaining time."""
    if expired or tier == "FREE":
        return (
            f"{hdr()}\n\n{frame('sᴛᴀᴛᴜs')}\n\n"
            f"{e_gem()}  {B('ᴛɪᴇʀ')}    : {tier}\n"
            f"{e_chart()} {B('ʟɪᴍɪᴛ')}   : {card_limit}/ʀᴜɴ\n"
            f"{e_lightning()} {B('ᴡᴏʀᴋᴇʀs')}  : {workers}\n"
            f"{e_calendar()}  {B('ᴇxᴘɪʀᴇs')} : No active key\n\n"
            f"{ftr()}"
        )
    return (
        f"{hdr()}\n\n{frame('sᴛᴀᴛᴜs')}\n\n"
        f"{e_gem()}  {B('ᴛɪᴇʀ')}    : {tier}\n"
        f"{e_chart()} {B('ʟɪᴍɪᴛ')}   : {card_limit}/ʀᴜɴ\n"
        f"{e_lightning()} {B('ᴡᴏʀᴋᴇʀs')}  : {workers}\n"
        f"{e_calendar()}  {B('ᴇxᴘɪʀᴇs')} : {expires}\n\n"
        f"{ftr()}"
    )


# ═════════════════════════════════════════════════════════════════════════
# PROXY
# ═════════════════════════════════════════════════════════════════════════
def format_proxy_checking(count):
    return (
        f"{hdr()}\n\n{frame('ᴘʀᴏxʏ ᴄʜᴇᴄᴋ')}\n\n"
        f"{e_refresh()} {B(f'ᴄʜᴇᴄᴋɪɴɢ {count} ᴘʀᴏxɪᴇs...')}\n\n"
        f"{I('ᴏɴʟʏ ʟɪᴠᴇ ᴘʀᴏxɪᴇs ᴡɪʟʟ ʙᴇ ᴀᴅᴅᴇᴅ.')}\n\n{D}"
    )


def format_proxy_added(live, total):
    return (
        f"{hdr()}\n\n{frame('ᴘʀᴏxɪᴇs ᴀᴅᴅᴇᴅ')}\n\n"
        f"{e_check_done()} {B(f'ᴀᴅᴅᴇᴅ {live} ʟɪᴠᴇ ᴘʀᴏxɪᴇs!')}\n\n"
        f"{e_clipboard()} {B('ᴛᴏᴛᴀʟ')} : {total}\n\n{ftr()}"
    )


def format_proxy_cleaned(live, dead):
    return (
        f"{hdr()}\n\n{frame('ᴘʀᴏxʏ ᴄʟᴇᴀɴᴇᴅ')}\n\n"
        f"{e_refresh()} {B('ʀᴇ-ᴄʜᴇᴄᴋɪɴɢ...')}\n\n"
        f"{e_check_done()} {B('ʟɪᴠᴇ')} : {live}\n"
        f"{e_cross()} {B('ᴅᴇᴀᴅ')} : {dead} (ʀᴇᴍᴏᴠᴇᴅ)\n\n"
        f"{e_clipboard()} {B('ᴛᴏᴛᴀʟ')} : {live}\n\n{ftr()}"
    )


def format_proxy_cleared(count):
    return f"{hdr()}\n\n{frame('ᴘʀᴏxɪᴇs ᴄʟᴇᴀʀᴇᴅ')}\n\n{e_cross()} {B(f'ᴄʟᴇᴀʀᴇᴅ {count} ᴘʀᴏxɪᴇs.')}\n\n{D}"


# ═════════════════════════════════════════════════════════════════════════
# CC GENERATOR
# ═════════════════════════════════════════════════════════════════════════
def format_ccgen(cards, bin_prefix="RANDOM", count=10, fixed_month=None, fixed_year=None):
    """Format generated cards output with copy block."""
    from templates.emojis import e_gift
    cards_text = "\n".join(cards)

    expiry_label = "Random"
    if fixed_month and fixed_year:
        expiry_label = f"{fixed_month}/{fixed_year}"

    return (
        f"{hdr()}\n\n{frame('ᴠᴀʟɪᴅ ᴄᴄ ɢᴇɴ')}\n\n"
        f"{e_card()}   {B('ɢᴇɴᴇʀᴀᴛᴇᴅ')} : {count} ᴄᴀʀᴅ(s)\n"
        f"{e_card()}   {B('ʙɪɴ')}      : {bin_prefix}\n"
        f"{e_calendar()}  {B('ᴇxᴘɪʀʏ')}  : {expiry_label}\n\n"
        f"<code>{cards_text}</code>\n\n"
        f"{ftr()}"
    )


def format_ccgen_usage():
    """Usage instructions for /ccgen."""
    return (
        f"{e_cross()} {B('ᴜsᴀɢᴇ:')}\n\n"
        f"{C('/ccgen')}                       — 10 random cards\n"
        f"{C('/ccgen <count>')}               — N random cards\n"
        f"{C('/ccgen <bin> <count>')}         — N cards with BIN\n"
        f"{C('/ccgen <bin> <mm> <yyyy> <n>')} — N cards, fixed expiry\n\n"
        f"{B('ᴇxᴀᴍᴘʟᴇs:')}\n"
        f"{C('/ccgen 25')}\n"
        f"{C('/ccgen 479851 10')}\n"
        f"{C('/ccgen 479851 12 2028 5')}\n\n"
        f"{I('ᴍᴀx 50 ᴄᴀʀᴅs ᴘᴇʀ ɢᴇɴ.')}"
    )


def format_amazon_usage():
    """Usage for /amz."""
    return (
        f"{e_cross()} {B('ᴜsᴀɢᴇ:')}\n"
        f"{C('/amz 4532640527811643|12|2025|123')}\n\n"
        f"Or reply to a card message with {C('/amz')}\n\n"
        f"{I('sᴇᴛ ᴄᴏᴏᴋɪᴇs ғɪʀsᴛ:')} {C('/setcookies <your_amazon_cookies>')}"
    )


def format_massamz_usage():
    """Usage for /massamz."""
    return (
        f"{e_cross()} {B('ᴜsᴀɢᴇ:')}\n"
        f"Send {C('/massamz')} then upload a .txt file with cards.\n"
        f"One card per line: {C('NUMBER|MM|YYYY|CVV')}\n\n"
        f"{I('ᴇɴsᴜʀᴇ ʏᴏᴜ ʜᴀᴠᴇ ᴄᴏᴏᴋɪᴇs sᴇᴛ:')} {C('/setcookies <cookies>')}"
    )


def format_cookies_saved(set_at):
    """Cookies saved successfully."""
    return (
        f"{e_check_done()} {B('ᴀᴍᴀᴢᴏɴ ᴄᴏᴏᴋɪᴇs sᴀᴠᴇᴅ!')}\n\n"
        f"{e_calendar()} {B('sᴇᴛ ᴀᴛ')} : {set_at}\n"
        f"{I('ᴛᴏ ᴜᴘᴅᴀᴛᴇ: /setcookies <new_cookies>')}"
    )


def format_cookies_missing():
    """No cookies set."""
    return (
        f"{e_cross()} {B('ɴᴏ ᴀᴍᴀᴢᴏɴ ᴄᴏᴏᴋɪᴇs ғᴏᴜɴᴅ.')}\n\n"
        f"{B('sᴇᴛ ʏᴏᴜʀ ᴄᴏᴏᴋɪᴇs:')}\n"
        f"{C('/setcookies <your_cookies>')}\n\n"
        f"{I('ɢᴇᴛ ᴄᴏᴏᴋɪᴇs ғʀᴏᴍ ʙʀᴏᴡsᴇʀ ᴅᴇᴠᴛᴏᴏʟs (F12) → ɴᴇᴛᴡᴏʀᴋ → ᴄᴏᴘʏ ᴄᴏᴏᴋɪᴇ ʜᴇᴀᴅᴇʀ')}"
    )


def format_cookies_status(set_at):
    """Show cookies status."""
    return (
        f"{e_check_done()} {B('ᴄᴏᴏᴋɪᴇs ᴀᴄᴛɪᴠᴇ')}\n\n"
        f"{e_calendar()} {B('sᴇᴛ ᴀᴛ')} : {set_at}\n\n"
        f"{I('ᴜᴘᴅᴀᴛᴇ: /setcookies <new_cookies>')}\n"
        f"{I('ᴄʟᴇᴀʀ: /clearcookies')}"
    )


def format_cookies_cleared():
    """Cookies cleared."""
    return f"{e_cross()} {B('ᴀᴍᴀᴢᴏɴ ᴄᴏᴏᴋɪᴇs ᴄʟᴇᴀʀᴇᴅ.')}"


def format_cookies_usage():
    """Usage for /setcookies."""
    return (
        f"{e_cross()} {B('ᴜsᴀɢᴇ:')}\n"
        f"{C('/setcookies <your_amazon_cookies>')}\n\n"
        f"{I('ᴄᴏᴏᴋɪᴇs ғʀᴏᴍ ʙʀᴏᴡsᴇʀ ᴅᴇᴠᴛᴏᴏʟs (F12)')}\n"
        f"{I('→ ɴᴇᴛᴡᴏʀᴋ ᴛᴀʙ → ᴀɴʏ ᴀᴍᴀᴢᴏɴ ʀᴇQᴜᴇsᴛ → ᴄᴏᴘʏ ᴄᴏᴏᴋɪᴇ ʜᴇᴀᴅᴇʀ')}"
    )


# ═════════════════════════════════════════════════════════════════════════
# AMAZON CHECK
# ═════════════════════════════════════════════════════════════════════════
def format_amazon_check(status, card, response, bin_info=None, flag=""):
    """Format Amazon single check result.

    status: 'APPROVED' | 'DECLINED' | 'ERROR'
    """
    sm = {
        "APPROVED": (e_heart(),      "𝑨𝑷𝑷𝑹𝑶𝑽𝑬𝑫"),
        "DECLINED": (e_warning(),   "𝑫𝑬𝑪𝑳𝑰𝑵𝑬𝑫"),
        "ERROR":    (e_warning(),   "ᴇʀʀᴏʀ"),
    }
    ei, label = sm.get(status, (e_warning(), "ᴇʀʀᴏʀ"))

    # Full card for approved, masked for declined/error
    if status == "APPROVED":
        cc_show = grp(card.number)
        cc_full = f"{cc_show}|{card.month}|{card.year}|{card.cvv}"
    else:
        cc_full = card.masked

    bin_section = ""
    if bin_info:
        bn = f"{bin_info.get('brand','?')} − {bin_info.get('type','?')} − {bin_info.get('level','?')}"
        bin_section = (
            f"{DS}\n"
            f"{e_card()}   {B('ʙɪɴ')}      : {bn}\n"
            f"{e_globe()}  {B('ʙᴀɴᴋ')}     : {bin_info.get('bank','?')}\n"
            f"{e_globe_flag()} {B('ᴄᴏᴜɴᴛʀʏ')} : {bin_info.get('country','?')} {flag}\n"
        )

    return (
        f"{hdr()}\n\n"
        f"{frame(label)}\n"
        f"   {ei} {ei} {ei}\n\n"
        f"{e_card()}   {B('ᴄᴄ')}       : {C(cc_full)}\n"
        f"{e_cart()}   {B('ɢᴀᴛᴇᴡᴀʏ')}  : Amazon Auth\n"
        f"{e_memo()}   {B('ʀᴇsᴘᴏɴsᴇ')} : {sc(response)}\n\n"
        f"{bin_section}"
        f"{ftr()}"
    )


def format_amazon_checking(card):
    """Checking message for Amazon."""
    return (
        f"{hdr()}\n\n"
        f"{e_refresh()} {B('ᴄʜᴇᴄᴋɪɴɢ ᴏɴ ᴀᴍᴀᴢᴏɴ...')}\n"
        f"{e_card()} {C(grp_masked(card))}\n\n"
        f"{e_hourglass()} {I('ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...')}\n\n{D}"
    )


def format_amazon_mass_options(card_count):
    """Mass Amazon check options (before starting)."""
    return (
        f"{hdr()}\n\n{frame('ᴍᴀss ᴀᴍᴀᴢᴏɴ')}\n\n"
        f"{e_cart()}   {B('ɢᴀᴛᴇᴡᴀʏ')} : Amazon Auth (Leviatan)\n"
        f"{e_card()}   {B('ᴄᴀʀᴅs')}   : {card_count}\n\n"
        f"{e_refresh()} {B('sᴛᴀʀᴛɪɴɢ ᴍᴀss ᴄʜᴇᴄᴋ...')}\n\n{D}"
    )


def format_amazon_mass_progress(total, checked, duration, approved, declined, errors):
    """Progress for mass Amazon check."""
    pct = (checked / total) if total > 0 else 0
    pct_num = int(pct * 100)

    eta_str = ""
    if checked > 0 and duration:
        parts = duration.split("m ")
        if len(parts) == 2:
            try:
                mins = int(parts[0])
                secs = int(parts[1].rstrip("s"))
                elapsed_s = mins * 60 + secs
                rate = elapsed_s / checked
                remaining = int((total - checked) * rate)
                eta_m = remaining // 60
                eta_s = remaining % 60
                eta_str = f" | ᴇᴛᴀ: {eta_m}m {eta_s}s"
            except (ValueError, ZeroDivisionError):
                pass

    return (
        f"{hdr()}\n\n{frame('ᴍᴀss ᴀᴍᴀᴢᴏɴ')}\n\n"
        f"{e_cart()}   {B('ɢᴀᴛᴇᴡᴀʏ')}    : Amazon Auth\n"
        f"{e_card()}   {B('ᴛᴏᴛᴀʟ')}      : {total}\n\n"
        f"{bar(pct)}\n"
        f"   {checked}/{total} ({pct_num}%)\n"
        f"{e_hourglass()} {B('ᴅᴜʀᴀᴛɪᴏɴ')}    : {duration}{eta_str}\n\n"
        f"{DS}\n"
        f"{e_heart()}     {B('ᴀᴘᴘʀᴏᴠᴇᴅ')}  : {approved}  {ratio(approved, total)}\n"
        f"{e_warning()}   {B('ᴅᴇᴄʟɪɴᴇᴅ')} : {declined}  {ratio(declined, total)}\n"
        f"{e_cross()}     {B('ᴇʀʀᴏʀ')}     : {errors}  {ratio(errors, total)}\n\n"
        f"{D}"
    )


def format_amazon_mass_complete(total, duration, approved, declined, errors):
    """Final summary for mass Amazon check."""
    rate = int((approved / total * 100)) if total > 0 else 0
    return (
        f"{hdr()}\n\n{frame('ᴀᴍᴀᴢᴏɴ ᴄʜᴇᴄᴋ ᴄᴏᴍᴘʟᴇᴛᴇ')}\n\n"
        f"{e_cart()}   {B('ɢᴀᴛᴇᴡᴀʏ')}    : Amazon Auth\n"
        f"{e_card()}   {B('ᴛᴏᴛᴀʟ')}      : {total}\n"
        f"{e_hourglass()} {B('ᴅᴜʀᴀᴛɪᴏɴ')}    : {duration}\n\n"
        f"{DS}\n"
        f"{e_heart()}     {B('ᴀᴘᴘʀᴏᴠᴇᴅ')}  : {approved}  {ratio(approved, total)}\n"
        f"{e_warning()}   {B('ᴅᴇᴄʟɪɴᴇᴅ')} : {declined}  {ratio(declined, total)}\n"
        f"{e_cross()}     {B('ᴇʀʀᴏʀ')}     : {errors}  {ratio(errors, total)}\n\n"
        f"{DS}\n"
        f"📈  {B('ᴀᴘᴘʀᴏᴠᴀʟ ʀᴀᴛᴇ')} : {rate}%\n\n"
        f"{ftr()}"
    )


def format_amazon_approved_list(cards):
    """List of approved Amazon cards."""
    lines = [f"{hdr()}\n\n{frame(f'ᴀᴍᴀᴢᴏɴ ᴀᴘᴘʀᴏᴠᴇᴅ ({len(cards)})')}\n"]
    for i, (card, response) in enumerate(cards, 1):
        lines.append(f"{e_heart()} {i}. {C(card.raw)}")
        lines.append(f"   {sc(response)}")
    lines.append(f"\n{ftr()}")
    return "\n".join(lines)