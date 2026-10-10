#!/usr/bin/env python3
"""Build index.html from template.html with Kevin's latest original X post (no API key needed)."""
import html, json, sys, urllib.request
from datetime import datetime, timezone

URL = "https://api.fxtwitter.com/2/profile/Kevin_Logan/statuses?count=40"

def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "kevin-linkpage/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["results"]

def pick(posts):
    for p in posts:
        txt = (p.get("text") or "").strip()
        if p.get("replying_to") or p.get("replying_to_status") or txt.startswith("@"):
            continue  # skip replies
        if p.get("is_repost") or txt.startswith("RT @"):
            continue
        if txt:
            return p
    return None

def ago(ts):
    d = datetime.now(timezone.utc) - datetime.fromtimestamp(ts, timezone.utc)
    s = int(d.total_seconds())
    if s < 3600: return f"{max(1, s // 60)}m ago"
    if s < 86400: return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"

def main():
    tpl = open("template.html", encoding="utf-8").read()
    try:
        p = pick(fetch())
    except Exception as e:
        print("fetch failed, keeping previous index.html:", e)
        return 0
    if not p:
        print("no suitable post found, keeping previous index.html")
        return 0
    ts = p.get("created_timestamp") or 0
    meta = f"{p.get('likes', 0)} likes · {p.get('replies', 0)} replies · View on X"
    out = (tpl.replace("{{TEXT}}", html.escape(p["text"]))
              .replace("{{URL}}", html.escape(p["url"]))
              .replace("{{WHEN}}", ago(ts) if ts else "")
              .replace("{{META}}", html.escape(meta)))
    open("index.html", "w", encoding="utf-8").write(out)
    print("built with post", p["url"])
    return 0

if __name__ == "__main__":
    sys.exit(main())
