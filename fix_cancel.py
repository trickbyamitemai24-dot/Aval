import re
with open("handlers/amazon_handler.py", "r") as f:
    code = f.read()

code = re.sub(
    r'        f"\{e_cross\(\)\} Mass Amazon check cancelled\.", parse_mode=ParseMode\.HTML,',
    r'        "❌ Mass Amazon check cancelled.", parse_mode=ParseMode.HTML,',
    code
)

with open("handlers/amazon_handler.py", "w") as f:
    f.write(code)
