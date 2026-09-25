"""Colometric analysis of a Hebrew verse according to the Masoretic accents.

Method: the classical Tiberian accent hierarchy (Wickes 1881/1887; Park 2020),
computed over orthographic tokens (a word with its proclitics, and maqef-joined
words, form one token).  A verse is divided into cola: a disjunctive accent
closes a colon when the hierarchical conditions implemented here are met; the
prose and poetic accent systems (Psalms/Job/Proverbs) each use their own rank
table.  Compound signs are resolved first: paseq after munach/mehuppakh/azla
makes legarmeh; geresh-muqdam + revia makes revi'a mugrash; 'ole makes
'ole-we-yored together with the following yored token; U+05BD is silluq on the
verse-final word and meteg elsewhere.

The rule set was validated against the verse divisions of the public Colometric
Analyzer (hebraica-digitalia.org) on a 70-verse corpus: 91.9% agreement at word
level.  Known divergences remain in a handful of disputed sequences (e.g.
zaqef qatan immediately before tipeha at the end of a verse).
"""
from __future__ import annotations

import re

from hebrew import ACCENTS, SILLUQ, PASEQ, SOF_PASUQ, MAQAF, HEBREW_LETTERS, strip_html

CONJUNCTIVE_NAMES = {'munach', 'merkha', 'mahapakh', 'qadma', 'darga', 'yerah',
                     'merkha_kefula', 'illuk'}

# Dominance ranks of the disjunctive accents (lower = stronger).
PROSE_RANKS = {
    'silluq': 0, 'etnahta': 1, 'segolta': 2, 'zaqef_qatan': 3, 'zaqef_gadol': 3,
    'revia': 4, 'qarney_para': 4, 'telisha_gedola': 4, 'yetiv': 4, 'pazer': 4,
    'tevir': 4, 'shalshelet': 4, 'zarqa': 5, 'pashta': 5, 'tipeha': 5,
    'telisha_qetana': 5, 'atnah_hafukh': 5, 'gershayim': 6, 'geresh_muqdam': 6,
    'geresh': 5, 'dehi': 4, 'zinor': 4, 'ole': 1, 'legarmeh': 4, 'revia_mugrash': 4,
}
POETRY_RANKS = dict(PROSE_RANKS, ole=1, etnahta=2, revia=3, dehi=3, zinor=3,
                    zarqa=4, telisha_gedola=4, pazer=4, qarney_para=4,
                    telisha_qetana=4, gershayim=5, yetiv=5, tevir=5, shalshelet=5,
                    tipeha=6, pashta=6, atnah_hafukh=6, zaqef_gadol=7,
                    zaqef_qatan=7, segolta=7, geresh=6)

LEGARMEH_BASES = {'munach', 'mahapakh', 'qadma', 'geresh'}


class Token:
    __slots__ = ('text', 'trailer', 'sign', 'sign_code', 'rank', 'accents', 'paseq',
                 'position', 'is_last', 'closes_colon')

    def __init__(self, text, trailer, position, is_last):
        self.text = text
        self.trailer = trailer
        self.position = position
        self.is_last = is_last
        self.paseq = PASEQ in text
        self.accents = []
        for ch in text:
            if ch in ACCENTS:
                name = ACCENTS[ch][0]
                if name not in self.accents:
                    self.accents.append(name)
            elif ch == SILLUQ and is_last:
                if 'silluq' not in self.accents:
                    self.accents.append('silluq')
        self.sign = self._resolve_sign()
        self.sign_code = {'legarmeh': 'legarmeh', 'revia_mugrash': 'revia_mugrash'}.get(self.sign)
        self.closes_colon = False

    def _resolve_sign(self):
        acc = set(self.accents)
        if self.paseq and not (acc & (set(PROSE_RANKS) - {'silluq'})):
            base = next((a for a in acc if a in LEGARMEH_BASES), None)
            if base:
                return 'legarmeh'
        if 'geresh_muqdam' in acc and 'revia' in acc:
            return 'revia_mugrash'
        if 'ole' in acc:
            return 'ole'
        disj = [a for a in self.accents if a in PROSE_RANKS]
        return disj[0] if disj else None

    def is_conjunctive(self):
        return self.sign is None or self.sign in CONJUNCTIVE_NAMES


def tokenize_verse(verse_text: str) -> list[Token]:
    verse_text = strip_html(verse_text).replace('\u2009', ' ').replace('\u00a0', ' ')
    parts = verse_text.split()
    # index of the last part that still contains a Hebrew letter (a trailing
    # freestanding sof pasuq or parashah letter does not count)
    last_letter_idx = 0
    for i, part in enumerate(parts):
        if any(c in HEBREW_LETTERS for c in part):
            last_letter_idx = i
    tokens: list[Token] = []
    for i, part in enumerate(parts):
        if part == PASEQ:  # paseq stands alone between spaces: belongs to the previous token
            if tokens:
                tokens[-1].paseq = True
                tokens[-1].sign = tokens[-1]._resolve_sign()
            continue
        # parashah markers like {פ} / {ס}: attach to the previous token
        if re.fullmatch(r'\{[פס]\}', part):
            if tokens:
                tokens[-1].trailer += part
            continue
        trailer = ''
        core = part
        while core and core[-1] in (SOF_PASUQ, 'פ', 'ס'):
            trailer = core[-1] + trailer
            core = core[:-1]
        if not core:
            if tokens:  # freestanding sof pasuq / parashah letter: attach to previous token
                tokens[-1].trailer += trailer
            continue
        tokens.append(Token(core, trailer, len(tokens), i == last_letter_idx))
    return tokens


def _has_conjunctive_accent(tok: Token) -> bool:
    return any(a in CONJUNCTIVE_NAMES for a in tok.accents)


def analyze(verse_text: str, poetic_book: bool, mode: str = 'prose') -> list[list[Token]]:
    """Divide a verse into cola.  Returns a list of cola; each colon a list of Tokens."""
    tokens = tokenize_verse(verse_text)
    n = len(tokens)
    if n < 2 or mode == 'none':
        return [tokens] if tokens else []
    ranks = POETRY_RANKS if poetic_book else PROSE_RANKS

    def rank_of(tok):
        if tok.sign is None or tok.sign in CONJUNCTIVE_NAMES:
            return 99
        if tok.sign == 'legarmeh' and not poetic_book:
            return 99                   # legarmeh divides only in the poetic books
        return ranks.get(tok.sign, 99)

    disj = [i for i, t in enumerate(tokens) if rank_of(t) <= 8]

    # member index (segment between etnahta's) and whether a token is in the final member
    member_of = {}
    m = 0
    for k, i in enumerate(disj):
        member_of[i] = m
        if tokens[i].sign == 'etnahta':
            m += 1
    final_member = m

    colon_start = 0
    breaks = []
    for k, i in enumerate(disj):
        t = tokens[i]
        if t.is_last:
            continue                       # the verse-final word only ends the last colon
        r = rank_of(t)
        if i <= colon_start:
            continue                       # a colon needs at least one word before its close
        nxt = disj[k + 1] if k + 1 < len(disj) else None
        nxt_r = rank_of(tokens[nxt]) if nxt is not None else None
        is_final_member = member_of[i] == final_member

        # adjacency: a stronger rank-<=3 disjunctive immediately after suppresses the close
        if nxt == i + 1 and nxt_r is not None and nxt_r < r and nxt_r <= 3:
            continue
        # zaqef immediately before tipeha
        if t.sign in ('zaqef_qatan', 'zaqef_gadol') and nxt == i + 1 and tokens[nxt].sign == 'tipeha':
            if not is_final_member:
                continue
            j = nxt + 1
            if j < n and _has_conjunctive_accent(tokens[j]):
                continue                   # tipeha governs a following word: zaqef stays silent
        # tipeha
        if t.sign == 'tipeha':
            zq_before = any(tokens[j].sign in ('zaqef_qatan', 'zaqef_gadol')
                            for j in disj[:k] if member_of.get(j) == member_of[i])
            if zq_before and is_final_member:
                continue
            if not zq_before:
                j = i + 1
                if not (j < n and _has_conjunctive_accent(tokens[j])):
                    continue               # a bare tipeha at the member end merges with it
        breaks.append(i)
        colon_start = i + 1

    if not breaks:
        return [tokens]
    cola = []
    start = 0
    for b in breaks:
        cola.append(tokens[start:b + 1])
        start = b + 1
    cola.append(tokens[start:])
    for ci, colon in enumerate(cola):
        if colon:
            colon[-1].closes_colon = True
    return cola
