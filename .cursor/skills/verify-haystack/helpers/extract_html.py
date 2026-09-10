import re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
out = Path(sys.argv[2])

def one(pat, flags=re.I|re.S):
    m = re.search(pat, text, flags)
    return m.group(1).strip() if m else ""

title = one(r"<title[^>]*>(.*?)</title>")
h1m = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.I|re.S)
h1 = re.sub(r"<[^>]+>", "", h1m.group(1)).strip() if h1m else ""
ph = one(r'<input[^>]*placeholder="([^"]+)"')
btn_m = re.search(r"<button[^>]*>(.*?)</button>", text, re.I|re.S)
btn = re.sub(r"<[^>]+>", "", btn_m.group(1)).strip() if btn_m else ""
tag = re.search(r"<button\b[^>]*>", text, re.I)
disabled = "yes" if tag and re.search(r"\bdisabled\b", tag.group(0), re.I) else "no"
lines = [
    "title=" + title,
    "h1=" + h1,
    "placeholder=" + ph,
    "button=" + btn,
    "button_disabled=" + disabled,
    "longmuch=" + str(text.count("LongMuch")),
    "subtitle=" + str(text.count("Clean. Instant. Fundamental analysis.")),
    "analyze=" + str(text.count("Analyze")),
    "placeholder_count=" + str(text.count("AAPL or TSLA")),
    "table=" + str(text.count("Financial Metrics")),
    "hardcoded_200B=" + str(text.count("$200B")),
    "create_next_app=" + str(text.count("Create Next App")),
]
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
