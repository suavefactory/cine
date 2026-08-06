"""Ponto focal de cada fotograma, para o site o enquadrar sem cortar caras.

O topo do modal é muito panorâmico e os fotogramas são 16:9, por isso sobra
imagem que tem de ser cortada. Cortar sempre pelo meio (ou sempre pelo topo)
decapita pessoas com frequência. Aqui procuram-se as caras e devolve-se a
altura onde o recorte as preserva, no formato que o CSS `object-position`
entende.

Sem caras — planos de paisagem, arquitectura, abstracções — cai-se numa
heurística de contraste: a faixa da imagem com mais detalhe é normalmente
onde está o assunto.

Tudo isto corre no scraper, uma vez por imagem, e fica em cache. O site
recebe só um número.
"""

import os
import urllib.request

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "models", "face_detection_yunet.onnx")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Sem análise possível, 38% fica acima do centro: nos fotogramas de cinema o
# olhar está quase sempre no terço superior.
DEFAULT_Y = 38.0

_detector = None


def _get_detector(size):
    global _detector
    try:
        import cv2
    except ImportError:
        return None
    if not os.path.exists(MODEL_PATH):
        return None
    if _detector is None:
        try:
            _detector = cv2.FaceDetectorYN.create(MODEL_PATH, "", size, 0.6, 0.3, 5000)
        except Exception:
            return None
    try:
        _detector.setInputSize(size)
    except Exception:
        return None
    return _detector


def _download(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _decode(data):
    import cv2, numpy as np
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _faces_center_y(img):
    """Percentagem vertical que mantém as caras dentro do recorte, ou None."""
    h, w = img.shape[:2]
    det = _get_detector((w, h))
    if det is None:
        return None
    try:
        _, faces = det.detect(img)
    except Exception:
        return None
    if faces is None or len(faces) == 0:
        return None
    # Enquadra o conjunto: do topo da cara mais alta à base da mais baixa, com
    # uma folga por cima para não rapar o cabelo.
    tops = [f[1] for f in faces]
    bots = [f[1] + f[3] for f in faces]
    top, bot = max(min(tops), 0), min(max(bots), h)
    margin = (bot - top) * 0.45
    centre = ((top - margin) + (bot + margin)) / 2
    return max(0.0, min(100.0, centre / h * 100))


def _contrast_center_y(img):
    """Sem caras: a faixa horizontal com mais detalhe costuma ter o assunto."""
    import cv2, numpy as np
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (5, 5), 0)
    energy = np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)).sum(axis=1)
    if energy.sum() <= 0:
        return None
    rows = np.arange(len(energy))
    return float((rows * energy).sum() / energy.sum() / len(energy) * 100)


def focus_from_image(img):
    """Como focus_y, mas para uma imagem já carregada — evita descarregar duas
    vezes quando quem chama já tem os pixels na mão."""
    if img is None or img.size == 0:
        return None
    y = _faces_center_y(img)
    if y is None:
        try:
            y = _contrast_center_y(img)
        except Exception:
            y = None
    if y is None:
        return None
    y = float(y) * 0.88
    return round(max(0.0, min(70.0, y)), 1)


def focus_y(url):
    """Percentagem vertical para `object-position`, ou None se não der."""
    try:
        img = _decode(_download(url))
    except Exception:
        return None
    if img is None or img.size == 0:
        return None
    y = _faces_center_y(img)
    if y is None:
        try:
            y = _contrast_center_y(img)
        except Exception:
            y = None
    if y is None:
        return None
    # Puxa ligeiramente para cima: o fundo da imagem desvanece no vidro, por
    # isso vale mais deixar o assunto acima do meio do que abaixo.
    y = float(y) * 0.88          # float nativo: numpy.float32 não serializa em JSON
    return round(max(0.0, min(70.0, y)), 1)


def focus_for(urls):
    """[percentagem, ...] alinhado com a lista de imagens dada."""
    return [focus_y(u) if u else None for u in (urls or [])]
