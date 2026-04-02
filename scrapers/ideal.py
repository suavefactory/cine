"""
Scraper: Cinema Ideal (Lisboa)
Fonte: https://www.cinemaidealemcasa.pt/no-cinema/ — HTML estático
Horários como texto livre (ex: "quinta, sábado 19h00 | sexta e terça 14h30")
"""

import urllib.request
import re
from html import unescape
from datetime import date, timedelta

CINEMA_ID = "ideal"
BASE_URL  = "https://www.cinemaidealemcasa.pt"
PROG_URL  = f"{BASE_URL}/no-cinema/"

# Dia → weekday Python (seg=0 … dom=6)
_DAY_MAP = {
    "segunda": 0, "segunda-feira": 0,
    "terça":   1, "terca":         1, "terça-feira": 1,
    "quarta":  2, "quarta-feira":  2,
    "quinta":  3, "quinta-feira":  3,
    "sexta":   4, "sexta-feira":   4,
    "sábado":  5, "sabado":        5,
    "domingo": 6,
}
# Regex que captura qualquer nome de dia (ordem: mais longo primeiro para evitar parciais)
_DAY_RE = re.compile(
    r'\b(segunda-feira|terça-feira|quarta-feira|quinta-feira|sexta-feira'
    r'|segunda|terça|terca|quarta|quinta|sexta|s[áa]bado|domingo)\b',
    re.IGNORECASE,
)


def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; cinelisboa/1.0)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="ignore")


def _norm_time(t):
    """'16h45' → '16:45',  '14.30' → '14:30'"""
    return re.sub(r'[Hh\.]', ':', t.strip())


def parse_schedule(text):
    """
    Converte texto livre de horário em lista de (date_str, time_str) para os próximos 14 dias.

    Exemplos reais:
      "domingo 14:30"
      "todos os dias 16h45 | 21h15 | sexta 12h00"
      "quinta e quarta 14h30 | sexta e terça 19h00"
      "quinta, sábado, domingo, segunda e quarta: 19h00 | sexta e terça: 14h30"
      "segunda 14h30"
      "sexta: 16h45"
    """
    today  = date.today()
    # Remove notas de rodapé: "* excepto sexta" e similares
    text   = re.sub(r'\*[^|]*', ' ', text)
    text   = unescape(text).strip()

    sessions  = []
    prev_days = None  # herda dias do segmento anterior quando não especificados

    for seg in text.split('|'):
        seg = seg.strip()
        if not seg:
            continue

        # ── Horas ──────────────────────────────────────────────────────────
        times = [_norm_time(t) for t in re.findall(r'\d{1,2}[h:\.]\d{2}', seg)]
        if not times:
            continue

        # ── Dias ───────────────────────────────────────────────────────────
        if re.search(r'todos os dias', seg, re.IGNORECASE):
            active = set(range(7))
        else:
            active = set()
            for m in _DAY_RE.finditer(seg):
                key = m.group(1).lower().replace("á", "a").replace("ç", "c")
                # normaliza para o formato no _DAY_MAP
                for k, v in _DAY_MAP.items():
                    if k.replace("á","a").replace("ç","c") == key:
                        active.add(v)
                        break

        if not active:
            active = prev_days or set()
        else:
            prev_days = active

        # ── Gera sessões para os próximos 14 dias ──────────────────────────
        for delta in range(14):
            d = today + timedelta(days=delta)
            if d.weekday() in active:
                for t in times:
                    sessions.append((d.isoformat(), t))

    # Remove duplicados e ordena
    seen, unique = set(), []
    for s in sessions:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return sorted(unique)


def parse(html):
    """Extrai filmes em cartaz do HTML da página /no-cinema/."""
    movies = []

    # Cada filme está num bloco delimitado por data-movie-date="DD/MM/YYYY"
    raw_blocks = re.split(r'data-movie-date="([^"]+)"[^>]*>', html)

    for idx in range(1, len(raw_blocks), 2):
        block = raw_blocks[idx + 1] if idx + 1 < len(raw_blocks) else ""

        # ── Título ─────────────────────────────────────────────────────────
        m_title = re.search(
            r'nome_filme_em_cartaz[^>]*>.*?<p>(.*?)</p>', block, re.DOTALL
        )
        if not m_title:
            continue
        title = unescape(re.sub(r'<[^>]+>', '', m_title.group(1))).strip()
        if not title:
            continue

        # ── Realizador ─────────────────────────────────────────────────────
        m_dir = re.search(
            r'nome_realizador_em_cartaz[^>]*>.*?<p>(.*?)</p>', block, re.DOTALL
        )
        director = unescape(re.sub(r'<[^>]+>', '', m_dir.group(1))).strip() if m_dir else None

        # ── Horário (primeira div.info_link) ───────────────────────────────
        info_divs = re.findall(
            r'class="avia_textblock info_link[^"]*"[^>]*>.*?<p>(.*?)</p>', block, re.DOTALL
        )
        sched_text = ""
        for div in info_divs:
            t = unescape(re.sub(r'<[^>]+>', ' ', div)).strip()
            if re.search(r'\d{1,2}[h:]\d{2}', t):
                sched_text = t
                break

        if not sched_text:
            continue  # sem horário definido (ex: "próximas estreias")

        sessions_raw = parse_schedule(sched_text)
        if not sessions_raw:
            continue

        # ── Poster ─────────────────────────────────────────────────────────
        m_poster = re.search(r'avia-img-lazy-loading[^>]*src="([^"]+)"', block)
        poster   = m_poster.group(1) if m_poster else None

        # ── Link bilheteira ────────────────────────────────────────────────
        m_link = re.search(r'(https://bilheteira\.cinemaidealemcasa\.pt/[^"\']+)', block)
        link   = m_link.group(1) if m_link else PROG_URL

        sessions = [{"date": d, "time": t, "cinema": CINEMA_ID} for d, t in sessions_raw]

        film_id = re.sub(r'[^a-z0-9]', '_', title.lower())[:40]
        movies.append({
            "id":       f"ideal_{film_id}",
            "title":    title,
            "director": director,
            "year":     None,
            "duration": None,
            "poster":   poster,
            "genres":   [],
            "link":     link,
            "sessions": sessions,
        })

    return movies


def scrape():
    print("[Cinema Ideal] A carregar programação...")
    try:
        html   = fetch_html(PROG_URL)
        movies = parse(html)
    except Exception as e:
        print(f"[Cinema Ideal] Erro: {e}")
        return []

    for m in movies:
        print(f"  → {m['title']} ({m['director']}) — {len(m['sessions'])} sessão(ões)")

    print(f"[Cinema Ideal] {len(movies)} filmes encontrados.")
    return movies


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), ensure_ascii=False, indent=2))
