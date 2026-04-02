"""
Scraper: Cinema Ideal (Lisboa)
Fonte: WordPress REST API — https://www.midas-filmes.pt/wp-json/wp/v2/filmes
Sessões expostas via campo ACF sala_de_cinema[].horario_sessoes (texto livre)
"""

import urllib.request
import json
import re
from html import unescape
from datetime import date, timedelta

CINEMA_ID = "ideal"
BASE_URL  = "https://www.cinemaidealemcasa.pt"
API_URL   = "https://www.midas-filmes.pt/wp-json/wp/v2/filmes"
MEDIA_URL = "https://www.midas-filmes.pt/wp-json/wp/v2/media"

# Mapeamento dias → weekday Python (seg=0 … dom=6)
PT_DAY_MAP = {
    "2ª": 0, "seg": 0,
    "3ª": 1, "ter": 1,
    "4ª": 2, "qua": 2,
    "5ª": 3, "qui": 3,
    "6ª": 4, "sex": 4,
    "sáb": 5, "sab": 5,
    "dom": 6,
}
# Padrão de correspondência de dias (ordenado do mais comprido para o mais curto)
_DAY_RE = re.compile(
    r'\b(s[áa]b|dom|seg|ter|qua|qui|sex|[2-6]ª)\b',
    re.IGNORECASE,
)
# Normaliza hora: "17.30" → "17:30", "16h45" → "16:45"
def _norm_time(t):
    t = re.sub(r'[Hh]', ':', t)
    t = re.sub(r'\.', ':', t)
    return t.strip()


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cinelisboa/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8", errors="ignore"))


_media_cache = {}
def get_poster(media_id):
    if not media_id:
        return None
    if media_id in _media_cache:
        return _media_cache[media_id]
    try:
        data  = fetch_json(f"{MEDIA_URL}/{media_id}")
        sizes = data.get("media_details", {}).get("sizes", {})
        url   = (sizes.get("medium_large") or sizes.get("medium") or {}).get("source_url") \
                or data.get("source_url", "")
        _media_cache[media_id] = url
        return url
    except Exception:
        return None


def parse_ficha_tecnica(text):
    """Extrai ano e duração de filmes_ficha_tecnica (ex: 'PAÍS - 2024 - 113\' - cor')."""
    if not text:
        return None, None
    text = unescape(re.sub(r"<[^>]+>", " ", text))
    m = re.search(r"(\d{4})\s*[-–]\s*(\d+)\s*[\'′\u2019\u2032]", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def parse_sessions(horario_text):
    """
    Converte horario_sessoes (texto livre) numa lista de (date_str, time_str).

    Formatos suportados:
      "sáb dom 15:45"               → rec. por dia da semana
      "2ª 14:30"                    → rec. por dia da semana (ord. pt)
      "6ª, 2ª 17.30\\nsáb, 4ª 15:00" → várias linhas, cada uma com dias+hora
      "5ª sáb 2ª 4ª 19:00"         → múltiplos dias + hora na mesma linha
      "SÁB, 13, 14:00"             → data específica (dia-do-mês)
    """
    if not horario_text:
        return []

    today = date.today()
    text  = unescape(re.sub(r"<[^>]+>", " ", horario_text))
    sessions = []

    # ── Formato específico: "DIA, DD, HH:MM" ────────────────────────────
    specific = re.findall(
        r'\b(?:seg|ter|qua|qui|sex|s[áa]b|dom|[2-6]ª)\s*,\s*(\d{1,2})\s*,\s*(\d{1,2}[h:\.]\d{2})',
        text, re.IGNORECASE,
    )
    if specific:
        for day_num_str, time_raw in specific:
            day_num  = int(day_num_str)
            time_str = _norm_time(time_raw)
            for delta in range(60):
                d = today + timedelta(days=delta)
                if d.day == day_num:
                    if d >= today:
                        sessions.append((d.isoformat(), time_str))
                    break
        return sessions

    # ── Formato recorrente: "dia(s) HH:MM [\\n dia(s) HH:MM]" ───────────
    for line in re.split(r'[\r\n]+', text):
        line = line.strip()
        if not line:
            continue

        # Extrai horas da linha
        times = [_norm_time(t) for t in re.findall(r'\d{1,2}[h:\.]\d{2}', line)]
        if not times:
            continue

        # Extrai dias da linha
        days_found = _DAY_RE.findall(line)
        active = {PT_DAY_MAP[d.lower()] for d in days_found if d.lower() in PT_DAY_MAP}
        if not active:
            continue

        for delta in range(14):
            d = today + timedelta(days=delta)
            if d.weekday() in active:
                for t in times:
                    sessions.append((d.isoformat(), t))

    # Remove duplicados mantendo ordem
    seen, unique = set(), []
    for s in sessions:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return sorted(unique)


def scrape():
    print("[Cinema Ideal] A carregar programação...")
    movies  = []
    checked = 0

    # Ordena por data de modificação DESC → filmes em cartaz são os mais recentes
    url = f"{API_URL}?per_page=100&orderby=modified&order=desc"
    try:
        data = fetch_json(url)
    except Exception as e:
        print(f"[Cinema Ideal] Erro: {e}")
        return []

    for f in data:
        checked += 1
        acf   = f.get("acf") or {}
        salas = acf.get("sala_de_cinema") or []
        sala  = next(
            (s for s in salas if "ideal" in (s.get("nome_sala_cinema") or "").lower()),
            None,
        )
        if not sala:
            continue

        horario      = sala.get("horario_sessoes", "")
        sessions_raw = parse_sessions(horario)
        if not sessions_raw:
            continue

        title     = unescape(f.get("title", {}).get("rendered", "")).strip()
        director  = (acf.get("filmes_realizador") or "").strip() or None
        year, dur = parse_ficha_tecnica(acf.get("filmes_ficha_tecnica") or "")
        poster    = get_poster(acf.get("filmes_capa_do_filme"))
        slug      = f.get("slug", "")
        link      = sala.get("link_para_site_ou_bilheteira") or f"https://www.midas-filmes.pt/filmes/{slug}/"

        sessions = [{"date": d, "time": t, "cinema": CINEMA_ID} for d, t in sessions_raw]

        print(f"  → {title} ({director}, {year}, {dur}min) — {len(sessions)} sessão(ões)")
        movies.append({
            "id":       f"ideal_{f['id']}",
            "title":    title,
            "director": director,
            "year":     year,
            "duration": dur,
            "poster":   poster,
            "genres":   [],
            "link":     link,
            "sessions": sessions,
        })

    print(f"[Cinema Ideal] {len(movies)} filmes encontrados (de {checked} verificados).")
    return movies


if __name__ == "__main__":
    print(json.dumps(scrape(), ensure_ascii=False, indent=2))
