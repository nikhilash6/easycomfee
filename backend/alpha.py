"""Tirar o fundo (LTX-2.5 IC-LoRA Alpha Gen): junta o video original com a mascara
gerada (branco = primeiro plano) num video com transparencia.

A mascara sai no tamanho e na duracao que o efeito usou: o original passa pelo mesmo
caminho (24 fps, escala ate cobrir e corte no centro, os primeiros N quadros), senao
o alfa nao cai em cima do objeto.

Ajustes do recorte (os de um keyer), aplicados so na mascara e sem gerar de novo:
borda para dentro/fora, suavizar a borda, ponto preto/branco, media entre quadros e
inverter.
"""
import hashlib
import json
import pathlib
import subprocess
from dataclasses import asdict, dataclass

_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# WebM VP9 com alfa abre no navegador (previa sobre xadrez) e no After Effects/Premiere;
# ProRes 4444 e o que os editores esperam para compor.
_CODECS = {
    "webm": ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "28",
             "-auto-alt-ref", "0", "-row-mt", "1"],
    "mov": ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
            "-alpha_bits", "16"],
}


@dataclass(frozen=True)
class Ajustes:
    borda: int = 0        # px: negativo encolhe o recorte (choke), positivo aumenta
    suavizar: float = 0   # px de desfoque na borda (feather)
    preto: float = 0.0    # abaixo disto vira transparente (0-1)
    branco: float = 1.0   # acima disto vira solido (0-1)
    tempo: int = 0        # quadros de cada lado na media (tira o tremido da borda)
    inverter: bool = False

    def neutro(self) -> bool:
        return self == Ajustes()

    def filtro(self) -> str:
        """Cadeia do ffmpeg para a mascara (ja em cinza)."""
        f = []
        if self.tempo:
            f.append(f"tmix=frames={2 * self.tempo + 1}")
        if self.preto > 0 or self.branco < 1:
            p, b = round(self.preto * 255), round(self.branco * 255)
            f.append(f"lut=y='clip((val-{p})*255/{max(1, b - p)},0,255)'")
        f += ["erosion" if self.borda < 0 else "dilation"] * abs(self.borda)
        if self.suavizar:
            f.append(f"gblur=sigma={self.suavizar}")
        if self.inverter:
            f.append("negate")
        return ",".join(f)


def _medir(video: str) -> tuple[int, int, int]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                        "-show_entries", "stream=width,height,nb_read_frames", "-of", "json", video],
                       capture_output=True, text=True, timeout=120, creationflags=_SEM_JANELA)
    s = json.loads(r.stdout)["streams"][0]
    return int(s["width"]), int(s["height"]), int(s["nb_read_frames"])


def nome_saida(base: pathlib.Path, formato: str, ajustes: Ajustes) -> pathlib.Path:
    """Um arquivo por combinacao de ajustes: mexer num controle nao apaga o anterior."""
    if ajustes.neutro():
        return base.with_suffix(f".{formato}")
    marca = hashlib.sha1(json.dumps(asdict(ajustes), sort_keys=True).encode()).hexdigest()[:8]
    return base.with_name(f"{base.name}_{marca}.{formato}")


def compor(original: str, mascara: str, saida: pathlib.Path, formato: str = "webm",
           ajustes: Ajustes = Ajustes()) -> pathlib.Path:
    """Escreve `saida` (uma vez; depois so devolve o que ja existe)."""
    if saida.exists() and saida.stat().st_size > 0:
        return saida
    largura, altura, quadros = _medir(mascara)
    extra = ajustes.filtro()
    filtro = (f"[0:v]fps=24,scale={largura}:{altura}:force_original_aspect_ratio=increase:flags=lanczos,"
              f"crop={largura}:{altura},setsar=1[cor];"
              f"[1:v]format=gray,scale={largura}:{altura},setsar=1{',' + extra if extra else ''}[a];"
              "[cor][a]alphamerge")
    tmp = saida.with_suffix(".parcial" + saida.suffix)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", original, "-i", mascara,
                        "-filter_complex", filtro, "-frames:v", str(quadros), "-an",
                        *_CODECS[formato], str(tmp)],
                       capture_output=True, text=True, timeout=900, creationflags=_SEM_JANELA)
    if r.returncode:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(r.stderr.strip()[-300:])
    tmp.replace(saida)
    return saida
