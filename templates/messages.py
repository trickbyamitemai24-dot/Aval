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
def format_help_page(page: int):
    if page == 1:
        content = (
            f"{e_fire()} 𝑪𝑯𝑬𝑪𝑲𝑰𝑵𝑮 {e_fire()}\n{DS}\n"
            f"{e_card()}  /sh {I('cc')}      — Single Check (Shopify)\n"
            f"{e_card()}  /st {I('cc')}      — Single Check (Stripe)\n"
            f"{e_card()}  /amz {I('cc')}     — Single Check (Amazon)\n"
            f"{e_rocket()}  /chk       — Mass Check (.txt)\n"
            f"{e_rocket()}  /massamz   — Mass Amazon Check (.txt)\n"
            f"{e_play()}  /resume    — Resume interrupted mass check\n\n"
            f"<i>* Auto-detect: Paste any CC natively in chat to check instantly!</i>"
        )
    elif page == 2:
        content = (
            f"{e_satellite()} 𝑷𝑹𝑶𝑿𝑰𝑬𝑺 & 𝑼𝑻𝑰𝑳𝑺 {e_satellite()}\n{DS}\n"
            f"{e_shield()}   /addproxy   — Add your own proxies\n"
            f"{e_gear()}   /proxy      — Check & clean dead proxies\n"
            f"{e_trash()}   /clearproxy — Clear all proxies\n\n"
            f"{e_cart()}   /setcookies — Set Amazon cookies\n"
            f"{e_info()}   /cookies    — View cookie status\n"
            f"{e_broom()}   /clearcookies — Clear cookies\n\n"
            f"{e_search()}   /bin {I('bin')}    — Fast BIN Lookup\n"
            f"{e_joker()}   /ccgen      — Generate Luhn-valid cards"
        )
    else:
        content = (
            f"{e_gem()} 𝑼𝑺𝑬𝑹 & 𝑨𝑫𝑴𝑰𝑵 {e_gem()}\n{DS}\n"
            f"{e_key()}   /redeem {I('key')}  — Redeem access key\n"
            f"{e_info()}   /plans     — View pricing & tiers\n\n"
            f"<b>Owner & Admin Tools:</b>\n"
            f"{e_chart()}   /stats     — System statistics\n"
            f"{e_user()}   /user {I('id')}   — View user info\n"
            f"{e_key()}   /genkey    — Generate premium keys\n"
            f"{e_key()}   /keys      — List active keys\n"
            f"{e_card()}   /charged   — Recent hits\n"
            f"{e_globe()}   /chkall    — Test store health\n"
            f"{e_alert()}   /ban       — Ban user"
        )
        
    return (
        f"{hdr()}\n\n"
        f"{frame(f'COMMAND LIST (PAGE {page}/3)')}\n\n"
        f"{content}\n\n"
        f"{ftr()}"
    )

