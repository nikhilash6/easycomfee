"""Teste de fumaça: chama as ferramentas MCP contra um Blender com a Bridge ligada.

    bridge/server/.venv/Scripts/python.exe bridge/tests/smoke_test.py [--editor]

Use com headless_serve.py (cena de teste). --editor também roda style_frame e
blockout_to_video no Editor de Imagens IA (gera de verdade, leva minutos).
"""

import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "server"))
from blender_bridge_mcp import app  # noqa: E402


def show(nome, r):
    texto = r[0] if isinstance(r, list) else r
    print(f"\n=== {nome}\n{texto[:1500]}")
    return json.loads(texto) if texto.lstrip().startswith(("{", "[")) else texto


async def main():
    show("status", await app.blender_status())
    cena = show("get_scene", await app.blender_get_scene())
    assert cena["active_camera"] == "CAM_01"
    show("get_object", await app.blender_get_object("CAM_01"))
    r = show("execute_python", await app.blender_execute_python(
        "bpy.ops.mesh.primitive_uv_sphere_add(location=(-3,1,1))\n"
        "bpy.context.object.name='Esfera'\nprint('ok')\n"
        "result = [o.name for o in bpy.data.objects]"))
    assert "Esfera" in r["result"]
    try:
        await app.blender_execute_python("x = 1/0")
        raise AssertionError("erro não propagou")
    except Exception as e:
        print("\n=== erro esperado\n", str(e)[-300:])
    show("api_lookup", await app.blender_api_lookup("Camera.lens"))
    show("screenshot", await app.blender_screenshot(frame=24, max_size=640))
    for mode in ("clay", "depth", "normal"):
        show(f"render {mode}", await app.blender_render(mode=mode, frame_start=1, frame_end=12,
                                                         max_size=640))
    if "--editor" in sys.argv:
        print(await app.editor_status())
        st = show("style_frame", await app.style_frame(
            "rua de cidade ao entardecer, prédio de concreto, caixa de madeira, "
            "esfera de metal, fotografia cinematográfica", frame=1, max_size=1024))
        assert st["files"], st
        show("blockout_to_video", await app.blockout_to_video(
            "rua de cidade ao entardecer, câmera em travelling lento, cinematográfico",
            style_image=st["files"][0], frame_start=1, frame_end=48))
    print("\nOK")


asyncio.run(main())
