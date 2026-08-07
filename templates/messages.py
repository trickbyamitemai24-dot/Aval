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
    # New premium emojis
    e_rocket, e_star, e_sparkles, e_crystal, e_comet,
    e_skull, e_target, e_hundred, e_chart_up,
    e_money_bag, e_cash_fly, e_bank, e_dollar,
    e_globe_us, e_satellite, e_shield, e_key, e_gear,
    e_heart_blue, e_heart_pink, e_devil, e_robot, e_user,
    e_trophy, e_bell, e_pin,
    e_green, e_red, e_yellow,
    e_alert, e_earth, e_ribbon, e_party, e_bulb, e_info,
    e_search, e_lock, e_unlock, e_link, e_pc,
    e_play, e_pause, e_stop_btn, e_broom, e_trash, e_new,
    e_folder, e_inbox, e_outbox, e_ticket, e_joker, e_timer,
    e_flag_us, e_stop,
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
    return f"{D}\n{e_crown()} {I('Owner: @rayzenqx')} {e_heart_blue()}"


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
            f"\n{e_chart_up()} 𝒀𝑶𝑼𝑹 𝑺𝑻𝑨𝑻𝑺 {e_chart_up()}\n{DS}\n"
            f"{e_target()}  {B('ᴄʜᴇᴄᴋs')}   : {checks}\n"
            f"{e_money_bag()}  {B('ᴄʜᴀʀɢᴇᴅ')} : {charged}\n"
            f"{e_green()}  {B('ʟɪᴠᴇ')}    : {live}\n\n"
        )

    return (
        f"{hdr()}\n\n"
        f"{frame('𝑾𝑬𝑳𝑪𝑶𝑴𝑬')}\n"
        f"   {e_sparkles()} {e_rocket()} {e_sparkles()}\n\n"
        f"{e_crown()}  {B('ᴛɪᴇʀ')}    : {tier}\n"
        f"{e_chart()} {B('ʟɪᴍɪᴛ')}   : {card_limit} ᴄᴀʀᴅs /ʀᴜɴ\n"
        f"{e_key()}  {B('ʀᴇᴅᴇᴇᴍ')}  : /redeem &lt;key&gt;\n\n"
        f"{stats_section}"
        f"{e_fire()} 𝑪𝑶𝑴𝑴𝑨𝑵𝑫𝑺 {e_fire()}\n{DS}\n"
        f"{e_card()}  /sh {I('cc')}     — Single Check (Shopify)\n"
        f"{e_card()}  /st {I('cc')}     — Single Check (Stripe)\n"
        f"{e_card()}  /amz {I('cc')}    — Single Check (Amazon)\n"
        f"{e_search()}  /bin {I('bin')}   — BIN Lookup\n"
        f"{e_joker()}  /ccgen           — Generate valid cards\n"
        f"{e_rocket()}  /chk      — Mass Check (.txt)\n"
        f"{e_rocket()}  /massamz  — Mass Amazon (.txt)\n"
        f"{e_play()} /resume   — Resume interrupted\n\n"
        f"{e_satellite()} 𝑷𝑹𝑶𝑿𝑰𝑶𝑺 {e_satellite()}\n{DS}\n"
        f"{e_shield()}  /addproxy   — Add proxies\n"
        f"{e_gear()}  /proxy      — Check &amp; clean\n"
        f"{e_trash()}  /clearproxy — Clear all\n\n"
        f"{e_cart()} 𝑨𝑴𝑨𝒁𝑶𝑵 𝑪𝑶𝑶𝑲𝑰𝑬𝑺 {e_cart()}\n{DS}\n"
        f"{e_lock()}  /setcookies — Set cookies\n"
        f"{e_info()}  /cookies    — View status\n"
        f"{e_broom()}  /clearcookies — Clear\n\n"
        f"{ftr()}"
    )


# ═════════════════════════════════════════════════════════════════════════
# SINGLE CHECK
# ═════════════════════════════════════════════════════════════════════════
def _ist_now() -> str:
    """Current time in IST (UTC+5:30) — ShopixRzr style."""
    from datetime import datetime, timedelta
    return (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%I:%M:%S %p")


def format_single_check(status, card, gateway, response, price, bin_info, flag=""):
    import html
    sm = {
        "CHARGED":  (e_money_bag(),  "𝑪𝑯𝑨𝑹𝑮𝑬𝑫"),
        "LIVE":     (e_check_done(), "𝑳𝑰𝑽𝑬 𝑪𝑨𝑹𝑫"),
        "LIVE_3DS": (e_check_done(), "𝑳𝑰𝑽𝑬 3DS"),
        "DEAD":     (e_skull(),      "𝑫𝑬𝑨𝑫 𝑪𝑨𝑹𝑫"),
    }
    ei, label = sm.get(status, (e_skull(), "𝑫𝑬𝑨𝑫 𝑪𝑨𝑹𝑫"))

    if status in ("CHARGED", "LIVE", "LIVE_3DS"):
        cc_show = grp(card.number)
        cc_full = f"{cc_show}|{card.month}|{card.year}|{card.cvv}"
    else:
        cc_full = card.masked

    brand_esc = html.escape(str(bin_info.get('brand','?')))
    type_esc = html.escape(str(bin_info.get('type','?')))
    level_esc = html.escape(str(bin_info.get('level','?')))
    bank_esc = html.escape(str(bin_info.get('bank','?')))
    country_esc = html.escape(str(bin_info.get('country','?')))
    gw_esc = html.escape(str(gateway))
    resp_esc = html.escape(sc(str(response)))

    bn = f"{brand_esc} − {type_esc} − {level_esc}"

    copy_section = ""
    if status in ("CHARGED", "LIVE", "LIVE_3DS"):
        copy_section = f"{e_clipboard()}  {B('ᴄᴏᴘʏ')}     : <code>{card.raw}</code>\n"

    return (
        f"{hdr()}\n\n"
        f"{frame(label)}\n"
        f"   {ei} {ei} {ei}\n\n"
        f"{e_card()}   {B('ᴄᴄ')}       : <tg-spoiler>{C(cc_full)}</tg-spoiler>\n"
        f"{copy_section}"
        f"{e_globe()}   {B('ɢᴀᴛᴇᴡᴀʏ')}  : {gw_esc}\n"
        f"{e_memo()}   {B('ʀᴇsᴘᴏɴsᴇ')} : {resp_esc}\n"
        f"{e_dollar()}  {B('ᴘʀɪᴄᴇ')}    : ${price}\n\n"
        f"{DS}\n"
        f"{e_search()}   {B('ʙɪɴ')}      : {bn}\n"
        f"{e_bank()}  {B('ʙᴀɴᴋ')}     : {bank_esc}\n"
        f"{e_earth()} {B('ᴄᴏᴜɴᴛʀʏ')} : {country_esc} {flag}\n"
        f"{e_timer()} {B('ᴛɪᴍᴇ')}    : {_ist_now()} IST\n\n"
        f"{ftr()}"
    )


# ═════════════════════════════════════════════════════════════════════════
# BIN
# ═════════════════════════════════════════════════════════════════════════
def format_bin(bin_info, flag=""):
    import html
    bank_esc = html.escape(str(bin_info.get('bank','?')))
    brand_esc = html.escape(str(bin_info.get('brand','?')))
    type_esc = html.escape(str(bin_info.get('type','?')))
    level_esc = html.escape(str(bin_info.get('level','?')))
    country_esc = html.escape(str(bin_info.get('country','?')))
    bin_esc = html.escape(str(bin_info.get('bin','?')))

    return (
        f"{hdr()}\n\n{frame('ʙɪɴ ʟᴏᴏᴋᴜᴘ')}\n\n"
        f"{e_card()}      {B('ʙɪɴ')}     : {bin_esc}\n"
        f"{e_bank()}      {B('ʙᴀɴᴋ')}   : {bank_esc}\n"
        f"{e_shield()}      {B('ʙʀᴀɴᴅ')}  : {brand_esc}\n"
        f"{e_chart()}     {B('ᴛʏᴘᴇ')}   : {type_esc}\n"
        f"{e_star()} {B('ʟᴇᴠᴇʟ')}  : {level_esc}\n"
        f"{e_earth()} {B('ᴄᴏᴜɴᴛʀʏ')} : {country_esc} {flag}\n\n"
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
        f"{e_search()}  /bin {I('bin')}    — BIN Lookup\n"
        f"{e_joker()}  /ccgen            — Generate Luhn-valid cards\n"
        f"{e_rocket()}  /chk       — Mass Check (.txt)\n"
        f"{e_rocket()}  /massamz   — Mass Amazon Check (.txt)\n"
        f"{e_play()} /resume    — Resume interrupted\n"
        f"{e_key()}  /redeem {I('key')}  — Redeem a key\n"
        f"{e_gem()} /plans     — View pricing\n\n"
        f"{e_satellite()} 𝑷𝑹𝑶𝑿𝑰𝑶𝑺 {e_satellite()}\n{DS}\n"
        f"{e_shield()}   /addproxy   — Add proxies\n"
        f"{e_gear()}   /proxy      — Check &amp; clean\n"
        f"{e_trash()}   /clearproxy — Clear all\n\n"
        f"{e_cart()} 𝑨𝑴𝑨𝒁𝑶𝑵 𝑪𝑶𝑶𝑲𝑰𝑬𝑺 {e_cart()}\n{DS}\n"
        f"{e_lock()}   /setcookies {I('cookies')} — Set Amazon cookies\n"
        f"{e_info()}   /cookies             — View cookie status\n"
        f"{e_broom()}   /clearcookies        — Clear cookies\n\n"
        f"{ftr()}"
    )


# ═════════════════════════════════════════════════════════════════════════
# ERRORS
# ═════════════════════════════════════════════════════════════════════════
def format_error(msg="An error occurred. Try again."):
    if msg.startswith("<tg-emoji") or msg.startswith("❌"):
        return msg
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
        f"{e_search()} {B('ᴄʜᴇᴄᴋɪɴɢ ᴄᴀʀᴅ...')}\n"
        f"{e_card()} {C(grp_masked(card))}\n\n"
        f"{e_hourglass_v2()} {I('ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...')}\n\n{D}"
    )


# ═════════════════════════════════════════════════════════════════════════
# MASS CHECK OPTIONS
# ═════════════════════════════════════════════════════════════════════════
def format_mass_check_options(c5, c10, call, cc, warn="", chq=0, cv40=0, csureship=0, call_combined=0):
    t = (
        f"{hdr()}\n\n{frame('ᴍᴀss ᴄʜᴇᴄᴋ')}\n\n"
        f"{e_folder()}  {B('sᴏᴜʀᴄᴇ')} : Global Sites\n"
        f"{e_target()} sᴇʟᴇᴄᴛ sɪᴛᴇs ᴘʀɪᴄᴇ ʀᴀɴɢᴇ:\n\n"
        f"   • $1 − $5        ({c5})\n"
        f"   • $1 − $10       ({c10})\n"
        f"   • Working         ({call})\n"
        f"   • {e_gem()} HQ            ({chq})\n"
        f"   • {e_lightning()} V40            ({cv40})\n"
        f"   • {e_shield()} Sureship     ({csureship})\n"
        f"   • {e_globe()} ALL Sites    ({call_combined})\n\n"
        f"{e_card()}  {B('ᴄᴀʀᴅs')}  : {cc}\n"
    )
    if warn:
        t += f"\n{warn}"
    return t


def format_mass_check_limit_warning(total, limit):
    lbl = "Free" if limit == 500 else "Tier"
    return f"{e_warning_alt()} {B(str(total))} ᴄᴀʀᴅs — {lbl} ʟɪᴍɪᴛ {B(str(limit))}. Checking first {B(str(limit))}."


# ═════════════════════════════════════════════════════════════════════════
# MASS CHECK PROGRESS
# ═════════════════════════════════════════════════════════════════════════
def format_mass_check_progress(price_range, total, checked, duration, charged, live, dead):
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
        f"{e_dollar()}  {B('ʀᴀɴɢᴇ')}      : {price_range}\n"
        f"{e_card()}   {B('ᴛᴏᴛᴀʟ')}      : {total}\n\n"
        f"{bar(pct)}\n"
        f"   {checked}/{total} ({pct_num}%)\n"
        f"{e_timer()} {B('ᴅᴜʀᴀᴛɪᴏɴ')}    : {duration}{eta_str}\n\n"
        f"{DS}\n"
        f"{e_money_bag()}   {B('ᴄʜᴀʀɢᴇᴅ')} : {charged}  {ratio(charged, total)}\n"
        f"{e_green()}   {B('ʟɪᴠᴇ')}    : {live}  {ratio(live, total)}\n"
        f"{e_skull()}   {B('ᴅᴇᴀᴅ')}    : {dead}  {ratio(dead, total)}\n\n"
        f"{D}"
    )


# ═════════════════════════════════════════════════════════════════════════
# MASS CHECK COMPLETE
# ═════════════════════════════════════════════════════════════════════════
def format_mass_check_complete(price_range, total, duration, charged, live, dead):
    success = charged + live
    rate = int((success / total * 100)) if total > 0 else 0
    return (
        f"{hdr()}\n\n{frame('ᴄʜᴇᴄᴋ ᴄᴏᴍᴘʟᴇᴛᴇ')}\n\n"
        f"{e_cart()}   {B('ɢᴀᴛᴇᴡᴀʏ')}    : #Mass_Shopify\n"
        f"{e_dollar()}  {B('ʀᴀɴɢᴇ')}      : {price_range}\n"
        f"{e_card()}   {B('ᴛᴏᴛᴀʟ')}      : {total}\n"
        f"{e_timer()} {B('ᴅᴜʀᴀᴛɪᴏɴ')}    : {duration}\n\n"
        f"{DS}\n"
        f"{e_money_bag()}   {B('ᴄʜᴀʀɢᴇᴅ')} : {charged}  {ratio(charged, total)}\n"
        f"{e_green()}   {B('ʟɪᴠᴇ')}    : {live}  {ratio(live, total)}\n"
        f"{e_skull()}   {B('ᴅᴇᴀᴅ')}    : {dead}  {ratio(dead, total)}\n\n"
        f"{DS}\n"
        f"{e_chart_up()}  {B('sᴜᴄᴄᴇss')}  : {rate}%  {ratio(success, total, 12)}\n\n"
        f"{ftr()}"
    )


# ═════════════════════════════════════════════════════════════════════════
# CARD LISTS
# ═════════════════════════════════════════════════════════════════════════
def format_charged_cards_list(cards):
    lines = [f"{hdr()}\n\n{frame(f'ᴄʜᴀʀɢᴇᴅ ({len(cards)})')}\n"]
    for i, (card, r) in enumerate(cards, 1):
        lines.append(f"{e_money_bag()} {i}. {C(card.raw)}")
        lines.append(f"   {r.gateway} | ${r.price}")
    lines.append(f"\n{ftr()}")
    return "\n".join(lines)


def format_live_cards_list(cards):
    lines = [f"{hdr()}\n\n{frame(f'ʟɪᴠᴇ ({len(cards)})')}\n"]
    for i, (card, r) in enumerate(cards, 1):
        lines.append(f"{e_green()} {i}. {C(card.raw)}")
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
        f"{C('/genkey &lt;plan&gt; &lt;quantity&gt; &lt;duration_days&gt;')}\n\n"
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
        f"{C('/ccgen &lt;count&gt;')}               — N random cards\n"
        f"{C('/ccgen &lt;bin&gt; &lt;count&gt;')}         — N cards with BIN\n"
        f"{C('/ccgen &lt;bin&gt; &lt;mm&gt; &lt;yyyy&gt; &lt;n&gt;')} — N cards, fixed expiry\n\n"
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
        f"{I('sᴇᴛ ᴄᴏᴏᴋɪᴇs ғɪʀsᴛ:')} {C('/setcookies &lt;your_amazon_cookies&gt;')}"
    )


def format_massamz_usage():
    """Usage for /massamz."""
    return (
        f"{e_cross()} {B('ᴜsᴀɢᴇ:')}\n"
        f"Send {C('/massamz')} then upload a .txt file with cards.\n"
        f"One card per line: {C('NUMBER|MM|YYYY|CVV')}\n\n"
        f"{I('ᴇɴsᴜʀᴇ ʏᴏᴜ ʜᴀᴠᴇ ᴄᴏᴏᴋɪᴇs sᴇᴛ:')} {C('/setcookies &lt;cookies&gt;')}"
    )


def format_cookies_saved(set_at):
    """Cookies saved successfully."""
    return (
        f"{e_check_done()} {B('ᴀᴍᴀᴢᴏɴ ᴄᴏᴏᴋɪᴇs sᴀᴠᴇᴅ!')}\n\n"
        f"{e_calendar()} {B('sᴇᴛ ᴀᴛ')} : {set_at}\n"
        f"{I('ᴛᴏ ᴜᴘᴅᴀᴛᴇ: /setcookies &lt;new_cookies&gt;')}"
    )


def format_cookies_missing():
    """No cookies set."""
    return (
        f"{e_cross()} {B('ɴᴏ ᴀᴍᴀᴢᴏɴ ᴄᴏᴏᴋɪᴇs ғᴏᴜɴᴅ.')}\n\n"
        f"{B('sᴇᴛ ʏᴏᴜʀ ᴄᴏᴏᴋɪᴇs:')}\n"
        f"{C('/setcookies &lt;your_cookies&gt;')}\n\n"
        f"{I('ɢᴇᴛ ᴄᴏᴏᴋɪᴇs ғʀᴏᴍ ʙʀᴏᴡsᴇʀ ᴅᴇᴠᴛᴏᴏʟs (F12) → ɴᴇᴛᴡᴏʀᴋ → ᴄᴏᴘʏ ᴄᴏᴏᴋɪᴇ ʜᴇᴀᴅᴇʀ')}"
    )


def format_cookies_status(set_at):
    """Show cookies status."""
    return (
        f"{e_check_done()} {B('ᴄᴏᴏᴋɪᴇs ᴀᴄᴛɪᴠᴇ')}\n\n"
        f"{e_calendar()} {B('sᴇᴛ ᴀᴛ')} : {set_at}\n\n"
        f"{I('ᴜᴘᴅᴀᴛᴇ: /setcookies &lt;new_cookies&gt;')}\n"
        f"{I('ᴄʟᴇᴀʀ: /clearcookies')}"
    )


def format_cookies_cleared():
    """Cookies cleared."""
    return f"{e_cross()} {B('ᴀᴍᴀᴢᴏɴ ᴄᴏᴏᴋɪᴇs ᴄʟᴇᴀʀᴇᴅ.')}"


def format_cookies_usage():
    """Usage for /setcookies."""
    return (
        f"{e_cross()} {B('ᴜsᴀɢᴇ:')}\n"
        f"{C('/setcookies &lt;your_amazon_cookies&gt;')}\n\n"
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
    import html
    sm = {
        "APPROVED": (e_money_bag(),  "𝑨𝑷𝑷𝑹𝑶𝑽𝑬𝑫"),
        "DECLINED": (e_skull(),     "𝑫𝑬𝑪𝑳𝑰𝑵𝑬𝑫"),
        "ERROR":    (e_warning(),   "ᴇʀʀᴏʀ"),
    }
    ei, label = sm.get(status, (e_warning(), "ᴇʀʀᴏʀ"))

    # Full card for approved, masked for declined/error
    if status == "APPROVED":
        cc_show = grp(card.number)
        cc_full = f"{cc_show}|{card.month}|{card.year}|{card.cvv}"
    else:
        cc_full = card.masked

    resp_esc = html.escape(sc(str(response)))

    copy_section = ""
    if status == "APPROVED":
        copy_section = f"{e_clipboard()}  {B('ᴄᴏᴘʏ')}     : <code>{card.raw}</code>\n"

    bin_section = ""
    if bin_info:
        brand_esc = html.escape(str(bin_info.get('brand','?')))
        type_esc = html.escape(str(bin_info.get('type','?')))
        level_esc = html.escape(str(bin_info.get('level','?')))
        bank_esc = html.escape(str(bin_info.get('bank','?')))
        country_esc = html.escape(str(bin_info.get('country','?')))
        bn = f"{brand_esc} − {type_esc} − {level_esc}"
        bin_section = (
            f"{DS}\n"
            f"{e_search()}   {B('ʙɪɴ')}      : {bn}\n"
            f"{e_bank()}  {B('ʙᴀɴᴋ')}     : {bank_esc}\n"
            f"{e_earth()} {B('ᴄᴏᴜɴᴛʀʏ')} : {country_esc} {flag}\n"
        )

    return (
        f"{hdr()}\n\n"
        f"{frame(label)}\n"
        f"   {ei} {ei} {ei}\n\n"
        f"{e_card()}   {B('ᴄᴄ')}       : {C(cc_full)}\n"
        f"{copy_section}"
        f"{e_globe()}   {B('ɢᴀᴛᴇᴡᴀʏ')}  : Amazon Auth\n"
        f"{e_memo()}   {B('ʀᴇsᴘᴏɴsᴇ')} : {resp_esc}\n\n"
        f"{bin_section}"
        f"{ftr()}"
    )


def format_amazon_checking(card):
    """Checking message for Amazon."""
    return (
        f"{hdr()}\n\n"
        f"{e_search()} {B('ᴄʜᴇᴄᴋɪɴɢ ᴏɴ ᴀᴍᴀᴢᴏɴ...')}\n"
        f"{e_card()} {C(grp_masked(card))}\n\n"
        f"{e_hourglass_v2()} {I('ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...')}\n\n{D}"
    )


def format_amazon_mass_options(card_count):
    """Mass Amazon check options (before starting)."""
    return (
        f"{hdr()}\n\n{frame('ᴍᴀss ᴀᴍᴀᴢᴏɴ')}\n\n"
        f"{e_globe()}   {B('ɢᴀᴛᴇᴡᴀʏ')} : Amazon Auth (Leviatan)\n"
        f"{e_card()}   {B('ᴄᴀʀᴅs')}   : {card_count}\n\n"
        f"{e_rocket()} {B('sᴛᴀʀᴛɪɴɢ ᴍᴀss ᴄʜᴇᴄᴋ...')}\n\n{D}"
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
        f"{e_globe()}   {B('ɢᴀᴛᴇᴡᴀʏ')}    : Amazon Auth\n"
        f"{e_card()}   {B('ᴛᴏᴛᴀʟ')}      : {total}\n\n"
        f"{bar(pct)}\n"
        f"   {checked}/{total} ({pct_num}%)\n"
        f"{e_timer()} {B('ᴅᴜʀᴀᴛɪᴏɴ')}    : {duration}{eta_str}\n\n"
        f"{DS}\n"
        f"{e_money_bag()}     {B('ᴀᴘᴘʀᴏᴠᴇᴅ')}  : {approved}  {ratio(approved, total)}\n"
        f"{e_skull()}   {B('ᴅᴇᴄʟɪɴᴇᴅ')} : {declined}  {ratio(declined, total)}\n"
        f"{e_warning()}     {B('ᴇʀʀᴏʀ')}     : {errors}  {ratio(errors, total)}\n\n"
        f"{D}"
    )


def format_amazon_mass_complete(total, duration, approved, declined, errors):
    """Final summary for mass Amazon check."""
    rate = int((approved / total * 100)) if total > 0 else 0
    return (
        f"{hdr()}\n\n{frame('ᴀᴍᴀᴢᴏɴ ᴄʜᴇᴄᴋ ᴄᴏᴍᴘʟᴇᴛᴇ')}\n\n"
        f"{e_globe()}   {B('ɢᴀᴛᴇᴡᴀʏ')}    : Amazon Auth\n"
        f"{e_card()}   {B('ᴛᴏᴛᴀʟ')}      : {total}\n"
        f"{e_timer()} {B('ᴅᴜʀᴀᴛɪᴏɴ')}    : {duration}\n\n"
        f"{DS}\n"
        f"{e_money_bag()}     {B('ᴀᴘᴘʀᴏᴠᴇᴅ')}  : {approved}  {ratio(approved, total)}\n"
        f"{e_skull()}   {B('ᴅᴇᴄʟɪɴᴇᴅ')} : {declined}  {ratio(declined, total)}\n"
        f"{e_warning()}     {B('ᴇʀʀᴏʀ')}     : {errors}  {ratio(errors, total)}\n\n"
        f"{DS}\n"
        f"{e_chart_up()}  {B('ᴀᴘᴘʀᴏᴠᴀʟ ʀᴀᴛᴇ')} : {rate}%\n\n"
        f"{ftr()}"
    )


def format_amazon_approved_list(cards):
    """List of approved Amazon cards."""
    lines = [f"{hdr()}\n\n{frame(f'ᴀᴍᴀᴢᴏɴ ᴀᴘᴘʀᴏᴠᴇᴅ ({len(cards)})')}\n"]
    for i, (card, response) in enumerate(cards, 1):
        lines.append(f"{e_money_bag()} {i}. {C(card.raw)}")
        lines.append(f"   {sc(response)}")
    lines.append(f"\n{ftr()}")
    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# CHECK ALL SITES
# ═════════════════════════════════════════════════════════════════════════

def format_chkall_start(card_masked, total, workers):
    """Initial 'starting' message for /chkall."""
    return (
        f"{hdr()}\n\n{frame('ᴄʜᴇᴄᴋ ᴀʟʟ sɪᴛᴇs')}\n\n"
        f"{e_card()}   {B('ᴄᴀʀᴅ')}     : {C(card_masked)}\n"
        f"{e_globe()}  {B('sᴛᴏʀᴇs')}   : {total}\n"
        f"{e_lightning()} {B('ᴡᴏʀᴋᴇʀs')}  : {workers} (ᴘᴀʀᴀʟʟᴇʟ)\n\n"
        f"{DS}\n"
        f"{e_cross()}  {B('ʙᴀᴅ sᴛᴏʀᴇs ᴡɪʟʟ ʙᴇ ғʟᴀɢɢᴇᴅ ғᴏʀ ᴅᴇʟᴇᴛɪᴏɴ')}\n\n"
        f"{e_refresh()} {I('sᴛᴀʀᴛɪɴɢ...')}\n\n{D}"
    )


def format_chkall_progress(card_masked, checked, total, duration,
                           charged, live, good, bad):
    """Live progress update for /chkall."""
    pct = (checked / total) if total > 0 else 0
    pct_num = int(pct * 100)

    # ETA
    eta_str = ""
    if checked > 0 and duration > 0:
        rate = duration / checked
        remaining = int((total - checked) * rate)
        eta_m = remaining // 60
        eta_s = remaining % 60
        eta_str = f" | ᴇᴛᴀ: {eta_m}m {eta_s}s"

    m = int(duration // 60)
    s = int(duration % 60)

    return (
        f"{hdr()}\n\n{frame('ᴄʜᴇᴄᴋ ᴀʟʟ sɪᴛᴇs')}\n\n"
        f"{e_card()}   {B('ᴄᴀʀᴅ')}      : {C(card_masked)}\n"
        f"{e_globe()}  {B('sᴛᴏʀᴇs')}    : {total}\n\n"
        f"{bar(pct)}\n"
        f"   {checked}/{total} ({pct_num}%)\n"
        f"{e_timer()} {B('ᴅᴜʀᴀᴛɪᴏɴ')}    : {m}m {s}s{eta_str}\n\n"
        f"{DS}\n"
        f"{e_money_bag()}         {B('ᴄʜᴀʀɢᴇᴅ')}  : {charged}  {ratio(charged, total)}\n"
        f"{e_green()}   {B('ʟɪᴠᴇ')}     : {live}  {ratio(live, total)}\n"
        f"{e_check_done()}   {B('ɢᴏᴏᴅ')}     : {good}  {ratio(good, total)}\n"
        f"{e_skull()}         {B('ʙᴀᴅ')}      : {bad}  {ratio(bad, total)}\n\n"
        f"{D}"
    )


def format_chkall_complete(card_masked, total, duration,
                           charged_stores, live_stores,
                           good_count, bad_stores):
    """Final result message for /chkall (no bad stores to delete)."""
    m = int(duration // 60)
    s = int(duration % 60)
    success = len(charged_stores) + len(live_stores)
    rate = int((success / total * 100)) if total > 0 else 0

    t = (
        f"{hdr()}\n\n{frame('ᴄʜᴇᴄᴋ ᴀʟʟ sɪᴛᴇs — ᴄᴏᴍᴘʟᴇᴛᴇ')}\n\n"
        f"{e_card()}   {B('ᴄᴀʀᴅ')}       : {C(card_masked)}\n"
        f"{e_globe()}  {B('sᴛᴏʀᴇs')}     : {total}\n"
        f"{e_timer()} {B('ᴅᴜʀᴀᴛɪᴏɴ')}     : {m}m {s}s\n\n"
        f"{DS}\n"
    )

    # Charged section
    t += f"{e_money_bag()}   {B('ᴄʜᴀʀɢᴇᴅ')}  : {len(charged_stores)}\n"
    for url, price in charged_stores[:10]:
        t += f"   {e_money_bag()} {url} — ${price}\n"
    if len(charged_stores) > 10:
        t += f"   {I(f'... ᴀɴᴅ {len(charged_stores) - 10} ᴍᴏʀᴇ')}\n"

    # Live section
    t += f"\n{e_green()} {B('ʟɪᴠᴇ')}     : {len(live_stores)}\n"
    for url, msg in live_stores[:10]:
        t += f"   {e_green()} {url} — {sc(msg)}\n"
    if len(live_stores) > 10:
        t += f"   {I(f'... ᴀɴᴅ {len(live_stores) - 10} ᴍᴏʀᴇ')}\n"

    # Summary
    t += (
        f"\n{DS}\n"
        f"{e_check_done()} {B('ɢᴏᴏᴅ sᴛᴏʀᴇs')}  : {good_count}  {ratio(good_count, total)}\n"
        f"{e_skull()}   {B('ʙᴀᴅ sᴛᴏʀᴇs')}   : {len(bad_stores)}  {ratio(len(bad_stores), total)}\n"
        f"{e_chart_up()}  {B('sᴜᴄᴄᴇss')}      : {rate}%  {ratio(success, total, 12)}\n\n"
    )

    if not bad_stores:
        t += f"{e_sparkles()} {B('ᴀʟʟ sᴛᴏʀᴇs ᴀʀᴇ ʜᴇᴀʟᴛʜʏ!')}\n\n"

    t += ftr()
    return t


def format_chkall_bad_stores(bad_stores):
    """Bad stores breakdown appended after the complete message."""
    # Group by error type
    error_counts = {}
    for _, _, reason in bad_stores:
        error_counts[reason] = error_counts.get(reason, 0) + 1

    t = (
        f"\n{e_cross()} {B('ʙᴀᴅ sᴛᴏʀᴇs ғʟᴀɢɢᴇᴅ ғᴏʀ ᴅᴇʟᴇᴛɪᴏɴ:')}\n"
        f"{I('sᴛᴏʀᴇs ᴡɪᴛʜ ᴇʀʀᴏʀs (ɴᴏ ᴘʀᴏᴅᴜᴄᴛs, ᴛɪᴍᴇᴏᴜᴛ, ᴅɴs ғᴀɪʟ, ᴇᴛᴄ.)')}\n\n"
    )
    for reason, count in sorted(error_counts.items(), key=lambda x: -x[1]):
        t += f"   • {sc(reason)}: {B(str(count))} sᴛᴏʀᴇs\n"

    t += (
        f"\n{DS}\n"
        f"{e_cross()} {B('ᴛᴏᴛᴀʟ ᴛᴏ ᴅᴇʟᴇᴛᴇ')}: {B(str(len(bad_stores)))} sᴛᴏʀᴇs\n\n"
        f"{I('ᴘʀᴇss ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴀᴘᴘʀᴏᴠᴇ ᴅᴇʟᴇᴛɪᴏɴ.')}"
    )
    return t


def format_chkall_usage():
    """Usage for /chkall."""
    return (
        f"{hdr()}\n\n{frame('ᴄʜᴇᴄᴋ ᴀʟʟ sɪᴛᴇs')}\n\n"
        f"{e_cross()} {B('ᴜsᴀɢᴇ:')}\n"
        f"{C('/chkall site 4798510629051356|12|2028|893')}\n\n"
        f"{I('ᴄʜᴇᴄᴋs ᴏɴᴇ ᴄᴀʀᴅ ᴀɢᴀɪɴsᴛ ᴀʟʟ sᴛᴏʀᴇs.')}\n"
        f"{I('ʙᴀᴅ/ᴇʀʀᴏʀ sᴛᴏʀᴇs ᴀʀᴇ ғʟᴀɢɢᴇᴅ ғᴏʀ ᴅᴇʟᴇᴛɪᴏɴ.')}\n\n"
        f"{ftr()}"
    )


def format_chkall_deleted(deleted, failed, files_modified, remaining):
    """Deletion complete message."""
    return (
        f"{hdr()}\n\n{frame('ᴅᴇʟᴇᴛɪᴏɴ ᴄᴏᴍᴘʟᴇᴛᴇ')}\n\n"
        f"{e_cross()}         {B('ᴅᴇʟᴇᴛᴇᴅ')}    : {deleted} sᴛᴏʀᴇs\n"
        f"{e_warning()}       {B('ғᴀɪʟᴇᴅ')}     : {failed}\n"
        f"{e_clipboard()}     {B('ғɪʟᴇs')}      : {files_modified} ᴍᴏᴅɪғɪᴇᴅ\n"
        f"{e_globe()}         {B('ʀᴇᴍᴀɪɴɪɴɢ')}  : {remaining} sᴛᴏʀᴇs\n\n"
        f"{ftr()}"
    )


def format_chkall_cancelled():
    """Deletion cancelled message."""
    return (
        f"{hdr()}\n\n{frame('ᴅᴇʟᴇᴛɪᴏɴ ᴄᴀɴᴄᴇʟʟᴇᴅ')}\n\n"
        f"{e_cross()} {B('ʙᴀᴅ sᴛᴏʀᴇs ᴋᴇᴘᴛ. ɴᴏ ᴄʜᴀɴɢᴇs ᴍᴀᴅᴇ.')}\n\n"
        f"{ftr()}"
    )
def format_processing(title, message):
    return (
        f"{hdr()}\n\n"
        f"{frame(title)}\n\n"
        f"{e_refresh()} {B(message)}\n\n"
        f"{ftr()}"
    )
