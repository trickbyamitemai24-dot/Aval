import re

with open("bot.py", "r") as f:
    code = f.read()

# Add imports
code = code.replace(
    'from handlers.proxy_handler import (',
    'from handlers.raw_text import handle_raw_text, cb_quick_check, cb_quick_msh\nfrom handlers.proxy_handler import ('
)

# Add handler before run_polling
handler = """
    # Auto-detect CCs in private chat
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_raw_text))
    app.add_handler(CallbackQueryHandler(cb_quick_check, pattern=r"^quick_check:"))
    app.add_handler(CallbackQueryHandler(cb_quick_msh, pattern=r"^quick_msh$"))

    logger.info("Bot handlers registered (28 commands). Starting polling...")
"""
code = code.replace('    logger.info("Bot handlers registered (28 commands). Starting polling...")', handler)

with open("bot.py", "w") as f:
    f.write(code)

print("raw_text hooked")
