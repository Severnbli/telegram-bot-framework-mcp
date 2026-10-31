"""Staleness check: every source path the guide (section 24) mentions must exist in the pinned clone.
Standalone (no deps): TGBOTBASE_DIR=/data/repo python check_guide.py [guide.md]
"""
import os
import re
import subprocess
import sys

repo = os.environ.get("TGBOTBASE_DIR", "/data/repo")
guide = sys.argv[1] if len(sys.argv) > 1 else "/data/knowledge/SKILL.md"

files = subprocess.run(["git", "-C", repo, "ls-files"], capture_output=True, text=True, check=True).stdout.splitlines()
text = open(guide, encoding="utf-8").read()
sec = text[text.index("## 24."):]
missing = []
for tok in sorted(set(re.findall(r"`([^`]+\.cs)`", sec))):
    if "*" in tok:
        pre = tok.split("*")[0]
        ok = any(("/" + pre) in "/" + f for f in files)
    else:
        ok = any(f == tok or f.endswith("/" + tok) for f in files)
    if not ok:
        missing.append(tok)
# directory-style references like `TelegramBotBase/DataSources/*`
for tok in sorted(set(re.findall(r"`([A-Za-z.]+/[^`]*\*)`", sec))):
    if not any(f.startswith(tok.split("*")[0]) or ("/" + tok.split("*")[0]) in "/" + f for f in files):
        missing.append(tok)
if missing:
    print("guide references paths missing from the pinned source:")
    print("\n".join("  " + m for m in missing))
    sys.exit(1)
print("guide paths ok")
