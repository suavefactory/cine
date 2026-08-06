"""Stills (fotogramas) de cada filme.

O caminho é sempre o mesmo: IMDb ID -> TMDb ID -> imagens do TMDb. O IMDb ID
vem do enricher, que já o resolve para quase todos os filmes, por isso a
correspondência é exacta e nunca traz imagens do filme errado.

A ponte IMDb -> TMDb vem do Wikidata (propriedade P4947), consultada em lote:
uma consulta resolve o catálogo inteiro. Com TMDB_API_KEY definida usa-se a
API oficial, que traz metadados para escolher as melhores imagens; sem chave
lê-se a página pública de backdrops, que serve o mesmo conteúdo.

Em último recurso fica a galeria do cinema e o backdrop do Letterboxd.
"""

import urllib.request, urllib.parse
import json, os, re, time

TMDB_KEY = os.environ.get("TMDB_API_KEY", "").strip()
TMDB_API = "https://api.themoviedb.org/3"
TMDB_WEB = "https://www.themoviedb.org"
TMDB_IMG = "https://image.tmdb.org/t/p/w1280"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
WD_HEADERS = {
    "User-Agent": "sesh.pt/1.0 (https://sesh.pt; ruipedrosimoes14@gmail.com)",
    "Accept": "application/sparql-results+json",
}

N_STILLS = 3


def _fetch(url, headers=HEADERS, timeout=25):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


# ── IMDb ID → TMDb ID, em lote pelo Wikidata ──────────────────────────────────

def tmdb_ids_for(imdb_ids, chunk=180):
    """{imdb_id: tmdb_id} para os que o Wikidata conhece.

    Em lote porque uma consulta SPARQL resolve centenas de filmes de uma vez —
    fazer uma por filme seria lento e mal-educado para com o serviço.
    """
    out = {}
    ids = [i for i in dict.fromkeys(imdb_ids) if i and i.startswith("tt")]
    for i in range(0, len(ids), chunk):
        batch = ids[i:i + chunk]
        values = " ".join(f'"{x}"' for x in batch)
        query = (f"SELECT ?imdb ?tmdb WHERE {{ VALUES ?imdb {{ {values} }} "
                 f"?f wdt:P345 ?imdb ; wdt:P4947 ?tmdb . }}")
        url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(query)
        try:
            rows = json.loads(_fetch(url, headers=WD_HEADERS, timeout=90))["results"]["bindings"]
        except Exception:
            continue
        for b in rows:
            out.setdefault(b["imdb"]["value"], b["tmdb"]["value"])
        time.sleep(0.5)
    return out


def _tmdb_id_via_api(imdb_id):
    """Recurso quando o Wikidata não conhece o filme (só com chave)."""
    if not TMDB_KEY:
        return None
    try:
        data = json.loads(_fetch(
            f"{TMDB_API}/find/{imdb_id}?external_source=imdb_id&api_key={TMDB_KEY}"))
    except Exception:
        return None
    for bucket in ("movie_results", "tv_results"):
        if data.get(bucket):
            return str(data[bucket][0]["id"])
    return None


# ── TMDb ID → imagens ─────────────────────────────────────────────────────────

def _score(img):
    """Sem texto sobreposto primeiro (iso_639_1 nulo), depois mais votadas."""
    return (
        0 if img.get("iso_639_1") in (None, "", "xx") else 1,
        -(img.get("vote_average") or 0),
        -(img.get("width") or 0),
    )


def _images_via_api(tmdb_id, n):
    try:
        data = json.loads(_fetch(f"{TMDB_API}/movie/{tmdb_id}/images?api_key={TMDB_KEY}"))
    except Exception:
        return []
    imgs = [b for b in (data.get("backdrops") or [])
            if b.get("file_path") and (b.get("aspect_ratio") or 0) >= 1.5]
    imgs.sort(key=_score)
    return [TMDB_IMG + b["file_path"] for b in imgs[:n]]


_WEB_IMG_RE = re.compile(r"https://image\.tmdb\.org/t/p/original/([A-Za-z0-9]+\.jpg)")


def _images_via_web(tmdb_id, n):
    """Página pública de backdrops — mesma ordem de qualidade que a API."""
    for kind in ("movie", "tv"):
        try:
            html = _fetch(f"{TMDB_WEB}/{kind}/{tmdb_id}/images/backdrops")
        except Exception:
            continue
        files = list(dict.fromkeys(_WEB_IMG_RE.findall(html)))
        if files:
            return [f"{TMDB_IMG}/{f}" for f in files[:n]]
    return []


def from_tmdb(tmdb_id, n=N_STILLS):
    if not tmdb_id:
        return []
    if TMDB_KEY:
        got = _images_via_api(tmdb_id, n)
        if got:
            return got
    return _images_via_web(tmdb_id, n)


# ── Junta tudo ────────────────────────────────────────────────────────────────

def collect(tmdb_id=None, cinema_stills=(), letterboxd_backdrop=None, n=N_STILLS):
    """Até n imagens, da melhor fonte para a pior, sem repetidos."""
    out = []
    candidates = list(from_tmdb(tmdb_id, n)) + list(cinema_stills or ())
    if letterboxd_backdrop:
        candidates.append(letterboxd_backdrop)
    for url in candidates:
        if url and url not in out:
            out.append(url)
        if len(out) >= n:
            break
    return out
