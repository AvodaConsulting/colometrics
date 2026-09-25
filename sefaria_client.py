"""Sefaria API client with on-disk JSON cache (stdlib only)."""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

BASE = "https://www.sefaria.org"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sefaria_cache")
try:
    os.makedirs(CACHE_DIR, exist_ok=True)
except OSError:
    pass  # read-only filesystem: run without a disk cache

_UA = {"User-Agent": "colometrics-study-app/1.0 (local research tool)"}

# The 39 books of the Tanakh in canonical order, with Sefaria title + short id.
BOOKS = [
    ("Genesis", "Gen"), ("Exodus", "Exod"), ("Leviticus", "Lev"), ("Numbers", "Num"),
    ("Deuteronomy", "Deut"), ("Joshua", "Josh"), ("Judges", "Judg"), ("Ruth", "Ruth"),
    ("I Samuel", "1Sam"), ("II Samuel", "2Sam"), ("I Kings", "1Kgs"), ("II Kings", "2Kgs"),
    ("I Chronicles", "1Chr"), ("II Chronicles", "2Chr"), ("Ezra", "Ezra"),
    ("Nehemiah", "Neh"), ("Esther", "Esth"), ("Job", "Job"), ("Psalms", "Ps"),
    ("Proverbs", "Prov"), ("Ecclesiastes", "Eccl"), ("Song of Songs", "Song"),
    ("Isaiah", "Isa"), ("Jeremiah", "Jer"), ("Lamentations", "Lam"), ("Ezekiel", "Ezek"),
    ("Daniel", "Dan"), ("Hosea", "Hos"), ("Joel", "Joel"), ("Amos", "Amos"),
    ("Obadiah", "Obad"), ("Jonah", "Jonah"), ("Micah", "Mic"), ("Nahum", "Nah"),
    ("Habakkuk", "Hab"), ("Zephaniah", "Zeph"), ("Haggai", "Hag"), ("Zechariah", "Zech"),
    ("Malachi", "Mal"),
]
BOOK_IDS = {short: title for title, short in BOOKS}
BOOK_TITLES = [t for t, _ in BOOKS]

# Books that use the poetic accent system (Psalms, Job, Proverbs).
POETIC_BOOKS = {"Job", "Psalms", "Proverbs"}


def _cache_path(key: str) -> str:
    safe = urllib.parse.quote(key, safe="")[:180]
    return os.path.join(CACHE_DIR, safe + ".json")


def _get(path: str, cache_ttl: float = 30 * 24 * 3600) -> dict | list:
    """GET a Sefaria API path, caching the decoded JSON on disk."""
    cached = _cache_path(path)
    if os.path.exists(cached):
        with open(cached, encoding="utf-8") as f:
            return json.load(f)
    url = BASE + path
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read().decode("utf-8"))
            break
        except Exception as e:  # transient network errors: back off and retry
            last = e
            time.sleep(1.5 * (attempt + 1))
    else:
        raise last
    tmp = cached + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, cached)
    except OSError:
        pass  # read-only filesystem: keep going without caching
    time.sleep(0.12)  # be polite
    return data


def index() -> list[dict]:
    """Book metadata: [{id, name, chapters:[verse counts...]}] in canonical order.

    Prefers the bundled book_index.json (no network needed at startup); otherwise
    fetches every /api/shape response in parallel (cached on disk after first run).
    """
    bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), "book_index.json")
    if os.path.exists(bundled):
        with open(bundled, encoding="utf-8") as f:
            return json.load(f)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=12) as ex:
        shapes = list(ex.map(lambda t: (t, _get("/api/shape/" + urllib.parse.quote(t[0]))), BOOKS))
    out = []
    for (title, short), shape in shapes:
        node = shape[0]
        out.append({"id": short, "name": title, "chapters": node["chapters"]})
    return out


def chapter(book_title: str, chapter: int) -> dict:
    """Hebrew (MAM, with te'amim) + English (default JPS) text of one chapter.

    Returns {verses: {n: {he, en}}, book, chapter}.
    """
    ref = f"{urllib.parse.quote(book_title)}.{chapter}"
    he = _get(f"/api/v3/texts/{ref}")
    en = _get(f"/api/texts/{ref}?lang=en&context=0")
    he_verses = he["versions"][0]["text"] if he.get("versions") else []
    en_verses = en.get("text", []) if isinstance(en.get("text"), list) else [en.get("text", "")]
    verses = {}
    for i in range(max(len(he_verses), len(en_verses))):
        verses[i + 1] = {
            "he": he_verses[i] if i < len(he_verses) else "",
            "en": (en_verses[i] if i < len(en_verses) else "") or "",
        }
    return {"book": book_title, "chapter": chapter, "verses": verses}


def lexicon_lookup(word_unaccented: str) -> list[dict]:
    """BDB + other lexicon entries for an unpointed Hebrew word (Sefaria /api/words)."""
    try:
        data = _get(f"/api/words/{urllib.parse.quote(word_unaccented)}", cache_ttl=90 * 24 * 3600)
    except Exception:
        return []
    entries = []
    for item in data if isinstance(data, list) else []:
        lex = item.get("parent_lexicon", "")
        content = item.get("content", {})
        senses = content.get("senses", [])
        entries.append({
            "headword": item.get("headword", ""),
            "lexicon": lex,
            "morphology": content.get("morphology", ""),
            "transliteration": item.get("transliteration", ""),
            "pronunciation": item.get("pronunciation", ""),
            "strong": item.get("strong_number", ""),
            "senses": senses,
            "full": lex == "BDB Dictionary",
        })
    return entries


def bdb_entry(word_unaccented: str) -> dict | None:
    for e in lexicon_lookup(word_unaccented):
        if "BDB" in e["lexicon"]:
            return e
    return None
