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


def to_title_case(s):
    """Converte títulos em MAIÚSCULAS para Title Case (ex: 'THE SHINING' → 'The Shining')."""
    if not s or not s.isupper():
        return s
    result = s.lower().title()
    # Corrige contrações: Don'T / Don'T → Don't (apostrofe reta ou curva)
    result = re.sub(r"['\u2019]([A-Z])\b", lambda m: "\u2019" + m.group(1).lower(), result)
    return result


def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cinelisboa/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="ignore")


def _parse_multi_description(text):
    """
    Extrai filmes individuais de um bloco de texto multi-filme.
    Suporta dois formatos:

    Formato A (secções separadas por linha em branco):
        TÍTULO
        de Realizador
        País, Ano – Duração min

    Formato B (sessão de grupo — múltiplos títulos ALL-CAPS, 1 realizador, anos compostos):
        TÍTULO 1
        "Subtítulo 1"
        TÍTULO 2
        "Subtítulo 2"
        de Realizador
        País, 1966, 1979, 1979 – 4, 44, 29 min

    Retorna lista de {title, director, year, duration}.
    """
    films = []
    # Normaliza quebras de linha e espaços não separáveis
    text = re.sub(r'\r\n', '\n', text).replace('\xa0', ' ').strip()
    sections = re.split(r'\n\s*\n', text)

    for section in sections:
        lines = [l.strip() for l in section.split('\n') if l.strip()]
        if not lines:
            continue

        pending_titles = []  # candidatos a título (para suporte a Formato B)
        director = None
        year = duration = None

        for line in lines:
            # Para em "Duração total", "legenda", "M/12", info de legenda
            if re.match(r'(Dura[çc][aã]o total|legenda|M/\d)', line, re.IGNORECASE):
                break

            # Subtítulo entre aspas — ignorar
            if re.match(r'^[\"\u201c\u201d]', line):
                continue

            # Elenco: "com ..." — ignorar
            if re.match(r'^com\s+', line):
                continue

            # Realizador: "de Nome"
            dm = re.match(r'^de\s+(.+)$', line)
            if dm and pending_titles:
                director = dm.group(1).strip()
                continue

            # Ano + duração composto: "..., Y1, Y2, Y3 – D1, D2, D3 min" (Formato B)
            cym = re.search(
                r'(\d{4}(?:,\s*\d{4})+)\s*[-\u2013]\s*(\d+(?:,\s*\d+)+)\s*min',
                line, re.IGNORECASE
            )
            if cym and pending_titles and director:
                _years = [int(y.strip()) for y in cym.group(1).split(',')]
                _durs  = [int(d.strip()) for d in cym.group(2).split(',')]
                for i, t in enumerate(pending_titles):
                    y_ = _years[i] if i < len(_years) else _years[-1]
                    d_ = _durs[i]  if i < len(_durs)  else _durs[-1]
                    films.append({"title": t, "director": director, "year": y_, "duration": d_})
                pending_titles = []
                director = year = duration = None
                continue

            # Ano + duração simples: "País, Ano[/Ano2] – N min"
            ym = re.search(r'(\d{4})(?:[/\-]\d{2,4})?\s*[-\u2013]\s*(\d+)\s*min', line, re.IGNORECASE)
            if ym and pending_titles:
                year = int(ym.group(1))
                duration = int(ym.group(2))
                continue

            # Título: primeira linha aceita qualquer conteúdo; linhas seguintes só ALL-CAPS
            if len(line) > 2 and not re.match(r'^\d', line):
                t = to_title_case(unescape(line))
                if not pending_titles or line.isupper():
                    pending_titles.append(t)

        # Fim da secção: usa o primeiro título (Formato A normal)
        if pending_titles and director and year:
            films.append({"title": pending_titles[0], "director": director, "year": year, "duration": duration})

    return films


def fetch_film_details(film_id, date_str, title_hint=None):
    """
    Busca a descrição de um filme na página do dia e extrai metadados.
    title_hint é usado para identificar o bloco infoText correto (evita
    cruzar dados entre filmes diferentes no mesmo dia).
    """
    url = f"{BASE_URL}/Programacao.aspx?id={film_id}&date={date_str}"
    try:
        html = fetch_html(url)
    except Exception:
        return []

    # Fragmentos de título para matching — usa primeiros 15 chars de cada parte
    title_frags = []
    if title_hint:
        for part in re.split(r'\s*[|+]\s*', title_hint):
            part = re.sub(r'\s+', ' ', part).strip()
            if len(part) > 4:
                title_frags.append(part[:15].upper())

    info_texts = re.findall(r'<div class="infoText[^"]*">(.*?)</div>', html, re.DOTALL)
    for it in info_texts:
        text = unescape(re.sub(r'<[^>]+>', ' ', it)).strip()
        text = re.sub(r'\r\n', '\n', text)
        # Tem de ter pelo menos 1 linha "de Realizador" e " min"
        if not re.search(r'\nde\s+\S', text):
            continue
        if ' min' not in text:
            continue
        # Se há title_hint, rejeita blocos que não contenham nenhum fragmento
        if title_frags:
            text_upper = text.upper()
            if not any(frag in text_upper for frag in title_frags):
                continue
        films = _parse_multi_description(text)
        if films:
            return films

    return []


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
        title = to_title_case(unescape(titles[0].strip()))

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

        # ── Sessão especial (convidado, debate, etc.) ────────────
        labels = []
        for info_div in re.findall(r'class="infoText"[^>]*>([^<]{4,200})<', block):
            text = unescape(info_div).strip()
            # "SESSÃO com a presença de X" → "Com a presença de X"
            gm = re.match(r'SESS[ÃA]O\s+(com\s+a\s+presen[çc]a\s+de\s+.+)', text, re.IGNORECASE)
            if gm:
                labels.append(gm.group(1)[0].upper() + gm.group(1)[1:])
                continue
            # "com a presença de X" (sem prefixo SESSÃO)
            if re.match(r'com\s+a\s+presen[çc]a\s+de\b', text, re.IGNORECASE):
                labels.append(text[0].upper() + text[1:])
                continue
            # "Sessão com apresentação" / "Sessão com X"
            if re.match(r'sess[ãa]o\s+com\b', text, re.IGNORECASE):
                labels.append(text[0].upper() + text[1:])
                continue
            # "com acompanhamento..." (sessões musicais/especiais)
            if re.match(r'com\s+acompanhamento\b', text, re.IGNORECASE):
                labels.append(text[0].upper() + text[1:])
                continue
            # "Conversa com X" / "Debate com X" / "Seguida de debate"
            if re.match(r'(conversa|debate|seguida\s+de\s+(?:conversa|debate))\b', text, re.IGNORECASE):
                labels.append(text[0].upper() + text[1:])

        sess = {"date": date_str, "time": time_str, "cinema": CINEMA_ID}
        if labels:
            sess["labels"] = list(dict.fromkeys(labels))  # dedup, preserve order
        movies[key]["sessions"].append(sess)

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

    # ── Resolve sessões sem metadados ou com título composto (multi-filme) ──
    # Aplica-se a:
    #   - QUALQUER sessão sem realizador ou sem ano
    #   - Sessões com " + " no título (podem ter metadados errados por contaminação adjacente)
    to_remove = set()
    to_add    = []
    for m in result:
        title = m.get("title", "")
        # "|" é sempre separador de múltiplos filmes na Cinemateca
        # "+" é separador apenas quando os dois lados são títulos substanciais (ex: "SOFT AND HARD + JLG/JLG")
        # — não quando é parte do título (ex: "MAVRO + ASPRO")
        has_pipe  = " | " in title
        has_plus  = " + " in title
        is_multi_title = has_pipe or (
            has_plus and len(title) > 25 and
            all(len(p.strip()) > 5 for p in title.split(" + "))
        )
        has_meta = m.get("director") and m.get("year")
        if has_meta and not is_multi_title:
            continue  # metadados completos e título simples — ok
        film_id  = m["id"].replace("cinemateca_", "")
        date_str = m["sessions"][0]["date"] if m["sessions"] else None
        if not date_str:
            continue
        films = fetch_film_details(film_id, date_str, title_hint=title)
        if not films:
            # Título multi com metadados suspeitos mas sem descrição → remover para evitar dados errados
            if is_multi_title and has_meta:
                to_remove.add(m["id"])
            continue  # conferência/palestra sem filme — mantém como está
        if len(films) == 1 and not is_multi_title:
            # Filme único sem metadados: actualiza in-place
            f = films[0]
            print(f"  [resolve] {m['title']!r} → {f['title']!r} ({f['director']}, {f['year']})")
            m["title"]    = f["title"]
            m["director"] = f["director"]
            m["year"]     = f["year"]
            m["duration"] = f["duration"]
        elif len(films) == 1 and is_multi_title:
            # Só 1 filme encontrado num título multi → descarta entrada ambígua
            to_remove.add(m["id"])
        elif len(films) >= 2:
            # Multi-filme: divide em entradas separadas
            print(f"  [multi] {m['title']!r} → {len(films)} filmes")
            to_remove.add(m["id"])
            for idx, f in enumerate(films):
                to_add.append({
                    "id":       f"cinemateca_{film_id}_{idx}",
                    "title":    f["title"],
                    "director": f["director"],
                    "year":     f["year"],
                    "duration": f["duration"],
                    "poster":   None,
                    "genres":   [],
                    "link":     m["link"],
                    "sessions": m["sessions"],
                })

    result = [m for m in result if m["id"] not in to_remove] + to_add

    for m in result:
        print(f"  → {m['title']}  ({m['director']}, {m['year']}, {m['duration']}min) — {len(m['sessions'])} sessão(ões)")

    print(f"[Cinemateca] {len(result)} filmes encontrados.")
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), ensure_ascii=False, indent=2))
