import re

with open("handlers/mass_check.py", "r") as f:
    code = f.read()

# Make sure strip_tg_emoji is imported
if "strip_tg_emoji" not in code:
    code = code.replace("from templates.emojis import e_lightning, e_memo, e_cross, e_check_done", "from templates.emojis import e_lightning, e_memo, e_cross, e_check_done, strip_tg_emoji, e_check, e_rocket, e_globe, e_folder")

# Fix buttons
code = code.replace('f"✅ HQ ({counts.get(\'hq\', 0)})"', 'strip_tg_emoji(f"{e_check()} HQ ({counts.get(\'hq\', 0)})")')
code = code.replace('f"⚡ V40 ({counts.get(\'v40\', 0)})"', 'strip_tg_emoji(f"{e_lightning()} V40 ({counts.get(\'v40\', 0)})")')
code = code.replace('f"🚀 Sureship ({counts.get(\'sureship\', 0)})"', 'strip_tg_emoji(f"{e_rocket()} Sureship ({counts.get(\'sureship\', 0)})")')
code = code.replace('f"📦 Working ({counts[\'all\']})"', 'strip_tg_emoji(f"{e_folder()} Working ({counts[\'all\']})")')
code = code.replace('f"🌐 ALL Sites ({counts.get(\'all_combined\', 0)})"', 'strip_tg_emoji(f"{e_globe()} ALL Sites ({counts.get(\'all_combined\', 0)})")')
code = code.replace('InlineKeyboardButton("❌ Cancel", callback_data=CB_CANCEL)', 'InlineKeyboardButton(strip_tg_emoji(f"{e_cross()} Cancel"), callback_data=CB_CANCEL)')

with open("handlers/mass_check.py", "w") as f:
    f.write(code)

