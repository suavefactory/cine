"""
Enricher: busca poster, rating (Letterboxd 0-5) e metadados via:
  1. Letterboxd  — rating + poster portrait
  2. OMDB        — fallback para poster, director, duration, year

Cache em data/omdb_cache.json
"""

import urllib.request, urllib.parse
import json, re, os, sys, unicodedata, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cinema_meta

OMDB_KEY   = "trilogy"
CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "omdb_cache.json")

# A Wikimedia exige um User-Agent que identifique a aplicação e dê forma de
# contacto; agentes genéricos apanham throttling agressivo. Com "cinelisboa/1.0"
# cada pedido demorava 15s (429 + espera) e uma corrida completa era impossível.
WIKI_HEADERS = {
    "User-Agent": "sesh.pt/1.0 (https://sesh.pt; ruipedrosimoes14@gmail.com)",
}

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
    "OS DOMINGOS":               "los-domingos",
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
    "NOSTALGIA (1983)":             "nostalghia",
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
    "O ÚLTIMO PADRINHO":            "iddu",
    "O ULTIMO PADRINHO":            "iddu",
    "ENTRONCAMENTO":                "entroncamento",
    "MARCEL E MONSIEUR PAGNOL":     "marcel-et-monsieur-pagnol",
    "VALOR SENTIMENTAL":            "sentimental-value-2025",
    "RIEFENSTAHL":                  "riefenstahl",
    "A PEQUENA AMÉLIE":             "little-amelie",
    "A PEQUENA AMELIE":             "little-amelie",
    "MR NOBODY CONTRA PUTIN":       "mr-nobody-against-putin",
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
    "UN ANNO DI SCUOLA":            "a-year-of-school",
    # ── INDIE Lisboa ──
    "A RIVER'S GAZE":               "a-rivers-gaze",
    "AUTO DA CASA":                 "auto-da-casa",
    "BARRIO TRISTE":                "barrio-triste",
    "BY DESIGN":                    "by-design",
    "CONFERENCE OF THE BIRDS":      "conference-of-the-birds",
    "ERUPCJA":                      "erupcja",
    "FIZ UM FOGUETE":               "fiz-um-foguete-imaginando-que-voce-vinha",
    "FRACTAIS TROPICAIS":           "fractais-tropicais",
    "FRÍO METAL":                   "frio-metal",
    "FRIO METAL":                   "frio-metal",
    "FUCKTOYS":                     "fucktoys",
    "HOLY DESTRUCTORS":             "holy-destructors",
    "MY WIFE CRIES":                "my-wife-cries",
    "QUEM TEM MEDO DE ZURITA?":     "quem-tem-medo-de-zurita-de-oliveira",
    "ROSE OF NEVADA":               "rose-of-nevada",
    "RUA ISTO NÃO É UM FILME":      "rua-isto-nao-e-um-filme-e-um-cometa",
    "RUA ISTO NAO E UM FILME":      "rua-isto-nao-e-um-filme-e-um-cometa",
    "VINTAGE GLITCH":               "vintage-glitch-cidades-para-acabar-com-todos-os-veroes-e-crepusculos",
    "THE BEWILDERMENT OF CHILE":    "the-bewilderment-of-chile",
    "ÓCULOS DE SOL PRETOS":         "oculos-de-sol-pretos",
    "OCULOS DE SOL PRETOS":         "oculos-de-sol-pretos",
    "NÃO DESVIAR O OLHAR":          "nao-desviar-o-olhar",
    "NAO DESVIAR O OLHAR":          "nao-desviar-o-olhar",
    # ── Medeia Nimas — ciclo PTA ──
    "EMBRIAGADO DE AMOR":           "punch-drunk-love",
    "JOGOS DE PRAZER":              "boogie-nights",
    "MAGNOLIA":                     "magnolia",
    "HAVERÁ SANGUE":                "there-will-be-blood",
    "HAVERA SANGUE":                "there-will-be-blood",
    "LINHA FANTASMA":               "phantom-thread",
    "VÍCIO INTRÍNSECO":             "inherent-vice",
    "VICIO INTRÍNSECO":             "inherent-vice",
    "VICIO INTRINSECO":             "inherent-vice",
    "LICORICE PIZZA":               "licorice-pizza",
    "O MENTOR":                     "the-master-2012",
    # ── Medeia Nimas — ciclo Marilyn Monroe ──
    "O PECADO MORA AO LADO":        "the-seven-year-itch",
    "O PRÍNCIPE E A CORISTA":       "the-prince-and-the-showgirl",
    "O PRINCIPE E A CORISTA":       "the-prince-and-the-showgirl",
    "NIAGARA":                      "niagara",
    "OS HOMENS PREFEREM AS LOIRAS": "gentlemen-prefer-blondes",
    "COMO SE CONQUISTA UM MILIONÁRIO": "how-to-marry-a-millionaire",
    "COMO SE CONQUISTA UM MILIONARIO": "how-to-marry-a-millionaire",
    "QUANTO MAIS QUENTE MELHOR":    "some-like-it-hot",
    "PARAGEM DE AUTOCARRO":         "bus-stop",
    "DESENGANO":                    "clash-by-night",
    "PARADA DE ESTRELAS":           "theres-no-business-like-show-business",
    "LOUCO POR MULHERES":           "love-happy",
    # ── Medeia Nimas — ciclo Kurosawa ──
    "OS SETE SAMURAIS":             "seven-samurai",
    "YOJIMBO, O INVENCÍVEL":        "yojimbo",
    "YOJIMBO, O INVENCIVEL":        "yojimbo",
    "O BARBA RUIVA":                "red-beard",
    "DODESKADEN – POUCA TERRA... POUCA TERRA": "dodeska-den",
    "DODESKADEN - POUCA TERRA... POUCA TERRA": "dodeska-den",
    "DERSU UZALA":                  "dersu-uzala",
    # ── Medeia Nimas — ciclo Ozu ──
    "A FLOR DO EQUINÓCIO":          "equinox-flower",
    "A FLOR DO EQUINOCIO":          "equinox-flower",
    "BOM DIA":                      "good-morning-1959",
    "CREPÚSCULO EM TÓQUIO":         "tokyo-twilight",
    "CREPUSCULO EM TOQUIO":         "tokyo-twilight",
    "O FIM DO OUTONO":              "late-autumn",
    "O GOSTO DO SAKÉ":              "an-autumn-afternoon",
    "O GOSTO DO SAKE":              "an-autumn-afternoon",
    # ── Medeia Nimas — ciclo Mizoguchi ──
    "CONTOS DA LUA VAGA":           "ugetsu",
    "A IMPERATRIZ YANG KWEI FEI":   "princess-yang-kwei-fei",
    "A MULHER DE QUEM SE FALA":     "uwasa-no-onna",
    "O HERÓI SACRÍLEGO":            "chikamatsu-monogatari",
    "O HEROI SACRILEGO":            "chikamatsu-monogatari",
    "RUA DA VERGONHA":              "street-of-shame",
    # ── Medeia Nimas — outros ──
    "CONTA COMIGO":                 "stand-by-me",
    "CONTOS CRUÉIS DA JUVENTUDE":   "cruel-story-of-youth",
    "CONTOS CRUEIS DA JUVENTUDE":   "cruel-story-of-youth",
    "PARASITAS":                    "parasite-2019",
    "DRIVE MY CAR":                 "drive-my-car",
    "DIAS PERFEITOS":               "perfect-days-2023",
    "EVIL DOES NOT EXIST – O MAL NÃO ESTÁ AQUI": "evil-does-not-exist",
    "EVIL DOES NOT EXIST - O MAL NAO ESTA AQUI": "evil-does-not-exist",
    "A MULHER QUE FUGIU":           "the-woman-who-ran",
    "A ROMANCISTA E O SEU FILME":   "in-our-day",
    "CULPADO – INOCENTE – MONSTRO": "monster-2023",
    "CULPADO - INOCENTE - MONSTRO": "monster-2023",
    "AS VERDADEIRAS MÃES":          "true-mothers",
    "AS VERDADEIRAS MAES":          "true-mothers",
    "RODA DA FORTUNA E DA FANTASIA":"wheel-of-fortune-and-fantasy",
    "A CRIADA":                     "the-handmaiden",
    "POESIA":                       "poetry",
    "O JOELHO DE CLAIRE":           "claires-knee",
    "O VERÃO DE KIKUJIRO":          "kikujiro",
    "O VERAO DE KIKUJIRO":          "kikujiro",
    "O PÂNTANO":                    "la-cienaga",
    "O PANTANO":                    "la-cienaga",
    "OS INADAPTADOS":               "the-misfits",
    "MISERY – O CAPÍTULO FINAL":    "misery",
    "MISERY - O CAPITULO FINAL":    "misery",
    "UM AMOR INEVITÁVEL":           "when-harry-met-sally",
    "UM AMOR INEVITAVEL":           "when-harry-met-sally",
    "VAMO-NOS AMAR":                "lets-make-love",
    "QUANDO A CIDADE DORME":        "the-asphalt-jungle",
    "VIOLÊNCIA E PAIXÃO":           "conversation-piece",
    "VIOLENCIA E PAIXAO":           "conversation-piece",
    "EVA":                          "all-about-eve",
    "RIO SEM REGRESSO":             "river-of-no-return",
    "MEKTOUB, MEU AMOR: CANTO SEGUNDO": "mektoub-my-love-intermezzo",
    "A CULPA FOI DO MACACO":        "monkey-business-1952",
    "MULHERES DA NOITE":            "girls-of-the-night",
    "SENHORA OGIN":                 "ogin-sama",
    # ── Trindade ──
    "FELLINI 8½":                   "8-1-2",
    "FELLINI 8 1/2":                "8-1-2",
    "O ACOSSADO":                   "breathless",
    # ── Títulos com slug não óbvio ──
    "JLG/JLG":                      "jlg-jlg-self-portrait-in-december",
    "O DRAMA":                      "the-drama",
    "A VOZ DE HIND RAJAB":          "the-voice-of-hind-rajab",
    "VIAGEM A TÓQUIO":              "tokyo-story",
    "VIAGEM A TOQUIO":              "tokyo-story",
    # ── Farocki / outros títulos alemães ──
    "ZWISCHEN ZWEI KRIEGEN":        "between-two-wars",
    # ── Oliveira ──
    "O GEBO E A SOMBRA":            "gebo-and-the-shadow",
    # ── Verão 1993 (Carla Simón) ──
    "VERÃO 1993":                   "summer-1993",
    "VERAO 1993":                   "summer-1993",
    # ── Filmes portugueses/outros sem slug automático ──
    "O AGENTE SECRETO":             "the-secret-agent-2025",
    "GOD-AND-A-HALF":               "god-and-a-half",
    # ── Cinemateca — ciclo Torre Bela / Ibérico / outros ──
    "TORRE BELA":                   "torre-bela",
    "TIGRES DE PAPEL":              "tigres-de-papel",
    "PAPER TIGERS":                 "tigres-de-papel",
    "EL CRIMEN DE CUENCA":          "the-crime-of-cuenca",
    "THE CRIME OF CUENCA":          "the-crime-of-cuenca",
    "OÙ GÎT VOTRE SOURIRE ENFOUÎ?": "where-does-your-hidden-smile-lie",
    "OU GIT VOTRE SOURIRE ENFOUI?": "where-does-your-hidden-smile-lie",
    "L'INHUMAINE":                  "linhumaine",
    "MAMMA":                        "mother-1982",
    "HAPPY DAY":                    "happy-day-1976",
    "EVDOKIA":                      "evdokia",
    "LOS SANTOS INOCENTES":         "los-santos-inocentes",
    "CANCIONES PARA DESPUÉS DE UNA GUERRA": "songs-for-after-a-war",
    "CANCIONES PARA DESPUES DE UNA GUERRA": "songs-for-after-a-war",
    "VIRIDIANA":                    "viridiana",
    "MARX PUÒ ASPETTARE":           "marx-can-wait",
    "MARX PUO ASPETTARE":           "marx-can-wait",
    "FRÁGIL COMO O MUNDO":          "fragil-como-o-mundo",
    "FRAGIL COMO O MUNDO":          "fragil-como-o-mundo",
    "SOFT AND HARD (A SOFT CONVERSATION BETWEEN TWO FRIENDS ON A HARD SUBJECT)": "soft-and-hard",
    "SOFT AND HARD":                "soft-and-hard",
    "THOMAS HARLAN – WANDERSPLITTER": "thomas-harlan-wandersplitter",
    "THOMAS HARLAN - WANDERSPLITTER": "thomas-harlan-wandersplitter",
    "THOMAS HARLAN – MOVING SHRAPNEL": "thomas-harlan-wandersplitter",
    "PUNISHMENT PARK":              "punishment-park",
    "REAL LIFE":                    "real-life",
    # ── Fernando Lopes — novos filmes ──
    # A Rapariga Que Sabia Demais (2025, Hambalek) ainda não tem página LB
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
    return _parse_lbxd_html(html)

def lbxd_fetch_by_imdb(imdb_id):
    """Busca a página do Letterboxd diretamente pelo IMDb ID, através do
    endpoint de redirect /imdb/{id}/ — resolve o filme de forma exata, sem
    depender de nenhuma adivinhação de slug a partir do título. É o caminho
    mais fiável de todos quando temos um IMDb ID (via Wikidata)."""
    url = f"https://letterboxd.com/imdb/{imdb_id}/"
    req = urllib.request.Request(url, headers=HEADERS_BROWSER)
    with urllib.request.urlopen(req, timeout=10) as r:
        html = r.read().decode("utf-8", errors="ignore")
    return _parse_lbxd_html(html)

def _parse_lbxd_html(html):
    from html import unescape as _unescape
    rating_m = re.search(r'twitter:data2" content="([\d.]+)', html)
    poster_m = re.search(r'"image"\s*:\s*"(https://a\.ltrbxd\.com[^"]+)"', html)
    desc_m   = re.search(r'<meta property="og:description" content="([^"]+)"', html)

    poster = None
    if poster_m:
        raw = poster_m.group(1)
        poster = re.sub(r'-0-\d+-0-\d+-crop', '-0-500-0-750-crop', raw)

    description = None
    if desc_m:
        description = _unescape(desc_m.group(1)).strip()

    # Géneros: links /films/genre/X/ — preserva ordem, sem duplicados
    genre_slugs = list(dict.fromkeys(re.findall(r'href="/films/genre/([^/"]+)/"', html)))
    genres = [g.replace("-", " ").title() for g in genre_slugs] if genre_slugs else None

    # País: primeiro país da lista /films/country/X/
    country_m = re.search(r'href="/films/country/[^/"]+/"[^>]*>\s*([^<]+?)\s*<', html)
    country = country_m.group(1).strip() if country_m else None

    # Realizador: extrai nome e slug para validação e página de realizador
    director_slug_m = re.search(r'href="/director/([^/]+)/"[^>]*>\s*([^<]+?)\s*</a>', html)
    director       = director_slug_m.group(2).strip() if director_slug_m else None
    director_slug  = director_slug_m.group(1)         if director_slug_m else None

    # Título (inglês/internacional) + ano: extrai do <title> "Film Name (2025) directed by..."
    lb_year  = None
    lb_title = None
    title_m = re.search(r'<title>([^(]*)\((\d{4})\)', html)
    if title_m:
        # Letterboxd põe sempre uma marca U+200E (LTR mark, &lrm;) no início
        # do <title> — sem unescape+strip ficava a aparecer literalmente.
        lb_title = _unescape(title_m.group(1)).strip().lstrip('‎‏').strip() or None
        try:
            lb_year = int(title_m.group(2))
        except ValueError:
            pass

    return {
        "rating":         float(rating_m.group(1)) if rating_m else None,
        "poster":         poster,
        "description":    description,
        "genres":         genres,
        "country":        country,
        "lb_director":    director,
        "lb_director_slug": director_slug,
        "lb_year":        lb_year,
        "lb_title":       lb_title,
    }

def lbxd_lookup(title, year=None, director=None):
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
    # Ignora parênteses com apenas um ano (ex: "Nostalgia (1983)")
    paren_m = re.search(r'\(([^)]+)\)', title)
    if paren_m and not re.match(r'^\d{4}$', paren_m.group(1).strip()):
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
            # Validação de realizador: se temos realizador esperado e o LB diz outro,
            # rejeita o match para evitar posters errados (ex: "sundays" ≠ Alauda Ruiz de Azúa)
            if director and data.get("lb_director"):
                lb_dir  = strip_accents(data["lb_director"].lower())
                exp_dir = strip_accents(director.lower())
                exp_last = strip_accents(exp_dir.split()[-1]) if exp_dir.split() else ""
                if exp_last and exp_last not in lb_dir:
                    time.sleep(0.3)
                    continue  # realizador não bate — ignora este slug
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
    req = urllib.request.Request(url, headers=WIKI_HEADERS)
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode())

def omdb_fetch_by_id(imdb_id):
    """Lookup exato por IMDb ID — não depende de o título bater certo."""
    params = {"i": imdb_id, "apikey": OMDB_KEY}
    url = "https://www.omdbapi.com/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=WIKI_HEADERS)
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
    # Ignora parênteses com apenas um ano (ex: "Nostalgia (1983)")
    paren_m = re.search(r'\(([^)]+)\)', title)
    paren_title = None
    if paren_m and not re.match(r'^\d{4}$', paren_m.group(1).strip()):
        paren_title = paren_m.group(1).strip()

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


# ── Resolução filme → IMDb ID ──────────────────────────────────────────────────
#
# O Letterboxd e o OMDB só sabem procurar pelo título original/inglês. Um filme
# listado com o título de distribuição português — que é como metade da
# programação de repertório aparece — nunca era encontrado por eles.
#
# Estas funções resolvem o filme até ao IMDb ID, que depois abre a página certa
# do Letterboxd pelo redirect /imdb/{id}/. Duas fontes complementares:
#
#   1. o autocomplete do IMDb, que indexa os títulos alternativos de
#      distribuição (é ele que sabe que "Sem Eira Nem Beira" é "Vagabond");
#   2. a filmografia estruturada do realizador no Wikidata, que apanha as
#      curtas e os documentários que o autocomplete não indexa em português.
#
# Nenhuma correspondência é aceite sem bater certo o realizador ou o ano — a
# alternativa é trocar filmes homónimos, que é pior do que não ter rating.

FILMO_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "filmography_cache.json")

# Tipos do IMDb que nunca são o filme que procuramos
IMDB_TYPES_BAD = {"videoGame", "musicVideo", "tvEpisode", "podcastSeries", "podcastEpisode"}


def load_filmo_cache():
    if os.path.exists(FILMO_CACHE_PATH):
        try:
            with open(FILMO_CACHE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            return {}
    return {}


def save_filmo_cache(cache):
    os.makedirs(os.path.dirname(FILMO_CACHE_PATH), exist_ok=True)
    with open(FILMO_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)


def _norm(t):
    t = strip_accents((t or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def imdb_suggest(query):
    """Candidatos do autocomplete do IMDb — indexa títulos de distribuição."""
    q = _norm(query).replace(" ", "_")
    if not q:
        return []
    url = f"https://v3.sg.media-imdb.com/suggestion/x/{urllib.parse.quote(q)}.json"
    req = urllib.request.Request(url, headers=HEADERS_BROWSER)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
    except Exception:
        return []
    out = []
    for x in data.get("d", []):
        i = x.get("id", "")
        if i.startswith("tt") and x.get("qid") not in IMDB_TYPES_BAD:
            out.append({"imdb_id": i, "title": x.get("l"), "year": x.get("y")})
    return out


def _wikidata_qid(name):
    """Q-id da pessoa no Wikidata, para a filmografia."""
    try:
        p = urllib.parse.urlencode({
            "action": "wbsearchentities", "search": name, "language": "en",
            "type": "item", "format": "json", "limit": 5,
        })
        res = _wiki_api_wikidata_raw(f"https://www.wikidata.org/w/api.php?{p}").get("search", [])
    except Exception:
        return None
    for r in res:
        if _norm(r.get("label", "")) == _norm(name):
            return r["id"]
    return res[0]["id"] if res else None


def _wiki_api_wikidata_raw(url):
    req = urllib.request.Request(url, headers=WIKI_HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def wikidata_filmography(director, cache):
    """{imdb_id: {"years": [...], "titles": [...]}} — filmes do realizador.

    Uma consulta serve uma retrospetiva inteira (quinze filmes da Varda saem
    todos da mesma), por isso fica em cache por realizador.
    """
    key = _norm(director)
    if not key:
        return {}
    if key in cache:
        return cache[key]
    qid = _wikidata_qid(director)
    if not qid:
        cache[key] = {}
        return {}
    query = f"""SELECT ?imdb ?y ?label WHERE {{
  ?f wdt:P57 wd:{qid} ; wdt:P345 ?imdb .
  OPTIONAL {{ ?f wdt:P577 ?dt . BIND(YEAR(?dt) AS ?y) }}
  OPTIONAL {{ ?f rdfs:label ?label FILTER(LANG(?label) IN ("en","pt","fr","it","es","de")) }}
}}"""
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={
        **WIKI_HEADERS,
        "Accept": "application/sparql-results+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            rows = json.loads(r.read())["results"]["bindings"]
    except Exception:
        return {}          # falha de rede: não fica em cache, tenta outra vez amanhã
    films = {}
    for b in rows:
        e = films.setdefault(b["imdb"]["value"], {"years": [], "titles": []})
        if "y" in b:
            try:
                y = int(b["y"]["value"])
                if y not in e["years"]:
                    e["years"].append(y)
            except ValueError:
                pass
        if "label" in b and b["label"]["value"] not in e["titles"]:
            e["titles"].append(b["label"]["value"])
    cache[key] = films
    return films


def _title_overlap(title, candidates):
    """Fracção de palavras em comum com o título mais parecido."""
    a = set(_norm(title).split())
    best = 0.0
    for c in candidates:
        b = set(_norm(c).split())
        if a and b:
            best = max(best, len(a & b) / max(len(a), len(b)))
    return best


def _validate_candidate(imdb_id, year, director):
    """Confirma pelo OMDB que este IMDb ID é mesmo o filme certo."""
    try:
        od = omdb_fetch_by_id(imdb_id)
    except Exception:
        return None
    if not od or od.get("Response") != "True":
        return None
    oy = None
    if od.get("Year"):
        try:
            oy = int(str(od["Year"])[:4])
        except ValueError:
            pass
    if year and oy and abs(oy - year) > 2:
        return None
    if director:
        return od if director_matches(od.get("Director", ""), director) else None
    # Sem realizador só o ano pode confirmar, e tem de ser certeiro
    return od if (year and oy and abs(oy - year) <= 1) else None


def resolve_imdb_id(title, year=None, director=None, original_title=None, filmo_cache=None):
    """(imdb_id, omdb, motivo) — None quando não há correspondência segura.

    Preferir não resolver a resolver mal: um rating errado num filme é pior
    para o site do que um filme sem rating.
    """
    filmo_cache = filmo_cache if filmo_cache is not None else {}
    queries = [q for q in (original_title, title) if q]
    seen = set()

    # 1. Autocomplete do IMDb, validado. O título original primeiro: é o que o
    #    IMDb indexa como principal, por isso acerta quase sempre à primeira.
    all_cands = []
    for q in queries:
        cands = imdb_suggest(q)
        time.sleep(0.2)
        if year:
            cands.sort(key=lambda c: abs((c.get("year") or 9999) - year))
        all_cands.extend(cands)
        for c in cands[:6]:
            if c["imdb_id"] in seen:
                continue
            seen.add(c["imdb_id"])
            cy = c.get("year")
            if year and cy and abs(cy - year) > 2:
                continue
            od = _validate_candidate(c["imdb_id"], year, director)
            time.sleep(0.15)
            if od:
                return c["imdb_id"], od, "imdb"

    if not director:
        return None, None, "sem realizador para validar"

    # 2. Filmografia do realizador. Apanha o que o autocomplete não indexa em
    #    português — sobretudo curtas e documentários.
    filmo = wikidata_filmography(director, filmo_cache)
    if not filmo:
        # O "realizador" não existe como pessoa. Às vezes é o cinema que
        # trocou os campos e pôs ali o título original (a Medeia lista
        # "As Donzelas Fizeram 25 Anos" com realizador "Les Demoiselles ont
        # eu 25 ans"). Vale a pena tentar esse texto como título, mas só com
        # o ano a confirmar — sem realizador não há outra forma de validar.
        if year and len(director.split()) > 2:
            for c in imdb_suggest(director)[:4]:
                cy = c.get("year")
                if cy and abs(cy - year) <= 1:
                    od = _validate_candidate(c["imdb_id"], year, None)
                    if od:
                        return c["imdb_id"], od, "campo realizador era o título"
        return None, None, "sem filmografia"

    # 2a. Um dos candidatos do autocomplete é do realizador certo: decidido.
    inter = [i for i in filmo if i in {c["imdb_id"] for c in all_cands}]
    if len(inter) == 1:
        return inter[0], _validate_candidate(inter[0], None, None) or None, "filmografia+imdb"

    if not year:
        return None, None, "sem ano para filtrar filmografia"

    # 2b. Filmes do realizador nesse ano.
    near = [i for i, v in filmo.items() if any(abs(y - year) <= 1 for y in v["years"])]
    if len(near) == 1:
        return near[0], None, "filmografia+ano"
    if len(near) > 1:
        scored = sorted(
            ((max(_title_overlap(q, filmo[i]["titles"]) for q in queries), i) for i in near),
            reverse=True)
        # Só desempata quando um dos títulos é claramente o mais parecido
        if scored[0][0] >= 0.5 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            return scored[0][1], None, "filmografia+ano+título"
        return None, None, f"{len(near)} filmes do realizador em {year}"
    return None, None, "nada na filmografia nesse ano"


# ── Enrich ─────────────────────────────────────────────────────────────────────

def enrich(movies):
    cache   = load_cache()
    filmo   = load_filmo_cache()
    changed = False

    for idx, movie in enumerate(movies):
        title = movie.get("title", "")
        year  = movie.get("year")
        key   = f"{title}|{year}"
        director = movie.get("director")

        # Guarda progresso a cada 20 filmes — um processamento grande (ex:
        # backfill de filmes sem rating) pode demorar dezenas de minutos por
        # causa do Wikidata/Letterboxd, e sem isto uma falha a meio perdia
        # tudo (só se gravava no fim).
        if changed and idx % 20 == 0:
            save_cache(cache)

        cached = cache.get(key)

        # ── Ficha da programação oficial do cinema ───────────────────────
        # Dá o título original (a chave para encontrar o filme no Letterboxd)
        # e a sinopse em português escrita pelo próprio cinema. É a melhor
        # fonte que existe para os dois, por isso vem antes de tudo o resto.
        # O scraper do Batalha já traz estes campos da API, sem pedido extra.
        # Uma ficha vazia é tentada de novo no dia seguinte (o cinema pode
        # ainda não ter publicado a sinopse). Sites sem extractor não custam
        # nada: fetch() devolve logo None sem chegar a fazer pedido.
        meta = (cached or {}).get("cinema")
        if not meta and movie.get("link"):
            meta = cinema_meta.fetch(movie["link"]) or {}
            if cached is not None:
                cached["cinema"] = meta
                changed = True
            time.sleep(0.2)
        meta = meta or {}
        orig_title = movie.get("original_title") or meta.get("original_title")
        if orig_title and to_slug(orig_title) == to_slug(title):
            orig_title = None
        cinema_plot_pt = movie.get("plot_pt") or meta.get("plot_pt")

        # Tenta de novo sempre que ainda não há rating — antes disto, uma
        # falha (transitória ou por título só em PT sem match) ficava em
        # cache para sempre e nunca mais era retentada, mesmo depois de
        # melhorar a lógica de resolução de título. Também reprocessa
        # entradas cujo campo "lbxd" ainda não tem os campos mais recentes.
        needs_fields = cached and cached.get("lbxd") is not None and (
            "description" not in cached["lbxd"] or "country" not in cached["lbxd"]
            or "lb_title" not in cached["lbxd"]
        )
        needs_rating = cached is None or not (cached.get("lbxd") and cached["lbxd"].get("rating"))

        if cached is None or needs_rating or needs_fields:
            print(f"  [LB] {title}...", end=" ", flush=True)
            lb   = cached.get("lbxd") if cached else None
            omdb = cached.get("omdb") if cached else None
            if cached is None or needs_rating:
                lb   = lbxd_lookup(title, year, director=director)
                omdb = omdb_lookup(title, year, director=director)
            elif needs_fields:
                lb_new = lbxd_lookup(title, year, director=director)
                if lb_new:
                    lb = lb_new

            # Título original da programação do cinema — o Letterboxd indexa
            # por ele, por isso quando existe é a via mais directa e a que
            # acerta mais vezes. Só depois se tentam os caminhos indirectos.
            if orig_title and not (lb and lb.get("rating")):
                lb_o = lbxd_lookup(orig_title, year, director=director)
                if lb_o and lb_o.get("rating"):
                    lb = lb_o
                if not (omdb and omdb.get("Response") == "True"):
                    omdb_o = omdb_lookup(orig_title, year, director=director)
                    if omdb_o:
                        omdb = omdb_o

            # Resolução até ao IMDb ID (autocomplete do IMDb + filmografia do
            # realizador no Wikidata) e daí para a página exacta do Letterboxd
            # pelo redirect /imdb/{id}/. É isto que apanha os filmes listados
            # só com título português, que antes ficavam sempre sem nada.
            if not (lb and lb.get("rating")):
                imdb_id, omdb_i, why = resolve_imdb_id(
                    title, year, director=director,
                    original_title=orig_title, filmo_cache=filmo)
                if imdb_id:
                    if omdb_i and not (omdb and omdb.get("Response") == "True"):
                        omdb = omdb_i
                    try:
                        lb_i = lbxd_fetch_by_imdb(imdb_id)
                        if lb_i and (lb_i.get("rating") or lb_i.get("poster")):
                            lb = lb_i
                    except Exception:
                        pass
                    time.sleep(0.3)
                    if not (omdb and omdb.get("Response") == "True"):
                        try:
                            omdb_b = omdb_fetch_by_id(imdb_id)
                            if omdb_b and omdb_b.get("Response") == "True":
                                omdb = omdb_b
                        except Exception:
                            pass

            # Título só em português (retrospetivas, cinema de autor) — nem
            # o Letterboxd nem o OMDB indexam por título traduzido, por isso
            # sem isto ficavam sempre sem rating/descrição/título inglês.
            wiki = cached.get("wiki") if cached else None
            if not (lb and lb.get("rating")):
                wd = resolve_english_title(
                    title, year, director=director,
                    extra_titles=(orig_title, (lb or {}).get("lb_title")))
                if wd:
                    wiki = wd
                # Caminho mais fiável: IMDb ID (Wikidata) → redirect exato do
                # Letterboxd (/imdb/{id}/) — sem adivinhar slug nenhum.
                if wd and wd.get("imdb_id"):
                    try:
                        lb_i = lbxd_fetch_by_imdb(wd["imdb_id"])
                        # valida realizador e ano quando os conhecemos
                        d_ok = True
                        if director and lb_i.get("lb_director"):
                            exp = strip_accents(director.lower()).split()
                            d_ok = bool(exp) and exp[-1] in strip_accents(lb_i["lb_director"].lower())
                        if year and lb_i.get("lb_year") and abs(lb_i["lb_year"] - year) > 2:
                            d_ok = False
                        if d_ok and (lb_i.get("rating") or lb_i.get("poster")):
                            lb = lb_i
                    except Exception:
                        pass
                    time.sleep(0.4)
                # Fallback: tentar o slug a partir do título inglês resolvido
                if wd and wd.get("title_en") and not (lb and lb.get("rating")):
                    lb_wd = lbxd_lookup(wd["title_en"], year, director=director)
                    if lb_wd and lb_wd.get("rating"):
                        lb = lb_wd
                if wd and wd.get("title_en"):
                    if not lb:
                        lb = {"lb_title": wd["title_en"]}
                    elif not lb.get("lb_title"):
                        lb["lb_title"] = wd["title_en"]
                if wd and wd.get("imdb_id") and not (omdb and omdb.get("Response") == "True"):
                    try:
                        omdb_wd = omdb_fetch_by_id(wd["imdb_id"])
                        if omdb_wd and omdb_wd.get("Response") == "True":
                            omdb = omdb_wd
                    except Exception:
                        pass

            # Descrição em português para os filmes que o cinema não descreve.
            # O bloco acima só consulta a Wikipédia quando falta rating, por
            # isso um filme que resolvia logo no Letterboxd nunca chegava a
            # ser procurado e ficava para sempre só com a descrição inglesa —
            # era o caso de toda a programação do Cinema Ideal.
            if wiki is None and not cinema_plot_pt:
                wiki = resolve_english_title(
                    title, year, director=director,
                    extra_titles=(orig_title, (lb or {}).get("lb_title"),
                                  (omdb or {}).get("Title")))

            cache[key] = {"lbxd": lb, "omdb": omdb, "wiki": wiki, "cinema": meta}
            changed = True
            if lb and lb.get("rating"):
                print(f"★ {lb['rating']}/5", end="")
            else:
                print("sem rating", end="")
            print()
        else:
            lb   = cached.get("lbxd")
            omdb = cached.get("omdb")
            wiki = cached.get("wiki")
            # Filme já com rating mas nunca pesquisado na Wikipédia — uma
            # obtém a descrição em português (extract_pt) e o título inglês.
            # Um sucesso fica em cache para sempre. Uma falha é retentada nos
            # dias seguintes até 3 vezes — uma falha transitória (HTTP 429 da
            # Wikipédia) não pode condenar o filme a nunca mais ter descrição,
            # mas também não vale a pena repetir todos os dias para sempre um
            # filme que genuinamente não tem página na Wikipédia.
            tries = cached.get("wiki_tries", 0)
            if wiki is None and tries < 3:
                print(f"  [WIKI] {title}...", flush=True)
                wiki = resolve_english_title(
                    title, year, director=director,
                    extra_titles=(orig_title, (lb or {}).get("lb_title"),
                                  (omdb or {}).get("Title")))
                cached["wiki"] = wiki
                cached["wiki_tries"] = tries + 1
                changed = True

        # ── Aplicar dados ───────────────────────────────────────────
        # Remove posters que não são de filme (landscape, prints, stills, etc.)
        # Comparação case-insensitive para apanhar variantes de capitalização
        _BAD_POSTER = (
            "1920x1080", "1920%",
            "placeholder-2-i",
            "captura-de-ecra",          # cinematrindade + São Jorge print screens
            "withoutlettering",
            "noltettering",
            "cdn.bndlyr.com",           # Batalha cinema — só fornece stills landscape
        )
        if movie.get("poster"):
            p_lower = movie["poster"].lower()
            if any(s in p_lower for s in _BAD_POSTER):
                movie["poster"] = None

        # Poster: Letterboxd sempre (sobrepõe poster do scraper), fallback OMDB
        if lb and lb.get("poster"):
            movie["poster"] = lb["poster"]
        elif not movie.get("poster") and omdb and omdb.get("Poster") and omdb["Poster"] != "N/A":
            movie["poster"] = omdb["Poster"]

        # Rating Letterboxd (escala 0-5)
        if lb and lb.get("rating"):
            movie["rating"] = lb["rating"]

        # Ano: Letterboxd é mais fiável que o site do cinema (ex: URLs com anos errados)
        # Só substitui quando LB confirma realizador — já validado em lbxd_lookup
        if lb and lb.get("lb_year") and lb["lb_year"] != movie.get("year"):
            movie["year"] = lb["lb_year"]

        # Géneros: Letterboxd sempre (sobrepõe scraper/OMDB), fallback OMDB
        if lb and lb.get("genres"):
            movie["genres"] = lb["genres"]
        elif not movie.get("genres") and omdb and omdb.get("Genre") not in (None, "N/A"):
            movie["genres"] = [g.strip() for g in omdb["Genre"].split(",")][:3]

        # Descrição (inglês): Letterboxd sempre, fallback OMDB
        if lb and lb.get("description"):
            movie["plot"] = lb["description"]
        elif not movie.get("plot") and omdb and omdb.get("Plot") not in (None, "N/A"):
            movie["plot"] = omdb["Plot"]

        # Descrição (português): a sinopse da programação do cinema primeiro —
        # é escrita para este filme, em português de Portugal, e é a que o
        # espectador vê no site do cinema. A intro do artigo da Wikipédia PT
        # (já validada) só entra quando o cinema não publica sinopse.
        # Às vezes o campo da sinopse traz só uma citação de crítica ("O cinema
        # é Nicholas Ray" — Godard, no Johnny Guitar): curto de mais para
        # servir de descrição, e nesse caso a Wikipédia diz mais ao espectador.
        wiki_pt = (wiki or {}).get("extract_pt")
        if cinema_plot_pt and (len(cinema_plot_pt) >= 100 or not wiki_pt):
            movie["plot_pt"] = cinema_plot_pt
        elif wiki_pt:
            movie["plot_pt"] = wiki_pt

        # Título inglês (para a versão EN do site): Letterboxd primeiro (mais
        # fiável para cinema de autor/festival), fallback OMDB. Só grava se
        # for de facto diferente do título original — evita duplicar quando
        # o filme já está listado em inglês, ou "diferenças" que são só
        # pontuação (aspas curvas, ano acrescentado pelo OMDB, etc.).
        title_en = None
        if lb and lb.get("lb_title"):
            title_en = lb["lb_title"]
        elif omdb and omdb.get("Title") not in (None, "N/A"):
            title_en = omdb["Title"]
        elif wiki and wiki.get("title_en"):
            title_en = wiki["title_en"]
        if title_en:
            # Remove desambiguadores à Wikipédia tipo "(1969 film)", "(TV
            # series)" ou só "(1969)" — nunca fazem parte do título real,
            # são só a convenção de nomeação de artigos da Wikipédia.
            title_en = re.sub(r'\s*\((?:19|20)\d{2}(?:\s+\w+)*\)$', '', title_en)
            title_en = re.sub(r'\s*\(film\)$', '', title_en, flags=re.I).strip()
            title_slug = to_slug(title_en)
            orig_slug  = to_slug(movie.get("title", ""))
            # Não só rejeita quando é exatamente igual — rejeita também quando
            # o título resolvido já está contido no original (ex: título
            # scraped "In the Mood For Love — Disponível Para Amar" já mostra
            # o nome inglês; sobrepor com uma variante tipo "in the mood for
            # love" sem maiúsculas só piorava a apresentação).
            # Vários cinemas listam o filme como "título internacional —
            # subtítulo português" ("In the Mood For Love — Disponível Para
            # Amar"). Nesse caso a versão inglesa é só a parte de lá, com a
            # capitalização tal como o cinema a escreve.
            if title_slug and title_slug in orig_slug and title_slug != orig_slug:
                for part in re.split(r'\s+[—–\-:]\s+', movie.get("title", "")):
                    if to_slug(part) == title_slug:
                        title_en = part.strip()
                        orig_slug = ""      # deixa de ser redundante
                        break

            same = bool(title_slug) and (title_slug == orig_slug or title_slug in orig_slug)
            if title_en and not same:
                movie["title_en"] = title_en
            elif movie.get("title_en"):
                del movie["title_en"]

        # País: Letterboxd sempre, fallback OMDB
        if lb and lb.get("country"):
            movie["country"] = lb["country"]
        elif not movie.get("country") and omdb and omdb.get("Country") not in (None, "N/A"):
            movie["country"] = omdb["Country"].split(",")[0].strip()

        # Director Letterboxd slug (para página de realizador na app)
        if lb and lb.get("lb_director_slug") and not movie.get("director_lbxd_slug"):
            movie["director_lbxd_slug"] = lb["lb_director_slug"]

        # Metadados via OMDB (fallbacks apenas)
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

    if changed:
        save_cache(cache)
    save_filmo_cache(filmo)

    return movies


# ── Directors ──────────────────────────────────────────────────────────────────

WIKI_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "wiki_director_cache.json")

def load_wiki_cache():
    if os.path.exists(WIKI_CACHE_PATH):
        with open(WIKI_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_wiki_cache(cache):
    os.makedirs(os.path.dirname(WIKI_CACHE_PATH), exist_ok=True)
    with open(WIKI_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def wiki_director(name):
    """Fetches director photo + short bio from Wikipedia, with Wikidata fallback for missing photos."""
    params = urllib.parse.urlencode({
        "action":     "query",
        "titles":     name,
        "prop":       "pageimages|extracts",
        "exintro":    True,
        "explaintext": True,
        "exsentences": 3,
        "pithumbsize": 400,
        "format":     "json",
        "redirects":  1,
    })
    url = f"https://en.wikipedia.org/w/api.php?{params}"
    req = urllib.request.Request(url, headers=WIKI_HEADERS)
    # Uma corrida completa pede dezenas de realizadores seguidos e a Wikipédia
    # responde 429 a meio — sem esperar e tentar de novo, perdia-se a foto e a
    # bio de metade dos realizadores por uma razão puramente transitória.
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode())
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(20 * (attempt + 1))
                continue
            raise
    pages = data["query"]["pages"]
    page = next(iter(pages.values()))
    if page.get("ns") == -1:  # missing page
        photo, bio = None, None
    else:
        photo   = page.get("thumbnail", {}).get("source")
        extract = page.get("extract", "").strip()
        sentences = re.split(r'(?<=[.!?])\s+', extract)
        bio = " ".join(sentences[:3]).strip() or None

    # Fallback to Wikidata when Wikipedia has no photo
    if not photo:
        wd_photo, wd_bio = wikidata_director(name)
        if wd_photo:
            photo = wd_photo
        if not bio and wd_bio:
            bio = wd_bio

    return photo, bio


def _wiki_api(lang, params):
    url = f"https://{lang}.wikipedia.org/w/api.php?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=WIKI_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        # rate limit da Wikipédia — espera e tenta uma segunda vez em vez de
        # desistir do filme (uma corrida grande dispara isto com facilidade)
        if e.code == 429:
            time.sleep(15)
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        raise

def _extract_matches_film(extract, year, director):
    """Confirma que o artigo encontrado é mesmo sobre este filme — a pesquisa
    de texto livre da Wikipédia é tolerante o suficiente para às vezes trazer
    coisas completamente erradas (uma canção, um filme homónimo mais recente,
    um cantor...). Exige menção a "filme"/"film" e, quando sabemos o
    realizador, o apelido dele no excerto — sem isto aceitávamos matches
    errados com demasiada frequência.
    """
    e = (extract or "").lower()
    if "filme" not in e and "film" not in e:
        return False
    if director:
        dparts = strip_accents(director.lower()).split()
        last = dparts[-1] if dparts else ""
        return bool(last) and last in strip_accents(e)
    if year:
        return any(str(y) in e for y in (year, year - 1, year + 1))
    # Sem realizador nem ano para validar — não há como confirmar que é o
    # filme certo. Aceitar às cegas foi o que produziu o match "Tony Stark
    # (Marvel Cinematic Universe)" para uma oficina sem realizador atribuído.
    return False

def _wikidata_claims(wikidata_id):
    """Devolve {"imdb_id":..., "pub_year":...} do item Wikidata — o ano de
    publicação (P577) é um sinal estruturado muito mais fiável do que
    esperar que o excerto do artigo mencione o ano, e é o que apanha casos
    tipo "François Ozon" ter dois filmes em anos consecutivos (o texto
    livre + janela de ±1 ano deixava passar o filme errado)."""
    try:
        entity = _wiki_api_wikidata({
            "action": "wbgetentities", "ids": wikidata_id,
            "props": "claims", "format": "json",
        })
        claims = entity["entities"][wikidata_id].get("claims", {})
        imdb_id = None
        if "P345" in claims:
            imdb_id = claims["P345"][0]["mainsnak"]["datavalue"]["value"]
        pub_year = None
        if "P577" in claims:
            try:
                pub_year = int(claims["P577"][0]["mainsnak"]["datavalue"]["value"]["time"][1:5])
            except (KeyError, ValueError, TypeError):
                pass
        return {"imdb_id": imdb_id, "pub_year": pub_year}
    except Exception:
        return {"imdb_id": None, "pub_year": None}

def _wiki_api_wikidata(params):
    url = f"https://www.wikidata.org/w/api.php?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=WIKI_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def resolve_english_title(title, year=None, director=None, extra_titles=()):
    """Resolve um título só disponível em português (retrospetivas, cinema
    de autor) para o título internacional — o Letterboxd e o OMDB só
    indexam títulos originais/ingleses, por isso falham sempre que o
    scraper só tem o título traduzido e não há alias manual para ele.

    Usa a pesquisa de texto livre da Wikipédia em português (mais tolerante
    a títulos de distribuição do que a pesquisa por label exata do
    Wikidata, que falha para a maioria destes títulos) e confirma o match
    pelo excerto do artigo antes de aceitar o "langlink" inglês.
    Devolve {"title_en":..., "imdb_id":..., "extract_pt":...} ou None.
    O extract_pt serve de descrição em português (a do Letterboxd/OMDB é
    sempre em inglês).

    `extra_titles` são outras formas de nomear o mesmo filme (título
    original, título internacional). A Wikipédia portuguesa nem sempre
    arquiva o artigo pelo título de distribuição — "SOY CUBA" não é
    encontrado, "I Am Cuba" é —, por isso vale a pena tentar todas.
    """
    queries = [title] + [t for t in extra_titles if t and t != title]
    # Último recurso: título + realizador. A pesquisa por título sozinho falha
    # quando a Wikipédia portuguesa arquiva o filme pelo título original
    # ("A PISCINA" e "The Swimming Pool" não encontram nada, "A Piscina
    # Jacques Deray" traz "La piscine"), e o nome do realizador é o termo que
    # liga os dois.
    if director:
        queries.append(f"{title} {director}")
    for q in queries:
        found = _wiki_lookup_film(q, year, director)
        if found:
            return found
    return None


def _wiki_lookup_film(title, year=None, director=None):
    try:
        search = _wiki_api("pt", {
            "action": "query", "list": "search", "srsearch": title,
            "format": "json", "srlimit": 3,
        })
        hits = search.get("query", {}).get("search", [])
    except Exception:
        return None
    finally:
        time.sleep(0.4)

    for hit in hits:
        try:
            detail = _wiki_api("pt", {
                "action": "query", "titles": hit["title"], "format": "json",
                "prop": "langlinks|pageprops|extracts",
                "lllang": "en", "exintro": 1, "explaintext": 1, "exsentences": 4,
                "redirects": 1,
            })
        except Exception:
            continue
        finally:
            time.sleep(0.4)

        page = next(iter(detail.get("query", {}).get("pages", {}).values()), {})
        extract = page.get("extract")
        if not _extract_matches_film(extract, year, director):
            continue
        # Rejeita a página do próprio realizador (biografia) — acontece com
        # títulos tipo "Jane B. por Agnès V." em que o texto livre acerta
        # mais fácil na bio da Varda do que no artigo do filme.
        if director and to_slug(page.get("title", "")) == to_slug(director):
            continue

        title_en = next((ll["*"] for ll in page.get("langlinks", []) if ll["lang"] == "en"), None)
        if title_en:
            # Marcas de artigo/desambiguação nunca fazem parte do título real
            title_en = re.sub(r'^[@:•·\-\s]+', '', title_en).strip() or None

        imdb_id = None
        wikidata_id = page.get("pageprops", {}).get("wikibase_item")
        if wikidata_id:
            wd = _wikidata_claims(wikidata_id)
            time.sleep(0.2)
            # Data de publicação estruturada discorda do ano que já
            # sabíamos — rejeita mesmo que o realizador bata certo (caso
            # real: "O Estrangeiro" (Ozon, 2025) resolveu para "When Fall
            # Is Coming", outro filme do Ozon, mas de 2024). Tolerância de
            # ±1 ano porque os sites dos cinemas confundem frequentemente
            # ano de produção com ano de estreia (ex: Cléo de 5 à 7,
            # 1962, listado como 1961) — o realizador é revalidado depois
            # na própria página do Letterboxd.
            if year and wd["pub_year"] and abs(wd["pub_year"] - year) > 1:
                continue
            imdb_id = wd["imdb_id"]

        extract_pt = (extract or "").strip() or None
        if not (title_en or imdb_id or extract_pt):
            continue
        return {"title_en": title_en, "imdb_id": imdb_id, "extract_pt": extract_pt}

    return None


def wikidata_director(name):
    """Fetches director photo from Wikidata/Wikimedia Commons."""
    try:
        # Search Wikidata for the person
        search_params = urllib.parse.urlencode({
            "action": "wbsearchentities", "search": name,
            "language": "en", "type": "item", "format": "json", "limit": 3,
        })
        req = urllib.request.Request(
            f"https://www.wikidata.org/w/api.php?{search_params}",
            headers=WIKI_HEADERS,
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            results = json.loads(r.read()).get("search", [])

        # Find best match: label matches name (case-insensitive)
        entity_id = None
        for r in results:
            if r.get("label", "").lower() == name.lower():
                entity_id = r["id"]
                break
        if not entity_id and results:
            entity_id = results[0]["id"]
        if not entity_id:
            return None, None

        # Fetch entity claims
        entity_params = urllib.parse.urlencode({
            "action": "wbgetentities", "ids": entity_id,
            "props": "claims|descriptions", "languages": "en", "format": "json",
        })
        req = urllib.request.Request(
            f"https://www.wikidata.org/w/api.php?{entity_params}",
            headers=WIKI_HEADERS,
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            entity_data = json.loads(r.read())
        entity = entity_data["entities"][entity_id]
        claims = entity.get("claims", {})
        description = entity.get("descriptions", {}).get("en", {}).get("value")

        # P18 = image
        if "P18" not in claims:
            return None, description
        filename = claims["P18"][0]["mainsnak"]["datavalue"]["value"]

        # Resolve Commons URL via MediaWiki API
        img_params = urllib.parse.urlencode({
            "action": "query", "titles": f"File:{filename}",
            "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 400, "format": "json",
        })
        req = urllib.request.Request(
            f"https://commons.wikimedia.org/w/api.php?{img_params}",
            headers=WIKI_HEADERS,
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            img_data = json.loads(r.read())
        img_page = next(iter(img_data["query"]["pages"].values()))
        photo = img_page.get("imageinfo", [{}])[0].get("thumburl")
        return photo, description
    except Exception:
        return None, None

def build_directors(movies):
    """Builds directors dict from movies with director info. Fetches Wikipedia data."""
    wiki_cache = load_wiki_cache()
    wiki_changed = False

    directors = {}
    for movie in movies:
        director = movie.get("director")
        if not director:
            continue
        if director in directors:
            continue

        lbxd_slug = movie.get("director_lbxd_slug")

        # Retenta os que ficaram sem nada, até 3 dias. Antes, um erro de rede
        # gravava {photo: None, bio: None} para sempre e o realizador nunca
        # mais era pesquisado — um 429 apanhado numa manhã má era definitivo.
        prev  = wiki_cache.get(director)
        tries = (prev or {}).get("tries", 0)
        if prev is None or (not prev.get("photo") and not prev.get("bio") and tries < 3):
            print(f"  [Wiki] {director}...", end=" ", flush=True)
            try:
                photo, bio = wiki_director(director)
                wiki_cache[director] = {"photo": photo, "bio": bio, "tries": tries + 1}
                wiki_changed = True
                print("ok" if photo or bio else "not found")
            except Exception as e:
                print(f"err: {e}")
                wiki_cache[director] = {"photo": None, "bio": None, "tries": tries + 1}
                wiki_changed = True
            time.sleep(0.4)

        cached = wiki_cache[director]
        directors[director] = {
            "lbxd_slug": lbxd_slug,
            "photo":     cached.get("photo"),
            "bio":       cached.get("bio"),
        }

    if wiki_changed:
        save_wiki_cache(wiki_cache)

    return directors


if __name__ == "__main__":
    # Reprocessa data/sessions.js sozinho, sem correr os scrapers dos
    # cinemas — usado para reenriquecer filmes já existentes (ex: backfill
    # de rating/descrição/título inglês) sem tocar nas sessões em si.
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "sessions.js")
    with open(data_path, encoding="utf-8") as f:
        js = f.read()
    payload = json.loads(js.replace("window.CINEMA_DATA = ", "").rstrip(";"))
    payload["movies"] = enrich(payload["movies"])
    # Também reprocessa os realizadores: as fotos e biografias falham em bloco
    # quando a Wikipédia devolve 429 a meio de uma corrida grande, e sem isto
    # as corridas extra da manhã nunca as recuperavam.
    payload["directors"] = build_directors(payload["movies"])
    with open(data_path, "w", encoding="utf-8") as f:
        f.write("window.CINEMA_DATA = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";")
    n_dir = sum(1 for d in payload["directors"].values() if d.get("photo"))
    print(f"\n✓ sessions.js atualizado ({len(payload['movies'])} filmes, "
          f"{n_dir}/{len(payload['directors'])} realizadores com foto)")
