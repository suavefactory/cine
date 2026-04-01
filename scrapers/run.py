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
from enricher   import enrich

SCRAPERS = [
    ("São Jorge",       scrape_sao_jorge),
    ("Cinemateca",      scrape_cinemateca),
    ("Medeia Nimas",    scrape_nimas),
    ("Fernando Lopes",  scrape_fernando),
]

def norm(text):
    """Normaliza título para comparação: minúsculas, sem acentos, sem pontuação extra."""
    t = unicodedata.normalize("NFD", (text or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9 ]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def deduplicate(movies):
    """Junta filmes com o mesmo título normalizado e ano, combinando as suas sessões."""
    merged = {}
    for m in movies:
        key = (norm(m["title"]), m.get("year"))
        if key not in merged:
            merged[key] = dict(m)
            merged[key]["sessions"] = list(m["sessions"])
        else:
            base = merged[key]
            # Adiciona sessões novas (evita duplicados)
            existing = {(s["date"], s["time"], s["cinema"]) for s in base["sessions"]}
            for s in m["sessions"]:
                if (s["date"], s["time"], s["cinema"]) not in existing:
                    base["sessions"].append(s)
                    existing.add((s["date"], s["time"], s["cinema"]))
            # Preenche campos em falta com os da entrada duplicada
            for field in ("director", "duration", "poster", "genres", "link", "festival"):
                if not base.get(field) and m.get(field):
                    base[field] = m[field]

    result = list(merged.values())
    # Ordena sessões de cada filme
    for m in result:
        m["sessions"].sort(key=lambda s: (s["date"], s["time"]))
    return result


def run():
    all_movies = []
    errors = []

    for name, scraper in SCRAPERS:
        try:
            movies = scraper()
            all_movies.extend(movies)
        except Exception as e:
            print(f"[ERRO] {name}: {e}")
            errors.append({"cinema": name, "error": str(e)})

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

    print("\n[Enricher] A buscar posters e ratings...")
    all_movies = enrich(all_movies)

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "movies":    all_movies,
        "errors":    errors,
    }

    # Escreve data/sessions.js (carregado pelo frontend como <script>)
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "sessions.js")

    js_content = f"window.CINEMA_DATA = {json.dumps(payload, ensure_ascii=False, indent=2)};"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(js_content)

    total_sessions = sum(len(m["sessions"]) for m in all_movies)
    print(f"\n✓ {len(all_movies)} filmes · {total_sessions} sessões → data/sessions.js")
    if errors:
        print(f"  {len(errors)} erro(s): {[e['cinema'] for e in errors]}")

if __name__ == "__main__":
    run()
