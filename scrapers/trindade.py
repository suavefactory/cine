"""
Scraper: Cinema Trindade (Porto)
Fonte: https://cinematrindade.pt/pt/programação
Platform: Nuxt 3 SSR — Film data embedded as JSON strings in hydration payload
Poster/director lookups via https://api.cinematrindade.pt/wp-json/wp/v2/
"""

import urllib.request
import re
import json
from html import unescape

CINEMA_ID = "trindade"
BASE_URL  = "https://cinematrindade.pt"
API_BASE  = "https://api.cinematrindade.pt/wp-json/wp/v2"
PROG_URL  = f"{BASE_URL}/pt/programa%C3%A7%C3%A3o"


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; cineportugal/1.0)",
        "Accept":     "*/*",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")


def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; cineportugal/1.0)",
        "Accept":     "application/json",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", errors="ignore"))


_director_cache = {}
_media_cache    = {}


def get_director(did):
    if did in _director_cache:
        return _director_cache[did]
    try:
        data = fetch_json(f"{API_BASE}/directors/{did}")
        name = unescape(data.get("title", {}).get("rendered", "")).strip()
        _director_cache[did] = name
        return name
    except Exception:
        return None


def get_poster_url(media_id):
    if media_id in _media_cache:
        return _media_cache[media_id]
    try:
        data  = fetch_json(f"{API_BASE}/media/{media_id}")
        sizes = data.get("media_details", {}).get("sizes", {})
        url   = (sizes.get("medium_large") or sizes.get("medium") or {}).get("source_url") \
                or data.get("source_url", "")
        _media_cache[media_id] = url
        return url
    except Exception:
        return None


def extract_films_from_page(html):
    """Extrai Film objects do payload de hidratação Nuxt (array JSON embebido no HTML)."""
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for script in scripts:
        if len(script) < 1000 or not script.startswith('['):
            continue
        try:
            data = json.loads(script)
        except Exception:
            continue
        films = []
        for item in data:
            if not isinstance(item, str):
                continue
            try:
                obj = json.loads(item)
                if isinstance(obj, dict) and "sessions" in obj and "slug" in obj:
                    films.append(obj)
            except Exception:
                pass
        if films:
            return films
    return []


def scrape():
    import time
    from datetime import date
    today = date.today().isoformat()

    print("[Trindade] A carregar página de programação...")
    raw_films = []
    for attempt in range(3):
        if attempt > 0:
            print(f"[Trindade] Tentativa {attempt + 1}/3...")
            time.sleep(3)
        try:
            html = fetch(PROG_URL)
            raw_films = extract_films_from_page(html)
        except Exception as e:
            print(f"[Trindade] Erro na tentativa {attempt + 1}: {e}")
        if raw_films:
            break

    print(f"[Trindade] {len(raw_films)} filmes encontrados na página, a filtrar sessões futuras...")

    movies = []
    for film in raw_films:
        # ── Sessões futuras ───────────────────────────────────────────────────
        future = []
        for s in film.get("sessions", []):
            date_str = s.get("date", "")
            time_obj = s.get("time", {})
            time_str = time_obj.get("start", "") if isinstance(time_obj, dict) else ""
            if not date_str or not time_str or date_str < today:
                continue
            sess = {"date": date_str, "time": time_str, "cinema": CINEMA_ID}
            note = (s.get("notes") or "").strip()
            if note:
                sess["labels"] = [note]
            future.append(sess)

        if not future:
            continue

        future.sort(key=lambda s: (s["date"], s["time"]))

        # ── Título ───────────────────────────────────────────────────────────
        title = unescape(film.get("title", "")).strip()
        if not title:
            continue

        # ── Realizador ───────────────────────────────────────────────────────
        director_ids = film.get("directors") or []
        names = [n for did in director_ids if (n := get_director(did))]
        director = ", ".join(names) or None

        # ── Poster ───────────────────────────────────────────────────────────
        poster = None
        poster_id = film.get("poster")
        if poster_id:
            poster = get_poster_url(poster_id)

        year     = film.get("year")
        duration = film.get("runtime")
        slug     = film.get("slug", "")
        film_id  = film.get("id", slug)
        link     = f"{BASE_URL}/pt/filmes/{slug}"

        print(f"  → {title} ({director}, {year}, {duration}min) — {len(future)} sessão(ões)")
        movies.append({
            "id":       f"trindade_{film_id}",
            "title":    title,
            "director": director,
            "year":     year,
            "duration": duration,
            "poster":   poster,
            "genres":   [],
            "link":     link,
            "sessions": future,
        })

    print(f"[Trindade] {len(movies)} filmes com sessões futuras.")
    return movies


if __name__ == "__main__":
    print(json.dumps(scrape(), ensure_ascii=False, indent=2))
