"""God-level premium Telegram emoji IDs from premium_structure.md."""

EMOJI_IDS = {
    "lightning":    "5445388803223091254",
    "warning":      "5447592907424955482",
    "card":         "5447453226498552490",
    "cart":         "5447319442562251569",
    "memo":         "5444889156792646660",
    "money":        "5409048419211682843",
    "globe_us":     "5447602197439218445",
    "globe_flag":   "5445326466067754897",
    "white_heart":  "5764979527331615949",
    "free":         "5406756500108501710",
    "chart":        "5231200819986047254",
    "gem":          "5364040533498932357",
    "gem_plans":    "5215191209131123104",
    "fire":         "6181540309357305513",
    "mobile":       "5445033158456145975",
    "check":        "5447242579827523388",
    "mailbox":      "5445163772706582819",
    "bronze":       "5453902265922376865",
    "silver":       "5447203607294265305",
    "gold":         "5440539497383087970",
    "crown":        "6088920147072915408",
    "cross":        "6037570896766438989",
    "refresh":      "5971837723676249096",
    "check_done":   "6088893844693195262",
    "clipboard":    "5445260044398524944",
    "hourglass":    "5445350406215465190",
    "smile":        "5303438381743618017",
    "search":       None,
    # New emoji from key_redeem_premium.txt
    "hourglass_v2": "5454415424319931791",  # ⏳ duration
    "calendar":     "5800810214689084012",  # 📅 expires
    "gift":         "6089193719309801680",  # 🎁 (batch gen)
    "warning_alt":  "5447381715293074599",  # ⚠️ (alt)
}


def emoji(name: str, fallback: str = "") -> str:
    eid = EMOJI_IDS.get(name)
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
    return fallback


def e_lightning():   return emoji("lightning", "⚡️")
def e_warning():     return emoji("warning", "⚠️")
def e_card():        return emoji("card", "💳")
def e_cart():        return emoji("cart", "🛒")
def e_memo():        return emoji("memo", "📝")
def e_money():       return emoji("money", "💵")
def e_globe():       return emoji("globe_us", "🌐")
def e_globe_flag():  return emoji("globe_flag", "🌐")
def e_heart():       return emoji("white_heart", "🤍")
def e_free():        return emoji("free", "🆓")
def e_chart():       return emoji("chart", "📊")
def e_gem():         return emoji("gem", "💎")
def e_gem_plans():   return emoji("gem_plans", "💎")
def e_fire():        return emoji("fire", "🔥")
def e_mobile():      return emoji("mobile", "📲")
def e_check():       return emoji("check", "✔️")
def e_mailbox():     return emoji("mailbox", "📬")
def e_bronze():      return emoji("bronze", "🥉")
def e_silver():      return emoji("silver", "🥈")
def e_gold():        return emoji("gold", "🥇")
def e_crown():       return emoji("crown", "👑")
def e_cross():       return emoji("cross", "❌")
def e_refresh():     return emoji("refresh", "🔄")
def e_check_done():  return emoji("check_done", "✅")
def e_clipboard():   return emoji("clipboard", "📋")
def e_hourglass():   return emoji("hourglass", "⏰")
def e_smile():       return emoji("smile", "😀")
def e_hourglass_v2(): return emoji("hourglass_v2", "⏳")
def e_calendar():    return emoji("calendar", "📅")
def e_warning_alt(): return emoji("warning_alt", "⚠️")
def e_gift():        return emoji("gift", "🎁")