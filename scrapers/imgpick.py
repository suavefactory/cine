"""Escolhe os fotogramas que vão para o site.

O TMDb mistura, na mesma lista, fotogramas do filme e arte promocional — o
poster esticado, cartazes sem o texto, montagens de divulgação. E a mesma
imagem aparece por vezes duas vezes, com recortes ligeiramente diferentes.
Aqui filtram-se as duas coisas e escolhem-se n imagens distintas.

Como se distingue arte de fotograma: comparando a paleta com a do poster do
filme. A arte promocional partilha a paleta com o poster (o cartaz do "I Want
Your Sex" e o "fotograma" que é esse cartaz sem o título dão correlação 0.82);
um fotograma verdadeiro do mesmo filme fica abaixo de 0.25.

Como se detectam repetidos: por hash perceptual — duas imagens visualmente
iguais dão hashes a poucos bits de distância, mesmo com recortes diferentes.
"""

import urllib.request

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# A arte tem de se destacar das outras candidatas por esta margem, e nunca
# é acusada abaixo do mínimo absoluto. Comparar com um limiar fixo não chega:
# num filme a preto e branco todas as imagens partilham a paleta do poster
# (0.98 e mais), e um limiar fixo deitava fora o filme inteiro.
POSTER_MIN = 0.70
POSTER_MARGIN = 0.35
# Abaixo disto (em bits de diferença) duas imagens são a mesma.
DUPLICATE_DISTANCE = 8


def _load(url, timeout=20):
    try:
        import cv2, numpy as np
    except ImportError:
        return None
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None
    return img if img is not None and img.size else None


def _palette(img):
    """Histograma de matiz e saturação — o que a arte partilha com o poster."""
    import cv2
    small = cv2.resize(img, (128, 128), interpolation=cv2.INTER_AREA)
    h = cv2.calcHist([cv2.cvtColor(small, cv2.COLOR_BGR2HSV)], [0, 1], None,
                     [32, 32], [0, 180, 0, 256])
    return cv2.normalize(h, h).flatten()


def _palette_similarity(a, b):
    import cv2
    return float(cv2.compareHist(a, b, cv2.HISTCMP_CORREL))


def _phash(img, size=8):
    """Hash perceptual: sobrevive a recortes e mudanças de tamanho."""
    import cv2
    g = cv2.cvtColor(cv2.resize(img, (size + 1, size), interpolation=cv2.INTER_AREA),
                     cv2.COLOR_BGR2GRAY)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v


def _distance(a, b):
    return bin(a ^ b).count("1")


def pick(candidates, poster_url=None, n=3, focus=True, examine=8):
    """[(url, ponto_focal), ...] — até n fotogramas distintos e sem arte.

    Se não houver opencv, devolve os primeiros n candidatos sem análise: mais
    vale mostrar imagens sem filtrar do que não mostrar nada.
    """
    candidates = [u for u in (candidates or []) if u]
    try:
        import cv2  # noqa: F401
    except ImportError:
        return [(u, None) for u in candidates[:n]]

    imgs = []
    for url in candidates[:examine]:
        img = _load(url)
        if img is not None:
            imgs.append((url, img))
    if not imgs:
        return []

    # Quanto cada candidata se parece com o poster. O que interessa não é o
    # valor absoluto mas o destaque: a arte salta à vista no meio das outras.
    rejeitar = set()
    if poster_url:
        p = _load(poster_url)
        if p is not None and len(imgs) >= 2:
            pal = _palette(p)
            sims = [_palette_similarity(pal, _palette(im)) for _, im in imgs]
            ordenadas = sorted(sims)
            mediana = ordenadas[len(ordenadas) // 2]
            limiar = max(POSTER_MIN, mediana + POSTER_MARGIN)
            rejeitar = {i for i, v in enumerate(sims) if v > limiar}

    chosen, hashes = [], []
    for i, (url, img) in enumerate(imgs):
        if len(chosen) >= n:
            break
        if i in rejeitar:
            continue
        h = _phash(img)
        if any(_distance(h, prev) <= DUPLICATE_DISTANCE for prev in hashes):
            continue
        hashes.append(h)
        y = None
        if focus:
            try:
                import focal
                y = focal.focus_from_image(img)
            except Exception:
                y = None
        chosen.append((url, y))

    # Se o filtro deixou o filme a seco, vale mais mostrar o que há do que
    # nada — repõem-se as descartadas pela semelhança com o poster.
    if len(chosen) < n:
        for i, (url, img) in enumerate(imgs):
            if len(chosen) >= n:
                break
            if url in {u for u, _ in chosen}:
                continue
            h = _phash(img)
            if any(_distance(h, prev) <= DUPLICATE_DISTANCE for prev in hashes):
                continue
            hashes.append(h)
            y = None
            if focus:
                try:
                    import focal
                    y = focal.focus_from_image(img)
                except Exception:
                    y = None
            chosen.append((url, y))
    return chosen
