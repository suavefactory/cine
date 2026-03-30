"""
Enricher: busca poster, rating (Letterboxd 0-5) e metadados via:
  1. Letterboxd  — rating + poster portrait
  2. OMDB        — fallback para poster, director, duration, year

Cache em data/omdb_cache.json
"""

import urllib.request, urllib.parse
import json, re, os, unicodedata, time

OMDB_KEY   = "trilogy"
CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "omdb_cache.json")

HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Títulos originais → slug Letterboxd (inglês)
LBXD_SLUGS = {
    # ── Títulos italianos / franceses / espanhóis ──
    "OTTO E MEZZO":              "8-1-2",
    "EL ÁNGEL EXTERMINADOR":     "the-exterminating-angel",
    "EL ANGEL EXTERMINADOR":     "the-exterminating-angel",
    "IL GATTOPARDO":             "the-leopard",
    "MON ONCLE":                 "my-uncle-1958",
    "LE MÉPRIS":                 "contempt",
    "LE MEPRIS":                 "contempt",
    "I SOLITI IGNOTI":           "big-deal-on-madonna-street",
    "LA RAGAZZA CON LA VALIGIA": "girl-with-a-suitcase",
    "IL GIORNO DELLA CIVETTA":   "mafia-1968",
    "LA RAGAZZA DI BUBE":        "bebos-girl",
    "EL SOL DEL MEMBRILLO":      "the-quince-tree-sun",
    "LAS AVENTURAS DE JUAN QUIN QUIN": "the-adventures-of-juan-quin-quin",
    "MEDEA":                     "medea-1969",
    # ── Títulos portugueses (filmes estrangeiros) ──
    "MAL VIVER":                 "bad-living",
    "VIVER MAL":                 "bad-living",
    "SANGUE DO MEU SANGUE":      "blood-of-my-blood",
    "OLHOS NEGROS":              "dark-eyes",
    "AS MINHAS NAMORADINHAS":    "my-little-loves",
    "INTRIGA INTERNACIONAL":     "north-by-northwest",
    "O SILÊNCIO":                "the-silence-1963",
    "O SILENCIO":                "the-silence-1963",
    "UM VERÃO DE AMOR":          "summer-interlude",
    "UM VERAO DE AMOR":          "summer-interlude",
    "A FLAUTA MÁGICA":           "the-magic-flute",
    "A FLAUTA MAGICA":           "the-magic-flute",
    "ASAS":                      "wings-1966",
    "ANTES DA MEIA-NOITE":       "before-midnight",
    "SORRISOS DE UMA NOITE DE VERÃO": "smiles-of-a-summer-night",
    "SORRISOS DE UMA NOITE DE VERAO": "smiles-of-a-summer-night",
    "FANNY E ALEXANDRE":         "fanny-and-alexander",
    "A MÁSCARA":                 "persona",
    "A MASCARA":                 "persona",
    "CENAS DA VIDA CONJUGAL":    "scenes-from-a-marriage",
    "BOYHOOD: MOMENTOS DE UMA VIDA": "boyhood",
    "O SÉTIMO SELO":             "the-seventh-seal",
    "O SETIMO SELO":             "the-seventh-seal",
    "OS PÁSSAROS":               "the-birds",
    "OS PASSAROS":               "the-birds",
    "EM BUSCA DA VERDADE":       "through-a-glass-darkly",
    "A JANELA INDISCRETA":       "rear-window",
    "ASCENSÃO":                  "the-ascent",
    "ASCENSAO":                  "the-ascent",
    "DEPOIS DO ENSAIO":          "after-the-rehearsal",
    "LÁGRIMAS E SUSPIROS":       "cries-and-whispers",
    "LAGRIMAS E SUSPIROS":       "cries-and-whispers",
    "MORANGOS SILVESTRES":       "wild-strawberries",
    "UMA LIÇÃO DE AMOR":         "a-lesson-in-love",
    "UMA LICAO DE AMOR":         "a-lesson-in-love",
    "PSICO":                     "psycho",
    "A MULHER QUE VIVEU DUAS VEZES": "vertigo",
    "SIBERÍADA":                 "siberiade",
    "SIBERIADA":                 "siberiade",
    "IVAN, O TERRÍVEL – PARTE 1": "ivan-the-terrible-part-i",
    "IVAN, O TERRIVEL – PARTE 1": "ivan-the-terrible-part-i",
    "IVAN, O TERRÍVEL – PARTE 2": "ivan-the-terrible-2",
    "IVAN, O TERRIVEL – PARTE 2": "ivan-the-terrible-2",
    "LADRÃO DE CASACA":          "to-catch-a-thief",
    "LADRAO DE CASACA":          "to-catch-a-thief",
    "O HOMEM DA CÂMARA DE FILMAR": "man-with-a-movie-camera",
    "O HOMEM DA CAMARA DE FILMAR": "man-with-a-movie-camera",
    "A VERGONHA":                "shame",
    "TU E EU":                   "you-and-me-1971",
    "A FONTE DA VIRGEM":         "the-virgin-spring",
    "O COURAÇADO POTEMKINE":     "battleship-potemkin",
    "O COURACADO POTEMKINE":     "battleship-potemkin",
    "ANTES DO AMANHECER":        "before-sunrise",
    "ANTES DO ANOITECER":        "before-sunset",
    "A PRISÃO":                  "prison-1949",
    "A PRISAO":                  "prison-1949",
    "MULHERES QUE ESPERAM":      "waiting-women",
    "A INFÂNCIA DE IVAN":        "ivans-childhood",
    "A INFANCIA DE IVAN":        "ivans-childhood",
    "CIDADE PORTUÁRIA":          "hamnstad",
    "CIDADE PORTUARIA":          "hamnstad",
    "O SACRIFÍCIO":              "the-sacrifice",
    "O SACRIFICIO":              "the-sacrifice",
    "LUZ DE INVERNO":            "winter-light",
    "DA VIDA DAS MARIONETAS":    "from-the-life-of-the-marionettes",
    "SONATA DE OUTONO":          "autumn-sonata",
    "ADEUS A MATIORA":           "farewell-1983",
    "AMADEUS – DIRECTOR'S CUT":  "amadeus",
    "ACORDAR PARA A VIDA":       "waking-life",
    "CHUVA DE JULHO":            "july-rain",
    "O SOL":                     "solntse",
    "DON GIOVANNI":              "don-giovanni-1979",
    "UMA LUZ NAS TREVAS":        "music-in-darkness",
    "ARSENAL":                   "arsenal-1929",
    "O SILÊNCIO":                "the-silence",
    "O SILENCIO":                "the-silence",
    "BATALHA ATRÁS DE BATALHA":  "one-battle-after-another",
    "BATALHA ATRAS DE BATALHA":  "one-battle-after-another",
    "O RAPAZ DA ILHA DE AMRUM":  "amrum",
    "OS DOMINGOS":               "sundays",
    "MÃE E FILHO":               "mother-and-son",
    "MAE E FILHO":               "mother-and-son",
    "DON GIOVANNI":              "don-giovanni",
    "INTERPOL / PICKUP ALLEY":   "pickup-alley",
    "INTERPOL":                  "pickup-alley",
    "O ESTRANGEIRO":             "quand-vient-lautomne",
    "ROMARIA":                   "romeria",
    "AINDA FUNCIONA?":           "is-this-thing-on-2025",
    "VISITA OU MEMÓRIAS E CONFISSÕES": "visit-or-memories-and-confessions",
    "VISITA OU MEMORIAS E CONFISSOES": "visit-or-memories-and-confessions",
    "A PAIXÃO":                  "the-passion-of-anna",
    "A PAIXAO":                  "the-passion-of-anna",
    "IVAN, O TERRÍVEL – PARTE 2": "ivan-the-terrible-part-ii-the-boyars-plot",
    "IVAN, O TERRIVEL – PARTE 2": "ivan-the-terrible-part-ii-the-boyars-plot",
    # ── Títulos em inglês com conflito de ano ──
    "DOM NA TRUBNOI":            "the-house-on-trubnaya",
    "PO ZAKONU":                 "by-the-law",
    "SANGUE DO MEU SANGUE":      "blood-of-my-blood",
    "HUGO":                      "hugo",
    "HUGO - 3D":                 "hugo",
    "THE SHINING":               "the-shining",
    "LOST HIGHWAY":              "lost-highway",
    "THE PINK PANTHER":          "the-pink-panther-1963",
    # ── Werner Herzog (Cinema Fernando Lopes) ──
    "AGUIRRE, A CÓLERA DE DEUS":    "aguirre-the-wrath-of-god",
    "AGUIRRE, A COLERA DE DEUS":    "aguirre-the-wrath-of-god",
    "O ENIGMA DE KASPAR HAUSER":    "the-enigma-of-kaspar-hauser",
    "NOSFERATU, O FANTASMA DA NOITE": "nosferatu-the-vampyre",
    "LIÇÕES DA ESCURIDÃO":          "lessons-of-darkness",
    "LICOES DA ESCURIDAO":          "lessons-of-darkness",
    "ALÉM DO AZUL SELVAGEM":        "the-wild-blue-yonder",
    "ALEM DO AZUL SELVAGEM":        "the-wild-blue-yonder",
    "FITZCARRALDO":                 "fitzcarraldo",
    "STROSZEK":                     "stroszek",
    "WOYZECK":                      "woyzeck-1979",
    "KINSKI – MEU INIMIGO MAIS QUERIDO": "my-best-fiend",
    "KINSKI - MEU INIMIGO MAIS QUERIDO": "my-best-fiend",
    # ── Fernando Lopes — outros títulos ──
    "O ÚLTIMO PADRINHO":            "the-last-godfather",
    "O ULTIMO PADRINHO":            "the-last-godfather",
    "ENTRONCAMENTO":                "entroncamento",
    "MARCEL E MONSIEUR PAGNOL":     "the-screenplay-of-my-life",
    "VALOR SENTIMENTAL":            "sentimental-value-2025",
    "RIEFENSTAHL":                  "riefenstahl",
    # ── São Jorge — filmes italianos e outros ──
    "ENRICO IV":                    "henry-iv",
    "DIE FREUDLOSE GASSE":          "the-joyless-street",
    "LIBERA, AMORE MIO…":           "libera-my-love",
    "LIBERA, AMORE MIO":            "libera-my-love",
    "CAMPO DE BATALHA (CAMPO DI BATTAGLIA)": "campo-di-battaglia",
    "CAMPO DI BATTAGLIA":           "campo-di-battaglia",
    "HEY JOE":                      "hey-joe-2024",
    "FUORI":                        "fuori-2025",
    "NAPOLI – NEW YORK":            "napoli-new-york",
    "NAPOLI - NEW YORK":            "napoli-new-york",
    "MODÌ – TRE GIORNI SULLE ALI DELLA FOLLIA": "modi-2024",
    "MODI - TRE GIORNI SULLE ALI DELLA FOLLIA": "modi-2024",
    "GIULIO REGENI – TUTTO IL MALE DEL MONDO": "giulio-regeni-tutto-il-male-del-mondo",
    "GIULIO REGENI - TUTTO IL MALE DEL MONDO": "giulio-regeni-tutto-il-male-del-mondo",
    "CINCO SEGUNDOS (CINQUE SECONDI)": "cinque-secondi",
    "CINQUE SECONDI":               "cinque-secondi",
    "BREVE HISTÓRIA DE AMOR (BREVE STORIA D'AMORE)": "breve-storia-damore",
    "BREVE STORIA D'AMORE":         "breve-storia-damore",
    "AS PROVADORAS DE HITLER (LE ASSAGGIATRICI)": "the-tasters",
    "LE ASSAGGIATRICI":             "the-tasters",
}

# Títulos originais → título inglês para OMDB
OMDB_ALIASES = {
    "OTTO E MEZZO":              "8½",
    "EL ÁNGEL EXTERMINADOR":     "The Exterminating Angel",
    "EL ANGEL EXTERMINADOR":     "The Exterminating Angel",
    "IL GATTOPARDO":             "The Leopard",
    "MON ONCLE":                 "My Uncle",
    "LE MÉPRIS":                 "Contempt",
    "LE MEPRIS":                 "Contempt",
    "MAL VIVER":                 "Bad Living",
    "VIVER MAL":                 "Bad Living",
    "DOM NA TRUBNOI":            "The House on Trubnaya",
    "PO ZAKONU":                 "By the Law",
    "I SOLITI IGNOTI":           "Big Deal on Madonna Street",
    "LA RAGAZZA CON LA VALIGIA": "Girl with a Suitcase",
    "IL GIORNO DELLA CIVETTA":   "Mafia",
    "LA RAGAZZA DI BUBE":        "Bebo's Girl",
    "7 BALAS PARA SELMA":        "Seven Bullets for Selma",
    "LAS AVENTURAS DE JUAN QUÍN QUÍN": "Adventures of Juan Quin Quin",
    # ── Títulos portugueses ──
    "OLHOS NEGROS":              "Dark Eyes",
    "AS MINHAS NAMORADINHAS":    "My Little Loves",
    "INTRIGA INTERNACIONAL":     "North by Northwest",
    "O SILÊNCIO":                "The Silence",
    "O SILENCIO":                "The Silence",
    "UM VERÃO DE AMOR":          "Summer Interlude",
    "UM VERAO DE AMOR":          "Summer Interlude",
    "A FLAUTA MÁGICA":           "The Magic Flute",
    "A FLAUTA MAGICA":           "The Magic Flute",
    "ASAS":                      "Wings",
    "ANTES DA MEIA-NOITE":       "Before Midnight",
    "SORRISOS DE UMA NOITE DE VERÃO": "Smiles of a Summer Night",
    "SORRISOS DE UMA NOITE DE VERAO": "Smiles of a Summer Night",
    "FANNY E ALEXANDRE":         "Fanny and Alexander",
    "A MÁSCARA":                 "Persona",
    "A MASCARA":                 "Persona",
    "CENAS DA VIDA CONJUGAL":    "Scenes from a Marriage",
    "BOYHOOD: MOMENTOS DE UMA VIDA": "Boyhood",
    "O SÉTIMO SELO":             "The Seventh Seal",
    "O SETIMO SELO":             "The Seventh Seal",
    "OS PÁSSAROS":               "The Birds",
    "OS PASSAROS":               "The Birds",
    "EM BUSCA DA VERDADE":       "Through a Glass Darkly",
    "A JANELA INDISCRETA":       "Rear Window",
    "ASCENSÃO":                  "The Ascent",
    "ASCENSAO":                  "The Ascent",
    "DEPOIS DO ENSAIO":          "After the Rehearsal",
    "LÁGRIMAS E SUSPIROS":       "Cries and Whispers",
    "LAGRIMAS E SUSPIROS":       "Cries and Whispers",
    "MORANGOS SILVESTRES":       "Wild Strawberries",
    "UMA LIÇÃO DE AMOR":         "A Lesson in Love",
    "UMA LICAO DE AMOR":         "A Lesson in Love",
    "PSICO":                     "Psycho",
    "A MULHER QUE VIVEU DUAS VEZES": "Vertigo",
    "SIBERÍADA":                 "Siberiade",
    "SIBERIADA":                 "Siberiade",
    "IVAN, O TERRÍVEL – PARTE 1": "Ivan the Terrible Part 1",
    "IVAN, O TERRIVEL – PARTE 1": "Ivan the Terrible Part 1",
    "IVAN, O TERRÍVEL – PARTE 2": "Ivan the Terrible Part 2",
    "IVAN, O TERRIVEL – PARTE 2": "Ivan the Terrible Part 2",
    "LADRÃO DE CASACA":          "To Catch a Thief",
    "LADRAO DE CASACA":          "To Catch a Thief",
    "O HOMEM DA CÂMARA DE FILMAR": "Man with a Movie Camera",
    "O HOMEM DA CAMARA DE FILMAR": "Man with a Movie Camera",
    "A VERGONHA":                "Shame",
    "A FONTE DA VIRGEM":         "The Virgin Spring",
    "O COURAÇADO POTEMKINE":     "Battleship Potemkin",
    "O COURACADO POTEMKINE":     "Battleship Potemkin",
    "ANTES DO AMANHECER":        "Before Sunrise",
    "ANTES DO ANOITECER":        "Before Sunset",
    "A PRISÃO":                  "Prison",
    "A PRISAO":                  "Prison",
    "MULHERES QUE ESPERAM":      "Waiting Women",
    "A INFÂNCIA DE IVAN":        "Ivan's Childhood",
    "A INFANCIA DE IVAN":        "Ivan's Childhood",
    "CIDADE PORTUÁRIA":          "Port of Call",
    "CIDADE PORTUARIA":          "Port of Call",
    "LUZ DE INVERNO":            "Winter Light",
    "DA VIDA DAS MARIONETAS":    "From the Life of the Marionettes",
    "SONATA DE OUTONO":          "Autumn Sonata",
    "ADEUS A MATIORA":           "Farewell",
    "AMADEUS – DIRECTOR'S CUT":  "Amadeus",
    "ACORDAR PARA A VIDA":       "Waking Life",
    "ANTES DO AMANHECER":        "Before Sunrise",
    "O COURAÇADO POTEMKINE":     "Battleship Potemkin",
    "DON GIOVANNI":              "Don Giovanni",
    "UMA LUZ NAS TREVAS":        "Music in Darkness",
    "ARSENAL":                   "Arsenal",
    "ALEXANDER NEVSKY":              "Alexander Nevsky",
    # ── Werner Herzog ──
    "AGUIRRE, A CÓLERA DE DEUS":    "Aguirre, the Wrath of God",
    "AGUIRRE, A COLERA DE DEUS":    "Aguirre, the Wrath of God",
    "O ENIGMA DE KASPAR HAUSER":    "The Enigma of Kaspar Hauser",
    "NOSFERATU, O FANTASMA DA NOITE": "Nosferatu the Vampyre",
    "LIÇÕES DA ESCURIDÃO":          "Lessons of Darkness",
    "LICOES DA ESCURIDAO":          "Lessons of Darkness",
    "ALÉM DO AZUL SELVAGEM":        "The Wild Blue Yonder",
    "ALEM DO AZUL SELVAGEM":        "The Wild Blue Yonder",
    "KINSKI – MEU INIMIGO MAIS QUERIDO": "My Best Fiend",
    "KINSKI - MEU INIMIGO MAIS QUERIDO": "My Best Fiend",
}


# ── Cache ──────────────────────────────────────────────────────────────────────

def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ── Utils ──────────────────────────────────────────────────────────────────────

def strip_accents(text):
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )

def clean_title(title):
    # Remove subtítulos após hífen, pipe, barra ou em-dash/en-dash
    title = re.sub(r'\s*[\-|/\u2013\u2014]\s*[^\-|/\u2013\u2014]+$', '', title)
    title = re.sub(r'\s*\(.*?\)', '', title)
    return title.strip()

def to_slug(title):
    t = strip_accents(title.lower())
    t = re.sub(r'[^a-z0-9 ]', '', t)
    t = re.sub(r'\s+', '-', t.strip())
    return t


# ── Letterboxd ─────────────────────────────────────────────────────────────────

def lbxd_fetch(slug):
    url = f"https://letterboxd.com/film/{slug}/"
    req = urllib.request.Request(url, headers=HEADERS_BROWSER)
    with urllib.request.urlopen(req, timeout=10) as r:
        html = r.read().decode("utf-8", errors="ignore")

    rating_m = re.search(r'twitter:data2" content="([\d.]+)', html)
    poster_m = re.search(r'"image"\s*:\s*"(https://a\.ltrbxd\.com[^"]+)"', html)

    poster = None
    if poster_m:
        raw = poster_m.group(1)
        # Aumenta resolução para 500×750
        poster = re.sub(r'-0-\d+-0-\d+-crop', '-0-500-0-750-crop', raw)

    return {
        "rating": float(rating_m.group(1)) if rating_m else None,
        "poster": poster,
    }

def lbxd_lookup(title, year=None):
    clean  = clean_title(title)
    upper  = clean.upper()
    no_acc = strip_accents(upper)

    slugs_to_try = []

    # 1. Alias explícito — testa título original ANTES de limpar (para distinguir Parte 1 / Parte 2)
    orig_upper  = title.upper()
    orig_no_acc = strip_accents(orig_upper)
    alias_slug  = (LBXD_SLUGS.get(orig_upper) or LBXD_SLUGS.get(orig_no_acc)
                   or LBXD_SLUGS.get(upper)   or LBXD_SLUGS.get(no_acc))
    if alias_slug:
        slugs_to_try.append(alias_slug)

    # 2. Título entre parênteses = língua original (ex: "A Alegria (La gioia)" → "la-gioia")
    paren_m = re.search(r'\(([^)]+)\)', title)
    if paren_m:
        paren_slug = to_slug(paren_m.group(1).strip())
        if paren_slug and year:
            for dy in [0, -1, -2]:
                slugs_to_try.append(f"{paren_slug}-{year + dy}")
        if paren_slug:
            slugs_to_try.append(paren_slug)

    # 3. Slug gerado do título limpo + variações de ano (±2 para diferenças de estreia)
    auto = to_slug(clean)
    if auto:
        if year:
            for dy in [0, -1, -2]:
                slugs_to_try.append(f"{auto}-{year + dy}")
        slugs_to_try.append(auto)

    best = None  # melhor resultado sem rating (só poster)
    for slug in slugs_to_try:
        try:
            data = lbxd_fetch(slug)
            if data["rating"]:
                return data          # rating encontrado → retorna imediatamente
            if data["poster"] and best is None:
                best = data          # guarda poster como fallback
        except Exception:
            pass
        time.sleep(0.3)  # respeita rate-limit

    return best  # retorna poster-only se não encontrou rating


# ── OMDB ───────────────────────────────────────────────────────────────────────

def omdb_fetch(title, year=None):
    params = {"t": title, "apikey": OMDB_KEY}
    if year:
        params["y"] = str(year)
    url = "https://www.omdbapi.com/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "cinelisboa/1.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode())

def director_matches(omdb_director, expected_director):
    """Verifica se o realizador bate certo (comparação parcial, case-insensitive)."""
    if not omdb_director or omdb_director == "N/A":
        return False  # rejeita se OMDB não tem realizador e nós temos
    a = strip_accents(expected_director.lower())
    b = strip_accents(omdb_director.lower())
    # Aceita se o apelido do realizador esperado aparece no resultado
    last_name = a.split()[-1] if a.split() else a
    return last_name in b


def omdb_lookup(title, year=None, director=None):
    clean    = clean_title(title)
    no_acc   = strip_accents(clean)
    alias    = OMDB_ALIASES.get(clean.upper()) or OMDB_ALIASES.get(no_acc.upper())

    # Título entre parênteses = título original (ex: "A Alegria (La gioia)" → "La gioia")
    paren_m = re.search(r'\(([^)]+)\)', title)
    paren_title = paren_m.group(1).strip() if paren_m else None

    attempts = []
    # Se existe título original (parênteses), usa-o e NÃO faz fallback para o título
    # traduzido (evita encontrar um filme diferente com título semelhante noutra língua)
    if paren_title:
        if year:
            for dy in [0, -1, -2]:
                attempts.append((paren_title, year + dy))
        attempts.append((paren_title, None))
        if alias:
            if year:
                for dy in [0, -1, -2]:
                    attempts.append((alias, year + dy))
            attempts.append((alias, None))
    else:
        if year:
            # Tenta o ano exacto e os 2 anos anteriores (diferenças de estreia)
            for dy in [0, -1, -2]:
                attempts.append((clean, year + dy))
                if no_acc != clean:
                    attempts.append((no_acc, year + dy))
            if alias:
                for dy in [0, -1, -2]:
                    attempts.append((alias, year + dy))
            attempts.append((clean, None))
        attempts += [(clean, None), (no_acc, None)]
        if alias:  attempts.append((alias, None))

    seen, unique = set(), []
    for a in attempts:
        if a not in seen:
            seen.add(a)
            unique.append(a)

    for t, y in unique:
        if not t: continue
        try:
            data = omdb_fetch(t, y)
            if data.get("Response") != "True":
                continue
            # Validação de ano (±2)
            if year and data.get("Year"):
                try:
                    if abs(int(data["Year"][:4]) - int(year)) > 2:
                        continue
                except ValueError:
                    pass
            # Validação de realizador — rejeita matches sem realizador quando temos um
            if director:
                if not director_matches(data.get("Director", ""), director):
                    continue
            # Validação de título — evita matches onde o OMDB retorna título muito diferente
            # (ex: procura "SEN" → OMDB devolve "Sen Kimsin?" → rejeita)
            omdb_t  = re.sub(r'[^a-z0-9 ]', '', strip_accents(data.get("Title","").lower())).strip()
            search_t = re.sub(r'[^a-z0-9 ]', '', strip_accents(t.lower())).strip()
            if omdb_t and search_t and omdb_t != search_t:
                if omdb_t.startswith(search_t) and len(search_t) / len(omdb_t) < 0.6:
                    continue  # título OMDB muito mais longo que a pesquisa
            return data
        except Exception:
            pass
    return None


# ── Enrich ─────────────────────────────────────────────────────────────────────

def enrich(movies):
    cache   = load_cache()
    changed = False

    for movie in movies:
        title = movie.get("title", "")
        year  = movie.get("year")
        key   = f"{title}|{year}"

        if key not in cache:
            print(f"  [LB] {title}...", end=" ", flush=True)
            director = movie.get("director")
            lb   = lbxd_lookup(title, year)
            omdb = omdb_lookup(title, year, director=director)
            cache[key] = {"lbxd": lb, "omdb": omdb}
            changed = True
            if lb and lb.get("rating"):
                print(f"★ {lb['rating']}/5", end="")
            else:
                print("sem rating", end="")
            print()
        else:
            lb   = cache[key].get("lbxd")
            omdb = cache[key].get("omdb")

        # ── Aplicar dados ───────────────────────────────────────────
        # Poster: Letterboxd sempre (sobrepõe poster do scraper), fallback OMDB
        if lb and lb.get("poster"):
            movie["poster"] = lb["poster"]
        elif not movie.get("poster") and omdb and omdb.get("Poster") and omdb["Poster"] != "N/A":
            movie["poster"] = omdb["Poster"]

        # Rating Letterboxd (escala 0-5)
        if lb and lb.get("rating"):
            movie["rating"] = lb["rating"]

        # Metadados via OMDB (fallbacks)
        if omdb:
            if not movie.get("director") and omdb.get("Director") not in (None, "N/A"):
                movie["director"] = omdb["Director"]
            if not movie.get("duration"):
                rt = omdb.get("Runtime", "")
                m = re.match(r"(\d+)", rt)
                if m: movie["duration"] = int(m.group(1))
            if not movie.get("year") and omdb.get("Year"):
                try: movie["year"] = int(omdb["Year"][:4])
                except ValueError: pass
            if not movie.get("genres") and omdb.get("Genre") not in (None, "N/A"):
                movie["genres"] = [g.strip() for g in omdb["Genre"].split(",")][:3]
            if not movie.get("plot") and omdb.get("Plot") not in (None, "N/A"):
                movie["plot"] = omdb["Plot"]
            if not movie.get("country") and omdb.get("Country") not in (None, "N/A"):
                movie["country"] = omdb["Country"]

    if changed:
        save_cache(cache)

    return movies


if __name__ == "__main__":
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "sessions.js")
    with open(data_path, encoding="utf-8") as f:
        js = f.read()
    payload = json.loads(js.replace("window.CINEMA_DATA = ", "").rstrip(";"))
    enrich(payload["movies"])
