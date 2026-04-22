"""
Scraper: Cinema São Jorge
Fonte: WordPress REST API — https://cinemasaojorge.pt/wp-json/wp/v2/evento
"""

import urllib.request
import json
import re
from html import unescape
from datetime import datetime, date

CINEMA_ID = "sao_jorge"
BASE_URL  = "https://cinemasaojorge.pt"

PT_MONTHS = {
    "janeiro": "01", "fevereiro": "02", "março": "03",   "abril": "04",
    "maio":    "05", "junho":    "06", "julho":  "07",   "agosto": "08",
    "setembro":"09", "outubro":  "10", "novembro":"11",  "dezembro":"12",
}

# Só queremos eventos de cinema (filmes + sessões de festival + sessões especiais)
INCLUDE_CLASSES = {"filme", "sessao-de-festival", "afim-de-filmes"}

# Títulos de eventos que não são sessões de cinema (e.g. cinema para bebés)
EXCLUDE_TITLE_PATTERNS = re.compile(
    r'cinema\s+de\s+colo',
    re.IGNORECASE
)


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cinelisboa/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cinelisboa/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="ignore")


def is_film(event):
    classes = " ".join(event.get("class_list", []))
    return any(f"categoria-de-evento-{c}" in classes for c in INCLUDE_CLASSES)


GENRE_MAP = {
    "drama": "Drama", "comedia": "Comédia", "thriller": "Thriller",
    "terror": "Terror", "documentario": "Documentário", "animacao": "Animação",
    "romance": "Romance", "accao": "Acção", "ficcao-cientifica": "Ficção Científica",
}

# Palavras que indicam o fim do nome do realizador
DIRECTOR_STOP = r'(?=\s+(?:Com|Ano|País|Duração|Realiz|M\/\d|Sala|Ficha|Morada|\d{4}\b))'


def parse_metadata(html):
    """
    Extrai director e duração do HTML da página do evento.
    Padrões encontrados:
        127'              → duração
        Realização João Canijo   → realizador (para antes de "Com", "Ano", etc.)
    """
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>',  '', text,  flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = unescape(re.sub(r'\s+', ' ', text))

    # Duração
    duration = None
    m = re.search(r'\b(\d{2,3})[\'′\u2019]', text)
    if m:
        duration = int(m.group(1))

    # Realizador — para antes das palavras-chave
    director = None
    pattern = (
        r'(?:Realiza(?:ção|dor)|Dire(?:ção|tor))\s+'
        r'((?:[A-ZÀ-Ú][a-zà-ú]+|da|de|do|dos|das)'
        r'(?:\s+(?:[A-ZÀ-Ú][a-zà-ú]+|da|de|do|dos|das))*)'
        + DIRECTOR_STOP
    )
    m = re.search(pattern, text)
    if m:
        raw = m.group(1).strip()
        # Remove palavras-chave que ficaram no fim por falha do lookahead
        for stop in ["Com", "Ano", "País", "Duração", "Ficha", "Sala", "Realizaç"]:
            raw = re.sub(rf"\s+{stop}\b.*$", "", raw)
        director = raw.strip() or None

    # Festival: <span class="tag ...">Nome do Festival</span>
    festival = None
    tag_m = re.search(r'<span[^>]+class="[^"]*\btag\b[^"]*"[^>]*>([^<]{4,80})</span>', html)
    if tag_m:
        candidate = unescape(tag_m.group(1)).strip()
        if not re.match(r'^M/\d+$', candidate):
            festival = candidate

    # Convidado: "com a presença de X", "conversa com X", "debate com X", "Q&A com X"
    guest = None
    guest_patterns = [
        r'com\s+a\s+presen[çc]a\s+d[eo]\s+([\w\s\.\-]+?)(?:[,\.\n]|$)',
        r'(conversa|debate|q&a)\s+com\s+([\w\s\.\-]+?)(?:[,\.\n]|$)',
        r'presen[çc]a\s+d[oa]\s+realizador[a]?(?:\s+e\s+[\w\s]+)?',
        r'seguida\s+de\s+(debate|conversa)',
    ]
    for pat in guest_patterns:
        gm = re.search(pat, text, re.IGNORECASE)
        if gm:
            raw = gm.group(0).strip()
            guest = raw[0].upper() + raw[1:]
            break

    return {"director": director, "duration": duration, "festival": festival, "guest": guest}


def parse_sessions(html):
    """
    Extrai sessões do HTML da página do evento.
    Estrutura encontrada:
        <time datetime="2026-03-30">Segunda-feira, 30 de março</time>
        <time datetime="20:00">20:00</time>
    """
    # Encontra pares: data ISO + hora dentro do mesmo bloco
    pattern = r'<time datetime="(\d{4}-\d{2}-\d{2})"[^>]*>.*?<time datetime="(\d{2}:\d{2})"'
    sessions = []

    for date_str, time_str in re.findall(pattern, html, re.DOTALL):
        sessions.append({
            "date":   date_str,
            "time":   time_str,
            "cinema": CINEMA_ID,
        })

    # Remove duplicados mantendo ordem
    seen = set()
    unique = []
    for s in sessions:
        key = (s["date"], s["time"])
        if key not in seen:
            seen.add(key)
            unique.append(s)

    return sorted(unique, key=lambda s: (s["date"], s["time"]))


def scrape():
    print("[São Jorge] A carregar eventos...")
    # Só eventos dos últimos 30 dias ou futuros, ordenados por modificação recente
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=30)).isoformat() + "T00:00:00"
    url = f"{BASE_URL}/wp-json/wp/v2/evento?per_page=50&_embed=1&after={cutoff}&orderby=modified&order=desc"
    events = fetch_json(url)

    results = []

    for event in events:
        if not is_film(event):
            continue

        link      = event.get("link", "")
        title_raw = event["title"]["rendered"]

        if EXCLUDE_TITLE_PATTERNS.search(unescape(title_raw)):
            continue

        # Detect and clean abertura/encerramento from title
        special_label = None
        title = title_raw
        m_sp = re.search(r'\s*\|\s*(sess[ãa]o\s+[\w\s]+?)\s*$', title_raw, re.IGNORECASE)
        if m_sp:
            # "sessão de abertura" → "Sessão de Abertura" (preposições em minúscula)
            _low  = {"de", "do", "da", "dos", "das", "e", "em"}
            words = m_sp.group(1).lower().split()
            special_label = " ".join(
                w if (i > 0 and w in _low) else w.capitalize()
                for i, w in enumerate(words)
            )
            title = title_raw[:m_sp.start()].strip()

        print(f"  → {unescape(title)}")

        try:
            html = fetch_html(link)
        except Exception as e:
            print(f"     Erro ao carregar página: {e}")
            continue

        sessions = parse_sessions(html)
        if not sessions:
            print(f"     Sem sessões encontradas, a saltar.")
            continue

        meta   = parse_metadata(html)

        # Add special labels to all sessions of this event
        extra_labels = []
        if special_label:
            extra_labels.append(special_label)
        if meta.get("guest"):
            extra_labels.append(meta["guest"])
        if extra_labels:
            for s in sessions:
                s["labels"] = extra_labels[:]

        # Géneros do class_list da API: "genre-drama" → "Drama"
        genres = []
        for cls in event.get("class_list", []):
            if cls.startswith("genre-"):
                g = cls[6:]
                label = GENRE_MAP.get(g, g.replace("-", " ").title())
                if label not in genres:
                    genres.append(label)

        # Poster
        poster = None
        media_list = event.get("_embedded", {}).get("wp:featuredmedia", [])
        if media_list:
            poster = media_list[0].get("source_url")

        print(f"     dir={meta['director']}  dur={meta['duration']}min  genres={genres}")

        results.append({
            "id":       f"sao_jorge_{event['id']}",
            "title":    unescape(title),
            "director": meta["director"],
            "duration": meta["duration"],
            "festival": meta.get("festival"),
            "poster":   poster,
            "genres":   genres,
            "link":     link,
            "sessions": sessions,
        })

    print(f"[São Jorge] {len(results)} filmes encontrados.")
    return results


if __name__ == "__main__":
    data = scrape()
    print(json.dumps(data, ensure_ascii=False, indent=2))
