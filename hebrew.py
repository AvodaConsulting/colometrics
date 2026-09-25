"""Hebrew text processing: Unicode tables, accent analysis, text modes, transliteration.

Unicode blocks used:
  Letters       U+05D0..U+05EA (+ final forms are included in that range)
  Points        U+05B0..U+05BC, U+05BF, U+05C1, U+05C2, U+05C7 (qamats qatan)
  Accents       U+0591..U+05AF except U+05BD (silluq/meteg), U+05BE (maqaf), U+05C0 (paseq)
  Punctuation   U+05BE maqaf, U+05C0 paseq, U+05C3 sof pasuq
"""

from __future__ import annotations

import html
import re
import unicodedata

# ---------------------------------------------------------------- accents ---

ACCENTS = {
    "\u0591": ("etnahta", "Etnachta / Athnach", "disjunctive"),
    "\u0592": ("segolta", "Segolta", "disjunctive"),
    "\u0593": ("shalshelet", "Shalshelet", "disjunctive"),
    "\u0594": ("zaqef_qatan", "Zaqef qatan", "disjunctive"),
    "\u0595": ("zaqef_gadol", "Zaqef gadol", "disjunctive"),
    "\u0596": ("tipeha", "Tipeha (tarḥa)", "disjunctive"),
    "\u0597": ("revia", "Reviʿa", "disjunctive"),
    "\u0598": ("zarqa", "Zarqa / tsinnorit", "disjunctive"),
    "\u0599": ("pashta", "Pashta", "disjunctive"),
    "\u059a": ("yetiv", "Yetiv", "disjunctive"),
    "\u059b": ("tevir", "Tevir", "disjunctive"),
    "\u059c": ("geresh", "Geresh / azla", "conjunctive"),
    "\u059d": ("geresh_muqdam", "Geresh muqdam", "disjunctive"),
    "\u059e": ("gershayim", "Gershayim", "disjunctive"),
    "\u059f": ("qarney_para", "Qarney para", "disjunctive"),
    "\u05a0": ("telisha_gedola", "Telisha gedola", "disjunctive"),
    "\u05a1": ("pazer", "Pazer", "disjunctive"),
    "\u05a2": ("atnah_hafukh", "Atnaḥ ḥafukh", "disjunctive"),
    "\u05a3": ("munach", "Munach", "conjunctive"),
    "\u05a4": ("mahapakh", "Mehuppakh", "conjunctive"),
    "\u05a5": ("merkha", "Mercha", "conjunctive"),
    "\u05a6": ("merkha_kefula", "Mercha kefula", "conjunctive"),
    "\u05a7": ("darga", "Darga", "conjunctive"),
    "\u05a8": ("qadma", "Qadma / azla", "conjunctive"),
    "\u05a9": ("telisha_qetana", "Telisha qetana", "disjunctive"),
    "\u05aa": ("yerah", "Yeraḥ ben yomo / galgal", "conjunctive"),
    "\u05ab": ("ole", "ʿOle", "conjunctive"),
    "\u05ac": ("illuk", "Illuq", "conjunctive"),
    "\u05ad": ("dehi", "Deḥi / reviʿa mugrash", "disjunctive"),
    "\u05ae": ("zinor", "Tsinnor", "disjunctive"),
}
SILLUQ = "\u05bd"          # silluq (verse-final) / meteg (elsewhere)
PASEQ = "\u05c0"
MAQAF = "\u05be"
SOF_PASUQ = "\u05c3"

ACCENT_CHARS = set(ACCENTS)
POINT_CHARS = set("\u05b0\u05b1\u05b2\u05b3\u05b4\u05b5\u05b6\u05b7\u05b8\u05b9\u05bb\u05bc\u05bf\u05c1\u05c2\u05c7")
HEBREW_LETTERS = frozenset(chr(c) for c in range(0x05D0, 0x05EB))


def strip_html(s: str) -> str:
    """Sefaria's MAM text wraps some signs in HTML spans; unwrap, keep inner text."""
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s)


# ------------------------------------------------------- word tokenization ---

class Word:
    """One accentual unit (a whitespace-delimited token; maqef-joined counts as one)."""

    __slots__ = ("token", "position", "accents", "paseq", "trailer", "is_last_of_verse")

    def __init__(self, token: str, position: int, trailer: str, is_last_of_verse: bool):
        self.token = token
        self.position = position            # 0-based index within the verse
        self.trailer = trailer
        self.is_last_of_verse = is_last_of_verse
        self.paseq = PASEQ in token
        marks = []
        for ch in token:
            if ch in ACCENT_CHARS:
                marks.append(ch)
            elif ch == SILLUQ and is_last_of_verse:
                marks.append(ch)            # silluq; elsewhere it is meteg, ignored
        # Pashta is frequently written twice (final + penultimate letter): dedupe while
        # preserving order; also collapse exact duplicates from other double-written marks.
        seen = []
        for m in marks:
            if m not in seen:
                seen.append(m)
        self.accents = seen

    @property
    def accent_names(self) -> list[str]:
        names = [ACCENTS[c][1] for c in self.accents if c in ACCENTS]
        if SILLUQ in self.accents:
            names.append("Silluq")
        return names

    @property
    def primary_accent(self) -> str | None:
        """The (code of the) dominant accent of this word, per ACCENT_RANK."""
        if not self.accents:
            return None
        return min(self.accents, key=lambda c: ACCENT_RANK.get(ACCENTS[c][0], 99))


def tokenize_verse(verse_text: str) -> list[Word]:
    """Split a verse string into Word units, keeping trailing separators."""
    verse_text = strip_html(verse_text).replace("\u2009", " ").replace("\u00a0", " ")
    raw = re.findall(r"\S+", verse_text)
    words = []
    n = len(raw)
    for i, tok in enumerate(raw):
        m = re.match(r"^(\S+?)(\s*)$", tok)
        core, trailing = tok, ""
        # separate sof pasuq / paseq-ish punctuation that Sefaria appends to the token
        if core.endswith(SOF_PASUQ):
            core, trailing = core[:-1], SOF_PASUQ
        words.append(Word(core, i, trailing, i == n - 1))
    return words


# ------------------------------------------------------------- colometry ---

# Dominance ranks per accent *within its accent system*.  Lower number = stronger
# (closer to the root of the verse's accent hierarchy).  These tables are the prose
# and poetic accent hierarchies described by Wickes (1881/1887) and Price (1990);
# they were fitted against the reference implementation's verse splits.
PROSE_RANK = {
    "silluq": 0,
    "etnahta": 1,
    "segolta": 2,
    "zaqef_gadol": 2,
    "zaqef_qatan": 2,
    "revia": 3,
    "qarney_para": 3,
    "pazer": 3,
    "telisha_gedola": 3,
    "yetiv": 3,
    "tevir": 3,
    "tipeha": 4,
    "zarqa": 4,
    "pashta": 4,
    "telisha_qetana": 4,
    "atnah_hafukh": 4,
    "gershayim": 5,
    "geresh_muqdam": 5,
    "shalshelet": 5,
    # conjunctives (never close a colon)
    "ole": 8, "illuk": 8, "dehi": 8, "zinor": 8,  # poetic set: re-ranked in POETRY_RANK
    "munach": 9, "merkha": 9, "mahapakh": 9, "qadma": 9, "darga": 9,
    "yerah": 9, "merkha_kefula": 9, "geresh": 9,
}
POETRY_RANK = {
    "silluq": 0,
    "ole": 1,                # ʿole we-yored (compound with tipeha/yored)
    "etnahta": 2,
    "revia": 3,
    "dehi": 3,               # reviʿa mugrash
    "zinor": 3,              # tsinnor
    "zarqa": 4,              # tsinnorit
    "telisha_gedola": 4,
    "telisha_qetana": 4,
    "pazer": 4,
    "qarney_para": 4,
    "geresh_muqdam": 4,
    "gershayim": 5,
    "yetiv": 5, "tevir": 5, "shalshelet": 5,
    "tipeha": 6,             # yored (component of ʿole we-yored)
    "pashta": 6,
    "atnah_hafukh": 6,
    "zaqef_gadol": 6, "zaqef_qatan": 6, "segolta": 6,
    "illuk": 9, "munach": 9, "merkha": 9, "mahapakh": 9,
    "qadma": 9, "darga": 9, "yerah": 9, "merkha_kefula": 9, "geresh": 9,
}
ACCENT_RANK = {name: PROSE_RANK[name] for name, _, _ in (v for v in ACCENTS.values())}
for _k, _v in POETRY_RANK.items():
    ACCENT_RANK[_k] = min(PROSE_RANK.get(_k, 99), _v)


def rank_of(accent_code: str, mode: str) -> int:
    name = "silluq" if accent_code == SILLUQ else ACCENTS[accent_code][0]
    table = POETRY_RANK if mode == "poetry" else PROSE_RANK
    return table.get(name, 99)


def word_rank(word: Word, mode: str) -> int:
    if not word.accents:
        return 99
    return min(rank_of(c, mode) for c in word.accents)


# ------------------------------------------------------------- text modes ---

def unaccented(text: str) -> str:
    """Remove cantillation accents; keep vowel points, meteg, dagesh, punctuation."""
    out = []
    for ch in text:
        if ch in ACCENT_CHARS or ch == PASEQ:
            continue
        out.append(ch)
    return "".join(out)


def consonantal(text: str) -> str:
    """Strip all pointing: vowels, accents, meteg, dagesh; keep letters + punctuation."""
    out = []
    for ch in text:
        if ch in HEBREW_LETTERS or ch in (MAQAF, SOF_PASUQ, " "):
            out.append(ch)
    return "".join(out)


# ---------------------------------------------------------- transliteration ---

CONS = {
    "\u05d0": "ʾ", "\u05d1": "v", "\u05d2": "g", "\u05d3": "d", "\u05d4": "h",
    "\u05d5": "w", "\u05d6": "z", "\u05d7": "ḥ", "\u05d8": "ṭ", "\u05d9": "y",
    "\u05da": "k", "\u05db": "k", "\u05dc": "l", "\u05dd": "m", "\u05de": "m",
    "\u05df": "n", "\u05e0": "n", "\u05e1": "s", "\u05e2": "ʿ", "\u05e3": "p",
    "\u05e4": "p", "\u05e5": "ṣ", "\u05e6": "ṣ", "\u05e7": "q", "\u05e8": "r",
    "\u05e9": "š", "\u05ea": "t",
}
FRICATIVE = {"\u05d1": "ḇ", "\u05d2": "ḡ", "\u05d3": "ḏ", "\u05db": "ḵ", "\u05da": "ḵ",
             "\u05e4": "p̄", "\u05e3": "p̄", "\u05ea": "ṯ"}
VOWELS = {
    "\u05b0": "ə", "\u05b1": "ă", "\u05b2": "a", "\u05b3": "o", "\u05b4": "i",
    "\u05b5": "ē", "\u05b6": "e", "\u05b7": "a", "\u05b8": "ā", "\u05b9": "ō",
    "\u05bb": "u", "\u05c7": "o",   # qamats qatan (MAM explicit)
}
BEGADKEFAT = set("\u05d1\u05d2\u05d3\u05db\u05e4\u05ea")


def transliterate(text: str) -> str:
    """Approximate scholarly (SBL-general style) transliteration."""
    text = strip_html(text)
    out = []
    for token in text.split():
        t = _translit_token(token)
        if t:
            out.append(t)
    joined = ' '.join(out)
    return joined.replace(SOF_PASUQ, '.').replace(MAQAF, '-')


LONG_VOWELS = ('ā', 'ē', 'ō', 'û', 'î', 'ê', 'ô')


def _translit_token(token: str) -> str:
    chars = [c for c in token if c in HEBREW_LETTERS or c in POINT_CHARS
             or c in ACCENT_CHARS or c == SILLUQ or c == MAQAF or c == SOF_PASUQ]
    n = len(chars)
    out = []
    i = 0
    while i < n:
        ch = chars[i]
        if ch == MAQAF:
            out.append('-')
            i += 1
            continue
        if ch == SOF_PASUQ:
            out.append('.')
            i += 1
            continue
        if ch in ACCENT_CHARS or ch == SILLUQ:
            i += 1
            continue
        if ch in POINT_CHARS:
            i += 1
            continue
        # base letter: collect its combining marks
        j = i + 1
        marks = []
        while j < n and chars[j] not in HEBREW_LETTERS and chars[j] not in (MAQAF, SOF_PASUQ):
            marks.append(chars[j])
            j += 1
        i = j
        dagesh = '\u05bc' in marks
        shin = '\u05c1' in marks
        sin = '\u05c2' in marks
        # vowel (first vowel point wins; qamats qatan overrides)
        vowel = None
        for m in marks:
            if m in ('\u05c7',):
                vowel = 'o'
            elif m in VOWELS and vowel is None:
                vowel = VOWELS[m]
            elif m in VOWELS and vowel is not None and m == '\u05b8':
                vowel = VOWELS[m]
        # matres
        nxt = chars[i] if i < n else None
        mater = False
        if ch == '\u05d9' and vowel is None and out:
            prev = out[-1]
            if prev.endswith('i'):
                out[-1] = prev[:-1] + 'î'; mater = True
            elif prev.endswith('ē'):
                out[-1] = prev[:-1] + 'ê'; mater = True
        if ch == '\u05d5':
            if dagesh:
                vowel = 'û'          # shureq
            elif vowel == 'o':
                vowel = 'ô'          # full ḥolem
            elif vowel is None and out and out[-1].endswith('o'):
                out[-1] = out[-1][:-1] + 'ô'; mater = True
        if ch == '\u05d4' and vowel is None and nxt == SOF_PASUQ:
            pass                    # final he silent
        # consonant
        if dagesh and ch in BEGADKEFAT:
            cons = {'\u05d1': 'b', '\u05d2': 'g', '\u05d3': 'd', '\u05db': 'k',
                    '\u05ea': 't', '\u05e4': 'p'}[ch]
        elif ch in FRICATIVE and ch in BEGADKEFAT:
            cons = FRICATIVE[ch]
        else:
            cons = shin_dot = None
            if ch == '\u05e9':
                cons = 'ś' if sin else 'š'
            else:
                cons = CONS[ch]
        # dagesh forte in non-begadkefat letters -> gemination
        if dagesh and ch not in BEGADKEFAT and ch not in ('\u05d5', '\u05d4', '\u05d0', '\u05e2', '\u05e8'):
            cons = cons + cons
        # sheva
        sheva = '\u05b0' in marks
        if sheva:
            prev = out[-1] if out else ''
            if not prev or prev.endswith(MAQAF) or prev.endswith(LONG_VOWELS) or prev.endswith('-'):
                pass                # silent sheva
            else:
                vowel = vowel or 'ə'
        if mater:
            continue
        if vowel:
            out.append(cons + vowel)
        else:
            out.append(cons)
    return ''.join(out)
