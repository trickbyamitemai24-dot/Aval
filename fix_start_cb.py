import re

with open("handlers/start.py", "r") as f:
    code = f.read()

# Fix start_sh
code = re.sub(
    r'    if data == "start_sh":\n        await query\.message\.reply_text\(\n            f"\{e_card\(\)\} Usage: <code>/sh 4798510629051356\|12\|2028\|893</code>\\n\\n"\n            "Or reply to a card message with <code>/sh</code>",\n            parse_mode=ParseMode\.HTML,\n        \)',
    '    if data == "start_sh":\n        from templates.messages import format_usage_sh\n        await query.message.reply_text(\n            format_usage_sh(), parse_mode=ParseMode.HTML,\n        )',
    code
)

# Fix start_chk
code = re.sub(
    r'    elif data == "start_chk":\n        await query\.message\.reply_text\(\n            f"\{e_memo\(\)\} Send <code>/chk</code> then upload a \.txt file with cards\.\\n"\n            "One card per line: <code>NUMBER\|MM\|YYYY\|CVV</code>",\n            parse_mode=ParseMode\.HTML,\n        \)',
    '    elif data == "start_chk":\n        from templates.messages import format_error\n        await query.message.reply_text(\n            format_error("Send <code>/chk</code> then upload a .txt file with cards.\\nOne card per line: <code>NUMBER|MM|YYYY|CVV</code>"),\n            parse_mode=ParseMode.HTML,\n        )',
    code
)

# Fix start_redeem
code = re.sub(
    r'    elif data == "start_redeem":\n        await query\.message\.reply_text\(\n            f"\{e_gem\(\)\} Usage: <code>/redeem AURORA-XXXX-XXXX-XXXX-XXXX</code>\\n\\n"\n            "Or reply to a key message with <code>/redeem</code>",\n            parse_mode=ParseMode\.HTML,\n        \)',
    '    elif data == "start_redeem":\n        from templates.messages import format_error\n        await query.message.reply_text(\n            format_error("Usage: <code>/redeem AURORA-XXXX-XXXX-XXXX-XXXX</code>\\nOr reply to a key message with <code>/redeem</code>"),\n            parse_mode=ParseMode.HTML,\n        )',
    code
)

# Fix start_proxy
code = re.sub(
    r'    elif data == "start_proxy":\n        await query\.message\.reply_text\(\n            f"\{e_mobile\(\)\} Proxy commands:\\n\\n"\n            "• <code>/addproxy</code> — Add proxies \(tested on Shopify\)\\n"\n            "• <code>/proxy</code> — Check &amp; clean dead proxies\\n"\n            "• <code>/clearproxy</code> — Clear all proxies",\n            parse_mode=ParseMode\.HTML,\n        \)',
    '    elif data == "start_proxy":\n        from templates.messages import hdr, ftr, frame\n        await query.message.reply_text(\n            f"{hdr()}\\n\\n{frame(\'PROXY COMMANDS\')}\\n\\n"\n            f"{e_mobile()} <code>/addproxy</code> — Add proxies (tested on Shopify)\\n"\n            f"{e_mobile()} <code>/proxy</code> — Check & clean dead proxies\\n"\n            f"{e_mobile()} <code>/clearproxy</code> — Clear all proxies\\n\\n"\n            f"{ftr()}",\n            parse_mode=ParseMode.HTML,\n        )',
    code
)

with open("handlers/start.py", "w") as f:
    f.write(code)
print("Start callback UI fixed")
