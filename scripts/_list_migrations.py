import os
import re

d = "/app/api/db/migrations/versions"
for fn in sorted(os.listdir(d)):
    if not fn.endswith(".py"):
        continue
    src = open(os.path.join(d, fn), encoding="utf-8").read()
    rev = re.search(r"revision\s*=\s*['\"]([^'\"]+)", src)
    down = re.search(r"down_revision\s*=\s*(.+)", src)
    print(f"{rev.group(1) if rev else '?':14s} <- {(down.group(1).strip() if down else '?'):46s} {fn[:44]}")
