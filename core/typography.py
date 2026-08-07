"""Mathematical Unicode typography converters — core/typography.py

Converts ASCII text to Mathematical Sans-Serif Bold and Mathematical Italic
for Telegram UI formatting without relying on HTML tags.
"""


def bold(text: str) -> str:
    """Convert ASCII characters (A-Z, a-z, 0-9) to Mathematical Sans-Serif Bold (𝗔-𝗭, 𝗮-𝘇, 𝟬-𝟵)."""
    out = []
    for ch in str(text):
        cp = ord(ch)
        if 0x41 <= cp <= 0x5A:      # A-Z
            out.append(chr(0x1D5D4 + (cp - 0x41)))
        elif 0x61 <= cp <= 0x7A:    # a-z
            out.append(chr(0x1D5EE + (cp - 0x61)))
        elif 0x30 <= cp <= 0x39:    # 0-9
            out.append(chr(0x1D7EC + (cp - 0x30)))
        else:
            out.append(ch)
    return "".join(out)


def _to_mi(text: str) -> str:
    """Convert ASCII text to Mathematical Italic (𝜀𝑟𝑎𝑦𝑧𝑒𝑛𝑞𝑥)."""
    out = []
    for ch in str(text):
        cp = ord(ch)
        if 0x41 <= cp <= 0x5A:      # A-Z
            out.append(chr(0x1D434 + (cp - 0x41)))
        elif 0x61 <= cp <= 0x7A:    # a-z
            if ch == 'h':           # Unicode exception for italic 'h'
                out.append('ℎ')
            else:
                out.append(chr(0x1D44E + (cp - 0x61)))
        else:
            out.append(ch)
    return "".join(out)
