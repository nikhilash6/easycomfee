"""Safe mode: ligado por padrao. Duas camadas:

1. Texto: o prompt com termos explicitos nem chega ao motor (`checar_prompt`).
2. Imagem: cada arquivo gerado passa por um classificador pequeno (ViT, ONNX,
   ~87 MB, roda no processador). O que der NSFW e servido borrado pela
   /api/imagem e pela /api/miniatura; o arquivo no disco nao muda.

Desligar e escolha de quem usa (Config Models), por conta e risco dele: os
modelos de pesos abertos nao tem filtro proprio.
"""
import io
import json
import logging
import pathlib
import re
import subprocess
import tempfile
import threading

import numpy as np

import config
from PIL import Image, ImageDraw, ImageFilter

log = logging.getLogger(__name__)

PASTA = pathlib.Path(__file__).parent / "modelos_seguro"
MODELO = PASTA / "nsfw_image_detection_int8.onnx"
# Falconsai/nsfw_image_detection (Apache-2.0) convertido pela onnx-community.
URL_MODELO = "https://huggingface.co/onnx-community/nsfw_image_detection-ONNX/resolve/main/onnx/model_quantized.onnx"
CACHE = PASTA / "classificacoes.json"
LIMIAR = 0.6

# Termos explicitos (ingles e portugues). Palavra inteira, sem acento importa.
_TERMOS = [
    "nude", "nudes", "nudity", "naked", "nsfw", "porn", "porno", "pornographic", "pornography", "hentai", "explicit sex",
    "sex scene", "having sex", "sexual intercourse", "intercourse", "topless", "bottomless", "nipples", "nipple", "genitals",
    "genitalia", "penis", "vagina", "vulva", "erection", "orgasm", "masturbat\\w*", "blowjob", "fellatio", "cunnilingus",
    "lingerie only", "undressed", "no clothes", "without clothes", "strip tease", "striptease", "xxx", "fetish", "bdsm",
    "onlyfans", "boobs", "tits", "pussy",
    "nua", "nuas", "pelada", "peladas", "pelado", "pelados", "nudez", "sexo", "transando", "pornografia",
    "seios", "mamilos", "mamilo", "pênis", "penis", "vagina", "buceta", "pau duro", "sem roupa", "sem roupas", "de calcinha",
]
_RE = re.compile(r"\b(" + "|".join(_TERMOS) + r")\b", re.IGNORECASE)

NEGATIVO = "nudity, nude, naked, nipples, genitals, sexual content, nsfw"

_trava = threading.Lock()
_sessao = None
_cache: dict[str, float] | None = None


def checar_prompt(*textos: str) -> str | None:
    """Devolve o termo bloqueado, ou None se o texto passa."""
    for t in textos:
        m = _RE.search(t or "")
        if m:
            return m.group(0)
    return None


def _ler_cache() -> dict[str, float]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _gravar_cache() -> None:
    PASTA.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(_ler_cache()), encoding="utf-8")


def _carregar():
    global _sessao
    if _sessao is not None:
        return _sessao
    import onnxruntime as ort
    if not MODELO.exists():
        import httpx
        PASTA.mkdir(exist_ok=True)
        tmp = MODELO.with_suffix(".part")
        with httpx.stream("GET", URL_MODELO, follow_redirects=True, timeout=120, verify=config.ssl_sistema()) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for parte in r.iter_bytes(1 << 20):
                    f.write(parte)
        tmp.replace(MODELO)
    _sessao = ort.InferenceSession(str(MODELO), providers=["CPUExecutionProvider"])
    return _sessao


def _nota_imagens(imagens: list[Image.Image]) -> float:
    s = _carregar()
    lote = np.stack([(np.asarray(i.convert("RGB").resize((224, 224), Image.BILINEAR), dtype=np.float32) / 255 - .5) / .5
                     for i in imagens]).transpose(0, 3, 1, 2)
    logits = s.run(None, {s.get_inputs()[0].name: lote})[0]
    e = np.exp(logits - logits.max(axis=1, keepdims=True))
    return float((e[:, 1] / e.sum(axis=1)).max())


def _quadros_video(dados: bytes, nome: str) -> list[Image.Image]:
    with tempfile.TemporaryDirectory() as d:
        arq = pathlib.Path(d) / pathlib.Path(nome).name
        arq.write_bytes(dados)
        out = pathlib.Path(d) / "q%02d.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(arq), "-vf", "fps=1,scale=320:-2", "-frames:v", "8", str(out)],
                       check=False, timeout=60)
        return [Image.open(p).copy() for p in sorted(pathlib.Path(d).glob("q*.jpg"))]


def nota(dados: bytes, nome: str, chave: str) -> float:
    """Probabilidade de NSFW (0-1), guardada por arquivo. Falha = 0 (nao bloqueia o app)."""
    c = _ler_cache()
    if chave in c:
        return c[chave]
    with _trava:
        if chave in c:
            return c[chave]
        try:
            ext = pathlib.Path(nome).suffix.lower()
            if ext in (".mp4", ".webm", ".mov", ".gif"):
                quadros = _quadros_video(dados, nome)
                v = _nota_imagens(quadros) if quadros else 0.0
            elif ext in (".png", ".jpg", ".jpeg", ".webp"):
                v = _nota_imagens([Image.open(io.BytesIO(dados))])
            else:
                return 0.0
        except Exception as e:  # sem internet para baixar o modelo, arquivo estranho...
            log.warning("safe mode: nao classificou %s: %s", nome, e)
            return 0.0
        c[chave] = round(v, 4)
        _gravar_cache()
        return c[chave]


def oculto(dados: bytes, nome: str, chave: str) -> bool:
    return nota(dados, nome, chave) >= LIMIAR


def borrar_imagem(dados: bytes) -> bytes:
    img = Image.open(io.BytesIO(dados)).convert("RGB")
    lado = max(img.size)
    img = img.resize((max(1, img.width * 64 // lado), max(1, img.height * 64 // lado))).resize(img.size, Image.BILINEAR)
    img = img.filter(ImageFilter.GaussianBlur(max(8, lado // 60)))
    d = ImageDraw.Draw(img)
    texto = "Hidden by Safe mode"
    l, t, r, b = d.textbbox((0, 0), texto, font_size=max(14, lado // 28))
    x, y = (img.width - (r - l)) // 2, (img.height - (b - t)) // 2
    d.rounded_rectangle((x - 16, y - 10, x + (r - l) + 16, y + (b - t) + 14), radius=12, fill=(15, 11, 18))
    d.text((x, y), texto, fill=(242, 255, 61), font_size=max(14, lado // 28))
    saida = io.BytesIO()
    img.save(saida, "PNG")
    return saida.getvalue()


def borrar_video(dados: bytes, nome: str) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        ent = pathlib.Path(d) / ("e" + pathlib.Path(nome).suffix)
        sai = pathlib.Path(d) / "s.mp4"
        ent.write_bytes(dados)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(ent), "-vf", "scale=iw/16:-2,scale=iw*16:-2:flags=neighbor,boxblur=20:2,scale=trunc(iw/2)*2:trunc(ih/2)*2",
                        "-an", "-c:v", "libx264", "-crf", "30", "-pix_fmt", "yuv420p", str(sai)], check=True, timeout=300)
        return sai.read_bytes()
