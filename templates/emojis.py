import re

# ═══════════════════════════════════════════════════════════════════
# GOD-LEVEL PREMIUM EMOJI ENGINE — Aurora Checker
# Merged from premium_structure.md + user's expanded emoji bank
# ═══════════════════════════════════════════════════════════════════

EMOJI_IDS = {
    # ── Core UI ───────────────────────────────────────────────────
    "lightning":    "6174996123522959140",
    "fire":         "5039644681583985437",
    "sparkles":     "5040016479722931047",
    "rocket":       "6174445826543191998",
    "star":         "5042061201983407048",
    "comet":        "5224607267797606837",
    "crystal":      "5042302287087666158",

    # ── Status ────────────────────────────────────────────────────
    "check_done":   "5278327121008167894",
    "cross":        "5040042498634810056",
    "warning":      "5420323339723881652",
    "check":        "5206607081334906820",
    "stop":         "6181277564732972292",
    "alert":        "5039671744172917707",
    "green_dot":    "5039928501612839813",
    "red_dot":      "5042042652019655612",
    "yellow_dot":   "6025833352441893055",

    # ── Finance ───────────────────────────────────────────────────
    "card":         "5447453226498552490",
    "money_bag":    "5039789890133296083",
    "dollar":       "5447579253723918909",
    "money":        "5409048419211682843",
    "cash_fly":     "5837027045376271166",
    "bank":         "6089185885289454318",

    # ── Cards & Check ─────────────────────────────────────────────
    "cart":         "5447319442562251569",
    "memo":         "5444889156792646660",
    "chart":        "5042290883949495533",
    "chart_up":     "5039808285478224750",
    "chart_down":   "5039759318556083411",
    "target":       "5039905162760553480",
    "skull":        "5042209657527993345",
    "hundred":      "5042297717242463211",

    # ── Network & System ──────────────────────────────────────────
    "globe":        "6321225560789877992",
    "globe_us":     "5447602197439218445",
    "globe_flag":   "5445326466067754897",
    "satellite":    "5447448489149625830",
    "gear":         "5445059250382469069",
    "shield":       "5042328396193864923",
    "key":          "5399885604701880145",
    "lock":         "5445059250382469069",
    "unlock":       "5445373981290952548",
    "link":         "5042101437237036298",
    "search":       "5042302287087666158",
    "pc":           "5039579582764680065",
    "mobile":       "5445033158456145975",

    # ── People & Fun ──────────────────────────────────────────────
    "crown":        "5039727497143387500",
    "user":         "5992129361090711368",
    "robot":        "6174896506051495705",
    "devil":        "6336664426325740768",
    "alien":        "6181389246767570324",
    "heart_blue":   "5300842752618018643",
    "heart_pink":   "5039643719511311434",
    "heart_red":    "5040072842578756396",
    "smile":        "5303438381743618017",

    # ── Tiers ─────────────────────────────────────────────────────
    "gem":          "5427168083074628963",
    "gem_plans":    "5215191209131123104",
    "trophy":       "6089185885289454318",
    "gold":         "6179279816529814743",
    "silver":       "6179279816529814743",
    "bronze":       "5453902265922376865",
    "free":         "5406756500108501710",

    # ── Time ──────────────────────────────────────────────────────
    "hourglass":    "5445350406215465190",
    "hourglass_v2": "5042036407137207122",
    "timer":        "6186053057265016346",
    "calendar":     "6168242008277125889",

    # ── Files & Data ──────────────────────────────────────────────
    "clipboard":    "5445260044398524944",
    "folder":       "6026239398650056451",
    "inbox":        "5443127283898405358",
    "outbox":       "5445355530111437729",
    "pin":          "5397782960512444700",
    "bell":         "5042111805288089118",
    "mailbox":      "5445163772706582819",

    # ── Controls ──────────────────────────────────────────────────
    "refresh":      "5348386034835015762",
    "play":         "5039753786638205957",
    "pause":        "5042036407137207122",
    "stop_btn":     "5134537521518085000",
    "broom":        "5039751080808809534",
    "trash":        "5039614900280754969",
    "new":          "5041852827350074289",

    # ── Misc ──────────────────────────────────────────────────────
    "gift":         "6089193719309801680",
    "ribbon":       "5039953030171067177",
    "ticket":       "5377624166436445368",
    "bulb":         "5042264341051605743",
    "joker":        "6028206863038811654",
    "party":        "5039778134807806727",
    "info":         "5334544901428229844",
    "flag_us":      "6034969533859499947",
    "earth":        "5447410659077661506",
    "warning_alt":  "5447381715293074599",
    "white_heart":  "5764979527331615949",
}

TG_EMOJI_RE = re.compile(r'<tg-emoji\s+emoji-id="\d+">(.*?)</tg-emoji>', re.S)

def strip_tg_emoji(s: str) -> str:
    """Remove custom emoji tags, keep fallback emoji. Use for button labels."""
    return TG_EMOJI_RE.sub(r'\1', s or '')

def emoji(name: str, fallback: str = "") -> str:
    eid = EMOJI_IDS.get(name)
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
    return fallback


# ── Core ──────────────────────────────────────────────────────────
def e_lightning():   return emoji("lightning", "⚡")
def e_fire():        return emoji("fire", "🔥")
def e_sparkles():    return emoji("sparkles", "✨")
def e_rocket():      return emoji("rocket", "🚀")
def e_star():        return emoji("star", "⭐")
def e_comet():       return emoji("comet", "☄️")
def e_crystal():     return emoji("crystal", "🔮")

# ── Status ────────────────────────────────────────────────────────
def e_check_done():  return emoji("check_done", "✅")
def e_cross():       return emoji("cross", "❌")
def e_warning():     return emoji("warning", "⚠️")
def e_check():       return emoji("check", "✔️")
def e_stop():        return emoji("stop", "⛔")
def e_alert():       return emoji("alert", "🚨")
def e_green():       return emoji("green_dot", "🟢")
def e_red():         return emoji("red_dot", "🔴")
def e_yellow():      return emoji("yellow_dot", "🟡")
def e_warning_alt(): return emoji("warning_alt", "⚠️")

# ── Finance ───────────────────────────────────────────────────────
def e_card():        return emoji("card", "💳")
def e_money_bag():   return emoji("money_bag", "💰")
def e_dollar():      return emoji("dollar", "💲")
def e_money():       return emoji("money", "💵")
def e_cash_fly():    return emoji("cash_fly", "💸")
def e_bank():        return emoji("bank", "🏦")

# ── Cards & Check ─────────────────────────────────────────────────
def e_cart():        return emoji("cart", "🛒")
def e_memo():        return emoji("memo", "📝")
def e_chart():       return emoji("chart", "📊")
def e_chart_up():    return emoji("chart_up", "📈")
def e_chart_down():  return emoji("chart_down", "📉")
def e_target():      return emoji("target", "🎯")
def e_skull():       return emoji("skull", "💀")
def e_hundred():     return emoji("hundred", "💯")

# ── Network & System ──────────────────────────────────────────────
def e_globe():       return emoji("globe", "🌐")
def e_globe_us():    return emoji("globe_us", "🌐")
def e_globe_flag():  return emoji("globe_flag", "🌐")
def e_satellite():   return emoji("satellite", "📡")
def e_gear():        return emoji("gear", "⚙️")
def e_shield():      return emoji("shield", "🛡")
def e_key():         return emoji("key", "🔑")
def e_lock():        return emoji("lock", "🔒")
def e_unlock():      return emoji("unlock", "🔓")
def e_link():        return emoji("link", "🔗")
def e_search():      return emoji("search", "🔍")
def e_pc():          return emoji("pc", "🖥")
def e_mobile():      return emoji("mobile", "📲")

# ── People & Fun ──────────────────────────────────────────────────
def e_crown():       return emoji("crown", "👑")
def e_user():        return emoji("user", "👤")
def e_robot():       return emoji("robot", "🤖")
def e_devil():       return emoji("devil", "😈")
def e_alien():       return emoji("alien", "👾")
def e_heart():       return emoji("white_heart", "🤍")
def e_heart_blue():  return emoji("heart_blue", "💙")
def e_heart_pink():  return emoji("heart_pink", "💖")
def e_heart_red():   return emoji("heart_red", "❤")
def e_smile():       return emoji("smile", "😀")

# ── Tiers ─────────────────────────────────────────────────────────
def e_gem():         return emoji("gem", "💎")
def e_gem_plans():   return emoji("gem_plans", "💎")
def e_trophy():      return emoji("trophy", "🏆")
def e_gold():        return emoji("gold", "🥇")
def e_silver():      return emoji("silver", "🥈")
def e_bronze():      return emoji("bronze", "🥉")
def e_free():        return emoji("free", "🆓")

# ── Time ──────────────────────────────────────────────────────────
def e_hourglass():   return emoji("hourglass", "⏰")
def e_hourglass_v2(): return emoji("hourglass_v2", "⏳")
def e_timer():       return emoji("timer", "⏱")
def e_calendar():    return emoji("calendar", "📅")

# ── Files & Data ──────────────────────────────────────────────────
def e_clipboard():   return emoji("clipboard", "📋")
def e_folder():      return emoji("folder", "📁")
def e_inbox():       return emoji("inbox", "📥")
def e_outbox():      return emoji("outbox", "📤")
def e_pin():         return emoji("pin", "📌")
def e_bell():        return emoji("bell", "🔔")
def e_mailbox():     return emoji("mailbox", "📬")

# ── Controls ──────────────────────────────────────────────────────
def e_refresh():     return emoji("refresh", "🔁")
def e_play():        return emoji("play", "▶️")
def e_pause():       return emoji("pause", "⏸")
def e_stop_btn():    return emoji("stop_btn", "⏹")
def e_broom():       return emoji("broom", "🧹")
def e_trash():       return emoji("trash", "🗑")
def e_new():         return emoji("new", "🆕")

# ── Misc ──────────────────────────────────────────────────────────
def e_gift():        return emoji("gift", "🎁")
def e_ribbon():      return emoji("ribbon", "🎀")
def e_ticket():      return emoji("ticket", "🎟")
def e_bulb():        return emoji("bulb", "💡")
def e_joker():       return emoji("joker", "🃏")
def e_party():       return emoji("party", "🎉")
def e_info():        return emoji("info", "ℹ️")
def e_flag_us():     return emoji("flag_us", "🇺🇸")
def e_earth():       return emoji("earth", "🌍")
