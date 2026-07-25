import re

TG_EMOJI_RE = re.compile(r'<tg-emoji\s+emoji-id="\d+">(.*?)</tg-emoji>', re.S)

def strip_tg_emoji(s: str) -> str:
    return TG_EMOJI_RE.sub(r'\1', s or '')

def e_card():
    return '<tg-emoji emoji-id="5447453226498552490">💳</tg-emoji>'

print("Original:", f"{e_card()} Single Check")
print("Stripped:", strip_tg_emoji(f"{e_card()} Single Check"))

