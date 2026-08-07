import re

with open("handlers/start.py", "r") as f:
    code = f.read()

# Fix start menu buttons
code = code.replace(
    'InlineKeyboardButton(strip_tg_emoji(f"{e_card()} Single Check"), callback_data="start_sh")',
    'InlineKeyboardButton(strip_tg_emoji(f"{e_card()} Single Check"), callback_data="start_sh", api_kwargs={"style": "primary"})'
)
code = code.replace(
    'InlineKeyboardButton(strip_tg_emoji(f"{e_memo()} Mass Check"), callback_data="start_chk")',
    'InlineKeyboardButton(strip_tg_emoji(f"{e_memo()} Mass Check"), callback_data="start_chk", api_kwargs={"style": "primary"})'
)
code = code.replace(
    'InlineKeyboardButton(strip_tg_emoji(f"{e_gem()} Plans"), callback_data="start_plans")',
    'InlineKeyboardButton(strip_tg_emoji(f"{e_gem()} Plans"), callback_data="start_plans")' # default
)
code = code.replace(
    'InlineKeyboardButton(strip_tg_emoji(f"{e_check_done()} Redeem"), callback_data="start_redeem")',
    'InlineKeyboardButton(strip_tg_emoji(f"{e_check_done()} Redeem"), callback_data="start_redeem", api_kwargs={"style": "success"})'
)

with open("handlers/start.py", "w") as f:
    f.write(code)


with open("handlers/mass_check.py", "r") as f:
    code = f.read()

# Fix mass check buttons
code = code.replace(
    'InlineKeyboardButton(strip_tg_emoji(f"{e_check()} HQ ({counts.get(\'hq\', 0)})"), callback_data=CB_PRICE_HQ,',
    'InlineKeyboardButton(strip_tg_emoji(f"{e_check()} HQ ({counts.get(\'hq\', 0)})"), callback_data=CB_PRICE_HQ, api_kwargs={"style": "primary"},'
)
code = code.replace(
    'InlineKeyboardButton(strip_tg_emoji(f"{e_lightning()} V40 ({counts.get(\'v40\', 0)})"), callback_data=CB_PRICE_V40,',
    'InlineKeyboardButton(strip_tg_emoji(f"{e_lightning()} V40 ({counts.get(\'v40\', 0)})"), callback_data=CB_PRICE_V40, api_kwargs={"style": "primary"},'
)
code = code.replace(
    'InlineKeyboardButton(strip_tg_emoji(f"{e_rocket()} Sureship ({counts.get(\'sureship\', 0)})"), callback_data=CB_PRICE_SURESHIP,',
    'InlineKeyboardButton(strip_tg_emoji(f"{e_rocket()} Sureship ({counts.get(\'sureship\', 0)})"), callback_data=CB_PRICE_SURESHIP, api_kwargs={"style": "primary"},'
)
code = code.replace(
    'InlineKeyboardButton(strip_tg_emoji(f"{e_folder()} Working ({counts[\'all\']})"), callback_data=CB_PRICE_ALL,',
    'InlineKeyboardButton(strip_tg_emoji(f"{e_folder()} Working ({counts[\'all\']})"), callback_data=CB_PRICE_ALL, api_kwargs={"style": "primary"},'
)
code = code.replace(
    'InlineKeyboardButton(strip_tg_emoji(f"{e_globe()} ALL Sites ({counts.get(\'all_combined\', 0)})"), callback_data=CB_PRICE_ALL_COMBINED,',
    'InlineKeyboardButton(strip_tg_emoji(f"{e_globe()} ALL Sites ({counts.get(\'all_combined\', 0)})"), callback_data=CB_PRICE_ALL_COMBINED, api_kwargs={"style": "primary"},'
)
code = code.replace(
    'InlineKeyboardButton(strip_tg_emoji(f"{e_cross()} Cancel"), callback_data=CB_CANCEL)',
    'InlineKeyboardButton(strip_tg_emoji(f"{e_cross()} Cancel"), callback_data=CB_CANCEL, api_kwargs={"style": "danger"})'
)

with open("handlers/mass_check.py", "w") as f:
    f.write(code)

with open("handlers/admin.py", "r") as f:
    code = f.read()

# Fix chkall delete buttons
code = code.replace(
    'InlineKeyboardButton(\n                strip_tg_emoji(f"{e_check_done()} Delete {len(bad_stores)} bad stores"),\n                callback_data="delete_bad_stores",\n            )',
    'InlineKeyboardButton(\n                strip_tg_emoji(f"{e_check_done()} Delete {len(bad_stores)} bad stores"),\n                callback_data="delete_bad_stores",\n                api_kwargs={"style": "danger"}\n            )'
)

# Fix pagination buttons
code = code.replace(
    'buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{cb_prefix}{page-1}"))',
    'buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{cb_prefix}{page-1}", api_kwargs={"style": "primary"}))'
)
code = code.replace(
    'buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"{cb_prefix}{page+1}"))',
    'buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"{cb_prefix}{page+1}", api_kwargs={"style": "primary"}))'
)
code = code.replace(
    'buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"charged_page_{page-1}"))',
    'buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"charged_page_{page-1}", api_kwargs={"style": "primary"}))'
)
code = code.replace(
    'buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"charged_page_{page+1}"))',
    'buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"charged_page_{page+1}", api_kwargs={"style": "primary"}))'
)

with open("handlers/admin.py", "w") as f:
    f.write(code)

print("Button styles applied via api_kwargs")
