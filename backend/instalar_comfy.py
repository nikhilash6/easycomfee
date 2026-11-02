"""Instala o ComfyUI portatil oficial dentro da pasta do EasyComfee.

Chamado pelo detectar_comfy.py quando o computador nao tem ComfyUI. Baixa o
pacote portatil do release oficial (Comfy-Org/ComfyUI, versao FIXA: a que os
workflows do app foram testados), confere o sha256 publicado pela Comfy,
descompacta com o tar do proprio Windows (le .7z, sem 7-Zip) e devolve a pasta.
So biblioteca padrao: roda com o Python do sistema, antes do .venv existir.

O pacote sai pela placa: NVIDIA (CUDA 13 ou, com driver antigo, CUDA 12.6),
AMD ou Intel. Sem placa dedicada nao instala: a Comfy Cloud e o caminho.
"""
import hashlib
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.request

VERSAO = "v0.37.0"
BASE = f"https://github.com/Comfy-Org/ComfyUI/releases/download/{VERSAO}/"
# sha256 publicados no release (api.github.com/repos/Comfy-Org/ComfyUI/releases/tags/v0.37.0).
PACOTES = {
    "nvidia": ("ComfyUI_windows_portable_nvidia.7z", "7805f634fab51f63a238aaf0cfe2a9833bb7c86ddfc8400a60919f44460d7d65"),
    "nvidia_cu126": ("ComfyUI_windows_portable_nvidia_cu126.7z", "4f8c587c8319a3595dcdc6b8fbfc7234d2d02fa6b1a328c1ab3e819c97d95fb8"),
    "amd": ("ComfyUI_windows_portable_amd.7z", "563da2462a866f8fdf8ccd091a8c0e185e785394408735f8e99647593a67dd79"),
    "intel": ("ComfyUI_windows_portable_intel.7z", "1041af3a25ca2c7b3615db3027ca0fd40df37c1758c4e9955e762672193ac4cc"),
}
RAIZ = pathlib.Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "ComfyUI"           # ComfyUI\ComfyUI_windows_portable\ComfyUI\main.py
TAR = pathlib.Path(r"C:\Windows\System32\tar.exe")


def _placa() -> str | None:
    """nvidia | nvidia_cu126 | amd | intel | None, pelo nvidia-smi e pelo Windows."""
    try:
        r = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            # Driver 610+ escreve "CUDA UMD Version: 13.3" em vez de "CUDA Version: 13.3"
            # (01/11/2026): sem achar o texto, o pacote cu126 vinha para uma RTX 50, que ele
            # nao roda. Sem nenhum dos dois, vale o numero do driver (CUDA 13 pede o 580+).
            m = re.search(r"CUDA (?:UMD )?Version:\s*(\d+)", r.stdout)
            if m:
                return "nvidia" if int(m.group(1)) >= 13 else "nvidia_cu126"
            m = re.search(r"Driver Version:\s*(\d+)|NVIDIA-SMI\s+(\d+)", r.stdout)
            versao = int(next(g for g in m.groups() if g)) if m else 0
            return "nvidia" if versao >= 580 else "nvidia_cu126"
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "(Get-CimInstance Win32_VideoController).Name -join ';'"],
                           capture_output=True, text=True, timeout=20)
        nomes = r.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        nomes = ""
    if "radeon" in nomes or "amd" in nomes:
        return "amd"
    if "arc" in nomes and "intel" in nomes:
        return "intel"
    return None


def _baixar(url: str, arquivo: pathlib.Path, sha: str) -> None:
    parcial = arquivo.with_suffix(arquivo.suffix + ".parcial")
    h = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=60) as r, open(parcial, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        feito, ultimo = 0, -1
        while bloco := r.read(1 << 20):
            f.write(bloco); h.update(bloco); feito += len(bloco)
            pct = feito * 100 // total if total else 0
            if pct != ultimo:
                ultimo = pct
                print(f"\r  Downloading ComfyUI: {pct:3d}%  ({feito / 1e9:.2f} of {total / 1e9:.2f} GB)", end="", flush=True)
    print()
    if h.hexdigest() != sha:
        parcial.unlink(missing_ok=True)
        raise RuntimeError("The download is damaged (checksum does not match). Run install.bat again.")
    parcial.replace(arquivo)


def instalar() -> pathlib.Path | None:
    """Baixa e descompacta o ComfyUI portatil. Devolve a pasta com main.py, ou None."""
    placa = _placa()
    if placa is None:
        print("\nNo NVIDIA, AMD or Intel Arc graphics card found, so ComfyUI can't run on this computer.\n"
              "You can still use EasyComfee with Comfy Cloud: open Config Models > Comfy Cloud API.")
        return None
    nome, sha = PACOTES[placa]
    pronto = DESTINO / "ComfyUI_windows_portable" / "ComfyUI"
    if (pronto / "main.py").is_file():
        print(f"ComfyUI is already installed in {pronto}")
        return pronto
    livre = shutil.disk_usage(RAIZ).free / 1e9
    if livre < 8:
        print(f"\nNot enough free disk space to install ComfyUI here ({livre:.1f} GB free, about 8 GB needed).")
        return None
    DESTINO.mkdir(exist_ok=True)
    arquivo = DESTINO / nome
    print(f"\nInstalling ComfyUI {VERSAO} for {placa.split('_')[0].upper()} (about 2 GB, a few minutes)...")
    if not arquivo.is_file():
        _baixar(BASE + nome, arquivo, sha)
    print("  Unpacking (this takes a minute or two)...")
    r = subprocess.run([str(TAR), "-xf", str(arquivo), "-C", str(DESTINO)], capture_output=True, text=True)
    if r.returncode != 0 or not (pronto / "main.py").is_file():
        raise RuntimeError("Could not unpack ComfyUI: " + (r.stderr.strip()[:300] or "unknown error"))
    arquivo.unlink(missing_ok=True)  # o .7z ja foi descompactado: libera ~2 GB
    print(f"  ComfyUI installed in {pronto}")
    return pronto


if __name__ == "__main__":
    print(instalar())
