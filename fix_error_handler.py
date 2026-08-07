import re

with open("core/error_handler.py", "r") as f:
    code = f.read()

# Make sure it imports format_error
if "from templates.messages import" not in code:
    code = "from templates.messages import format_error\n" + code

# We replace the final string returns with format_error(string)
# Let's just do it manually with regex for simple returns
code = re.sub(r'return "([^"]+)"', r'return format_error("\1")', code)
code = re.sub(r"return '([^']+)'", r'return format_error("\1")', code)

with open("core/error_handler.py", "w") as f:
    f.write(code)

print("Error handler messages fixed")
