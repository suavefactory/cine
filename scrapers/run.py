"""
cine.lisboa — runner principal
Corre todos os scrapers e gera data/sessions.js para o frontend.

Uso:
    python3 scrapers/run.py
"""

import json
import sys
import os
import unicodedata
import re
from datetime import datetime, timezone

# Garante que o import dos scrapers funciona mesmo correndo de outra pasta
sys.path.insert(0, os.path.dirname(__file__))

from sao_jorge  import scrape as scrape_sao_jorge
from cinemateca import scrape as scrape_cinemateca
from nimas      import scrape as scrape_nimas
from fernando   import scrape as scrape_fernando
from batalha    import scrape as scrape_batalha
from trindade   import scrape as scrape_trindade
from ideal         import scrape as scrape_ideal
from campo_alegre  import scrape as scrape_campo_alegre
from enricher   import enrich, build_directors

SCRAPERS = [
    ("São Jorge",      "sao_jorge",      scrape_sao_jorge),
    ("Cinemateca",     "cinemateca",     scrape_cinemateca),
    ("Medeia Nimas",   "nimas",          scrape_nimas),
    ("Fernando Lopes", "fernando_lopes", scrape_fernando),
    ("Batalha",        "batalha",        scrape_batalha),
    ("Trindade",       "trindade",       scrape_trindade),
    ("Cinema Ideal",   "ideal",          scrape_ideal),
    ("Campo Alegre",   "campo_alegre",   scrape_campo_alegre),
]

def norm(text):
    """Normaliza título para comparação: minúsculas, sem acentos, sem pontuação extra."""
    t = unicodedata.normalize("NFD", (text or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9 ]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _levenshtein(s1, s2):
    if s1 == s2: return 0
    if len(s1) < len(s2): s1, s2 = s2, s1
    if not s2: return len(s1)
    prev = list(range(len(s2) + 1))
    for c1 in s1:
        curr = [prev[0] + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j] + (c1 != c2), curr[-1] + 1, prev[j + 1] + 1))
        prev = curr
    return prev[-1]


def fuzzy_merge(movies):
    """Junta filmes cujos títulos normalizados diferem em ≤ 1 caracter (mesmo ano).
    Captura variantes ortográficas como 'Projecto Global' ↔ 'Projeto Global'."""
    norms = [norm(m["title"]) for m in movies]
    years = [m.get("year") for m in movies]
    canonical = list(range(len(movies)))

    for i in range(len(movies)):
        if canonical[i] != i:
            continue
        for j in range(i + 1, len(movies)):
            if canonical[j] != j:
                continue
            t1, t2 = norms[i], norms[j]
            # Exige títulos com pelo menos 8 chars para evitar falsos positivos
            if len(t1) < 8 or len(t2) < 8:
                continue
            # Diferença de comprimento máxima de 3
            if abs(len(t1) - len(t2)) > 3:
                continue
            # Títulos que diferem apenas nos dígitos são programas numerados distintos
            # (ex: "SILVESTRE CURTAS 3" ≠ "SILVESTRE CURTAS 4")
            if re.sub(r"\d", "#", t1) == re.sub(r"\d", "#", t2):
                continue
            y1, y2 = years[i], years[j]
            # Aceita diferença de ±1 ano (metadados ligeiramente divergentes entre cinemas)
            if y1 is not None and y2 is not None and abs(y1 - y2) > 1:
                continue
            if _levenshtein(t1, t2) <= 1:
                canonical[j] = i
                base = movies[i]
                dup  = movies[j]
                existing = {(s["date"], s["time"], s["cinema"]) for s in base["sessions"]}
                for s in dup["sessions"]:
                    if (s["date"], s["time"], s["cinema"]) not in existing:
                        base["sessions"].append(s)
                for field in ("director", "year", "duration", "poster", "genres", "link", "festival"):
                    if not base.get(field) and dup.get(field):
                        base[field] = dup[field]
                print(f"  [dedup-fuzzy] {dup['title']!r} → {base['title']!r}")

    return [m for i, m in enumerate(movies) if canonical[i] == i]


def deduplicate(movies):
    """Junta filmes com o mesmo título normalizado, combinando sessões de todos os cinemas.
    Entradas com year=None fazem merge com qualquer entrada do mesmo título (independente do ano)."""
    merged   = {}  # key → movie dict
    by_title = {}  # norm_title → key (para resolver year=None vs year=X)

    for m in movies:
        t    = norm(m["title"])
        year = m.get("year")

        # Resolve chave: se year=None ou há entrada sem ano com o mesmo título, usa essa
        if year is None and t in by_title:
            key = by_title[t]
        elif year is not None and t in by_title and by_title[t][1] is None:
            key = by_title[t]  # merge no entry existente sem ano
        else:
            key = (t, year)
            by_title[t] = key

        if key not in merged:
            merged[key] = dict(m)
            merged[key]["sessions"] = list(m["sessions"])
        else:
            base = merged[key]
            existing = {(s["date"], s["time"], s["cinema"]) for s in base["sessions"]}
            for s in m["sessions"]:
                if (s["date"], s["time"], s["cinema"]) not in existing:
                    base["sessions"].append(s)
                    existing.add((s["date"], s["time"], s["cinema"]))
            for field in ("director", "year", "duration", "poster", "genres", "link", "festival"):
                if not base.get(field) and m.get(field):
                    base[field] = m[field]

    result = list(merged.values())
    for m in result:
        m["sessions"].sort(key=lambda s: (s["date"], s["time"]))
    return result


def load_previous(out_path):
    """Lê movies do sessions.js anterior para usar como fallback."""
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            content = f.read()
        json_str = content.removeprefix("window.CINEMA_DATA = ").removesuffix(";").strip()
        return json.loads(json_str).get("movies", [])
    except Exception:
        return []


def run():
    out_dir  = os.path.join(os.path.dirname(__file__), "..", "data")
    out_path = os.path.join(out_dir, "sessions.js")
    previous = load_previous(out_path)

    all_movies = []
    errors = []

    for name, cinema_id, scraper in SCRAPERS:
        try:
            movies = scraper()
        except Exception as e:
            print(f"[ERRO] {name}: {e}")
            errors.append({"cinema": name, "error": str(e)})
            movies = []

        if not movies:
            # Fallback: preserva sessões do ciclo anterior para este cinema
            prev = [m for m in previous
                    if any(s.get("cinema") == cinema_id for s in m.get("sessions", []))]
            if prev:
                print(f"  [FALLBACK] {name}: 0 filmes obtidos, a usar {len(prev)} filmes anteriores")
                movies = prev
            else:
                print(f"  [AVISO] {name}: 0 filmes e sem dados anteriores")

        all_movies.extend(movies)

    # Limpa asteriscos dos horários e títulos (e.g. Nimas devolve "18:30 *")
    for movie in all_movies:
        movie["title"] = movie["title"].replace("*", "").strip()
        for s in movie["sessions"]:
            s["time"] = s["time"].replace("*", "").strip()

    # Filtra sessões passadas (mantém só os próximos 60 dias)
    today = datetime.now(timezone.utc).date().isoformat()
    for movie in all_movies:
        movie["sessions"] = [
            s for s in movie["sessions"]
            if s["date"] >= today
        ]
    all_movies = [m for m in all_movies if m["sessions"]]

    # Deduplica filmes com o mesmo título+ano (e.g. Cinemateca com 2 IDs diferentes)
    all_movies = deduplicate(all_movies)
    # Segunda passagem: une variantes ortográficas (projecto/projeto, acção/ação, etc.)
    all_movies = fuzzy_merge(all_movies)

    print("\n[Enricher] A buscar posters e ratings...")
    all_movies = enrich(all_movies)

    print("\n[Directors] A buscar fotos e bios de realizadores...")
    directors = build_directors(all_movies)
    print(f"[Directors] {len(directors)} realizadores.")

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "movies":    all_movies,
        "directors": directors,
        "errors":    errors,
    }

    # Escreve data/sessions.js (carregado pelo frontend como <script>)
    os.makedirs(out_dir, exist_ok=True)

    js_content = f"window.CINEMA_DATA = {json.dumps(payload, ensure_ascii=False, indent=2)};"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(js_content)

    total_sessions = sum(len(m["sessions"]) for m in all_movies)
    print(f"\n✓ {len(all_movies)} filmes · {total_sessions} sessões → data/sessions.js")
    if errors:
        print(f"  {len(errors)} erro(s): {[e['cinema'] for e in errors]}")

if __name__ == "__main__":
    run()
