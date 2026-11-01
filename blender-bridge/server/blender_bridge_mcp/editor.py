"""Cliente HTTP do EasyComfee (FastAPI local, porta 8600; EDITOR_URL muda).

Só usa a API pública do app: as gerações passam pela fila dele, então
galeria, controle de VRAM e cancelamento continuam funcionando.
"""

import asyncio
import json
import os
import pathlib
import time

import httpx

BASE = os.environ.get("EDITOR_URL", "http://127.0.0.1:8600")
FIM = {"pronto", "erro"}


class EditorError(RuntimeError):
    pass


def _client(timeout=60.0):
    return httpx.AsyncClient(base_url=BASE, timeout=timeout)


async def _req(method, path, timeout=60.0, **kw):
    try:
        async with _client(timeout) as c:
            r = await c.request(method, path, **kw)
    except httpx.ConnectError:
        raise EditorError(
            f"EasyComfee is not answering at {BASE}. Open it from its shortcut "
            "(or start.bat) and try again.") from None
    if r.status_code >= 400:
        try:
            detalhe = r.json().get("detail", r.text)
        except ValueError:
            detalhe = r.text
        raise EditorError(f"EasyComfee answered {r.status_code} on {path}: {str(detalhe)[:800]}")
    return r


async def health():
    r = await _req("GET", "/api/saude", timeout=10)
    return r.json()


async def limits():
    """O que a máquina do Editor aguenta (GET /api/limites), ou None se o Editor
    for de uma versão sem esse endpoint."""
    try:
        r = await _req("GET", "/api/limites", timeout=15)
    except EditorError as e:
        if " 404 " in str(e):
            return None
        raise
    # Sem o endpoint, a rota curinga do Editor devolve o HTML do site com 200.
    if "json" not in r.headers.get("content-type", ""):
        return None
    return r.json()


async def upload(path):
    """Envia um arquivo para a pasta de entrada do motor; devolve o nome lá."""
    p = pathlib.Path(path)
    with p.open("rb") as f:
        r = await _req("POST", "/api/referencia", timeout=300,
                       files={"arquivo": (p.name, f, "application/octet-stream")})
    return r.json()["nome"]


async def generate(pedido):
    pedido = {"prompt": "", **pedido}
    r = await _req("POST", "/api/gerar", json=pedido, timeout=120)
    return r.json()


async def task(task_id):
    r = await _req("GET", "/api/tarefas", timeout=20)
    for t in r.json():
        if t.get("id") == task_id:
            return t
    raise EditorError(f"job {task_id} is not among the 50 most recent EasyComfee jobs")


async def wait(task_id, timeout=1800, poll=3.0):
    limite = time.monotonic() + timeout
    t = await task(task_id)
    while t.get("estado") not in FIM:
        if time.monotonic() > limite:
            return t
        await asyncio.sleep(poll)
        t = await task(task_id)
    return t


def results(t):
    """As saídas de uma tarefa: cada item é {"nome", "subpasta", "tipo"}."""
    out = []
    for item in t.get("imagens") or []:
        if isinstance(item, str):
            try:
                item = json.loads(item)
            except ValueError:
                item = {"nome": item}
        out.append(item)
    return out


async def download(item, dest_dir):
    dest = pathlib.Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    params = {"nome": item["nome"], "subpasta": item.get("subpasta", ""),
              "tipo": item.get("tipo", "output")}
    r = await _req("GET", "/api/imagem", params=params, timeout=600)
    alvo = dest / pathlib.Path(item["nome"]).name
    alvo.write_bytes(r.content)
    return str(alvo)


async def free_memory():
    r = await _req("POST", "/api/liberar-memoria", timeout=60)
    try:
        return r.json()
    except ValueError:
        return {"ok": True}
