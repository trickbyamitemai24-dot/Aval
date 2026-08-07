import re

with open("handlers/proxy_handler.py", "r") as f:
    code = f.read()

code = re.sub(
    r'f"\{e_lightning\(\)\} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 \{e_lightning\(\)\}\\n"\s*f"\{D\}\\n\\n"',
    r'f"{hdr()}\\n\\n"',
    code
)

with open("handlers/proxy_handler.py", "w") as f:
    f.write(code)

