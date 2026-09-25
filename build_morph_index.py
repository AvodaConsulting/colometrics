#!/usr/bin/env python3
"""Build per-book morphology indexes from the Open Scriptures Hebrew Bible (morphhb).

Source: https://github.com/openscriptures/morphhb (wlc/*.xml, CC-BY 4.0).
Each <w> carries lemma ("b/7225"), morph ("HR/Ncfsa") and pointed text with '/'
separating morphemes ("בְּ/רֵאשִׁ֖ית"). Output: morph_data/{BookId}.json with
{chapter: {verse: [[text, morph, lemma], ...]}}.
"""
import json
import os
import re
import sys
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

REPO_ZIP = "https://github.com/openscriptures/morphhb/archive/refs/heads/master.zip"
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "morph_data")
NS = "{http://www.bibletechnologies.net/2003/OSIS/namespace}"

os.makedirs(OUT, exist_ok=True)


def download():
    zpath = os.path.join(ROOT, "sefaria_cache", "morphhb.zip")
    if not os.path.exists(zpath):
        print("downloading morphhb …", flush=True)
        urllib.request.urlretrieve(REPO_ZIP, zpath)
    return zpath


def parse_book(path):
    tree = ET.parse(path)
    out = {}
    for verse in tree.iter(NS + "verse"):
        vid = verse.get("osisID", "")
        m = re.fullmatch(r"([A-Za-z0-9]+)\.(\d+)\.(\d+)", vid)
        if not m:
            continue
        _, ch, v = m.group(1), str(int(m.group(2))), str(int(m.group(3)))
        words = []
        for w in verse.iter(NS + "w"):
            text = "".join(w.itertext())
            morph = w.get("morph") or ""
            lemma = w.get("lemma") or ""
            words.append([text, morph, lemma])
        if words:
            out.setdefault(ch, {})[v] = words
    return out


def main():
    zpath = download()
    mismatches = 0
    with zipfile.ZipFile(zpath) as z:
        names = [n for n in z.namelist()
                 if re.fullmatch(r"morphhb-master/wlc/[A-Za-z0-9]+\.xml", n)]
        for name in sorted(names):
            book = os.path.basename(name)[:-4]
            with z.open(name) as f:
                data = parse_book_fileobj(f)
            if not data:
                continue
            dest = os.path.join(OUT, book + ".json")
            tmp = dest + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fo:
                json.dump(data, fo, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, dest)
            nw = sum(len(v) for ch in data.values() for v in ch.values())
            print(f"{book:6s} {nw:6d} verses-chapters", flush=True)


def _qere_word(note_el):
    for rdg in note_el.iter(NS + "rdg"):
        if "qere" in (rdg.get("type") or ""):
            for w in rdg.iter(NS + "w"):
                return ["".join(w.itertext()), w.get("morph") or "", w.get("lemma") or ""]
    return None


def _verse_words(verse):
    words = []
    children = list(verse)
    for i, child in enumerate(children):
        if child.tag != NS + "w":
            continue
        if "ketiv" in (child.get("type") or ""):
            # the running text is the ketiv; MAM shows the qere, which lives in
            # the following variant note — prefer it, fall back to the ketiv
            qere = None
            for sib in children[i + 1:]:
                if sib.tag == NS + "note":
                    qere = _qere_word(sib)
                    break
                if sib.tag == NS + "w":
                    break
            if qere:
                words.append(qere)
            else:
                words.append(["".join(child.itertext()), child.get("morph") or "",
                              child.get("lemma") or ""])
            continue
        words.append(["".join(child.itertext()), child.get("morph") or "", child.get("lemma") or ""])
    return words


def parse_book_fileobj(f):
    tree = ET.parse(f)
    out = {}
    for verse in tree.iter(NS + "verse"):
        vid = verse.get("osisID", "")
        m = re.fullmatch(r"([A-Za-z0-9]+)\.(\d+)\.(\d+)", vid)
        if not m:
            continue
        ch, v = str(int(m.group(2))), str(int(m.group(3)))
        words = _verse_words(verse)
        if words:
            out.setdefault(ch, {})[v] = words
    return out


if __name__ == "__main__":
    main()
