#!/usr/bin/env python3
"""Build index.html from template.html: Kevin's latest original post + latest meme.

No API key needed. A failed X fetch must not fail the deploy: rebuild from
snapshot/post.json (the last good post) or keep the committed index.html.
"""
import html, json, os, re, sys, urllib.request
from datetime import datetime, timezone

URL = "https://api.fxtwitter.com/2/profile/Kevin_Logan/statuses?count=100"
ME = "kevin_logan"
SNAPSHOT = "snapshot/post.json"
COUNT_FALLBACK = ("4,100+", "870+", "1,300+")

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
        m = [x for x in media_items(p) if x.get("type") in ("gif", "photo")]
        if len([x for x in media_items(p) if x.get("type") == "photo"]) > 1:
            continue
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
        return list(COUNT_FALLBACK)

def load_snapshot():
    try:
        with open(SNAPSHOT, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("no snapshot:", e)
        return None
    if (data.get("text") or "").strip() and data.get("url"):
        return data
    print("snapshot missing text or url")
    return None

def save_snapshot(data):
    os.makedirs(os.path.dirname(SNAPSHOT), exist_ok=True)
    tmp = SNAPSHOT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, SNAPSHOT)

def write_index(text):
    tmp = "index.html.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, "index.html")

def meme_html(meme):
    if not meme:
        return ""
    url = html.escape(meme.get("page_url") or "https://x.com/Kevin_Logan")
    cap = (meme.get("caption") or "").strip()
    cap_html = f'<div class="cap">{html.escape(cap)}</div>' if cap else ""
    if meme.get("type") == "gif" and meme.get("video") and os.path.exists(meme["video"]):
        poster = meme.get("poster") or ""
        poster_attr = f' poster="{html.escape(poster)}"' if poster and os.path.exists(poster) else ""
        el = f'<video src="{html.escape(meme["video"])}"{poster_attr} loop muted playsinline preload="metadata"></video>'
    elif meme.get("type") == "photo" and meme.get("image") and os.path.exists(meme["image"]):
        el = f'<img src="{html.escape(meme["image"])}" alt="Latest meme" loading="lazy">'
    elif meme.get("remote_html"):
        el = meme["remote_html"]
    else:
        return ""
    return (f'<div class="meme"><div class="lh"><span class="dot"></span> LATEST PHOTO / MEME</div>'
            f'<a class="box" href="{url}">{el}</a>{cap_html}</div>')

LATEST_BOT = "latest-bot.json"

def _meta(page, prop):
    m = re.search(r'<meta (?:property|name)="%s" content="([^"]*)"' % re.escape(prop), page)
    return html.unescape(m.group(1)).strip() if m else ""

def latest_bot():
    """Kevin's newest marketplace bot. latest-bot.json holds the link (edit it when a new bot ships);
    the name, blurb and preview image are refreshed from the live marketplace page when it is reachable."""
    try:
        with open(LATEST_BOT, encoding="utf-8") as f:
            bot = json.load(f)
    except Exception as e:
        print("no latest bot:", e)
        return None
    if not bot.get("url"):
        return None
    try:
        req = urllib.request.Request(bot["url"], headers={"User-Agent": "Mozilla/5.0 (compatible; linkpage)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            page = r.read().decode("utf-8", "replace")
        title = re.sub(r"\s+by\s+[^\n]+$", "", _meta(page, "og:title"))
        desc = _meta(page, "og:description")
        if desc:
            first = re.split(r"(?<=[.!?])\s", desc, maxsplit=1)[0].rstrip(".,")
            if not first.endswith((".", "!", "?")):
                first += "."
            bot["description"] = first
        if title:
            bot["name"] = title
        img = _meta(page, "og:image")
        if img and save(img, "bot.png.tmp"):
            os.replace("bot.png.tmp", "bot.png")
            bot["image"] = "bot.png"
    except Exception as e:
        print("bot page refresh failed, using latest-bot.json:", e)
    return bot

def bot_html(bot):
    if not bot or not bot.get("name"):
        return ""
    url = html.escape(bot["url"])
    img = bot.get("image") or ""
    img_html = (f'<img src="{html.escape(img)}" alt="{html.escape(bot["name"])} preview" loading="lazy" width="1200" height="630">'
                if img and os.path.exists(img) else "")
    desc = html.escape(bot.get("description") or "")
    return (f'<div class="bot"><div class="lh"><span class="dot"></span> Latest Grok Bot</div>'
            f'<a class="botcard" href="{url}">{img_html}<span class="bb"><span class="bn">{html.escape(bot["name"])}</span>'
            + (f'<span class="bd">{desc}</span>' if desc else "")
            + '<span class="try">Try it <span aria-hidden="true">&rarr;</span></span></span></a></div>')

_BOT = None

def _bot():
    global _BOT
    if _BOT is None:
        _BOT = latest_bot() or {}
    return _BOT

def render(tpl, data):
    ts = data.get("created_timestamp") or 0
    when = ago(ts) if ts else ""
    posts, followers, following = (data.get("posts"), data.get("followers"), data.get("following"))
    out = (tpl.replace("{{POSTS}}", posts or COUNT_FALLBACK[0])
              .replace("{{FOLLOWERS}}", followers or COUNT_FALLBACK[1])
              .replace("{{FOLLOWING}}", following or COUNT_FALLBACK[2])
              .replace("{{TEXT}}", html.escape(data["text"]))
              .replace("{{URL}}", html.escape(data["url"]))
              .replace("{{WHEN}}", when)
              .replace("{{META}}", html.escape(data.get("meta") or "View on X"))
              .replace("{{MEME}}", meme_html(data.get("meme")))
              .replace("{{LATEST_BOT}}", bot_html(_bot())))
    write_index(out)

def publish_fallback(tpl, reason):
    print(reason)
    snap = load_snapshot()
    if snap:
        render(tpl, snap)
        print("rebuilt index.html from last good post:", snap.get("url"))
        return 0
    if os.path.isfile("index.html") and os.path.getsize("index.html") > 0:
        print("keeping existing index.html")
        return 0
    render(tpl, {
        "text": "Latest post will show up here once X is reachable again.",
        "url": "https://x.com/Kevin_Logan",
        "created_timestamp": 0,
        "meta": "View on X",
        "posts": COUNT_FALLBACK[0],
        "followers": COUNT_FALLBACK[1],
        "following": COUNT_FALLBACK[2],
        "meme": None,
    })
    print("wrote static fallback index.html")
    return 0

def main():
    tpl = open("template.html", encoding="utf-8").read()
    try:
        posts = fetch()
    except Exception as e:
        return publish_fallback(tpl, f"fetch failed, keeping last good post: {e}")
    p = latest_post(posts)
    if not p:
        return publish_fallback(tpl, "no suitable post, keeping last good post")
    ts = p.get("created_timestamp") or 0
    meta = f"{p.get('likes', 0)} likes · {p.get('replies', 0)} replies · View on X"
    meme = None
    mp, mm = latest_meme(posts, p.get("id"))
    if mp and mm:
        page_url = mp["url"]
        cap = (mp.get("text") or "").strip()
        if mm["type"] == "gif":
            video = save(mm["url"], "meme.mp4")
            poster = save(mm.get("thumbnail_url", ""), "meme.jpg") if mm.get("thumbnail_url") else None
            meme = {
                "page_url": page_url,
                "type": "gif",
                "caption": cap,
                "video": video or "",
                "poster": poster or "",
            }
            if not video:
                meme["remote_html"] = f'<video src="{html.escape(mm["url"])}" loop muted playsinline preload="metadata"></video>'
        else:
            image = save(mm["url"], "meme.jpg")
            meme = {
                "page_url": page_url,
                "type": "photo",
                "caption": cap,
                "image": image or "",
            }
            if not image:
                meme["remote_html"] = f'<img src="{html.escape(mm["url"])}" alt="Latest meme" loading="lazy">'
    posts_n, fol_n, fing_n = counts()
    data = {
        "id": p.get("id"),
        "text": p["text"],
        "url": p["url"],
        "created_timestamp": ts,
        "meta": meta,
        "posts": posts_n,
        "followers": fol_n,
        "following": fing_n,
        "meme": meme,
    }
    # remote_html is only for this deploy; the persisted snapshot points at local files.
    persisted = dict(data)
    if meme and meme.get("remote_html") and not (meme.get("video") or meme.get("image")):
        persisted["meme"] = None
    elif meme:
        persisted["meme"] = {k: v for k, v in meme.items() if k != "remote_html"}
    save_snapshot(persisted)
    render(tpl, data)
    print("post:", p["url"], "| meme:", mp["url"] if mp else None)
    return 0

if __name__ == "__main__":
    sys.exit(main())
