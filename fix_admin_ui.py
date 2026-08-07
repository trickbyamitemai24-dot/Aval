import os
import re

with open("handlers/admin.py", "r") as f:
    code = f.read()

# Make sure hdr, ftr, frame are imported
if "from templates.messages import" in code and "hdr" not in code:
    code = code.replace("from templates.messages import (", "from templates.messages import (\n    hdr, ftr, frame,")

# Fix keys_cmd
code = code.replace('lines = [f"📋 Batch Keys ({\'active\' if active_only else \'all\'}): {len(rows)}\\n"]', 'lines = [f"{hdr()}\\n\\n{frame(\'BATCH KEYS\')}\\n"]')
code = code.replace('    if len(rows) > 30:\n        lines.append(f"\\n... and {len(rows) - 30} more")', '    if len(rows) > 30:\n        lines.append(f"\\n... and {len(rows) - 30} more")\n    lines.append(f"\\n{ftr()}")')

# Fix charged_cmd
code = code.replace('lines = [f"{e_heart()} <b>Recent Charged Cards ({len(rows)})</b>\\n"]', 'lines = [f"{hdr()}\\n\\n{frame(\'RECENT CHARGED\')}\\n"]')
code = code.replace('        )\n\n    await update.message.reply_text(', '        )\n    lines.append(f"\\n{ftr()}")\n\n    await update.message.reply_text(')

# Fix user_cmd
code = code.replace('        f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\\n"\n        f"{DIVIDER}\\n\\n"\n        f"👤 {BOLD(\'User Info\')}\\n\\n"', '        f"{hdr()}\\n\\n"\n        f"{frame(\'USER PROFILE\')}\\n\\n"')
code = code.replace('        f"{DIVIDER}",', '        f"{ftr()}",')

# Fix stats_cmd
code = code.replace('        f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\\n"\n        f"{DIVIDER}\\n\\n"\n        f"{e_chart()} {BOLD(\'𝑩𝑶𝑻 𝑺𝑻𝑨𝑻𝑰𝑺𝑻𝑰𝑪𝑺\')}\\n\\n"', '        f"{hdr()}\\n\\n"\n        f"{frame(\'BOT STATISTICS\')}\\n\\n"')
code = code.replace('        f"{DIVIDER}\\n"\n        f"{e_mailbox()} {ITALIC(\'Bot Statistics\')}",', '        f"{ftr()}",')

with open("handlers/admin.py", "w") as f:
    f.write(code)

print("Admin UI fixed")
