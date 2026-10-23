#!/usr/bin/env python3
"""Build index.html from template.html: Kevin's latest original post + latest meme.

No API key needed. A failed X fetch must not fail the deploy: rebuild from
snapshot/post.json (the last good post) or keep the committed index.html.

snapshot/meme.json is the last meme that qualified (original post, one photo
or GIF, caption of 140 characters or less). The section keeps rendering that
meme. A newer qualifying post replaces it; a quiet fetch does not clear it.
"""
import html, json, os, re, sys, urllib.request
from datetime import datetime, timezone

URL = "https://api.fxtwitter.com/2/profile/Kevin_Logan/statuses?count=100"
ME = "kevin_logan"
SNAPSHOT = "snapshot/post.json"
MEME_SNAPSHOT = "snapshot/meme.json"
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

def status_id(value):
    """Numeric status id from a post, a meme snapshot, or a status URL."""
    if isinstance(value, dict):
        raw = value.get("id")
        if raw is None or raw == "":
            raw = value.get("page_url") or value.get("url") or ""
        value = raw
    match = re.search(r"(\d+)$", str(value or "").strip())
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0

def created_ts(value):
    if not isinstance(value, dict):
        return 0
    try:
        return int(value.get("created_timestamp") or 0)
    except (TypeError, ValueError):
        return 0

def is_newer_meme(candidate, saved):
    """True when candidate should replace saved.

    Newer means a higher status id. A later date is used only when neither
    side has an id. The same id is not newer.
    """
    if not candidate:
        return False
    if not saved:
        return True
    cid, sid = status_id(candidate), status_id(saved)
    if cid and sid:
        return cid > sid
    if cid and not sid:
        return True
    if sid and not cid:
        return False
    return created_ts(candidate) > created_ts(saved)

def latest_post(posts):
    for p in posts:
        if mine(p) and not is_reply(p) and (p.get("text") or "").strip():
            return p

def qualifying_media(p):
    """Original post, a single photo or one GIF, caption of 140 characters or less."""
    if not mine(p) or is_reply(p):
        return None
    items = media_items(p)
    if len([x for x in items if x.get("type") == "photo"]) > 1:
        return None
    media = [x for x in items if x.get("type") in ("gif", "photo")]
    if media and len((p.get("text") or "")) <= 140:
        return media[0]
    return None

def latest_meme(posts, skip_id):
    # Newest qualifying post, skipping the one already shown as the latest post.
    skip = status_id(skip_id)
    best_p, best_m, best_id = None, None, -1
    for p in posts:
        pid = status_id(p)
        if skip and pid == skip:
            continue
        media = qualifying_media(p)
        if media and pid > best_id:
            best_p, best_m, best_id = p, media, pid
    if best_p:
        return best_p, best_m
    return None, None

def ago(ts):
    s = int((datetime.now(timezone.utc) - datetime.fromtimestamp(ts, timezone.utc)).total_seconds())
    if s < 3600: return f"{max(1, s // 60)}m ago"
    if s < 86400: return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"

def save(url, name):
    # Write beside the destination and replace only after a full download, so a
    # failed newer meme cannot wipe the saved meme.jpg / meme.mp4.
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "kevin-linkpage/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if not data:
            print("save empty:", url)
            return None
        tmp = name + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, name)
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

def load_meme():
    try:
        with open(MEME_SNAPSHOT, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("no meme snapshot:", e)
        return None
    if not isinstance(data, dict) or not data.get("page_url"):
        print("meme snapshot missing page_url")
        return None
    if data.get("type") not in ("photo", "gif"):
        print("meme snapshot has no photo or gif")
        return None
    return data

def save_meme(meme):
    os.makedirs(os.path.dirname(MEME_SNAPSHOT) or ".", exist_ok=True)
    tmp = MEME_SNAPSHOT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meme, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, MEME_SNAPSHOT)

def renderable(meme):
    if not isinstance(meme, dict):
        return False
    if meme.get("type") == "gif" and meme.get("video") and os.path.exists(meme["video"]):
        return True
    if meme.get("type") == "photo" and meme.get("image") and os.path.exists(meme["image"]):
        return True
    return bool(meme.get("remote_html"))

def persisted_meme(meme):
    """Local files worth committing. A remote-only tag is for this deploy."""
    if not isinstance(meme, dict):
        return None
    kind = meme.get("type")
    base = {
        "id": str(meme.get("id") or status_id(meme) or ""),
        "page_url": meme.get("page_url") or "",
        "caption": meme.get("caption") or "",
        "created_timestamp": created_ts(meme),
    }
    if not base["page_url"]:
        return None
    if kind == "gif" and meme.get("video") and os.path.exists(meme["video"]):
        stored = dict(base, type="gif", video=meme["video"])
        if meme.get("poster") and os.path.exists(meme["poster"]):
            stored["poster"] = meme["poster"]
        return stored
    if kind == "photo" and meme.get("image") and os.path.exists(meme["image"]):
        return dict(base, type="photo", image=meme["image"])
    return None

def active_meme(passed):
    """Committed snapshot/meme.json wins when it can still be rendered.

    main() writes that file before render when a newer meme is accepted.
    """
    saved = load_meme()
    if renderable(saved):
        return saved
    if renderable(passed):
        return passed
    return None

def download_meme(mp, mm):
    page_url = mp["url"]
    cap = (mp.get("text") or "").strip()
    meme = {
        "id": str(mp.get("id") or status_id(page_url) or ""),
        "page_url": page_url,
        "type": mm["type"],
        "caption": cap,
        "created_timestamp": created_ts(mp),
    }
    if mm["type"] == "gif":
        video = save(mm["url"], "meme.mp4")
        if not video:
            meme["remote_html"] = f'<video src="{html.escape(mm["url"])}" loop muted playsinline preload="metadata"></video>'
            return meme
        meme["video"] = video
        if mm.get("thumbnail_url"):
            poster = save(mm["thumbnail_url"], "meme.jpg")
            if poster:
                meme["poster"] = poster
        return meme
    image = save(mm["url"], "meme.jpg")
    meme["image"] = image or ""
    if image:
        if os.path.exists("meme.mp4"):
            os.remove("meme.mp4")
        return meme
    meme["remote_html"] = f'<img src="{html.escape(mm["url"])}" alt="Latest meme" loading="lazy">'
    return meme

def resolve_meme(posts, skip_id):
    """Keep snapshot/meme.json unless a newer qualifying post downloaded."""
    saved = load_meme()
    mp, mm = latest_meme(posts, skip_id)
    saved_url = (saved or {}).get("page_url")
    if not mp or not mm:
        print("no qualifying meme; keeping", saved_url)
        return saved
    candidate = {
        "id": mp.get("id"),
        "page_url": mp.get("url"),
        "created_timestamp": mp.get("created_timestamp") or 0,
    }
    if not is_newer_meme(candidate, saved):
        print("qualifying meme is not newer; keeping", saved_url)
        return saved
    stored = persisted_meme(download_meme(mp, mm))
    if not stored:
        print("newer meme did not save; keeping", saved_url)
        return saved
    save_meme(stored)
    print("replaced meme with", stored.get("page_url"))
    return stored

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
    data = dict(data)
    data["meme"] = active_meme(data.get("meme"))
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
        meme = load_meme()
        print("rebuilt index.html from last good post:", snap.get("url"), "| meme:", (meme or {}).get("page_url"))
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
    meme = resolve_meme(posts, p.get("id"))
    posts_n, fol_n, fing_n = counts()
    data = {
        "id": str(p.get("id") or ""),
        "text": p["text"],
        "url": p["url"],
        "created_timestamp": ts,
        "meta": meta,
        "posts": posts_n,
        "followers": fol_n,
        "following": fing_n,
        "meme": persisted_meme(meme) if meme else None,
    }
    save_snapshot(data)
    render(tpl, data)
    print("post:", p["url"], "| meme:", (data.get("meme") or {}).get("page_url"))
    return 0

if __name__ == "__main__":
    sys.exit(main())
