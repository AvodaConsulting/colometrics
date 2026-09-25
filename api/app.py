"""Vercel serverless entry point.

Vercel has no long-running processes, so this is a small WSGI adapter that
dispatches to the same pure API functions the local server.py uses. vercel.json
rewrites the app's REST paths onto this single function:

    /api/index                  →  /api/app?r=index
    /api/chapter/Ps/1?mode=…    →  /api/app?r=chapter&b=Ps&c=1&mode=…
    /api/colometry/Ps/1/1       →  /api/app?r=colometry&b=Ps&c=1&v=1&mode=…
    /api/word/Ps/1/1/0          →  /api/app?r=word&b=Ps&c=1&v=1&w=0
    /api/lexicon/{form}         →  /api/app?r=lexicon&form=…

The local server (server.py) is untouched and keeps serving the same API.
"""
import json
import os
import sys
from urllib.parse import parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

# server.py fills BOOKS only in main(); the bundled index makes it instant here
server.BOOKS = {b['id']: b for b in server.sf.index()}


def _respond(start_response, obj, status=200):
    body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
    start_response(f'{status} OK', [
        ('Content-Type', 'application/json; charset=utf-8'),
        ('Content-Length', str(len(body))),
        ('Cache-Control', 'no-store'),
    ])
    return [body]


def app(environ, start_response):
    qs = environ.get('QUERY_STRING', '')
    p = parse_qs(qs)
    r = p.get('r', [''])[0]

    def one(key, default=''):
        return p.get(key, [default])[0]

    try:
        if r == 'index':
            return _respond(start_response, server.api_index())
        if r == 'chapter':
            mode = one('mode', 'accented')
            data = server.api_chapter(one('b'), int(one('c')), mode)
            if isinstance(data, tuple):
                return _respond(start_response, data[0], data[1])
            return _respond(start_response, data)
        if r == 'colometry':
            data = server.api_colometry(one('b'), int(one('c')), int(one('v')), one('mode', 'prose'))
            if data is None:
                return _respond(start_response, {'error': 'not found'}, 404)
            return _respond(start_response, data)
        if r == 'word':
            data = server.word_info(one('b'), int(one('c')), int(one('v')), one('w'))
            if data is None:
                return _respond(start_response, {'error': 'not found'}, 404)
            return _respond(start_response, data)
        if r == 'lexicon':
            data = server.api_lexicon(one('form'))
            if isinstance(data, tuple):
                return _respond(start_response, data[0], data[1])
            return _respond(start_response, data)
    except Exception as e:  # noqa: BLE001
        return _respond(start_response, {'error': str(e)}, 500)
    return _respond(start_response, {'error': 'unknown route'}, 404)
