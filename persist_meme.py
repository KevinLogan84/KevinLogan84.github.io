#!/usr/bin/env python3
"""Copy a meme-state artifact into the checkout. Does not commit or push.

The hourly workflow commits only when git sees a change, so a run with no new
meme leaves the committed snapshot in place.
"""
import json, os, shutil, sys

import build

NAMES = ("meme.json", "meme.jpg", "meme.mp4")

def find_files(root):
    found = {}
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in files:
            if name in NAMES and name not in found:
                found[name] = os.path.join(dirpath, name)
    return found

def load_json(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"{path} is not a meme snapshot")
    return data

def _same(src, dest):
    if not os.path.isfile(dest):
        return False
    with open(src, "rb") as a, open(dest, "rb") as b:
        return a.read() == b.read()

def _copy(src, dest):
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    if _same(src, dest):
        return False
    shutil.copyfile(src, dest)
    return True

def validate(data, files):
    if not data.get("id") or not data.get("page_url") or data.get("type") not in ("photo", "gif"):
        raise SystemExit(f"meme snapshot is incomplete: {data!r}")
    if data["type"] == "photo" and "meme.jpg" not in files:
        raise SystemExit("photo meme snapshot has no meme.jpg")
    if data["type"] == "gif" and "meme.mp4" not in files:
        raise SystemExit("gif meme snapshot has no meme.mp4")

def apply_artifact(artifact_dir, repo="."):
    """Copy the artifact when it is the same meme or a newer one.

    Returns "kept" or "updated". An older status id is left untouched.
    """
    files = find_files(artifact_dir)
    if "meme.json" not in files:
        raise SystemExit("meme-state artifact has no meme.json")
    data = load_json(files["meme.json"])
    validate(data, files)
    dest_json = os.path.join(repo, "snapshot", "meme.json")
    old_id = 0
    if os.path.isfile(dest_json):
        try:
            old_id = build.status_id(load_json(dest_json))
        except Exception:
            old_id = 0
    new_id = build.status_id(data)
    if old_id and (not new_id or new_id < old_id):
        print(f"artifact meme {new_id} is older than {old_id}; keeping git snapshot")
        return "kept"
    changed = _copy(files["meme.json"], dest_json)
    if "meme.jpg" in files:
        changed = _copy(files["meme.jpg"], os.path.join(repo, "meme.jpg")) or changed
    mp4 = os.path.join(repo, "meme.mp4")
    if data.get("type") == "gif":
        changed = _copy(files["meme.mp4"], mp4) or changed
    elif os.path.isfile(mp4):
        os.remove(mp4)
        changed = True
    result = "updated" if changed else "kept"
    print(f"meme snapshot {result}: {data.get('id')}")
    return result

def main(argv):
    check = "--check" in argv
    paths = [a for a in argv if not a.startswith("-")]
    if len(paths) != 1:
        raise SystemExit("usage: persist_meme.py <artifact-dir> [--check]")
    files = find_files(paths[0])
    if "meme.json" not in files:
        raise SystemExit("meme-state artifact has no meme.json")
    data = load_json(files["meme.json"])
    validate(data, files)
    if check:
        print("meme artifact", data["id"], data["type"])
        return 0
    apply_artifact(paths[0])
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
