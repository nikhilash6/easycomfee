"""GET /api/limites: o teto do 3D render que a Blender Bridge (MCP) le."""
import asyncio
import pathlib
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import app as A  # noqa: E402
import maquina  # noqa: E402


def _pedir(vram):
    async def falso():
        return {"gpu": "Placa", "vram_gb": vram, "ram_gb": 64.0}

    async def rodar():
        original = maquina.detectar
        maquina.detectar = falso
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=A.app),
                                         base_url="http://127.0.0.1:8600") as c:
                return await c.get("/api/limites")
        finally:
            maquina.detectar = original
    return asyncio.run(rodar())


def test_limites_formato_da_bridge():
    r = _pedir(16.0)
    assert r.status_code == 200 and "json" in r.headers["content-type"]
    d = r.json()
    assert d["maquete"] == {"quadros": 353, "lado": 720}
    assert d["profundidade"]["quadros"] == 353
    assert d["hardware"]["vram_gb"] == 16.0


def test_limites_placa_grande_e_pequena():
    assert _pedir(24.0).json()["maquete"]["lado"] == 1088
    assert _pedir(8.0).json()["maquete"]["lado"] is None


def _rota(metodo, caminho, **kw):
    async def rodar():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=A.app),
                                     base_url="http://127.0.0.1:8600") as c:
            return await c.request(metodo, caminho, **kw)
    return asyncio.run(rodar())


def test_bridge_estado_e_instalar(monkeypatch):
    import bridge
    r = _rota("GET", "/api/bridge")
    assert r.status_code == 200 and r.json()["disponivel"] is True
    assert {"instalada", "blender", "clientes"} <= set(r.json())
    pedidos = []
    monkeypatch.setattr(bridge, "instalar", lambda clientes: pedidos.append(clientes) or True)
    r = _rota("POST", "/api/bridge/instalar", json={"clientes": ["LM Studio"]})
    assert r.status_code == 200 and pedidos == [["LM Studio"]]
    monkeypatch.setattr(bridge, "instalar", lambda clientes: False)
    assert _rota("POST", "/api/bridge/instalar", json={}).status_code == 409
    # De outro site, nada: o mesmo bloqueio de origem das outras rotas.
    r = _rota("POST", "/api/bridge/pasta", headers={"Origin": "https://site-externo.example"})
    assert r.status_code == 403
