"""
Scraper: Culturgest Lisboa
Fontes:
  - https://www.culturgest.pt/en/whats-on/schedule/events/?typology=5
    → sessões individuais de cinema com data e hora específicas
  - https://indielisboa.com/en/festival/schedule/?caldt=YYYY-MM-DD
    → sessões IndieLisboa no Culturgest (quando o festival está em programação)
"""

import urllib.request
import http.cookiejar
import re
from html import unescape
from datetime import date, timedelta

CINEMA_ID   = "culturgest"
BASE_URL    = "https://www.culturgest.pt"
LISTING_URL = f"{BASE_URL}/en/whats-on/by-event/?typology=5"
EVENTS_URL  = f"{BASE_URL}/en/whats-on/schedule/events/?typology=5"

INDIE_SCHEDULE_URL = "https://indielisboa.com/en/festival/schedule/"

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

_jar    = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))


def _fetch(url, referer=None, ajax=False):
    headers = {"User-Agent": _UA}
    if referer:
        headers["Referer"] = referer
    if ajax:
        headers["X-Requested-With"] = "XMLHttpRequest"
    req = urllib.request.Request(url, headers=headers)
    with _opener.open(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")


def _clean(html_frag):
    return unescape(re.sub(r"<[^>]+>", " ", html_frag)).strip()


def _parse_date_time(date_block_html):
    """
    <p>13 MAY 2026<br />WED 19:00</p>  →  ("2026-05-13", "19:00")
    Retorna (None, None) se for intervalo de datas sem hora específica.
    """
    text = re.sub(r"<br\s*/?>", "\n", date_block_html, flags=re.IGNORECASE)
    text = _clean(text)
    if "\u2013" in text or "\u2014" in text or re.search(r"\d\s*[-\u2013\u2014]\s*\d", text):
        return None, None
    time_m = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if not time_m:
        return None, None
    time_str = f"{int(time_m.group(1)):02d}:{time_m.group(2)}"
    date_m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})", text)
    if not date_m:
        return None, None
    month = MONTH_MAP.get(date_m.group(2).lower()[:3])
    if not month:
        return None, None
    date_str = f"{int(date_m.group(3))}-{month:02d}-{int(date_m.group(1)):02d}"
    return date_str, time_str


def _parse_festival_dates(date_block_html):
    """
    <p>30 APR<br />– 10 MAY 2026</p>  →  ["2026-04-30", …, "2026-05-10"]
    Retorna lista vazia se não conseguir parsear.
    """
    text = re.sub(r"<br\s*/?>", " ", date_block_html, flags=re.IGNORECASE)
    text = _clean(text)
    # Padrão: "30 APR – 10 MAY 2026"  ou  "30 APR – 10 MAY\n2026"
    m = re.search(
        r"(\d{1,2})\s+([A-Za-z]{3,})\s*[\u2013\u2014-]\s*(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})",
        text,
    )
    if not m:
        return []
    m1 = MONTH_MAP.get(m.group(2).lower()[:3])
    m2 = MONTH_MAP.get(m.group(4).lower()[:3])
    year = int(m.group(5))
    if not m1 or not m2:
        return []
    start = date(year, m1, int(m.group(1)))
    end   = date(year, m2, int(m.group(3)))
    days  = []
    d = start
    while d <= end:
        days.append(d.isoformat())
        d += timedelta(days=1)
    return days


# ── Culturgest standalone events ──────────────────────────────────────────────

def _scrape_event(path):
    """Obtém um evento individual com data+hora específica no Culturgest."""
    url = BASE_URL + path
    try:
        html = _fetch(url)
    except Exception:
        return None

    date_block = re.search(r'class="event-info-block date"[^>]*>(.*?)</div>', html, re.DOTALL)
    if not date_block:
        return None

    date_str, time_str = _parse_date_time(date_block.group(1))
    if not date_str:
        return None

    today = date.today().isoformat()
    if date_str < today:
        return None

    header_m = re.search(r'class="event-detail-header">(.*?)</header>', html, re.DOTALL)
    if not header_m:
        return None
    header = header_m.group(1)

    h1_m  = re.search(r"<h1[^>]*>(.*?)</h1>", header, re.DOTALL)
    sub_m = re.search(r'class="subtitle"[^>]*>(.*?)</', header, re.DOTALL)
    artist   = _clean(h1_m.group(1))  if h1_m  else ""
    subtitle = _clean(sub_m.group(1)) if sub_m else ""

    film_title = subtitle if subtitle else artist
    director   = artist   if subtitle else None
    if not film_title:
        return None

    poster = None
    banner_m = re.search(r'class="[^"]*highlight-banner[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    if banner_m:
        src_m = re.search(r'<source\s+srcset="([^"]+)"', banner_m.group(1))
        if src_m:
            poster = (BASE_URL + src_m.group(1)) if src_m.group(1).startswith("/") else src_m.group(1)

    slug = path.rstrip("/").rsplit("/", 1)[-1]
    return {
        "id":       f"culturgest_{slug}",
        "title":    film_title,
        "director": director,
        "year":     None,
        "duration": None,
        "poster":   poster,
        "genres":   [],
        "link":     url,
        "sessions": [{"date": date_str, "time": time_str, "cinema": CINEMA_ID}],
    }


# ── IndieLisboa sessions at Culturgest ────────────────────────────────────────

INDIE_MONTHS = {
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
}


def _parse_indie_day(html):
    """
    Extrai sessões no Culturgest de uma página do calendário IndieLisboa.
    Retorna lista de {title, date_str, time_str, duration, url}.
    """
    h2s = [
        (m.start(), unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip())
        for m in re.finditer(r"<h2[^>]*>(.*?)</h2>", html, re.DOTALL)
    ]
    title_links = [
        (m.start(), unescape(re.sub(r"<[^>]+>", "", m.group(0))).strip(), m.group(1))
        for m in re.finditer(
            r'<a href="(https://indielisboa\.com/en/screening/[^"]+)"[^>]*>.*?</a>',
            html, re.DOTALL,
        )
    ]

    sessions = []
    for i in range(len(h2s) - 1):
        pos_dt, text_dt = h2s[i]
        _,      text_v  = h2s[i + 1]
        if "Culturgest" not in text_v:
            continue

        # Parse "May 02 2026, Saturday, 15:00 (96')"
        dm = re.match(
            r"(\w+)\s+(\d+)\s+(\d{4}),\s*\w+,\s*(\d+:\d+)(?:\s*\((\d+)'?\))?",
            text_dt,
        )
        if not dm:
            continue
        month = INDIE_MONTHS.get(dm.group(1).lower())
        if not month:
            continue
        date_str = f"{dm.group(3)}-{month:02d}-{int(dm.group(2)):02d}"
        time_str = dm.group(4)
        duration = int(dm.group(5)) if dm.group(5) else None

        # Title: nearest screening link before pos_dt
        cands = [(p, t, u) for p, t, u in title_links if p < pos_dt]
        if not cands:
            continue
        _, title, scr_url = max(cands, key=lambda x: x[0])

        sessions.append({
            "title":    title,
            "date_str": date_str,
            "time_str": time_str,
            "duration": duration,
            "url":      scr_url,
        })

    return sessions


def _scrape_indielisboa(festival_dates):
    """
    Busca todas as sessões IndieLisboa no Culturgest para o período do festival.
    Agrupa por título e devolve lista de movie dicts.
    """
    today = date.today().isoformat()
    movies = {}  # title_key → movie dict

    _SKIP = re.compile(
        r"(?:lisbon\s*talk|indietalk|talk\s*#\d|workshop|debate|conversa|lecture)",
        re.IGNORECASE,
    )

    for day in festival_dates:
        if day < today:
            continue
        url = f"{INDIE_SCHEDULE_URL}?caldt={day}"
        try:
            html = _fetch(url)
        except Exception as e:
            print(f"    [IndieFilboa] Erro em {day}: {e}")
            continue

        for s in _parse_indie_day(html):
            if _SKIP.search(s["title"]):
                continue
            key = s["title"].lower().strip()
            if key not in movies:
                movies[key] = {
                    "id":       f"culturgest_indie_{re.sub(r'[^a-z0-9]', '_', key)[:40]}",
                    "title":    s["title"],
                    "director": None,
                    "year":     None,
                    "duration": s["duration"],
                    "poster":   None,
                    "genres":   [],
                    "link":     s["url"],
                    "sessions": [],
                    "festival": "INDIE",
                }
            movies[key]["sessions"].append({
                "date":    s["date_str"],
                "time":    s["time_str"],
                "cinema":  CINEMA_ID,
                "labels":  ["INDIE Lisboa 2026"],
            })

    return list(movies.values())


# ── Main ──────────────────────────────────────────────────────────────────────

def scrape():
    print("[Culturgest] A carregar programação de cinema...")

    try:
        _fetch(LISTING_URL)
        events_html = _fetch(EVENTS_URL, referer=LISTING_URL, ajax=True)
    except Exception as e:
        print(f"  Erro: {e}")
        return []

    _NAV = {"full-view", "by-event", "filter", "archive", "pdf-agenda"}
    seen, event_paths = set(), []
    for raw in re.findall(r'<a href="(/en/whats-on/[^"]+)"', events_html):
        path = raw.split("?")[0].split("#")[0].rstrip("/")
        slug = path.rsplit("/", 1)[-1]
        if slug not in _NAV and path not in seen:
            seen.add(path)
            event_paths.append(path)

    movies = []

    for path in event_paths:
        url = BASE_URL + path
        try:
            detail_html = _fetch(url)
        except Exception:
            continue

        date_block = re.search(
            r'class="event-info-block date"[^>]*>(.*?)</div>', detail_html, re.DOTALL
        )
        if not date_block:
            continue

        date_str, time_str = _parse_date_time(date_block.group(1))

        if date_str:
            # Sessão individual com hora específica
            film = _scrape_event(path)
            if film:
                s = film["sessions"][0]
                print(f"  → {film['title']}  ({film['director']}) — {s['date']} {s['time']}")
                movies.append(film)

        elif "indielisboa" in detail_html.lower():
            # Evento de festival IndieLisboa → buscar sessões no calendário IndieFilboa
            festival_dates = _parse_festival_dates(date_block.group(1))
            if festival_dates:
                print(f"  [INDIE] A carregar sessões Culturgest ({festival_dates[0]} → {festival_dates[-1]})...")
                indie_movies = _scrape_indielisboa(festival_dates)
                for m in indie_movies:
                    n_sess = len(m["sessions"])
                    print(f"    → {m['title']} — {n_sess} sessão(ões)")
                movies.extend(indie_movies)

    print(f"[Culturgest] {len(movies)} filmes encontrados.")
    return movies


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), ensure_ascii=False, indent=2))
