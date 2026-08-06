"""Metadados lidos da própria página do filme no site do cinema.

A programação oficial é a melhor fonte que existe para dois campos que mais
nenhuma API dá bem:

  * o **título original**, que é o que o Letterboxd e o IMDb indexam — sem
    ele, um filme listado só com o título de distribuição português (todo o
    cinema de repertório: Varda, Visconti, Truffaut, Rohmer...) nunca é
    encontrado;
  * a **sinopse em português**, escrita pelo cinema, melhor do que um excerto
    de Wikipédia ou uma tradução automática.

Cada site tem o seu extractor. `fetch()` escolhe pelo domínio do link e nunca
levanta exceção — um cinema fora do ar não pode partir o enriquecimento todo.
"""

import urllib.request, urllib.parse
import json, re, html

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
}


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def _text(fragment):
    """HTML → texto corrido, com as tags de bloco a virar quebras de linha."""
    if not fragment:
        return None
    f = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", fragment)
    f = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", f)
    t = html.unescape(re.sub(r"<[^>]+>", "", f))
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{2,}", "\n", t).strip() or None


def _year(v):
    try:
        return int(str(v)[:4])
    except (TypeError, ValueError):
        return None


# ── medeiafilmes.com (Cinema Medeia Nimas) ────────────────────────────────────

def _medeia(url):
    """A Medeia serve a ficha completa como JSON embutido (`global.data`)."""
    htm = _get(url)
    m = re.search(r"global\.data\s*=\s*(\{)", htm)
    if not m:
        return None
    obj, _ = json.JSONDecoder().raw_decode(htm[m.start(1):])
    f = obj.get("film") or {}
    if not f:
        return None
    # A galeria do filme, quando existe: fotogramas 16:9 escolhidos pelo cinema
    stills = []
    for e in sorted(f.get("media") or [], key=lambda x: int(x.get("position") or 0)):
        name = (e.get("image_name") or "").strip()
        if name and int(e.get("image_width") or 0) > int(e.get("image_height") or 1):
            stills.append("https://medeiafilmes.com/uploads/library/" + urllib.parse.quote(name))
    return {
        "original_title": (f.get("title_original") or "").strip() or None,
        "plot_pt":  _text(f.get("text")),
        "country":  (f.get("country") or "").strip() or None,
        "genre":    (f.get("genre") or "").strip() or None,
        "year":     _year(f.get("production_year")),
        "director": (f.get("director_name") or "").strip() or None,
        "stills":   stills or None,
    }


# ── cinematrindade.pt ─────────────────────────────────────────────────────────

_TRINDADE_LABELS = {
    "título original": "original_title",
    "titulo original": "original_title",
    "países": "country",
    "paises": "country",
    "ano": "year",
}


def _trindade(url):
    """No Trindade o rótulo e o valor saem colados na mesma linha depois de
    tirar as tags ("Título OriginalDomicile Conjugal"), por isso o valor é o
    que sobra da linha depois do rótulo."""
    htm = _get(url)
    body = re.sub(r"(?is)<(script|style|svg|nav|header|footer)[^>]*>.*?</\1>", " ", htm)
    lines = [l.strip() for l in (_text(body) or "").split("\n") if l.strip()]
    out = {}
    for line in lines:
        low = line.lower()
        for label, key in _TRINDADE_LABELS.items():
            if low.startswith(label) and key not in out:
                val = line[len(label):].lstrip(": ").strip()
                if val:
                    out[key] = val
    if "year" in out:
        out["year"] = _year(out["year"])
    # A sinopse é o parágrafo longo que vem a seguir à ficha técnica
    longest = max(lines, key=len, default="")
    if len(longest) > 150:
        out["plot_pt"] = longest
    return out or None


# ── cinemateca.pt ─────────────────────────────────────────────────────────────

def _cinemateca(url):
    """A Cinemateca põe o título original entre parênteses ou num rótulo."""
    htm = _get(url)
    body = re.sub(r"(?is)<(script|style|svg|nav|header|footer)[^>]*>.*?</\1>", " ", htm)
    txt = _text(body) or ""
    out = {}
    m = re.search(r"(?im)^\s*t[íi]tulo\s+original\s*:?\s*(.+)$", txt)
    if m:
        out["original_title"] = m.group(1).strip()
    paras = [l.strip() for l in txt.split("\n") if len(l.strip()) > 200]
    if paras:
        out["plot_pt"] = max(paras, key=len)
    return out or None


HANDLERS = {
    "medeiafilmes.com":         _medeia,
    "www.medeiafilmes.com":     _medeia,
    "cinematrindade.pt":        _trindade,
    "www.cinematrindade.pt":    _trindade,
    "cinemateca.pt":            _cinemateca,
    "www.cinemateca.pt":        _cinemateca,
}


def fetch(link):
    """{original_title, plot_pt, country, year, ...} ou None. Nunca levanta."""
    if not link:
        return None
    fn = HANDLERS.get(urllib.parse.urlparse(link).netloc)
    if not fn:
        return None
    try:
        d = fn(link)
    except Exception:
        return None
    return {k: v for k, v in (d or {}).items() if v} or None
