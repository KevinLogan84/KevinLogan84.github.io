#!/usr/bin/env python3
"""Build index.html from template.html: Kevin's latest original post + latest meme (GIF/photo post of his own). No API key needed."""
import html, json, sys, urllib.request
from datetime import datetime, timezone

URL = "https://api.fxtwitter.com/2/profile/Kevin_Logan/statuses?count=100"
ME = "kevin_logan"

def fetch():
    import time
    last = None
    for i in range(6):
        for ua in ("kevin-linkpage/1.0", "Mozilla/5.0 (compatible; linkpage)"):
            try:
                req = urllib.request.Request(URL, headers={"User-Agent": ua})
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.load(r)["results"]
            except Exception as e:
                last = e
        time.sleep(10 * (i + 1))
    raise last

def mine(p):
    return (p.get("author") or {}).get("screen_name", "").lower() == ME and not p.get("reposted_by")

def is_reply(p):
    txt = (p.get("text") or "").strip()
    return bool(p.get("replying_to")) or txt.startswith("@")

def media_items(p):
    return ((p.get("media") or {}).get("all")) or []

def latest_post(posts):
    for p in posts:
        if mine(p) and not is_reply(p) and (p.get("text") or "").strip():
            return p

def latest_meme(posts, skip_id):
    # a meme = Kevin's own recent post with a GIF or photo, short caption, not a reply to someone
    for p in posts:
        if not mine(p) or p.get("id") == skip_id:
            continue
        m = [x for x in media_items(p) if x.get("type") == "gif"]
        if m and len((p.get("text") or "")) <= 140 and not is_reply(p):
            return p, m[0]
    return None, None

def ago(ts):
    s = int((datetime.now(timezone.utc) - datetime.fromtimestamp(ts, timezone.utc)).total_seconds())
    if s < 3600: return f"{max(1, s // 60)}m ago"
    if s < 86400: return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"

def save(url, name):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "kevin-linkpage/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            open(name, "wb").write(r.read())
        return name
    except Exception as e:
        print("save failed:", url, e)
        return None

def counts():
    try:
        req = urllib.request.Request("https://api.fxtwitter.com/Kevin_Logan", headers={"User-Agent": "kevin-linkpage/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            u = json.load(r)["user"]
        return [f"{int(u[k]):,}" for k in ("tweets", "followers", "following")]
    except Exception as e:
        print("counts failed:", e)
        return ["4,100+", "870+", "1,300+"]

def main():
    tpl = open("template.html", encoding="utf-8").read()
    try:
        posts = fetch()
    except Exception as e:
        print("fetch failed, keeping previous index.html:", e)
        return 0
    p = latest_post(posts)
    if not p:
        print("no suitable post, keeping previous index.html")
        return 0
    ts = p.get("created_timestamp") or 0
    meta = f"{p.get('likes', 0)} likes · {p.get('replies', 0)} replies · View on X"
    meme_html = ""
    mp, mm = latest_meme(posts, p.get("id"))
    if mp:
        url = html.escape(mp["url"])
        if mm["type"] == "gif":
            v = save(mm["url"], "meme.mp4"); th = save(mm.get("thumbnail_url", ""), "meme.jpg") if mm.get("thumbnail_url") else None
            el = f'<video src="{v or html.escape(mm["url"])}" poster="{th or ""}" autoplay loop muted playsinline preload="auto"></video>'
        else:
            el = f'<img src="{html.escape(mm["url"])}" alt="Latest meme" loading="lazy">'
        cap = html.escape((mp.get("text") or "").strip())
        meme_html = (f'<div class="meme"><div class="lh"><span class="dot"></span> Latest meme</div>'
                     f'<a class="box" href="{url}">{el}</a>' + (f'<div class="cap">{cap}</div>' if cap else "") + '</div>')
    posts_n, fol_n, fing_n = counts()
    out = (tpl.replace("{{POSTS}}", posts_n).replace("{{FOLLOWERS}}", fol_n).replace("{{FOLLOWING}}", fing_n).replace("{{TEXT}}", html.escape(p["text"]))
              .replace("{{URL}}", html.escape(p["url"]))
              .replace("{{WHEN}}", ago(ts) if ts else "")
              .replace("{{META}}", html.escape(meta))
              .replace("{{MEME}}", meme_html))
    open("index.html", "w", encoding="utf-8").write(out)
    print("post:", p["url"], "| meme:", mp["url"] if mp else None)
    return 0

if __name__ == "__main__":
    sys.exit(main())
