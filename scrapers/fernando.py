"""
Scraper: Cinema Fernando Lopes (Lisboa)
Fonte: https://cinemafernandolopes.pt/Programacao
  - Programação: <h2> blocks com datas (<b>DDD, DD mon</b>) e sessões (HHhMM - <a href="SLUG">TÍTULO</a>)
  - Metadados por filme: página individual /{SLUG}
  - Séries/ciclos detectados dinamicamente (mesmo slug, títulos diferentes) — não se faz fetch da página
"""

import urllib.request
import re
import time
from html import unescape
from datetime import date

CINEMA_ID = "fernando"
BASE_URL  = "https://cinemafernandolopes.pt"
PROG_URL  = f"{BASE_URL}/Programacao"

PT_MONTHS = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
}


def fetch_html(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="ignore")


def strip_tags(html):
    return re.sub(r"<[^>]+>", "", html)


def parse_date(date_str):
    """Converte 'qua, 25 mar' → '2026-03-25'. Avança o ano só se a data estiver
    há mais de 60 dias no passado (nunca para datas da semana corrente)."""
    m = re.search(r"(\d{1,2})\s+(\w{3})", date_str.lower())
    if not m:
        return None
    day   = int(m.group(1))
    month = PT_MONTHS.get(m.group(2))
    if not month:
        return None
    today = date.today()
    year  = today.year
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None
    # Avança o ano só se a data estiver mais de 60 dias no passado
    if (today - candidate).days > 60:
        year += 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_time(t):
    """Converte '21h00' → '21:00'."""
    m = re.match(r"(\d{1,2})h(\d{2})", t.strip())
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def clean_anchor_title(raw_html):
    """
    Remove tags internas de uma âncora: sufixos de série, 'última sessão', etc.
    Retorna texto limpo.
    """
    # Remove conteúdo de <b> que é metadata de série/estado
    # Usa .*? para apanhar nested tags dentro de <b> (ex: <b>- <small>última sessão</small></b>)
    raw_html = re.sub(r"<b>.*?(?:mostra|última\s+sessão|essencial|with\s+english).*?</b>",
                      "", raw_html, flags=re.IGNORECASE | re.DOTALL)
    # Remove <small>...</small>
    raw_html = re.sub(r"<small>.*?</small>", "", raw_html, flags=re.DOTALL)
    # Strip restantes tags
    text = strip_tags(raw_html)
    # Remove sufixos em texto puro (com ou sem traço antes)
    text = re.sub(r"\s*[-–]?\s*mostra\s+essencial.*$",        "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*[-–]?\s*última\s+sessão.*$",            "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*[-–]?\s*with\s+english\s+subtitles.*$", "", text, flags=re.IGNORECASE)
    text = unescape(text)
    # Remove traço inicial ou final residual
    text = re.sub(r"^\s*[-–]\s*", "", text)
    text = re.sub(r"\s*[-–]\s*$",  "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_schedule(html):
    """
    Extrai lista de dicts {title, slug, date, time} da página de programação.
    """
    sessions = []
    current_date = None

    for block in re.findall(r"<h2>(.*?)</h2>", html, re.DOTALL):
        # Verifica se o bloco contém um cabeçalho de data
        date_m = re.search(r"<b>\s*(\w+,\s*\d{1,2}\s+\w+)\s*</b>", block, re.IGNORECASE)
        if date_m:
            parsed = parse_date(date_m.group(1))
            if parsed:
                current_date = parsed
            # Continua a processar o resto do bloco (pode conter sessões a seguir à data)
            block = block[date_m.end():]

        if not current_date:
            continue

        # Encontra todas as sessões: HHhMM ([-–])? <a href="SLUG">TÍTULO...</a>
        # Suporta casos onde o traço está dentro da âncora ("21h30 <a>- TÍTULO</a>")
        for m in re.finditer(
            r"(\d{1,2}h\d{2})\s*[-–]?\s*"
            r"<a\s[^>]*href=[\"']([^\"'#][^\"']*)[\"'][^>]*>"
            r"(.*?)</a>",
            block, re.DOTALL
        ):
            time_raw, slug, title_raw = m.group(1), m.group(2), m.group(3)

            # Ignora links que não são filmes (subscrição, inglês, etc.)
            if "Screenings" in slug or "screenings" in slug:
                continue

            # Detect per-session labels from the raw anchor HTML (before cleaning)
            labels = []
            if re.search(r'with\s+english', title_raw, re.IGNORECASE):
                labels.append("Legendas em inglês")
            if re.search(r'última\s+sess[aã]o', title_raw, re.IGNORECASE):
                labels.append("Última sessão")

            t     = parse_time(time_raw)
            title = clean_anchor_title(title_raw)
            if t and title and len(title) > 1:
                s = {"title": title, "slug": slug, "date": current_date, "time": t}
                if labels:
                    s["labels"] = labels
                sessions.append(s)

    return sessions


def scrape_film_page(slug):
    """
    Obtém metadados (título, realizador, ano, duração, géneros, poster) de /{slug}.
    """
    url = f"{BASE_URL}/{slug}"
    try:
        html = fetch_html(url)

        # Título: primeiro <h1> não-vazio
        title = None
        for h1_m in re.finditer(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL):
            t = unescape(strip_tags(h1_m.group(1))).strip()
            if len(t) > 2 and "{" not in t and "}" not in t:
                title = t
                break

        # Metadados: <small>"SUBTITLE" / 2024 / M/12 / Drama / 122 MIN.</small>
        # Separador é " / " (espaço-barra-espaço) exceto em "M/12"
        year, duration, genres = None, None, []
        meta_m = re.search(r"<small>([^<]{8,}MIN[^<]*)</small>", html, re.IGNORECASE)
        if meta_m:
            meta = unescape(meta_m.group(1))
            parts = [p.strip() for p in meta.split(" / ")]
            for part in parts:
                if re.match(r"^(19|20)\d{2}$", part):
                    year = int(part)
                elif re.match(r"^\d{2,3}\s*MIN\.?$", part, re.IGNORECASE):
                    duration = int(re.search(r"\d+", part).group())
                elif re.match(r"^M/\d+$", part):
                    pass  # classificação etária
                elif part.startswith(('"', '\u201c', '\u201d')):
                    pass  # subtítulo original (aspas retas ou curvas)
                elif part and len(part) > 1 and not part[0].isdigit():
                    genres.append(part)

        # Realizador: <h2><small>REALIZAÇÃO</small></h2> seguido de <h2>NOME</h2>
        director = None
        dir_m = re.search(
            r"<h2>\s*<small>\s*REALIZA[ÇC][ÃA]O\s*</small>\s*</h2>\s*<h2>(.*?)</h2>",
            html, re.DOTALL | re.IGNORECASE
        )
        if dir_m:
            director = unescape(strip_tags(dir_m.group(1))).strip() or None

        # Poster: primeira <img> em modo retrato (width < height) no domínio cargo.site
        poster = None
        for img_m in re.finditer(r"<img\s([^>]+)>", html):
            attrs = img_m.group(1)
            w_m   = re.search(r'width="(\d+)"',    attrs)
            h_m   = re.search(r'height="(\d+)"',   attrs)
            src_m = re.search(r'data-src="(https://freight\.cargo\.site[^"]+)"', attrs)
            if w_m and h_m and src_m:
                if int(w_m.group(1)) < int(h_m.group(1)):  # retrato
                    poster = src_m.group(1)
                    break

        return {
            "title":    title,
            "director": director,
            "year":     year,
            "duration": duration,
            "genres":   genres,
            "poster":   poster,
        }
    except Exception as e:
        print(f"    Erro ao processar {url}: {e}")
        return {}


def scrape():
    print("[Fernando Lopes] A carregar programação...")
    html         = fetch_html(PROG_URL)
    raw_sessions = parse_schedule(html)

    if not raw_sessions:
        raise RuntimeError("Nenhuma sessão encontrada em " + PROG_URL)

    print(f"[Fernando Lopes] {len(raw_sessions)} sessões brutas encontradas.")

    # Detecta slugs de série: mesmo slug, mais de um título diferente
    slug_titles = {}
    for s in raw_sessions:
        slug_titles.setdefault(s["slug"], set()).add(s["title"])
    series_slugs = {slug for slug, titles in slug_titles.items() if len(titles) > 1}
    if series_slugs:
        print(f"[Fernando Lopes] Séries detectadas: {series_slugs}")

    # Agrupa sessões por (slug) ou (slug + título) para séries
    films_dict = {}
    for s in raw_sessions:
        slug  = s["slug"]
        title = s["title"]
        key   = (slug, title) if slug in series_slugs else (slug, "")
        if key not in films_dict:
            films_dict[key] = {"slug": slug, "title": title, "sessions": []}
        sess_entry = {"date": s["date"], "time": s["time"], "cinema": CINEMA_ID}
        if s.get("labels"):
            sess_entry["labels"] = s["labels"]
        films_dict[key]["sessions"].append(sess_entry)

    # Obtém metadados e monta lista final
    movies     = []
    meta_cache = {}  # slug → metadata

    for key, film in films_dict.items():
        slug  = film["slug"]
        title = film["title"]
        print(f"  [Fernando Lopes] {title}...", end=" ", flush=True)

        is_series = slug in series_slugs
        # Busca sempre a página do filme para obter o título canónico.
        # Para séries reais (e.g. Werner Herzog), a página não devolve título útil
        # → o anchor text fica como fallback. Para VALOR-SENTIMENTAL etc., a página
        # tem o título correto e sobrepõe-se ao rótulo abreviado do schedule.
        if slug not in meta_cache:
            meta_cache[slug] = scrape_film_page(slug)
            time.sleep(0.3)
        meta = meta_cache[slug]

        print(f"{len(film['sessions'])} sessão(ões)")

        raw_title = meta.get("title") or title
        # Rejeita títulos com CSS (e.g. quando a página retorna CSS no lugar de HTML)
        if "{" in raw_title or "}" in raw_title or len(raw_title) > 200:
            raw_title = title
        # Para séries: só usa o título da página se a página também tem realizador ou ano
        # (= é uma página de filme real). Páginas de ciclo/retrospetiva (e.g. Werner Herzog)
        # não têm esses campos → usa o texto do anchor como título do filme.
        if is_series and meta.get("title") and not (meta.get("year") or meta.get("director")):
            raw_title = title
        # Remove etiquetas de série/retrospetiva que aparecem no <h1> da página
        final_title = re.sub(r"\s*[-–]\s*mostra\s+essencial.*$",         "", raw_title, flags=re.IGNORECASE).strip()
        final_title = re.sub(r"\s*[-–]\s*última\s+sessão.*$",             "", final_title, flags=re.IGNORECASE).strip()
        final_title = re.sub(r"\s*[-–]\s*with\s+english\s+subtitles.*$", "", final_title, flags=re.IGNORECASE).strip()
        final_title = re.sub(r"\s*[-–]\s*\w+\s+essencial.*$",            "", final_title, flags=re.IGNORECASE).strip()
        final_title = final_title or title

        # ID único
        import unicodedata
        safe = re.sub(r"[^a-z0-9]", "_",
                      unicodedata.normalize("NFD", title.lower()))
        movie_id = f"fernando_{re.sub(r'_+', '_', safe).strip('_')}"

        # For series films, use the series page title as the festival name
        festival = None
        if is_series:
            series_title = meta_cache.get(slug, {}).get("title")
            if series_title and "{" not in series_title:
                festival = series_title
            else:
                festival = " ".join(w.title() for w in slug.split("-"))

        movies.append({
            "id":       movie_id,
            "title":    final_title,
            "director": meta.get("director"),
            "year":     meta.get("year"),
            "duration": meta.get("duration"),
            "poster":   meta.get("poster"),
            "genres":   meta.get("genres", []),
            "festival": festival,
            "link":     f"{BASE_URL}/{slug}",
            "sessions": sorted(film["sessions"], key=lambda s: (s["date"], s["time"])),
        })

    # Merge filmes duplicados: mesmo realizador + mesmo poster (e.g. versão PT vs versão EN)
    merged = {}
    for m in movies:
        merge_key = (m.get("director"), m.get("poster")) if m.get("director") and m.get("poster") else None
        if merge_key and merge_key in merged:
            # Mantém o título mais curto (normalmente o PT), junta as sessões
            existing = merged[merge_key]
            if len(m["title"]) < len(existing["title"]):
                existing["title"] = m["title"]
            existing["sessions"] = sorted(
                existing["sessions"] + m["sessions"],
                key=lambda s: (s["date"], s["time"])
            )
        else:
            merged[merge_key or id(m)] = m

    movies = list(merged.values())
    print(f"[Fernando Lopes] {len(movies)} filmes com sessões.")
    return movies


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(scrape(), ensure_ascii=False, indent=2))
