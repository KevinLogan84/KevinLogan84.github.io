#!/usr/bin/env python3
"""Prove the saved meme stays, and a newer qualifying post replaces it.

No network. Run from the repo root: python3 test_meme.py
"""
import json, os, shutil, subprocess, sys, tempfile, unittest, urllib.request
from contextlib import contextmanager

import build
import persist_meme

ROOT = os.path.dirname(os.path.abspath(__file__))
SEED_ID = "2111684584047833508"
SEED_CAPTION = "Never going to miss the opportunity to share Grok Bot with someone."
SAVED_ID = "1000"
SAVED_CAP = "Saved meme caption stays."
LABEL = "LATEST PHOTO / MEME"

def make_post(pid, text, media=None, reply=False, repost=False, author="Kevin_Logan", ts=0, mention=False):
    body = text if not mention else "@someone " + text
    return {
        "id": str(pid),
        "text": body,
        "url": f"https://x.com/Kevin_Logan/status/{pid}",
        "author": {"screen_name": author},
        "replying_to": "someone" if reply else None,
        "reposted_by": {"screen_name": "Kevin_Logan"} if repost else None,
        "created_timestamp": ts,
        "likes": 1,
        "replies": 0,
        "media": {"all": list(media or [])},
    }

def photo(url="https://example.test/p.jpg"):
    return {"type": "photo", "url": url}

def gif(url="https://example.test/g.mp4"):
    return {"type": "gif", "url": url, "thumbnail_url": "https://example.test/g.jpg"}

def saved_meme():
    return {
        "id": SAVED_ID,
        "page_url": f"https://x.com/Kevin_Logan/status/{SAVED_ID}",
        "caption": SAVED_CAP,
        "created_timestamp": 100,
        "type": "photo",
        "image": "meme.jpg",
    }

@contextmanager
def isolated(meme=None, post=True):
    cwd = os.getcwd()
    tmp = tempfile.mkdtemp()
    try:
        shutil.copy(os.path.join(ROOT, "template.html"), os.path.join(tmp, "template.html"))
        os.makedirs(os.path.join(tmp, "snapshot"))
        with open(os.path.join(tmp, "snapshot", "meme.json"), "w", encoding="utf-8") as f:
            json.dump(meme or saved_meme(), f)
            f.write("\n")
        with open(os.path.join(tmp, "meme.jpg"), "wb") as f:
            f.write(b"seed-image")
        if post:
            with open(os.path.join(tmp, "snapshot", "post.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "id": "900",
                    "text": "Snapshot post",
                    "url": "https://x.com/Kevin_Logan/status/900",
                    "created_timestamp": 90,
                    "meta": "View on X",
                    "posts": "1",
                    "followers": "2",
                    "following": "3",
                }, f)
        os.chdir(tmp)
        build._BOT = {}
        yield tmp
    finally:
        build._BOT = None
        os.chdir(cwd)
        shutil.rmtree(tmp)

def run_main(posts):
    calls = []

    def fake_save(url, name):
        calls.append((url, name))
        with open(name, "wb") as f:
            f.write(b"downloaded " + url.encode())
        return name

    build.fetch = lambda: posts
    build.counts = lambda: ("9", "8", "7")
    build.save = fake_save
    build._BOT = {}
    code = build.main()
    page = open("index.html", encoding="utf-8").read()
    meme = json.load(open(build.MEME_SNAPSHOT, encoding="utf-8"))
    return code, page, meme, calls

class MemeSnapshotTests(unittest.TestCase):
    def setUp(self):
        self._fetch, self._counts, self._save, self._bot = build.fetch, build.counts, build.save, build._BOT

    def tearDown(self):
        build.fetch, build.counts, build.save, build._BOT = self._fetch, self._counts, self._save, self._bot

    def test_seed_status_is_committed(self):
        data = json.load(open(os.path.join(ROOT, "snapshot", "meme.json"), encoding="utf-8"))
        self.assertEqual(str(data["id"]), SEED_ID)
        self.assertEqual(data["page_url"], f"https://x.com/Kevin_Logan/status/{SEED_ID}")
        self.assertEqual(data["type"], "photo")
        self.assertEqual(data["caption"], SEED_CAPTION)
        self.assertLessEqual(len(data["caption"]), 140)
        image = os.path.join(ROOT, data["image"])
        self.assertGreater(os.path.getsize(image), 0)
        print("(seed) snapshot/meme.json is status", SEED_ID, file=sys.stderr)

    def test_caption_limit_stays_140(self):
        self.assertIsNotNone(build.qualifying_media(make_post(1, "a" * 140, [photo()])))
        self.assertIsNone(build.qualifying_media(make_post(2, "a" * 141, [photo()])))
        self.assertIsNone(build.qualifying_media(make_post(3, "reply", [photo()], reply=True)))
        self.assertIsNone(build.qualifying_media(make_post(4, "mention", [photo()], mention=True)))
        self.assertIsNone(build.qualifying_media(make_post(5, "two", [photo("https://example.test/1.jpg"), photo("https://example.test/2.jpg")])))
        self.assertIsNone(build.qualifying_media(make_post(6, "repost", [photo()], repost=True)))
        self.assertIsNone(build.qualifying_media(make_post(7, "video", [{"type": "video", "url": "https://example.test/v.mp4"}])))
        self.assertIsNone(build.qualifying_media(make_post(8, "nope", [photo()], author="someone_else")))
        self.assertIsNotNone(build.qualifying_media(make_post(9, "gif", [gif()])))

    def test_higher_status_id_is_newer_than_a_later_date(self):
        seed = {"id": SEED_ID, "created_timestamp": 1}
        self.assertTrue(build.is_newer_meme({"id": "2111684584047833509", "created_timestamp": 1}, seed))
        self.assertFalse(build.is_newer_meme({"id": "2111684584047833507", "created_timestamp": 9_999_999_999}, seed))
        self.assertFalse(build.is_newer_meme({"id": SEED_ID, "created_timestamp": 9_999_999_999}, seed))
        self.assertFalse(build.is_newer_meme({"created_timestamp": 50}, seed))
        self.assertTrue(build.is_newer_meme({"created_timestamp": 20}, {"created_timestamp": 10}))
        self.assertEqual(build.latest_meme([make_post(4000, "pic", [photo()])], 4000), (None, None))
        self.assertEqual(build.latest_meme([make_post(4000, "pic", [photo()])], "4000"), (None, None))
        older = make_post(10, "old pic", [photo()])
        newer = make_post(20, "new pic", [photo()])
        found, _media = build.latest_meme([older, newer], None)
        self.assertEqual(found["id"], "20")

    def test_a_no_qualifying_post_keeps_saved_meme(self):
        posts = [
            make_post(4000, "Just a text update", ts=400),
            make_post(3900, "reply pic", [photo("https://example.test/reply.jpg")], reply=True, ts=390),
            make_post(3800, "mention pic", [photo("https://example.test/mention.jpg")], mention=True, ts=380),
            make_post(3700, "album", [photo("https://example.test/1.jpg"), photo("https://example.test/2.jpg")], ts=370),
            make_post(3600, "x" * 141, [photo("https://example.test/long.jpg")], ts=360),
            make_post(3500, "repost pic", [photo("https://example.test/repost.jpg")], repost=True, ts=350),
            make_post(3400, "video only", [{"type": "video", "url": "https://example.test/v.mp4"}], ts=340),
            make_post(3300, "not kevin", [photo("https://example.test/other.jpg")], author="someone_else", ts=330),
        ]
        with isolated():
            before = open("meme.jpg", "rb").read()
            code, page, meme, calls = run_main(posts)
            self.assertEqual(code, 0)
            self.assertEqual(meme["id"], SAVED_ID)
            self.assertEqual(meme["caption"], SAVED_CAP)
            self.assertEqual(open("meme.jpg", "rb").read(), before)
            self.assertEqual(calls, [])
            self.assertIn(LABEL, page)
            self.assertIn(SAVED_CAP, page)
            self.assertIn(f"https://x.com/Kevin_Logan/status/{SAVED_ID}", page)
            self.assertNotIn("{{", page)
            print("(a) no qualifying post kept saved meme", meme["id"], file=sys.stderr)

    def test_b_newer_qualifying_post_replaces_it(self):
        posts = [
            make_post(4000, "Latest is text", ts=400),
            make_post(500, "Older than the saved meme", [photo("https://example.test/old.jpg")], ts=50),
            make_post(3600, "y" * 141, [photo("https://example.test/long.jpg")], ts=360),
            make_post(3000, "Newer qualifying meme.", [photo("https://example.test/new.jpg")], ts=300),
        ]
        with isolated():
            code, page, meme, calls = run_main(posts)
            self.assertEqual(code, 0)
            self.assertEqual(meme["id"], "3000")
            self.assertEqual(meme["caption"], "Newer qualifying meme.")
            self.assertEqual(meme["type"], "photo")
            self.assertEqual(meme["image"], "meme.jpg")
            self.assertTrue(any(name == "meme.jpg" for _url, name in calls))
            self.assertIn(LABEL, page)
            self.assertIn("Newer qualifying meme.", page)
            self.assertIn("https://x.com/Kevin_Logan/status/3000", page)
            self.assertNotIn(SAVED_CAP, page)
            self.assertNotIn("Older than the saved meme", page)
            self.assertNotIn("{{", page)
            print("(b) newer qualifying post replaced saved meme with", meme["id"], file=sys.stderr)

    def test_older_qualifying_post_does_not_replace(self):
        posts = [
            make_post(4000, "Latest is text", ts=400),
            make_post(500, "Older than the saved meme", [photo("https://example.test/old.jpg")], ts=50),
        ]
        with isolated():
            before = open("meme.jpg", "rb").read()
            _code, page, meme, calls = run_main(posts)
            self.assertEqual(meme["id"], SAVED_ID)
            self.assertEqual(calls, [])
            self.assertEqual(open("meme.jpg", "rb").read(), before)
            self.assertIn(SAVED_CAP, page)
            self.assertNotIn("Older than the saved meme", page)

    def test_featured_post_does_not_loosen_into_the_meme(self):
        posts = [make_post(4000, "Featured photo stays in the latest post", [photo("https://example.test/feat.jpg")], ts=400)]
        with isolated():
            _code, page, meme, calls = run_main(posts)
            self.assertEqual(meme["id"], SAVED_ID)
            self.assertEqual(calls, [])
            self.assertIn(f'<a class="box" href="https://x.com/Kevin_Logan/status/{SAVED_ID}">', page)
            self.assertIn("Featured photo stays in the latest post", page)

    def test_newer_gif_replaces_saved_photo(self):
        posts = [
            make_post(4000, "Latest is text", ts=400),
            make_post(3100, "A new gif meme", [gif()], ts=310),
        ]
        with isolated():
            _code, page, meme, calls = run_main(posts)
            self.assertEqual(meme["id"], "3100")
            self.assertEqual(meme["type"], "gif")
            self.assertEqual(meme["video"], "meme.mp4")
            self.assertTrue(os.path.isfile("meme.mp4"))
            self.assertTrue(any(name == "meme.mp4" for _url, name in calls))
            self.assertIn("<video ", page)
            self.assertIn("A new gif meme", page)
            self.assertIn(LABEL, page)

    def test_failed_fetch_keeps_meme_and_exits_zero(self):
        def boom():
            raise OSError("simulated fetch failure")

        with isolated():
            before = json.load(open("snapshot/meme.json", encoding="utf-8"))
            image = open("meme.jpg", "rb").read()
            build.fetch = boom
            code = build.main()
            page = open("index.html", encoding="utf-8").read()
            after = json.load(open("snapshot/meme.json", encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertEqual(after, before)
            self.assertEqual(open("meme.jpg", "rb").read(), image)
            self.assertIn(LABEL, page)
            self.assertIn(SAVED_CAP, page)
            self.assertNotIn("{{", page)

    def test_failed_fetch_without_post_snapshot_still_shows_meme(self):
        def boom():
            raise OSError("simulated fetch failure")

        with isolated(post=False):
            build.fetch = boom
            code = build.main()
            page = open("index.html", encoding="utf-8").read()
            self.assertEqual(code, 0)
            self.assertIn(LABEL, page)
            self.assertIn(SAVED_CAP, page)
            self.assertNotIn("{{", page)

    def test_failed_download_keeps_existing_image(self):
        path = os.path.join(tempfile.mkdtemp(), "meme.jpg")
        with open(path, "wb") as f:
            f.write(b"original-image")

        def boom(req, timeout=60):
            raise OSError("nope")

        orig = urllib.request.urlopen
        urllib.request.urlopen = boom
        try:
            self.assertIsNone(build.save("https://example.test/x.jpg", path))
        finally:
            urllib.request.urlopen = orig
        self.assertEqual(open(path, "rb").read(), b"original-image")

    def test_artifact_keep_and_replace_for_git(self):
        repo = tempfile.mkdtemp()
        extra = []
        try:
            subprocess.check_call(["git", "init", "-q", "-b", "main"], cwd=repo)
            os.makedirs(os.path.join(repo, "snapshot"))
            meme = saved_meme()
            meme_path = os.path.join(repo, "snapshot", "meme.json")
            with open(meme_path, "w", encoding="utf-8") as f:
                json.dump(meme, f)
                f.write("\n")
            with open(os.path.join(repo, "meme.jpg"), "wb") as f:
                f.write(b"seed-image")
            subprocess.check_call(["git", "add", "snapshot/meme.json", "meme.jpg"], cwd=repo)
            subprocess.check_call(
                ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "seed"],
                cwd=repo,
            )

            same = tempfile.mkdtemp()
            extra.append(same)
            shutil.copy(meme_path, os.path.join(same, "meme.json"))
            shutil.copy(os.path.join(repo, "meme.jpg"), os.path.join(same, "meme.jpg"))
            self.assertEqual(persist_meme.apply_artifact(same, repo), "kept")
            subprocess.check_call(["git", "add", "snapshot/meme.json", "meme.jpg"], cwd=repo)
            quiet = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo)
            self.assertEqual(quiet.returncode, 0, "(a) unchanged artifact must not stage a commit")

            newer = tempfile.mkdtemp()
            extra.append(newer)
            new_meme = dict(meme, id="3000", caption="Newer qualifying meme.", page_url="https://x.com/Kevin_Logan/status/3000", created_timestamp=300)
            with open(os.path.join(newer, "meme.json"), "w", encoding="utf-8") as f:
                json.dump(new_meme, f)
                f.write("\n")
            with open(os.path.join(newer, "meme.jpg"), "wb") as f:
                f.write(b"new-image")
            self.assertEqual(persist_meme.apply_artifact(newer, repo), "updated")
            subprocess.check_call(["git", "add", "snapshot/meme.json", "meme.jpg"], cwd=repo)
            dirty = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo)
            self.assertNotEqual(dirty.returncode, 0, "(b) newer artifact must be committable")
            got = json.load(open(meme_path, encoding="utf-8"))
            self.assertEqual(got["id"], "3000")

            older = tempfile.mkdtemp()
            extra.append(older)
            old_meme = dict(new_meme, id="2000", caption="Older artifact", page_url="https://x.com/Kevin_Logan/status/2000")
            with open(os.path.join(older, "meme.json"), "w", encoding="utf-8") as f:
                json.dump(old_meme, f)
            with open(os.path.join(older, "meme.jpg"), "wb") as f:
                f.write(b"old-image")
            self.assertEqual(persist_meme.apply_artifact(older, repo), "kept")
            self.assertEqual(json.load(open(meme_path, encoding="utf-8"))["id"], "3000")
            self.assertEqual(open(os.path.join(repo, "meme.jpg"), "rb").read(), b"new-image")
            print("(a) unchanged meme artifact stays unstaged", file=sys.stderr)
            print("(b) newer meme artifact is staged for commit", file=sys.stderr)
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            for path in extra:
                shutil.rmtree(path, ignore_errors=True)

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2, buffer=False).run(suite)
    if result.wasSuccessful():
        print("(a) no qualifying post keeps the saved meme")
        print("(b) a newer qualifying post replaces it")
    sys.exit(0 if result.wasSuccessful() else 1)
