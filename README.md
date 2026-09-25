# Colometrics — Masoretic Colometry of the Hebrew Bible

A local web app for studying the Tanakh in the original language: it displays the
biblical text with the Masoretic cantillation accents (teʿamim) and divides every
verse into *cola* (prosodic lines) according to the classical Tiberian accent
hierarchy, with a full BDB lexicon lookup for every word.

Inspired by the public [Colometric Analyzer](https://www.hebraica-digitalia.org/)
(Studia Hebraica Digitalia); text and lexicon are served by the
[Sefaria API](https://www.sefaria.org).

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/AvodaConsulting/colometrics)

One click deploys the app to a free Render web service (sign in with GitHub when
asked, keep the defaults, confirm — a few minutes later you get a public URL).

## Run

```bash
python3 server.py          # or: python3 server.py 8080
```

Then open <http://localhost:8654>. No third-party Python packages are required
(standard library only). The first start fetches book metadata from Sefaria; all
API responses are cached on disk in `sefaria_cache/` and reused afterwards.

## Features

### Colometric Analyzer (Study)
- Book / chapter / verse selectors with prev/next verse navigation across
  chapter and book boundaries.
- Three views: **No colometry**, **Poetry**, **Prose** — the poetic view applies
  the accent hierarchy of the poetic books (Psalms, Job, Proverbs), the prose
  view that of the twenty-one prose books, so any verse can be examined under
  either system.
- Click any word — or directly one of its parts (a prefix like בְּ/וַ, the
  article, or a pronominal suffix like וֹ): the word is segmented in place and
  each morpheme carries its parsing from the OSHB morphology (stem,
  conjugation, person, gender, number, state). Every part — prefixes, the core
  and suffixes alike — opens a focused panel with the part's parsing, a compact
  **BDB** summary and a button revealing the complete unabridged BDB article; a
  "whole word" button returns to the full word panel with its accent sign(s)
  and morpheme breakdown.
- Optional English translation of the verse (Translation toggle); deep links
  `#/analyzer/{book}/{chapter}/{verse}?mode=…&word=…&en=1`.
- Colon lines shrink-to-fit so each colon stays on one row.

### Reader
- Any chapter in four forms: accented (Miqra according to the Masorah),
  unaccented (vowel points only), consonantal (letters only), scholarly
  transliteration; optional English translation in parallel; prev/next chapter
  navigation.

### About
Method, sources, licenses and technical notes.

## Method

`colometry.py` implements the classical accent hierarchy (Wickes 1881/1887;
Park 2020) over orthographic tokens (a word with its proclitics; maqef-joined
words count as one token). Disjunctive accents carry dominance ranks per accent
system; a colon closes when the ranked-domain conditions are met, with the
classical special cases (zaqef before tipeha, tipeha at member end, legarmeh,
ʿole we-yored, reviʿa mugrash, silluq vs meteg by position). The rule set was
validated against the public Colometric Analyzer on a 70-verse corpus
(≈93% agreement at word level, all simple verses identical); a few disputed
sequences (e.g. a zaqef qatan immediately before a tipeha) may be divided
differently — the classical literature disagrees on some of these as well.

Unicode notes: U+05BD is read as silluq on the verse-final word and as meteg
elsewhere; per Unicode Technical Note #27, the character named ZARQA (U+0598)
is treated as the conjunctive tsinnorit and ZINOR (U+05AE) as the disjunctive
in the poetic books.

## Deploy

The app is a single stdlib-Python process with no dependencies — any host that
can run a container (or Python 3.11+) works.

### Vercel (serverless, never sleeps)

Vercel has no long-running processes, so `api/app.py` is a small WSGI adapter
that dispatches to the same pure API functions as `server.py`; `vercel.json`
rewrites the app's REST paths onto it and serves `static/` directly:

```sh
vercel login     # once: email verification code, no card needed
vercel --prod    # from the repo root; prints the public URL
```

Each cold start loads the bundled `book_index.json` (instant) and fetches
Sefaria data on demand (60 s function ceiling, typically 1–3 s); within a warm
instance the on-disk cache in `/tmp` keeps repeat visits fast. Static assets
and the frontend are served from the edge, not through the function.

### Render.com (free tier)

1. Push this repository to GitHub (`git remote add origin … && git push`).
2. In the Render dashboard: **New → Web Service** → pick the repo. Render
   auto-detects `render.yaml` + `Dockerfile` (or choose Docker manually).
3. Leave everything default (free plan) and deploy. The app listens on
   `0.0.0.0:$PORT` as required; `book_index.json` makes startup instant, and
   Sefaria data is fetched on demand (a writable disk caches it; a read-only
   disk works too, just always fetches).

Note: the free tier **sleeps after ~15 minutes without traffic** and restarts
on the next request (cold start ≈ 30 s including the first Sefaria fetch).

### Any Docker host

```sh
docker build -t colometrics .
docker run -p 8654:10000 -e HOST=0.0.0.0 colometrics
# open http://localhost:8654
```

### Local (no Docker)

```sh
python3 server.py        # http://localhost:8654
```

## Files

| File | Role |
| --- | --- |
| `server.py` | stdlib HTTP server: static files + JSON API |
| `colometry.py` | accent sign resolution + colometric division |
| `hebrew.py` | Unicode tables, text modes (unaccented/consonantal), transliteration |
| `morphology.py` | OSHB morph-code decoding + alignment of morphology to the displayed text |
| `build_morph_index.py` | builds `morph_data/` from the Open Scriptures Hebrew Bible |
| `sefaria_client.py` | Sefaria API client with disk cache |
| `static/` | frontend (vanilla JS single-page app) |
| `sefaria_cache/` | cached API responses (created at runtime, safe to delete) |
| `morph_data/` | per-book morphology indexes (CC-BY 4.0, Open Scriptures Hebrew Bible) |

## API

- `GET /api/index` — 39 books with per-chapter verse counts
- `GET /api/chapter/{book}/{chapter}?mode=accented|unaccented|consonantal|translit`
- `GET /api/colometry/{book}/{chapter}/{verse}?mode=none|prose|poetry`
- `GET /api/word/{book}/{chapter}/{verse}/{word_index}` — accent info + BDB
