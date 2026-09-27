#!/usr/bin/env python3
"""Colometrics — local web app server (Python standard library only).

Serves the static frontend and a small JSON API that proxies Sefaria
(text + BDB lexicon) with an on-disk cache, and runs the colometric analysis.

Run:  python3 server.py   (then open http://localhost:8654)
"""
from __future__ import annotations

import html as _html
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

import colometry
import hebrew
import morphology
import sefaria_client as sf

ROOT = os.path.dirname(os.path.abspath(__file__))
BOOKS = {}
POETIC_IDS = {'Ps', 'Job', 'Prov'}

MIME = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
        '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8',
        '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.woff2': 'font/woff2'}


def api_index():
    return sf.index()


def api_chapter(book_id, ch, mode='accented'):
    book = BOOKS.get(book_id)
    if not book:
        return {'error': 'unknown book'}, 404
    data = sf.chapter(book['name'], ch)
    transform = {'accented': lambda t: t,
                 'unaccented': hebrew.unaccented,
                 'consonantal': hebrew.consonantal,
                 'translit': hebrew.transliterate}.get(mode, lambda t: t)
    for v in data['verses'].values():
        v['he'] = transform(hebrew.strip_html(v['he']))
        v['en'] = clean_english(v['en'])
    data['mode'] = mode
    data['rtl'] = mode != 'translit'
    return data


def verse_words(book_id, ch, v):
    book = BOOKS.get(book_id)
    if not book:
        return None
    data = sf.chapter(book['name'], ch)
    verse = data['verses'].get(str(v)) or data['verses'].get(v)
    if not verse:
        return None
    return verse


def word_info(book_id, ch, v, word_idx):
    verse = verse_words(book_id, ch, v)
    if verse is None:
        return None
    tokens = colometry.tokenize_verse(verse['he'])
    idx = int(word_idx)
    if idx < 0 or idx >= len(tokens):
        return None
    tok = tokens[idx]
    alignment = morphology.align(tokens, book_id, ch, v)
    morphemes = morphology.morphemes(tok.text, alignment.get(idx))
    poetic = book_id in POETIC_IDS
    ranks = colometry.POETRY_RANKS if poetic else colometry.PROSE_RANKS
    rank = ranks.get(tok.sign, None) if tok.sign and tok.sign not in colometry.CONJUNCTIVE_NAMES else None
    accents = []
    for name in tok.accents:
        meta = next((m for m in hebrew.ACCENTS.values() if m[0] == name), None)
        if name == 'silluq':
            meta = ('silluq', 'Silluq', 'disjunctive')
        accents.append({'name': name, 'title': meta[1] if meta else name,
                        'role': meta[2] if meta else ''})
    unpointed = hebrew.consonantal(tok.text)
    lookup_form = hebrew.unaccented(tok.text)
    # the lexeme the morphology points at: last Strong-numbered lemma among
    # the morphemes (clitics carry letter codes, suffixes repeat the stem's)
    core_strong = ''
    numeric = [x['lemma'] for x in morphemes if re.match(r'\d', x.get('lemma') or '')]
    if numeric:
        m_strong = re.match(r'\d+', numeric[-1])
        core_strong = m_strong.group(0) if m_strong else ''
    entries = sf.lexicon_lookup(lookup_form)
    bdb = next((e for e in entries if 'BDB' in e['lexicon'] and 'Augmented' in e['lexicon']
                and core_strong and e['strong'] == core_strong), None)
    if bdb is None:
        bdb = next((e for e in entries if 'BDB' in e['lexicon'] and 'Augmented' in e['lexicon']), None)
    bdb_full = next((e for e in entries if e['lexicon'] == 'BDB Dictionary'
                     and core_strong and e['strong'] == core_strong), None)
    if bdb_full is None and bdb:
        bdb_full = next((e for e in entries if e['lexicon'] == 'BDB Dictionary'
                         and e['headword'] == bdb['headword']), None)
    if bdb_full is None:
        bdb_full = next((e for e in entries if e['lexicon'] == 'BDB Dictionary'), None)
    return {
        'token': tok.text, 'trailer': tok.trailer, 'position': idx,
        'unpointed': unpointed,
        'accents': accents,
        'paseq': tok.paseq,
        'sign': tok.sign,
        'sign_title': _sign_title(tok),
        'role': 'conjunctive' if tok.is_conjunctive() else 'disjunctive',
        'rank': rank,
        'is_verse_final': tok.is_last,
        'transliteration': hebrew.transliterate(tok.text),
        'morphemes': morphemes,
        'bdb': bdb,
        'bdb_full': bdb_full,
        'lexicon_entries': entries,
    }


def api_lexicon(form: str, strong: str = '', alt: str = ''):
    form = hebrew.strip_html(form).strip()
    if not form or len(form) > 60:
        return {'error': 'bad form'}, 400
    # look up the form itself and, when given, the whole word it was segmented
    # from — a bare stem (רֹעִ from רֹעִי) often surfaces the wrong lexeme.
    # Sefaria's /api/words matches the voweled-but-uncantillated form best;
    # the raw form with te'amim can miss entries (e.g. עֲצַת → 6098).
    forms = []
    for src in (form, alt):
        src = hebrew.strip_html(src).strip()
        if not src:
            continue
        for f in [hebrew.unaccented(src), hebrew.consonantal(src)]:
            if f and f not in forms:
                forms.append(f)
    seen = set()
    merged = []
    for f in forms:
        for e in sf.lexicon_lookup(f):
            # strong number is part of the identity: homograph lexemes share a
            # headword and lexicon but differ by Strong number (עֵצָה 6097/6098)
            key = e['headword'] + '|' + e['lexicon'] + '|' + e['strong']
            if key not in seen:
                seen.add(key)
                merged.append(e)
    # prefer the lexeme the morphology actually points to (OSHB Strong number)
    m = re.match(r'\d+', strong or '')
    strong = m.group(0) if m else ''
    if strong:
        heads = {e['headword'] for e in merged if e['strong'] == strong}
        def rank(e):
            if e['strong'] == strong:
                return 0
            if e['lexicon'] == 'BDB Dictionary' and e['headword'] in heads:
                return 1
            return 2
        merged.sort(key=rank)  # stable: only promotes matches, keeps order otherwise
    return {'form': form, 'entries': merged}


def _sign_title(tok):
    titles = {'legarmeh': 'Legarmeh (paseq)', 'revia_mugrash': 'Reviʿa mugrash',
              'ole': 'ʿOle we-yored', 'silluq': 'Silluq', None: ''}
    if tok.sign in titles:
        return titles[tok.sign]
    meta = next((m for m in hebrew.ACCENTS.values() if m[0] == tok.sign), None)
    return meta[1] if meta else tok.sign


def clean_english(en):
    en = en or ''
    en = re.sub(r'<sup class="footnote-marker">.*?</i>', '', en, flags=re.S)
    en = en.replace('<br>', ' ').replace('<br/>', ' ').replace('<br />', ' ')
    en = re.sub(r'<[^>]+>', '', en)
    return _html.unescape(en).strip()


def api_colometry(book_id, ch, v, mode):
    verse = verse_words(book_id, ch, v)
    if verse is None:
        return None
    poetic = book_id in POETIC_IDS
    cola = colometry.analyze(verse['he'], poetic, mode)
    tokens = colometry.tokenize_verse(verse['he'])
    alignment = morphology.align(tokens, book_id, ch, v)
    morph_by_pos = {}
    for idx, tok in enumerate(tokens):
        mm = morphology.morphemes(tok.text, alignment.get(idx))
        if mm and any(x['morph'] for x in mm):
            core = max((i for i, x in enumerate(mm) if not x['morph'].startswith('S')),
                       default=len(mm) - 1)
            packed = []
            for i, x in enumerate(mm):
                kind = 'suffix' if x['morph'].startswith('S') else ('core' if i == core else 'prefix')
                packed.append({'t': x['t'], 's': x['short'], 'l': x['long'],
                               'g': x['clitic'], 'k': kind, 'lm': x['lemma']})
            morph_by_pos[idx] = packed
    out = []
    for colon in cola:
        words = []
        for t in colon:
            w = {'t': t.text, 'tr': t.trailer, 'i': t.position,
                 'acc': t.accents, 'p': t.paseq, 'cl': t.closes_colon}
            if t.position in morph_by_pos:
                w['m'] = morph_by_pos[t.position]
            words.append(w)
        out.append(words)
    return {'book': book_id, 'chapter': ch, 'verse': v, 'mode': mode,
            'poetic_book': poetic, 'cola': out, 'english': clean_english(verse['en'])}


class Handler(BaseHTTPRequestHandler):
    server_version = 'Colometrics/1.0'

    def log_message(self, fmt, *args):
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        qs = parse_qs(parsed.query)
        try:
            if path == '/api/index':
                return self._json(api_index())
            m = re.fullmatch(r'/api/chapter/([A-Za-z1-3]+)/(\d+)', path)
            if m:
                mode = qs.get('mode', ['accented'])[0]
                data = api_chapter(m.group(1), int(m.group(2)), mode)
                if isinstance(data, tuple):
                    return self._json(*data)
                return self._json(data)
            m = re.fullmatch(r'/api/colometry/([A-Za-z1-3]+)/(\d+)/(\d+)', path)
            if m:
                mode = qs.get('mode', ['prose'])[0]
                data = api_colometry(m.group(1), int(m.group(2)), int(m.group(3)), mode)
                if data is None:
                    return self._json({'error': 'not found'}, 404)
                return self._json(data)
            m = re.fullmatch(r'/api/word/([A-Za-z1-3]+)/(\d+)/(\d+)/(\d+)', path)
            if m:
                data = word_info(m.group(1), int(m.group(2)), int(m.group(3)), m.group(4))
                if data is None:
                    return self._json({'error': 'not found'}, 404)
                return self._json(data)
            m = re.fullmatch(r'/api/lexicon/(.+)', path)
            if m:
                data = api_lexicon(m.group(1), qs.get('strong', [''])[0], qs.get('alt', [''])[0])
                if isinstance(data, tuple):
                    return self._json(*data)
                return self._json(data)
            return self._static(path)
        except BrokenPipeError:
            pass
        except Exception as e:  # noqa: BLE001
            self._json({'error': str(e)}, 500)

    def _static(self, path):
        if path in ('/', ''):
            path = '/index.html'
        full = os.path.normpath(os.path.join(ROOT, 'static', path.lstrip('/')))
        if not full.startswith(os.path.join(ROOT, 'static')) or not os.path.isfile(full):
            self._json({'error': 'not found'}, 404)
            return
        ext = os.path.splitext(full)[1]
        mtime = os.path.getmtime(full)
        ims = self.headers.get('If-Modified-Since')
        if ims:
            try:
                from email.utils import parsedate_to_datetime
                if parsedate_to_datetime(ims).timestamp() >= int(mtime):
                    self.send_response(304)
                    self.end_headers()
                    return
            except Exception:
                pass
        with open(full, 'rb') as f:
            body = f.read()
        import email.utils
        self.send_response(200)
        self.send_header('Content-Type', MIME.get(ext, 'application/octet-stream'))
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Last-Modified', email.utils.formatdate(mtime, usegmt=True))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body)


def main(port=None):
    port = port or int(os.environ.get('PORT', '8654'))
    host = os.environ.get('HOST', '127.0.0.1')
    print('Building book index...', flush=True)
    global BOOKS
    BOOKS = {b['id']: b for b in sf.index()}
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f'Serving on http://{host}:{port}  (Ctrl-C to stop)', flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nBye.')


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
