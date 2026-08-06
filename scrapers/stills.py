"""Stills (fotogramas) de cada filme.

Fonte principal: TMDb, ligado pelo IMDb ID que o enricher já resolve — é uma
correspondência exacta, não há risco de trazer imagens do filme errado. Em
recurso, o backdrop do Letterboxd, que dá uma imagem em vez de nenhuma.

A chave do TMDb vem da variável de ambiente TMDB_API_KEY (secret no GitHub
Actions). Sem chave o módulo continua a funcionar, só fica limitado ao recurso.
"""

import urllib.request, urllib.parse
import json, os, re, time

TMDB_KEY  = os.environ.get("TMDB_API_KEY", "").strip()
TMDB_API  = "https://api.themoviedb.org/3"
TMDB_IMG  = "https://image.tmdb.org/t/p/w1280"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

N_STILLS = 3


def _get_json(url, timeout=12):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _tmdb_id(imdb_id):
    """IMDb ID -> TMDb ID. Correspondência exacta, sem pesquisa por título."""
    url = f"{TMDB_API}/find/{imdb_id}?external_source=imdb_id&api_key={TMDB_KEY}"
    data = _get_json(url)
    for bucket in ("movie_results", "tv_results"):
        if data.get(bucket):
            return data[bucket][0]["id"], ("movie" if bucket == "movie_results" else "tv")
    return None, None


def _score(img):
    """Ordena os candidatos: imagens sem texto sobreposto primeiro (iso_639_1
    nulo quer dizer que a imagem não tem legendas nem título gravado), depois
    as mais votadas, depois as de maior resolução."""
    return (
        0 if img.get("iso_639_1") in (None, "", "xx") else 1,
        -(img.get("vote_average") or 0),
        -(img.get("width") or 0),
    )


def from_tmdb(imdb_id, n=N_STILLS):
    """Até n stills 16:9 do TMDb, ou [] se não houver chave ou resultados."""
    if not (TMDB_KEY and imdb_id):
        return []
    try:
        tid, kind = _tmdb_id(imdb_id)
        if not tid:
            return []
        time.sleep(0.15)
        data = _get_json(f"{TMDB_API}/{kind}/{tid}/images?api_key={TMDB_KEY}")
    except Exception:
        return []
    imgs = [b for b in (data.get("backdrops") or []) if b.get("file_path")]
    # Descarta imagens estreitas: um still tem de encher a largura da galeria
    imgs = [b for b in imgs if (b.get("aspect_ratio") or 0) >= 1.5]
    imgs.sort(key=_score)
    return [TMDB_IMG + b["file_path"] for b in imgs[:n]]


def collect(imdb_id=None, cinema_stills=(), letterboxd_backdrop=None, n=N_STILLS):
    """Junta as fontes por ordem de qualidade, sem repetir, até n imagens.

    TMDb primeiro (é a única que dá três fotogramas verdadeiros), depois a
    galeria do próprio cinema, e por fim o backdrop do Letterboxd — uma
    imagem vale mais do que um espaço vazio.
    """
    out = []
    candidates = list(from_tmdb(imdb_id, n)) + list(cinema_stills or ())
    if letterboxd_backdrop:
        candidates.append(letterboxd_backdrop)
    for url in candidates:
        if url and url not in out:
            out.append(url)
        if len(out) >= n:
            break
    return out
