"""Blender Bridge (MCP, opcional) vista do Config Models: estado, instalacao com um
clique e abrir a pasta do addon. A instalacao faz o mesmo que blender-bridge/install.bat
(ambiente do servidor, .zip do addon, mcp-config.json) e registra nos clientes pedidos.
"""
import importlib.util
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import threading
import zipfile

PASTA = pathlib.Path(__file__).resolve().parent.parent / "blender-bridge"
SERVIDOR = PASTA / "server"
PYTHON = SERVIDOR / ".venv" / "Scripts" / "python.exe"
ZIP = PASTA / "blender_bridge_addon.zip"
CONEXAO = pathlib.Path.home() / ".blender_bridge" / "connection.json"
_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

ESTADO = {"instalando": False, "erro": "", "etapa": ""}
_trava = threading.Lock()


def _config():
    """O escrever_config.py da Bridge (so biblioteca padrao): clientes e registro."""
    spec = importlib.util.spec_from_file_location("bridge_config", SERVIDOR / "escrever_config.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _blender_ligado() -> bool:
    try:
        c = json.loads(CONEXAO.read_text(encoding="utf-8"))
        with socket.create_connection((c["host"], int(c["port"])), timeout=0.5):
            return True
    except (OSError, ValueError, KeyError):
        return False


def estado() -> dict:
    if not PASTA.is_dir():
        return {"disponivel": False}
    cfg = _config()
    return {"disponivel": True, "instalada": PYTHON.exists() and ZIP.exists(),
            "ffmpeg": shutil.which("ffmpeg") is not None, "blender": _blender_ligado(),
            "clientes": [{"nome": n, "registrado": cfg.registrado(a)} for n, a in cfg.clientes()],
            **ESTADO}


def _rodar(args, etapa):
    ESTADO["etapa"] = etapa
    r = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=900,
                       creationflags=_SEM_JANELA)
    if r.returncode:
        raise RuntimeError(f"{etapa}: {(r.stderr or r.stdout).strip()[-400:]}")


def _instalar(clientes: list[str]):
    try:
        if not PYTHON.exists():
            # sys._base_executable: o Python de verdade, nao o do .venv do app.
            _rodar([getattr(sys, "_base_executable", sys.executable), "-m", "venv",
                    str(SERVIDOR / ".venv")], "Creating the Python environment")
        _rodar([str(PYTHON), "-m", "pip", "install", "-q", "-r", str(SERVIDOR / "requirements.txt")],
               "Installing the server")
        ESTADO["etapa"] = "Packing the Blender add-on"
        with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
            for f in (PASTA / "addon" / "blender_bridge").rglob("*.py"):
                if "__pycache__" not in f.parts:
                    z.write(f, f.relative_to(PASTA / "addon"))
        _rodar([str(PYTHON), str(SERVIDOR / "escrever_config.py"), "--registrar", ",".join(clientes)],
               "Adding it to your AI app")
        ESTADO["erro"] = ""
    except Exception as e:  # mostrado no card; o usuario pode tentar de novo
        ESTADO["erro"] = str(e)
    finally:
        ESTADO["instalando"], ESTADO["etapa"] = False, ""


def instalar(clientes: list[str]) -> bool:
    """Comeca em segundo plano; False se ja estiver instalando."""
    with _trava:
        if ESTADO["instalando"]:
            return False
        ESTADO.update(instalando=True, erro="", etapa="Starting")
    threading.Thread(target=_instalar, args=(clientes,), daemon=True).start()
    return True


def abrir_pasta():
    os.startfile(PASTA)  # Explorer, na pasta com o .zip do addon e o README
