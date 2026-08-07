with open("handlers/mass_check.py", "r") as f:
    code = f.read()

code = code.replace(
    'InlineKeyboardButton(\n                f"$1-5 ({counts[\'5\']})", callback_data=CB_PRICE_5,\n            )',
    'InlineKeyboardButton(\n                f"$1-5 ({counts[\'5\']})", callback_data=CB_PRICE_5, api_kwargs={"style": "primary"}\n            )'
)
code = code.replace(
    'InlineKeyboardButton(\n                f"$1-10 ({counts[\'10\']})", callback_data=CB_PRICE_10,\n            )',
    'InlineKeyboardButton(\n                f"$1-10 ({counts[\'10\']})", callback_data=CB_PRICE_10, api_kwargs={"style": "primary"}\n            )'
)

with open("handlers/mass_check.py", "w") as f:
    f.write(code)

with open("handlers/admin.py", "r") as f:
    code = f.read()

code = code.replace(
    'InlineKeyboardButton(\n                strip_tg_emoji(f"{e_cross()} Cancel"),\n                callback_data="cancel_deletion",\n            )',
    'InlineKeyboardButton(\n                strip_tg_emoji(f"{e_cross()} Cancel"),\n                callback_data="cancel_deletion",\n                api_kwargs={"style": "primary"}\n            )'
)

with open("handlers/admin.py", "w") as f:
    f.write(code)

with open("handlers/start.py", "r") as f:
    code = f.read()

code = code.replace(
    'InlineKeyboardButton(f"{strip_tg_emoji(e_gem())} Plans", callback_data="start_plans")',
    'InlineKeyboardButton(f"{strip_tg_emoji(e_gem())} Plans", callback_data="start_plans", api_kwargs={"style": "primary"})'
)
code = code.replace(
    'InlineKeyboardButton(f"{strip_tg_emoji(e_clipboard())} Status", callback_data="start_status")',
    'InlineKeyboardButton(f"{strip_tg_emoji(e_clipboard())} Status", callback_data="start_status", api_kwargs={"style": "primary"})'
)
code = code.replace(
    'InlineKeyboardButton(f"{strip_tg_emoji(e_mobile())} Proxies", callback_data="start_proxy")',
    'InlineKeyboardButton(f"{strip_tg_emoji(e_mobile())} Proxies", callback_data="start_proxy", api_kwargs={"style": "primary"})'
)

with open("handlers/start.py", "w") as f:
    f.write(code)

print("Missed button styles added")
