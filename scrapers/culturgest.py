"""
Scraper: Culturgest Lisboa
Fonte: https://www.culturgest.pt/en/whats-on/schedule/events/?typology=5

Inclui apenas sessões individuais de cinema com data e hora específicas.
Eventos de festival com intervalo de datas (ex: "30 APR – 10 MAY") são ignorados
porque não têm sessões individuais identificáveis.
"""

import urllib.request
import http.cookiejar
import re
from html import unescape
from datetime import date

CINEMA_ID   = "culturgest"
BASE_URL    = "https://www.culturgest.pt"
LISTING_URL = f"{BASE_URL}/en/whats-on/by-event/?typology=5"
EVENTS_URL  = f"{BASE_URL}/en/whats-on/schedule/events/?typology=5"

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# Opener partilhado com cookie jar (necessário para o endpoint AJAX do Django)
_jar    = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))


def _fetch(url, referer=None, ajax=False):
    headers = {"User-Agent": _UA}
    if referer:
        headers["Referer"] = referer
    if ajax:
        headers["X-Requested-With"] = "XMLHttpRequest"
    req = urllib.request.Request(url, headers=headers)
    with _opener.open(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="ignore")


def fetch_html(url):
    """Busca uma página de detalhe de evento (usa o opener com cookies)."""
    return _fetch(url)


def _clean(html_frag):
    return unescape(re.sub(r"<[^>]+>", " ", html_frag)).strip()


def _parse_date_time(date_block_html):
    """
    Extrai (date_str, time_str) do bloco:
      <p>13 MAY 2026<br />WED 19:00</p>  →  ("2026-05-13", "19:00")
    Retorna (None, None) se for um intervalo de datas ("–") sem hora específica.
    """
    text = re.sub(r"<br\s*/?>", "\n", date_block_html, flags=re.IGNORECASE)
    text = _clean(text)

    # Intervalo de datas → ignorar
    if "\u2013" in text or "\u2014" in text or re.search(r"\d\s*[-\u2013\u2014]\s*\d", text):
        return None, None

    # Hora obrigatória
    time_m = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if not time_m:
        return None, None
    time_str = f"{int(time_m.group(1)):02d}:{time_m.group(2)}"

    # Data: "13 MAY 2026" ou "13 MAY\n2026" etc.
    date_m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})", text)
    if not date_m:
        return None, None
    month = MONTH_MAP.get(date_m.group(2).lower()[:3])
    if not month:
        return None, None
    date_str = f"{int(date_m.group(3))}-{month:02d}-{int(date_m.group(1)):02d}"
    return date_str, time_str


def _scrape_event(path):
    """
    Obtém metadados de um evento individual.
    Retorna None se for um festival/evento sem hora específica.
    """
    url = BASE_URL + path
    try:
        html = fetch_html(url)
    except Exception:
        return None

    # Bloco de data/hora
    date_block = re.search(
        r'class="event-info-block date"[^>]*>(.*?)</div>', html, re.DOTALL
    )
    if not date_block:
        return None
    date_str, time_str = _parse_date_time(date_block.group(1))
    if not date_str:
        return None  # Intervalo de datas → festival, ignorar

    today = date.today().isoformat()
    if date_str < today:
        return None  # Sessão já passou

    # Título e subtítulo dentro do event-detail-header
    header_m = re.search(r'class="event-detail-header">(.*?)</header>', html, re.DOTALL)
    if not header_m:
        return None
    header = header_m.group(1)

    h1_m  = re.search(r"<h1[^>]*>(.*?)</h1>", header, re.DOTALL)
    sub_m = re.search(r'class="subtitle"[^>]*>(.*?)</', header, re.DOTALL)
    artist   = _clean(h1_m.group(1))  if h1_m  else ""
    subtitle = _clean(sub_m.group(1)) if sub_m else ""

    # Se há subtítulo, é o título do filme; o h1 é o realizador/artista
    film_title = subtitle if subtitle else artist
    director   = artist   if subtitle else None

    if not film_title:
        return None

    # Poster: primeiro <source srcset> no highlight-banner (768x768, crop quadrado)
    poster = None
    banner_m = re.search(r'class="[^"]*highlight-banner[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    if banner_m:
        src_m = re.search(r'<source\s+srcset="([^"]+)"', banner_m.group(1))
        if src_m:
            poster = BASE_URL + src_m.group(1) if src_m.group(1).startswith("/") else src_m.group(1)

    # ID baseado no slug do URL
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


def scrape():
    print("[Culturgest] A carregar programação de cinema...")

    try:
        # Visita a página principal primeiro para obter o cookie de sessão Django
        _fetch(LISTING_URL)
        # Agora busca o JSON/HTML dos eventos via endpoint AJAX
        html = _fetch(EVENTS_URL, referer=LISTING_URL, ajax=True)
    except Exception as e:
        print(f"  Erro: {e}")
        return []

    # Links únicos de eventos (strip query string; ignora páginas de navegação)
    _NAV = {"full-view", "by-event", "filter", "archive", "pdf-agenda"}
    seen, links = set(), []
    for raw in re.findall(r'<a href="(/en/whats-on/[^"]+)"', html):
        path = raw.split("?")[0].split("#")[0].rstrip("/")
        slug = path.rsplit("/", 1)[-1]
        if slug not in _NAV and path not in seen:
            seen.add(path)
            links.append(path)

    movies = []
    for link in links:
        film = _scrape_event(link)
        if film:
            s = film["sessions"][0]
            print(f"  → {film['title']}  ({film['director']}) — {s['date']} {s['time']}")
            movies.append(film)

    print(f"[Culturgest] {len(movies)} filmes encontrados.")
    return movies


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), ensure_ascii=False, indent=2))
