"""
Scraper: Cinema Ideal (Lisboa)
Sessões:   https://bilheteira.cinemaidealemcasa.pt/session/with-movies (JSON API exacta)
Realizador: https://www.cinemaidealemcasa.pt/no-cinema/ (HTML, campo nome_realizador)
"""

import urllib.request
import json
import re
from html import unescape
from collections import defaultdict

CINEMA_ID    = "ideal"
BASE_URL     = "https://www.cinemaidealemcasa.pt"
PROG_URL     = f"{BASE_URL}/no-cinema/"
SESSIONS_API = "https://bilheteira.cinemaidealemcasa.pt/session/with-movies"

# "INDIE BARRIO TRISTE 138" → ("Barrio Triste", True)
_INDIE_RE = re.compile(r'^INDIE\s+(.+)\s+\d+$', re.IGNORECASE)

# Billing titles that lack the INDIE prefix but are INDIE films
_INDIE_OVERRIDES = {
    "NÃO DESVIAR O OLHAR 429": "Não Desviar o Olhar",
}

def _title_case(s):
    """Title-case without capitalizing letters after apostrophes (e.g. "River's" not "River'S")."""
    return re.sub(r"(?<!['\u00b4\u2019])\b(\w)", lambda m: m.group(1).upper(), s.lower())

def _parse_indie(raw_title):
    """Returns (clean_title, is_indie). Strips INDIE prefix and trailing billing number."""
    if raw_title in _INDIE_OVERRIDES:
        return _INDIE_OVERRIDES[raw_title], True
    m = _INDIE_RE.match(raw_title.strip())
    if not m:
        return raw_title, False
    film = m.group(1).strip()
    # Title-case ALL-CAPS titles; normalize ´ → ' to avoid bad casing
    if film == film.upper():
        film = film.replace("\u00b4", "'")
        film = _title_case(film)
    return film, True


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; cinelisboa/1.0)",
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="ignore")


def fetch_sessions():
    """Devolve sessões reais da bilheteira: {title → [(date_str, time_str)]}."""
    data = json.loads(fetch(SESSIONS_API))
    by_movie = defaultdict(list)
    for s in data:
        if s.get("sessionState", 0) != 0:
            continue  # salta sessões canceladas/fechadas
        title = unescape(s["movie"]["title"]).strip()
        dt    = s["dateTime"]  # "2026-04-03T14:30:00"
        date_str, time_str = dt[:10], dt[11:16]
        poster = s["movie"].get("imageUrl") or None
        by_movie[title].append({
            "date":   date_str,
            "time":   time_str,
            "poster": poster,
            "link":   f"https://bilheteira.cinemaidealemcasa.pt/?movieid={s['movie']['id']}",
        })
    return by_movie


def fetch_directors():
    """Lê /no-cinema/ e devolve {title_upper → director}."""
    html = fetch(PROG_URL)
    directors = {}
    # Split em blocos por filme
    blocks = re.split(r'data-movie-date="[^"]*"[^>]*>', html)
    for block in blocks:
        m_title = re.search(r'nome_filme_em_cartaz[^>]*>.*?<p>(.*?)</p>', block, re.DOTALL)
        m_dir   = re.search(r'nome_realizador_em_cartaz[^>]*>.*?<p>(.*?)</p>', block, re.DOTALL)
        if m_title and m_dir:
            title = unescape(re.sub(r'<[^>]+>', '', m_title.group(1))).strip().upper()
            dire  = unescape(re.sub(r'<[^>]+>', '', m_dir.group(1))).strip()
            if title and dire:
                directors[title] = dire
    return directors


def scrape():
    print("[Cinema Ideal] A carregar sessões da bilheteira...")
    try:
        by_movie = fetch_sessions()
    except Exception as e:
        print(f"[Cinema Ideal] Erro na bilheteira: {e}")
        return []

    print("[Cinema Ideal] A carregar realizadores do site...")
    try:
        directors = fetch_directors()
    except Exception as e:
        print(f"[Cinema Ideal] Aviso: não foi possível obter realizadores: {e}")
        directors = {}

    movies = []
    for raw_title, sess_list in by_movie.items():
        clean_title, is_indie = _parse_indie(raw_title)
        director = (directors.get(clean_title.upper())
                    or directors.get(raw_title.upper())
                    or directors.get(raw_title) or None)
        poster   = next((s["poster"] for s in sess_list if s.get("poster")), None)
        link     = sess_list[0]["link"] if sess_list else PROG_URL

        sessions = sorted(
            [{"date": s["date"], "time": s["time"], "cinema": CINEMA_ID} for s in sess_list],
            key=lambda s: (s["date"], s["time"]),
        )

        film_id = re.sub(r'[^a-z0-9]', '_', clean_title.lower())[:40]
        festival = "INDIE Lisboa" if is_indie else None
        print(f"  → {clean_title} ({director}) {'[INDIE] ' if is_indie else ''}— {len(sessions)} sessão(ões)")
        movies.append({
            "id":       f"ideal_{film_id}",
            "title":    clean_title,
            "director": director,
            "year":     None,
            "duration": None,
            "poster":   poster,
            "genres":   [],
            "festival": festival,
            "link":     link,
            "sessions": sessions,
        })

    print(f"[Cinema Ideal] {len(movies)} filmes encontrados.")
    return movies


if __name__ == "__main__":
    print(json.dumps(scrape(), ensure_ascii=False, indent=2))
