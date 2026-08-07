import re

with open("templates/messages.py", "r") as f:
    code = f.read()

# Add format_processing
if "def format_processing" not in code:
    code += """
def format_processing(title, message):
    return (
        f"{hdr()}\\n\\n"
        f"{frame(title)}\\n\\n"
        f"{e_refresh()} {B(message)}\\n\\n"
        f"{ftr()}"
    )
"""

with open("templates/messages.py", "w") as f:
    f.write(code)

