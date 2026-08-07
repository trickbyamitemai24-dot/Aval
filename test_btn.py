import requests
import os
import json

token = os.environ.get("BOT_TOKEN")
if not token:
    print("NO TOKEN")
    exit()

# Try to get updates to find the user's chat_id
url = f"https://api.telegram.org/bot{token}/getUpdates"
resp = requests.get(url).json()
chat_id = None
if resp.get("ok") and resp["result"]:
    chat_id = resp["result"][-1]["message"]["chat"]["id"]

if not chat_id:
    print("No chat id found.")
    exit()

# Send message with styled button
send_url = f"https://api.telegram.org/bot{token}/sendMessage"
payload = {
    "chat_id": chat_id,
    "text": "Test colored buttons",
    "reply_markup": {
        "inline_keyboard": [
            [
                {"text": "Primary", "callback_data": "1", "style": "primary"},
                {"text": "Danger", "callback_data": "2", "style": "danger"},
                {"text": "Success", "callback_data": "3", "style": "success"},
            ]
        ]
    }
}
res = requests.post(send_url, json=payload).json()
print(json.dumps(res, indent=2))
