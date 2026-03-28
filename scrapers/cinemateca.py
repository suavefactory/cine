"""
Scraper: Cinemateca Portuguesa
Fonte: https://cinemateca.pt/Programacao.aspx — HTML estático, tudo numa página
"""

import urllib.request
import re
from html import unescape

CINEMA_ID = "cinemateca"
BASE_URL  = "https://cinemateca.pt"
PROG_URL  = f"{BASE_URL}/Programacao.aspx"


def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cinelisboa/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="ignore")


def parse(html):
    """
    Estrutura do HTML:

      <div class="sectionDay">25</div>
      <div class="sectionWeekDay">qua</div>  (dentro de sectionMonth com "mar2026")

      <a href="?id=19654"><div class="lista">
        <div class="infoDate mT5mB10">25/03/2026, 15h30 | Sala M. Félix Ribeiro</div>
        <div class="infoTitle mBottomNull">THE SHINING</div>
        <div class="infoBiblio"><span class="colorPink">de </span>Stanley Kubrick</div>
        <div class="infoBiblio">Estados Unidos, 1980 - 142 min </div>
      </div></a>
    """
    movies = {}  # title_key → movie dict

    # Parte o HTML em blocos por filme — links do tipo ?id=XXXX ou ?id=XXXX&date=...
    blocks = re.split(r'<a href="\?id=(\d+)[^"]*">', html)

    for i in range(1, len(blocks), 2):
        film_id = blocks[i]
        block   = blocks[i + 1] if i + 1 < len(blocks) else ""

        # ── Data / hora ──────────────────────────────────────────
        m = re.search(r'(\d{2}/\d{2}/\d{4}),\s*(\d{2})h(\d{2})', block)
        if not m:
            continue
        day, month, year = m.group(1).split("/")
        date_str = f"{year}-{month}-{day}"
        time_str = f"{m.group(2)}:{m.group(3)}"

        # ── Título ───────────────────────────────────────────────
        titles = re.findall(r'class="infoTitle[^"]*">([^<]+)<', block)
        if not titles:
            continue
        # Primeiro título é o principal; segundo (em itálico) é o original
        title = unescape(titles[0].strip())

        # ── Realizador ───────────────────────────────────────────
        director = None
        m2 = re.search(r'colorPink">de\s*</span>([^<]+)', block)
        if m2:
            director = unescape(m2.group(1).strip())

        # ── País, ano, duração ───────────────────────────────────
        film_year = duration = None
        m3 = re.search(r'(\d{4})\s*-\s*(\d+)\s*min', block)
        if m3:
            film_year = int(m3.group(1))
            duration  = int(m3.group(2))

        # ── Agrupa sessões por filme (mesmo id) ──────────────────
        key = film_id
        if key not in movies:
            movies[key] = {
                "id":       f"cinemateca_{film_id}",
                "title":    title,
                "director": director,
                "year":     film_year,
                "duration": duration,
                "poster":   None,
                "genres":   [],
                "link":     f"{BASE_URL}/programacao.aspx?id={film_id}",
                "sessions": [],
            }

        movies[key]["sessions"].append({
            "date":   date_str,
            "time":   time_str,
            "cinema": CINEMA_ID,
        })

    return list(movies.values())


def scrape():
    from datetime import date, timedelta

    print("[Cinemateca] A carregar programação (14 dias)...")

    all_movies = {}  # id → movie

    for i in range(14):
        day = (date.today() + timedelta(days=i)).isoformat()
        url = f"{PROG_URL}?date={day}"
        try:
            html   = fetch_html(url)
            movies = parse(html)
            for m in movies:
                key = m["id"]
                if key not in all_movies:
                    all_movies[key] = m
                else:
                    all_movies[key]["sessions"].extend(m["sessions"])
        except Exception as e:
            print(f"  Erro em {day}: {e}")

    result = list(all_movies.values())
    for m in result:
        # Remove sessões duplicadas e ordena
        seen = set()
        unique = []
        for s in m["sessions"]:
            k = (s["date"], s["time"])
            if k not in seen:
                seen.add(k)
                unique.append(s)
        m["sessions"] = sorted(unique, key=lambda s: (s["date"], s["time"]))
        print(f"  → {m['title']}  ({m['director']}, {m['year']}, {m['duration']}min) — {len(m['sessions'])} sessão(ões)")

    print(f"[Cinemateca] {len(result)} filmes encontrados.")
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), ensure_ascii=False, indent=2))
