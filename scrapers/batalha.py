"""
Scraper: Batalha Centro de Cinema (Porto)
API: https://repeater.bondlayer.com/fetch  (BndLyr CMS)
Colecção de sessões: cjN82wrJdnNJZqCM   Projeto: sibrwridqpbpm4e3
"""

import urllib.request
import json
import re
from html import unescape
from datetime import datetime, timezone, timedelta

CINEMA_ID  = "batalha"
BASE_URL   = "https://www.batalhacentrodecinema.pt"
API_URL    = "https://repeater.bondlayer.com/fetch"
PROJECT_ID = "sibrwridqpbpm4e3"
COLLECTION = "cjN82wrJdnNJZqCM"
REPEATER_ID = "ck42eatHiYE3bglX"
HASH       = "1775044304610"


def utc_to_lisbon(dt_str):
    """Converte ISO UTC para data/hora de Lisboa (UTC+1 inverno, UTC+2 verão DST)."""
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    year = dt.year
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
    local     = dt + timedelta(hours=offset)
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")


def get_str(obj, key):
    """Devolve string de campo BndLyr ({all: ...} ou str)."""
    val = obj.get(key, "") if isinstance(obj, dict) else ""
    if isinstance(val, dict):
        val = val.get("all") or val.get("pt") or val.get("en") or ""
    return unescape(re.sub(r"<[^>]+>", "", str(val or ""))).strip()


def get_text(obj, key, lang):
    """Como get_str mas para campos de texto longo numa língua específica.

    A BndLyr guarda a versão portuguesa em "all" e a inglesa em "en", e o
    conteúdo vem em HTML — ao contrário de get_str, aqui as tags de bloco
    passam a quebras de linha em vez de desaparecerem e colarem palavras.
    """
    val = obj.get(key, "") if isinstance(obj, dict) else ""
    if isinstance(val, dict):
        val = val.get(lang) or (val.get("all") if lang == "pt" else "") or ""
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", str(val or ""))
    s = unescape(re.sub(r"<[^>]+>", "", s))
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n{2,}", "\n", s).strip()


def fetch_sessions():
    """Chama o BndLyr repeater API e devolve items + related."""
    payload = {
        "projectId": PROJECT_ID,
        "contentId": "0",
        "locale":    "pt",
        "hash":      HASH,
        "repeater": {
            "id":         REPEATER_ID,
            "repeaterId": REPEATER_ID,
            "collection": COLLECTION,
            "filters": [
                {
                    "attr":             "datetime_date",
                    "condition":        "datetime-isSameOrAfter",
                    "dateDirection":    "_future",
                    "dateStart":        "_today",
                    "dateExcludeToday": False,
                    "remoteFilter":     False,
                }
            ],
            "sorts":      [{"attr": "datetime_date", "direction": "asc"}],
            "limit":      {"enabled": False},
            "pagination": {"enabled": False},
            "page":       0,
            "perPage":    500,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "cineportugal/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        resp = json.loads(r.read().decode("utf-8"))
    if resp.get("error"):
        raise RuntimeError(f"BndLyr API error: {resp['error']}")
    return resp.get("items", []), resp.get("related", [])


def scrape():
    print("[Batalha] A chamar BndLyr API para sessões futuras...")
    items, related_list = fetch_sessions()
    print(f"[Batalha] {len(items)} sessões, {len(related_list)} registos relacionados")

    # related é um dict {id: record}
    films = related_list if isinstance(related_list, dict) else {}
    # Também indexa por lowercase para facilitar lookup (IDs podem ter case misto)
    films_lower = {k.lower(): v for k, v in films.items()}

    # Agrupa sessões por filme(s)
    movie_map = {}  # film_id → {meta, sessions[]}

    for item in items:
        date_raw = item.get("datetime_date", "")
        if not date_raw:
            continue

        date_str, time_str = utc_to_lisbon(date_raw)

        presenca = get_str(item, "text_presencas")
        sess = {"date": date_str, "time": time_str, "cinema": CINEMA_ID}
        if presenca:
            sess["labels"] = [presenca]

        # Sessão de filme único
        ref_film = item.get("ref_film")
        # Sessão multi-filme
        multi = item.get("multiRef_films") or {}
        if isinstance(multi, dict):
            multi_ids = sorted(multi.keys(), key=lambda k: multi[k])
        elif isinstance(multi, list):
            multi_ids = multi
        else:
            multi_ids = []

        if ref_film:
            film_ids = [ref_film]
        elif multi_ids:
            film_ids = multi_ids
        else:
            # Sem filme associado — evento/quiz/visita, ignorar
            continue

        for fid in film_ids:
            if fid not in movie_map:
                movie_map[fid] = {"film_id": fid, "sessions": []}
            movie_map[fid]["sessions"].append(sess)

    movies = []
    for fid, entry in movie_map.items():
        film = films.get(fid) or films_lower.get(fid.lower()) or {}

        title = get_str(film, "text_display_title") or get_str(film, "text_title")
        if not title:
            title = get_str(film, "_slug") or fid
            title = title.replace("-", " ").title()

        d1 = get_str(film, "text_director1")
        d2 = get_str(film, "text_director2")
        director = ", ".join(filter(None, [d1, d2])) or None

        year     = film.get("number_year_of_production")
        duration = film.get("number_minutes")
        if year:     year     = int(year)
        if duration: duration = int(duration)

        poster = get_str(film, "image_photo") or None
        slug   = get_str(film, "_slug") or fid.replace("_", "-")
        link   = f"{BASE_URL}/filmes/{slug}"

        # A API já traz o título original e a sinopse em português e inglês —
        # o título original é o que o Letterboxd e o IMDb indexam (o Batalha
        # lista muito filme com o título traduzido), e a sinopse do cinema é
        # a da programação oficial, melhor do que qualquer aproximação.
        original_title = get_str(film, "text_original_title") or None
        if original_title and original_title.lower() == title.lower():
            original_title = None
        plot_pt = get_text(film, "text_sinopse", "pt") or None
        plot_en = get_text(film, "text_sinopse", "en") or None
        country = get_str(film, "text_productioncountry1") or None

        # Deduplica sessões
        seen, unique = set(), []
        for s in entry["sessions"]:
            k = (s["date"], s["time"])
            if k not in seen:
                seen.add(k)
                unique.append(s)
        unique.sort(key=lambda s: (s["date"], s["time"]))

        print(f"  → {title} ({director}, {year}, {duration}min) — {len(unique)} sessão(ões)")
        movie = {
            "id":       f"batalha_{fid}",
            "title":    title,
            "director": director,
            "year":     year,
            "duration": duration,
            "poster":   poster,
            "genres":   [],
            "link":     link,
            "sessions": unique,
        }
        if original_title: movie["original_title"] = original_title
        if plot_pt:        movie["plot_pt"]        = plot_pt
        if plot_en:        movie["plot"]           = plot_en
        if country:        movie["country"]        = country
        movies.append(movie)

    print(f"[Batalha] {len(movies)} filmes encontrados.")
    return movies


if __name__ == "__main__":
    print(json.dumps(scrape(), ensure_ascii=False, indent=2))
