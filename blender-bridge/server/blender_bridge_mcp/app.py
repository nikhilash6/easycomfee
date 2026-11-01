"""Servidor MCP da Bridge: ferramentas para o Blender aberto e para o EasyComfee.

Funciona com qualquer cliente MCP (Claude, LM Studio, VS Code, Cursor...). O roteiro
de blocking que antes era uma skill do Claude Code vem do proprio servidor
(`blocking_guide`), e os passos que pediam terminal viraram ferramentas
(`previz_solve`, `previz_load_core`): um cliente sem shell faz o fluxo inteiro.
"""

import asyncio
import json
import os
import pathlib
import subprocess
import sys
import time

from mcp.server.mcpserver import Image, MCPServer

from . import blender, editor, media

BRIDGE = pathlib.Path(__file__).resolve().parents[2]
BLOCKING = BRIDGE / "blocking"
OUTPUT = pathlib.Path(os.environ.get("BRIDGE_OUTPUT_DIR", BRIDGE / "output"))
EDITOR_FPS = 24
# Teto de quadros (24 fps) por efeito no EasyComfee. O da maquete depende da placa e
# vem de GET /api/limites; este valor so vale se o app nao tiver o endpoint.
EDITOR_MAX_FRAMES = {"maquete": 241, "profundidade": 353}


async def _max_frames(effect):
    lim = await editor.limits()
    if lim and lim.get(effect, {}).get("quadros"):
        return lim[effect]["quadros"]
    return EDITOR_MAX_FRAMES[effect]

mcp = MCPServer(
    "blender-bridge",
    instructions=(
        "Controls the scene open in Blender (Z up, meters; degrees when reading, radians "
        "in bpy) and generates images/videos with EasyComfee, a local ComfyUI studio. "
        "To block out a shot from an idea and turn it into a video, FIRST call "
        "blocking_guide and follow it step by step. Read the scene with blender_get_scene "
        "before changing it and check with blender_screenshot after. style_frame makes the "
        "look image from the blocking; blockout_to_video turns the animation into the final "
        "video (LTX 2.5 '3D render -> Video')."),
)


def _run_dir(label):
    # Milissegundos e contador: duas chamadas no mesmo segundo nao dividem a pasta.
    base = f"{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}_{label}"
    d, n = OUTPUT / base, 1
    while d.exists():
        n += 1
        d = OUTPUT / f"{base}_{n}"
    d.mkdir(parents=True)
    return d


async def _bl(cmd, timeout=60.0, **params):
    return await asyncio.to_thread(blender.call, cmd, timeout, **params)


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ roteiro

_REFERENCIAS = {"camera_rules": "CAMERA_RULES.md", "shot_grammar": "SHOT_GRAMMAR.md",
                "seedance_prompt": "SEEDANCE_PROMPT.md"}


@mcp.tool()
async def blocking_guide(topic: str = "main") -> str:
    """The step-by-step method for blocking a shot in Blender and turning it into video.
    Call this FIRST for any previz/blocking/camera-move request. topic='main' (the
    workflow), 'camera_rules' (a solver gate failed, or designing a move), 'shot_grammar'
    (framings, ramps, cuts, or building a place the user named) or 'seedance_prompt'."""
    if topic == "main":
        return (BLOCKING / "GUIDE.md").read_text(encoding="utf-8")
    if topic not in _REFERENCIAS:
        raise ValueError(f"topic must be one of: main, {', '.join(_REFERENCIAS)}")
    return (BLOCKING / "references" / _REFERENCIAS[topic]).read_text(encoding="utf-8")


@mcp.tool()
async def previz_load_core() -> str:
    """Loads the previz helpers (PV.checker, PV.actor, PV.load_bake, PV.audit...) into the
    open Blender. Run once per Blender session, and again if a call says KeyError 'PV'.
    Afterwards each blender_execute_python starts with PV = bpy.app.driver_namespace["PV"]."""
    core = str(BLOCKING / "scripts" / "previz_core.py")
    code = (f"mod = type(bpy)('PV'); mod.__dict__['__file__'] = {core!r}\n"
            f"exec(open({core!r}, encoding='utf-8').read(), mod.__dict__)\n"
            "bpy.app.driver_namespace['PV'] = mod\n"
            "result = sorted(n for n in dir(mod) if not n.startswith('_'))")
    return _dump(await _bl("execute_python", 60, code=code))


@mcp.tool()
async def previz_solve(name: str, spec: str = "", rigs: bool = False) -> str:
    """Checks a shot spec with the camera solver, offline, before touching Blender.
    name: a short shot name (letters, digits, _). spec: the full Python text that defines
    SHOT = {...} (see blocking_guide). Writes it, runs the six gates per shot and, when all
    pass (exit 0), writes bake.json next to it: pass that path to PV.load_bake in Blender.
    rigs=True only lists the camera rigs and their limits."""
    solver = str(BLOCKING / "scripts" / "solve_shot.py")
    if rigs:
        args = [solver, "--rigs"]
        pasta = OUTPUT
    else:
        if not name.replace("_", "").isalnum() or not spec.strip():
            raise ValueError("give a simple name (letters, digits, _) and the spec text")
        pasta = OUTPUT / "previz" / name
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"{name}.py").write_text(spec, encoding="utf-8")
        args = [solver, str(pasta / f"{name}.py")]
    pasta.mkdir(parents=True, exist_ok=True)
    r = await asyncio.to_thread(subprocess.run, [sys.executable, *args], capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=120,
                                cwd=str(pasta))
    bake = pasta / "bake.json"
    return _dump({"exit_code": r.returncode, "passed": r.returncode == 0,
                  "output": (r.stdout + r.stderr)[-6000:],
                  "spec": None if rigs else str(pasta / f"{name}.py"),
                  "bake": str(bake) if not rigs and bake.exists() else None})


# ------------------------------------------------------------------- Blender

@mcp.tool()
async def blender_status() -> str:
    """Blender version, the open file and whether it has unsaved changes."""
    return _dump(await _bl("status", 10))


@mcp.tool()
async def blender_get_scene(limit: int = 200) -> str:
    """Scene summary: frames/fps, render settings, active camera, markers and objects
    (position in meters, rotation in degrees, dimensions, camera lenses)."""
    return _dump(await _bl("get_scene", 30, limit=limit))


@mcp.tool()
async def blender_get_object(name: str) -> str:
    """Details of one object: world bounding box, modifiers, constraints and keyframes."""
    return _dump(await _bl("get_object", 30, name=name))


@mcp.tool()
async def blender_execute_python(code: str, timeout_s: float = 120) -> str:
    """Runs bpy code in the open Blender (bpy, mathutils, bmesh and math are imported).
    Assign to `result` to return data; print() output comes back too. Each run is one
    Ctrl+Z step for the user. Rotations in bpy are radians."""
    return _dump(await _bl("execute_python", timeout_s, code=code))


@mcp.tool()
async def blender_api_lookup(query: str) -> str:
    """Looks up the bpy API of this Blender version instead of guessing names.
    Examples: 'Camera', 'Camera.lens', 'bpy.ops.mesh.primitive_cube_add', or a word
    ('keyframe') to search."""
    return _dump(await _bl("api_lookup", 30, query=query))


@mcp.tool()
async def blender_screenshot(view: str = "camera", camera: str | None = None,
                             frame: int | None = None, max_size: int = 1024) -> list:
    """Picture of the viewport (view='viewport') or through the camera (view='camera',
    default), drawn in OpenGL without rendering. Use it to check blocking and framing."""
    path = _run_dir("shot") / "screenshot.png"
    info = await _bl("screenshot", 60, path=str(path), view=view, camera=camera,
                     frame=frame, max_size=max_size)
    return [_dump(info), Image(path=path)]


@mcp.tool()
async def blender_render(mode: str = "clay", camera: str | None = None,
                         frame_start: int | None = None, frame_end: int | None = None,
                         step: int = 1, max_size: int = 1280, video: bool = True,
                         clay_color: str = "SINGLE") -> list:
    """Renders through the camera and saves PNGs (plus an MP4 if video=True and there is
    more than one frame). mode: clay (Workbench), depth (near=white, EEVEE), normal
    (normals matcap) or beauty (the scene's own settings). For clay, clay_color='SINGLE'
    makes everything grey and 'MATERIAL' keeps each block's color. Markers bound to
    cameras put the cuts in the render. The scene is restored at the end."""
    d = _run_dir(f"render_{mode}")
    n = (frame_end - frame_start + 1) // max(1, step) if None not in (frame_start, frame_end) else 250
    res = await _bl("render_frames", max(120, n * 10), output_dir=str(d / "frames"), mode=mode,
                    camera=camera, frame_start=frame_start, frame_end=frame_end,
                    step=step, max_size=max_size, clay_color=clay_color)
    if video and len(res["frames"]) > 1:
        res["mp4"] = await asyncio.to_thread(media.encode_mp4, d / "frames", res["fps"],
                                             d / f"{mode}.mp4")
    first = res["frames"][0]
    res["frames"] = f"{len(res['frames'])} PNGs in {d / 'frames'}"
    return [_dump(res), Image(path=first)]


@mcp.tool()
async def blender_import_media(path: str, mode: str = "camera_background",
                               camera: str | None = None, opacity: float = 0.6,
                               frame_start: int | None = None) -> str:
    """Brings an image or video into the scene: mode='camera_background' (over the
    camera, to compare with the blocking) or mode='vse' (in the video sequencer)."""
    return _dump(await _bl("import_media", 60, path=path, mode=mode, camera=camera,
                           opacity=opacity, frame_start=frame_start))


# ---------------------------------------------------------------- EasyComfee

@mcp.tool()
async def editor_status() -> str:
    """Health of EasyComfee and its engine (ComfyUI), plus what its machine can take:
    GPU, VRAM, RAM and the 3D render -> Video limit (frames at 24 fps, short side)."""
    return _dump({**await editor.health(), "limites": await editor.limits()})


@mcp.tool()
async def editor_upload(path: str) -> str:
    """Sends a local file to EasyComfee. Returns the name to use in `referencias`
    (for a video, use 'entrada:<name>' as referencias[0] in transformar_video)."""
    return await editor.upload(path)


async def _finish(t, label, timeout_s):
    if t.get("estado") not in editor.FIM:
        t = await editor.wait(t["id"], timeout=timeout_s)
    out = {"id": t["id"], "estado": t.get("estado"), "erro": t.get("erro"),
           "detalhe": t.get("detalhe"), "duracao": t.get("duracao"), "files": []}
    if t.get("estado") == "pronto":
        d = _run_dir(label)
        for item in editor.results(t):
            out["files"].append(await editor.download(item, d))
    elif t.get("estado") != "erro":
        out["aviso"] = "still running; check again with editor_task"
    return out


@mcp.tool()
async def editor_generate(request: dict, wait: bool = True, timeout_s: int = 1800) -> str:
    """Raw request to EasyComfee's POST /api/gerar (fields of PedidoGeracao: modelo,
    prompt, referencias, efeito_video, chaves_video, seed...). With wait=True it waits
    for the result and downloads it to the output folder."""
    t = await editor.generate(request)
    if not wait:
        return _dump(t)
    return _dump(await _finish(t, f"editor_{request.get('modelo', 'gerar')}", timeout_s))


@mcp.tool()
async def editor_task(task_id: str, wait: bool = True, timeout_s: int = 1800) -> str:
    """State of an EasyComfee job; with wait=True waits and downloads the results."""
    t = await editor.task(task_id)
    if not wait and t.get("estado") not in editor.FIM:
        return _dump(t)
    return _dump(await _finish(t, f"editor_{t.get('modelo', 'tarefa')}", timeout_s))


@mcp.tool()
async def editor_free_memory() -> str:
    """Asks EasyComfee to unload the models from the GPU."""
    return _dump(await editor.free_memory())


# ------------------------------------------------------------ fluxo completo

@mcp.tool()
async def style_frame(prompt: str, camera: str | None = None, frame: int | None = None,
                      source: str = "clay", control: str = "profundidade",
                      strength: float = 1.0, seed: int | None = None,
                      max_size: int = 1280, timeout_s: int = 900) -> list:
    """Makes the final-look image of one frame from the blocking: renders the frame through
    the camera (source='clay' or 'depth') and sends it to EasyComfee's structure-guided
    image mode (control: 'profundidade' = depth, 'contorno' = edges, 'pose'). The result is
    the style image for blockout_to_video. Describe the final scene in the prompt
    (materials, light, era) and say what each colored block is."""
    d = _run_dir("style")
    if frame is None:
        frame = (await _bl("get_scene", 30, limit=1))["frame"]["current"]
    r = await _bl("render_frames", 300, output_dir=str(d), mode=source, camera=camera,
                  frame_start=frame, frame_end=frame, max_size=max_size, prefix="guia_")
    guia = r["frames"][0]
    nome = await editor.upload(guia)
    pedido = {"modelo": "controle", "prompt": prompt, "referencias": [nome],
              "tipo_controle": control, "forca_controle": strength}
    if seed is not None:
        pedido["seed"] = seed
    out = await _finish(await editor.generate(pedido), "style_result", timeout_s)
    out["guia"] = guia
    content = [_dump(out)]
    if out["files"]:
        content.append(Image(path=out["files"][0]))
    return content


@mcp.tool()
async def blockout_to_video(prompt: str, style_image: str | None = None,
                            camera: str | None = None, frame_start: int | None = None,
                            frame_end: int | None = None, effect: str = "maquete",
                            keyframes: list[dict] | None = None,
                            import_mode: str = "camera_background", seed: int | None = None,
                            clay_color: str = "MATERIAL", max_size: int = 1280,
                            timeout_s: int = 2400) -> str:
    """Turns the blocking animation into the final video with EasyComfee.

    effect='maquete' (3D render -> Video, LTX 2.5): clay render + style image (required,
    make it with style_frame); keyframes=[{"frame": <Blender frame>, "image": <path>}] pin
    extra images at moments of the shot. effect='profundidade' (Follow depth): a ready
    depth pass; the style image is optional. Length limit at 24 fps: see editor_status
    (353 frames, ~14.7 s, on a 16 GB GPU).
    clay_color: MATERIAL (default, keeps each block's color) or SINGLE (all grey).
    camera=None follows the active camera and camera markers, so the blocking's cuts are
    in the guide video. import_mode: camera_background, vse or none."""
    if effect not in {"maquete", "profundidade"}:
        raise ValueError("effect must be 'maquete' or 'profundidade'")
    if effect == "maquete" and not style_image:
        raise ValueError("effect 'maquete' needs style_image (make it with style_frame)")
    cena = await _bl("get_scene", 30, limit=1)
    a = frame_start if frame_start is not None else cena["frame"]["start"]
    b = frame_end if frame_end is not None else cena["frame"]["end"]
    fps = cena["frame"]["fps"]
    quadros_24 = round((b - a + 1) * EDITOR_FPS / fps)
    teto = await _max_frames(effect)
    if quadros_24 > teto:
        raise ValueError(f"{quadros_24} frames at 24 fps go past the {teto}-frame limit of "
                         f"'{effect}' on this machine; split the shot (frame_start/frame_end)")
    # O app usa 8k+1 quadros e arredonda para BAIXO (240 viravam 233, 9,7 s).
    # Completa o guia ate o proximo 8k+1 com quadros depois do fim; a animacao
    # so segura a ultima pose, e o plano sai com a duracao pedida.
    n = b - a + 1
    alvo = (n + 6) // 8 * 8 + 1
    if abs(fps - EDITOR_FPS) < 0.01 and n < alvo <= teto:
        b = a + alvo - 1

    d = _run_dir(f"video_{effect}")
    mode = "clay" if effect == "maquete" else "depth"
    r = await _bl("render_frames", max(300, (b - a + 1) * 15), output_dir=str(d / "frames"),
                  mode=mode, camera=camera, frame_start=a, frame_end=b, max_size=max_size,
                  clay_color=clay_color)
    mp4 = await asyncio.to_thread(media.encode_mp4, d / "frames", r["fps"], d / f"{mode}.mp4")

    refs = ["entrada:" + await editor.upload(mp4)]
    if style_image:
        refs.append(await editor.upload(style_image))
    pedido = {"modelo": "transformar_video", "efeito_video": effect, "prompt": prompt,
              "referencias": refs}
    if effect == "profundidade":
        pedido["mapa_pronto"] = True
    if keyframes:
        pedido["chaves_video"] = [
            # O app conta quadros a partir de 1, a 24 fps, desde o inicio do clipe.
            {"quadro": round((int(k["frame"]) - a) * EDITOR_FPS / fps) + 1,
             "imagem": await editor.upload(k["image"])} for k in keyframes]
    if seed is not None:
        pedido["seed"] = seed
    out = await _finish(await editor.generate(pedido), f"video_{effect}_result", timeout_s)
    out.update({"guia_mp4": mp4, "render": {k: r[k] for k in ("camera", "resolution", "fps")},
                "frames": [a, b]})
    videos = [f for f in out["files"] if pathlib.Path(f).suffix.lower() in {".mp4", ".mov", ".webm"}]
    if videos and import_mode != "none":
        out["import"] = await _bl("import_media", 60, path=videos[0], mode=import_mode,
                                  camera=camera, frame_start=a)
    return _dump(out)


def main():
    mcp.run("stdio")
