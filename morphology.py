"""Westminster/OSHB morphology: decode morph codes and align them to MAM tokens.

Data: morph_data/{Book}.json built by build_morph_index.py from the
Open Scriptures Hebrew Bible (morph = OSHM codes, e.g. "HR/Ncfsa",
lemma = Strong's numbers with clitic prefixes, text morphemes joined by "/").
"""
from __future__ import annotations

import json
import os
import re

import hebrew

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "morph_data")

STEMS_HE = dict(q="qal", N="niphal", p="piel", P="pual", h="hiphil", H="hophal",
                t="hithpael", o="polel", O="polal", r="hithpolel", m="poel", M="poal",
                k="palel", K="pulal", Q="qal passive", l="pilpel", L="polpal",
                f="hithpalpel", D="nithpael", j="pealal", i="pilel", u="hothpaal",
                c="tiphil", v="hishtaphel", w="nithpalel", y="nithpoel", z="hithpoel")
STEMS_AR = dict(q="peal", Q="peil", u="hithpeel", p="pael", P="ithpaal", M="hithpaal",
                a="aphel", h="haphel", s="saphel", e="shaphel", H="hophal", i="ithpeel",
                t="hishtaphel", v="ishtaphel", w="hithaphel", o="polel", z="ithpoel",
                r="hithpolel", f="hithpalpel", b="hephal", c="tiphel", m="poel",
                l="palpel", L="ithpalpel", O="ithpolel", G="ittaphal")
CONJUGATIONS = dict(p="perfect (qatal)", q="sequential perfect (weqatal)",
                    i="imperfect (yiqtol)", w="sequential imperfect (wayyiqtol)",
                    h="cohortative", j="jussive", v="imperative",
                    r="participle (active)", s="participle (passive)",
                    a="infinitive absolute", c="infinitive construct")
NOUN_TYPES = dict(c="common", g="gentilic", p="proper name")
ADJ_TYPES = dict(a="adjective", c="cardinal number", g="gentilic", o="ordinal number")
PRON_TYPES = dict(d="demonstrative", f="indefinite", i="interrogative", p="personal",
                  r="relative")
SUFFIX_TYPES = dict(d="directional ה", h="paragogic ה", n="paragogic ן", p="pronominal")
PARTICLE_TYPES = dict(a="affirmation", d="definite article", e="exhortation",
                      i="interrogative", j="interjection", m="demonstrative",
                      n="negative", o="direct object marker", r="relative")
PREP_TYPES = dict(d="definite article")
GENDERS = dict(m="masculine", f="feminine", c="common", b="common")
NUMBERS = dict(s="singular", p="plural", d="dual")
STATES = dict(a="absolute", c="construct", d="determined")
ORDINALS = {1: "1st", 2: "2nd", 3: "3rd"}

CLITIC_GLOSSES = {"b": "in · with · by", "k": "as · like", "l": "to · for",
                  "c": "and", "d": "the", "m": "from", "e": "?"}

SUFFIX_GLOSSES = {"Sp1cs": "my", "Sp1cp": "our",
                  "Sp2ms": "your (masc. sg.)", "Sp2fs": "your (fem. sg.)",
                  "Sp2mp": "your (masc. pl.)", "Sp2fp": "your (fem. pl.)",
                  "Sp3ms": "his · its", "Sp3fs": "her · its",
                  "Sp3mp": "their (masc.)", "Sp3fp": "their (fem.)",
                  "Sd": "towards (directional ה)", "Sh": "paragogic ה",
                  "Sn": "paragogic nun"}

PARTICLE_GLOSSES = {"Td": "the (article)", "To": "את — direct object marker",
                    "Ti": "interrogative", "Tn": "not", "Ta": "surely",
                    "Te": "please · I pray", "Tr": "relative particle",
                    "C": "and", "R": "preposition"}


def _pgn(code, i):
    """Parse person(1/2/3)+gender(m/f/c)+number(s/p/d) starting at i."""
    out = []
    if i < len(code) and code[i] in "123":
        out.append(ORDINALS[int(code[i])] + " person")
        i += 1
    if i < len(code) and code[i] in GENDERS:
        out.append(GENDERS[code[i]])
        i += 1
    if i < len(code) and code[i] in NUMBERS:
        out.append(NUMBERS[code[i]])
        i += 1
    return out, i


def decode(code: str) -> dict:
    """Decode one OSHM morph code (without the H/A language prefix)."""
    if not code:
        return {"short": "", "long": ""}
    pos, rest = code[0], code[1:]
    if pos == "N":
        t = NOUN_TYPES.get(rest[:1], "")
        body = rest[1:] if t else rest
        g = GENDERS.get(body[:1], "") if body else ""
        n = NUMBERS.get(body[1:2], "") if len(body) > 1 else ""
        st = STATES.get(body[2:3], "") if len(body) > 2 else ""
        bits = [x for x in [t, g, n, st] if x]
        noun = "proper noun" if t == "proper name" else "noun"
        return {"short": f"n. {' '.join(bits)}".strip(), "long": " · ".join([noun] + bits)}
    if pos == "V":
        stem = STEMS_HE.get(rest[:1], rest[:1])
        conj_code = rest[1:2]
        conj = CONJUGATIONS.get(conj_code, "")
        conj_short = {"p": "perf", "q": "perf seq", "i": "impf", "w": "wayyiqtol",
                      "h": "cohort", "j": "juss", "v": "imper", "r": "ptcp act",
                      "s": "ptcp pass", "a": "inf abs", "c": "inf cstr"}.get(conj_code, conj_code)
        pgn, _ = _pgn(rest, 2)
        pgn_short = "".join(x[0] for x in pgn if x and x[0].isdigit()) + \
            "".join({"masculine": "m", "feminine": "f", "common": "c"}.get(x, "")[0]
                    for x in pgn if x in ("masculine", "feminine", "common")) + \
            "".join({"singular": "s", "plural": "p", "dual": "d"}.get(x, "")[0]
                    for x in pgn if x in ("singular", "plural", "dual"))
        bits = [stem, conj] + pgn
        short = " ".join(x for x in [stem, conj_short, pgn_short] if x) or stem
        return {"short": short, "long": " · ".join([b for b in bits if b])}
    if pos == "A":
        t = ADJ_TYPES.get(rest[:1], "adjective")
        body = rest[1:] if rest[:1] in ADJ_TYPES else rest
        g = GENDERS.get(body[:1], "")
        n = NUMBERS.get(body[1:2], "")
        st = STATES.get(body[2:3], "")
        bits = [x for x in [t, g, n, st] if x]
        return {"short": "adj. " + " ".join([x for x in [g, n, st] if x]).strip(),
                "long": " · ".join(bits)}
    if pos == "R":
        return {"short": "prep.", "long": "preposition"}
    if pos == "C":
        return {"short": "conj.", "long": "conjunction"}
    if pos == "D":
        return {"short": "adv.", "long": "adverb"}
    if pos == "T":
        t = PARTICLE_TYPES.get(rest[:1], "particle")
        return {"short": t.split()[0] + ".", "long": t}
    if pos == "P":
        t = PRON_TYPES.get(rest[:1], "pronoun")
        pgn, _ = _pgn(rest, 1)
        bits = [t] + pgn
        return {"short": "pron. " + " ".join(pgn).strip(), "long": " · ".join(bits)}
    if pos == "S":
        t = SUFFIX_TYPES.get(rest[:1], "suffix")
        pgn, _ = _pgn(rest, 1)
        bits = [t] + pgn
        return {"short": "sfx " + " ".join(pgn).strip(), "long": " · ".join(bits)}
    if pos == "X":
        return {"short": "indecl.", "long": "indeclinable"}
    return {"short": code, "long": code}


_BOOKS_CACHE: dict[str, dict] = {}


def _book(book_id: str):
    if book_id not in _BOOKS_CACHE:
        path = os.path.join(DATA_DIR, book_id + ".json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                _BOOKS_CACHE[book_id] = json.load(f)
        else:
            _BOOKS_CACHE[book_id] = {}
    return _BOOKS_CACHE[book_id]


def _key(unpointed: str) -> str:
    return unpointed.replace(hebrew.MAQAF, "/")


def verse_words(book_id: str, ch: int, v: int):
    return _book(book_id).get(str(ch), {}).get(str(v))


def align(tokens, book_id: str, ch: int, v: int):
    """Align colometry tokens to OSHB words of the verse.

    Single tokens match by unpointed form (occurrence order). Maqef compounds —
    stored in OSHB as separate words — match against a run of consecutive OSHB
    words whose forms equal the token's parts. Returns {token_index: oshb_word
    or [oshb_word, ...]}."""
    owords = verse_words(book_id, ch, v)
    if not owords:
        return {}
    okeys = [_key(hebrew.consonantal(w[0])) for w in owords]
    pools: dict[str, list] = {}
    for k, w in zip(okeys, owords):
        pools.setdefault(k, []).append(w)
    counters: dict[str, int] = {}
    my_keys = [_key(hebrew.consonantal(t.text)) for t in tokens]
    oshb_counts: dict[str, int] = {}
    for k in okeys:
        oshb_counts[k] = oshb_counts.get(k, 0) + 1
    my_counts: dict[str, int] = {}
    for k in my_keys:
        my_counts[k] = my_counts.get(k, 0) + 1
    result = {}
    cursor = 0
    for idx, t in enumerate(tokens):
        key = my_keys[idx]
        n = counters.get(key, 0)
        counters[key] = n + 1
        pool = pools.get(key)
        if pool:
            if len(pool) == 1 or my_counts.get(key, 0) != oshb_counts.get(key, 0):
                result[idx] = pool[0] if len(pool) == 1 else pool[min(n, len(pool) - 1)]
            else:
                result[idx] = pool[n]
            continue
        if "/" in key:
            parts = key.split("/")
            k = len(parts)
            found = None
            for s in range(cursor, len(owords) - k + 1):
                if okeys[s:s + k] == parts:
                    found = s
                    break
            if found is None:
                for s in range(0, cursor):
                    if okeys[s:s + k] == parts:
                        found = s
                        break
            if found is not None:
                result[idx] = owords[found:found + k]
                cursor = found + k
    return result


def _split_by_consonants(my_text: str, otext: str):
    """Split my_text into morpheme parts following OSHB's '/'-division, using
    consonant counts, so the MAM pointing (including accents) stays intact."""
    o_parts = otext.split("/")
    counts = [sum(1 for c in p if c in hebrew.HEBREW_LETTERS) for p in o_parts]
    mine = [c for c in my_text if c in hebrew.HEBREW_LETTERS]
    if sum(counts) != len(mine) or not counts or 0 in counts:
        return None
    parts, cur, idx = [], "", 0
    for ch in my_text:
        if ch in hebrew.HEBREW_LETTERS and cur and idx < len(counts) - 1 and \
                sum(1 for c in cur if c in hebrew.HEBREW_LETTERS) >= counts[idx]:
            parts.append(cur)
            cur = ""
            idx += 1
        cur += ch
    parts.append(cur)
    return parts if len(parts) == len(counts) else None


def morphemes(token_text: str, oshb_word):
    """Split a MAM token into morphemes guided by the OSHB word's '/'-structure.

    `oshb_word` is a single [text, morph, lemma] triple or a list of them (a
    maqef run). Returns a list of {t, morph, short, long, lemma, clitic} dicts,
    or None when the token cannot be aligned."""
    if not oshb_word:
        return None
    if isinstance(oshb_word[0], list):            # a maqef run of several words
        otext = "/".join(w[0] for w in oshb_word)
        omorph = "/".join(w[1] for w in oshb_word)
        olema = "/".join(w[2] for w in oshb_word)
    else:                                         # a single [text, morph, lemma]
        otext, omorph, olema = oshb_word
    n = otext.count("/") + 1
    morph_parts = omorph.split("/") if omorph else [""] * n
    morph_parts = [p[1:] if p[:1] in ("H", "A") else p for p in morph_parts]
    lemma_parts = olema.split("/") if olema else [""] * n
    # lemmas omit the suffix part (it rides on the last lemma): pad backwards
    while len(lemma_parts) < n:
        lemma_parts.append(lemma_parts[-1] if lemma_parts else "")
    my_parts = token_text.split(hebrew.MAQAF)
    if len(my_parts) == n:
        texts = my_parts
    else:
        texts = _split_by_consonants(token_text, otext) or otext.split("/")
    out = []
    for i in range(n):
        code = morph_parts[i] if i < len(morph_parts) else ""
        dec = decode(code)
        lemma = lemma_parts[i] if i < len(lemma_parts) else ""
        if code.startswith("S"):
            gloss = SUFFIX_GLOSSES.get(code, "pronominal suffix")
        elif code in PARTICLE_GLOSSES and not (code == "R" and lemma in CLITIC_GLOSSES):
            gloss = PARTICLE_GLOSSES[code]
        else:
            gloss = CLITIC_GLOSSES.get(lemma, "") if (n > 1 or lemma in CLITIC_GLOSSES) else ""
        out.append({
            "t": texts[i],
            "morph": code,
            "short": dec["short"],
            "long": dec["long"],
            "lemma": lemma,
            "clitic": gloss,
        })
    return out
