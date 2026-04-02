"""
Scraper: Batalha Centro de Cinema (Porto)
Fonte: https://www.batalhacentrodecinema.pt/
Platform: BndLyr CMS — sessões em content JS file
"""

import urllib.request
import re
import json
from html import unescape
from datetime import datetime, timezone, timedelta

CINEMA_ID = "batalha"
BASE_URL  = "https://www.batalhacentrodecinema.pt"
HOME_URL  = BASE_URL + "/"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cineportugal/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")


def utc_to_lisbon(dt_str):
    """Converte datetime ISO UTC para data/hora de Lisboa (UTC+1 inverno, UTC+2 verão)."""
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    year = dt.year
    # Último domingo de março = início DST, último domingo de outubro = fim DST
    def last_sunday(y, month):
        for d in range(31, 24, -1):
            try:
                if datetime(y, month, d).weekday() == 6:
                    return datetime(y, month, d, 1, 0, tzinfo=timezone.utc)
            except ValueError:
                pass
    dst_start = last_sunday(year, 3)
    dst_end   = last_sunday(year, 10)
    offset    = 2 if dst_start <= dt < dst_end else 1
    lisbon    = dt + timedelta(hours=offset)
    return lisbon.strftime("%Y-%m-%d"), lisbon.strftime("%H:%M")


def extract_content_url(html):
    """Extrai o URL do content JS a partir do HTML da homepage."""
    m = re.search(r'(https://cdn\.bndlyr\.com/[^"\']+content\.[^"\']+\.js[^"\']*)', html)
    if m:
        return m.group(1)
    return None


def parse_bndlyr_json(js_text):
    """Extrai window.BndLyrContent do JS e devolve o dict."""
    m = re.search(r'window\.BndLyrContent\s*=\s*', js_text)
    if not m:
        return None
    start = m.end()
    depth, i = 0, start
    while i < len(js_text):
        if js_text[i] == '{':
            depth += 1
        elif js_text[i] == '}':
            depth -= 1
            if depth == 0:
                return json.loads(js_text[start:i + 1])
        i += 1
    return None


def get_str(obj, key):
    """Devolve string de um campo BndLyr (pode ser str ou {"all": "...", "en": "..."})."""
    val = obj.get(key, "")
    if isinstance(val, dict):
        val = val.get("all") or val.get("en") or ""
    return unescape(re.sub(r"<[^>]+>", "", val or "")).strip()


def scrape():
    print("[Batalha] A carregar homepage...")
    html = fetch(HOME_URL)

    content_url = extract_content_url(html)
    if not content_url:
        print("[Batalha] ERRO: URL do content JS não encontrado")
        return []

    print(f"[Batalha] Content JS: {content_url}")
    js_text = fetch(content_url)

    data = parse_bndlyr_json(js_text)
    if not data:
        print("[Batalha] ERRO: não consegui parsear BndLyrContent")
        return []

    # ── Recolhe sessões e filmes de todos os repeaters ───────────────────────
    sessions_by_film = {}  # film_id → list of session dicts
    film_records = {}      # film_id → BndLyr film object

    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        items   = value.get("items", [])
        related = value.get("related", {})
        if not isinstance(items, list) or not items:
            continue

        # Repeater de sessões: itens têm datetime_date + ref_film
        if "datetime_date" in items[0] and "ref_film" in items[0]:
            for item in items:
                ref_film = item.get("ref_film")
                dt_str   = item.get("datetime_date", "")
                if not ref_film or not dt_str:
                    continue
                date_str, time_str = utc_to_lisbon(dt_str)
                presenca = get_str(item, "text_presencas")
                sessions_by_film.setdefault(ref_film, []).append({
                    "date": date_str, "time": time_str, "presenca": presenca
                })

        # Registo de filmes no campo related
        for fid, fdata in (related or {}).items():
            if isinstance(fdata, dict) and ("text_title" in fdata or "text_display_title" in fdata):
                film_records[fid] = fdata

    if not sessions_by_film:
        print("[Batalha] AVISO: nenhuma sessão encontrada")
        return []

    movies = []
    for film_id, sessions in sessions_by_film.items():
        film = film_records.get(film_id, {})

        # Título (prefere display_title)
        title = get_str(film, "text_display_title") or get_str(film, "text_title")
        if not title:
            slug = get_str(film, "_slug") or film_id
            title = slug.replace("-", " ").title()

        # Realizador
        d1 = get_str(film, "text_director1")
        d2 = get_str(film, "text_director2")
        director = ", ".join(filter(None, [d1, d2])) or None

        year     = film.get("number_year_of_production")
        duration = film.get("number_minutes")
        if year:     year     = int(year)
        if duration: duration = int(duration)

        poster = get_str(film, "image_photo") or None
        slug   = get_str(film, "_slug") or film_id.replace("_", "-")
        link   = f"{BASE_URL}/filmes/{slug}"

        # Deduplica e converte sessões
        seen, unique = set(), []
        for s in sessions:
            k = (s["date"], s["time"])
            if k not in seen:
                seen.add(k)
                sess = {"date": s["date"], "time": s["time"], "cinema": CINEMA_ID}
                if s.get("presenca"):
                    sess["labels"] = [s["presenca"]]
                unique.append(sess)
        unique.sort(key=lambda s: (s["date"], s["time"]))

        print(f"  → {title} ({director}, {year}, {duration}min) — {len(unique)} sessão(ões)")
        movies.append({
            "id":       f"batalha_{film_id}",
            "title":    title,
            "director": director,
            "year":     year,
            "duration": duration,
            "poster":   poster,
            "genres":   [],
            "link":     link,
            "sessions": unique,
        })

    print(f"[Batalha] {len(movies)} filmes encontrados.")
    return movies


if __name__ == "__main__":
    print(json.dumps(scrape(), ensure_ascii=False, indent=2))
