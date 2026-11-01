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
