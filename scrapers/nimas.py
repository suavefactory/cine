"""
Scraper: Cinema Medeia Nimas (Lisboa)
Fonte: https://medeiafilmes.com/filmes-em-exibicao
  - global.data.schedule.events → lista de filmes + filtro por cinema-medeia-nimas
  - Para cada filme: fetch da página individual para sessões detalhadas
"""

import urllib.request
import json
import re
import time
from html import unescape

CINEMA_ID = "nimas"
BASE_URL  = "https://medeiafilmes.com"
LIST_URL  = f"{BASE_URL}/filmes-em-exibicao"
NIMAS_SLUG = "cinema-medeia-nimas"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _normalise_session_label(text):
    """
    Condensa labels longos com listas de nomes num texto curto.
    Ex: "Presença dos actores X, Y, Z, o produtor W e ..."
        → "Presença da equipa e elenco"
    """
    t = text.lower()
    # Presença com lista de nomes (mais de uma vírgula = lista longa)
    if re.search(r'presen[çc]a\s+d', t) and (text.count(',') >= 1 or len(text) > 60):
        # Verifica se menciona realizador (não "directora da fotografia" etc.)
        if re.search(r'\brealizador\b', t) or re.search(r'\bdirector\b(?!\s+da\s+fotografia)', t):
            return "Presença do realizador e equipa"
        return "Presença da equipa e elenco"
    return text


def fetch_html(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="ignore")


def extract_global_data(html):
    """Extrai global.data do primeiro bloco <script> que o contém."""
    scripts = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    for s in scripts:
        if "global.data" in s:
            idx = s.find("global.data = ")
            if idx >= 0:
                js_obj = s[idx + len("global.data = "):].strip().rstrip(";")
                return json.loads(js_obj)
    return None


def parse_duration(length_str):
    """Converte '2h02' ou '1h30' para minutos."""
    if not length_str:
        return None
    m = re.match(r"(\d+)h(\d+)", length_str)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.match(r"(\d+)min", length_str)
    if m:
        return int(m.group(1))
    return None


def scrape_film_page(url, cinema_id, cinema_slug):
    """
    Obtém metadados e sessões de uma página de filme individual da Medeia Filmes.
    Retorna dict com: year, duration, genre, sessions (lista de {date, time}).
    """
    try:
        html  = fetch_html(url)
        data  = extract_global_data(html)
        if not data:
            return None
        film = data.get("film", {})

        year     = None
        yr_str   = film.get("production_year", "")
        if yr_str:
            try:
                year = int(str(yr_str)[:4])
            except ValueError:
                pass

        duration = parse_duration(film.get("length", ""))
        genre    = film.get("genre") or None

        programme = film.get("programme", {})
        sessions  = []
        for cinema_data in programme.values():
            if not isinstance(cinema_data, dict):
                continue
            if cinema_data.get("slug") != cinema_slug:
                continue
            for s in cinema_data.get("sessions", {}).values():
                if not isinstance(s, dict):
                    continue
                date  = s.get("date")
                hours = s.get("hours", [])
                info  = s.get("info", {})

                labels = []
                if isinstance(info, dict):
                    for item in info.values():
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = unescape(re.sub(r"<[^>]+>", "", item.get("text", ""))).strip()
                            if not text:
                                continue
                            text = _normalise_session_label(text)
                            labels.append(text[0].upper() + text[1:])

                for h in hours:
                    sess = {"date": date, "time": h, "cinema": cinema_id}
                    if labels:
                        sess["labels"] = labels[:]
                    sessions.append(sess)

        return {
            "year":     year,
            "duration": duration,
            "genre":    genre,
            "sessions": sessions,
        }
    except Exception as e:
        print(f"    Erro ao processar {url}: {e}")
        return None


def scrape_medeia_cinema(cinema_id, cinema_slug, label):
    """Função genérica para scraper qualquer cinema Medeia Filmes."""
    print(f"[{label}] A carregar lista de filmes...")
    html = fetch_html(LIST_URL)
    data = extract_global_data(html)
    if not data:
        raise RuntimeError(f"Não foi possível extrair global.data para {label}")

    events = data.get("schedule", {}).get("events", {})
    cinema_events = [
        ev for ev in events.values()
        if cinema_slug in ev.get("theaters", {})
        and "/filmes/" in ev.get("url", "")
    ]
    print(f"[{label}] {len(cinema_events)} filmes encontrados.")

    movies = []
    for ev in cinema_events:
        title    = unescape(ev.get("title", "").strip())
        director = ev.get("director")
        if director:
            director = unescape(director.strip()) or None
        image    = ev.get("image") or None
        url      = ev.get("url", "")

        if not title:
            continue

        slug = url.rstrip("/").split("/")[-1]
        print(f"  [{label}] {title}...", end=" ", flush=True)

        details = scrape_film_page(url, cinema_id, cinema_slug)
        time.sleep(0.3)

        if not details or not details["sessions"]:
            print("sem sessões")
            continue

        print(f"{len(details['sessions'])} sessão(ões)")

        genres = []
        if details.get("genre"):
            genres = [g.strip() for g in details["genre"].split(",") if g.strip()]

        movies.append({
            "id":       f"{cinema_id}_{slug}",
            "title":    title,
            "director": director,
            "year":     details["year"],
            "duration": details["duration"],
            "poster":   image,
            "genres":   genres,
            "link":     url,
            "sessions": sorted(details["sessions"], key=lambda s: (s["date"], s["time"])),
        })

    print(f"[{label}] {len(movies)} filmes com sessões.")
    return movies


def scrape():
    return scrape_medeia_cinema(CINEMA_ID, NIMAS_SLUG, "Nimas")


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(scrape(), ensure_ascii=False, indent=2))
