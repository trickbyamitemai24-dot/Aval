import re

with open("handlers/proxy_handler.py", "r") as f:
    code = f.read()

# Make sure hdr, ftr, frame are imported
if "from templates.messages import" in code and "hdr" not in code:
    code = code.replace("from templates.messages import (", "from templates.messages import (\n    hdr, ftr, frame,")

# Fix addproxy prompt
code = re.sub(
    r'f"\{e_lightning\(\)\} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 \{e_lightning\(\)\}\\n"\\n\s*f"\{D\}\\n\\n"',
    r'f"{hdr()}\\n\\n"',
    code
)

code = re.sub(
    r'f"\{I\(\'Only live proxies will be added\.\'\)\}\\n\\n\{D\}"',
    r'f"{I(\'Only live proxies will be added.\')}\\n\\n{ftr()}"',
    code
)

code = re.sub(
    r'f"\{I\(\'Testing each proxy on real Shopify stores\.\.\.\'\)\}\\n\\n\{D\}"',
    r'f"{I(\'Testing each proxy on real Shopify stores...\')}\\n\\n{ftr()}"',
    code
)

# Fix addproxy result
code = re.sub(
    r'f"\{e_check_done\(\)\} \{B\(\'Proxy Check Complete\'\)\}\\n\\n"',
    r'f"{frame(\'PROXY CHECK COMPLETE\')}\\n\\n"',
    code
)

# Fix proxy check prompt
code = re.sub(
    r'f"\{e_refresh\(\)\} \{B\(\'Re-checking \{len\(proxies\)\} proxies on Shopify\.\.\.\'\)\}\\n\\n"',
    r'f"{frame(\'RE-CHECKING PROXIES\')}\\n\\n{e_refresh()} {B(f\'Testing {len(proxies)} proxies...\')}\\n\\n"',
    code
)

code = re.sub(
    r'f"\{I\(\'Removing dead proxies\.\.\.\'\)\}\\n\\n\{D\}"',
    r'f"{I(\'Removing dead proxies...\')}\\n\\n{ftr()}"',
    code
)

with open("handlers/proxy_handler.py", "w") as f:
    f.write(code)

print("Proxy UI fixed")
