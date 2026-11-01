"""Comandos da Bridge. Todos rodam no thread principal do Blender.

Cada comando recebe kwargs vindos do JSON e devolve algo serializavel.
Funciona no Blender 4.5 e 5.x; onde a API mudou, ha um caminho para cada.
"""

import contextlib
import io
import math
import os
import pathlib
import tempfile
import traceback

import bpy
import mathutils

COMMANDS = {}


def command(fn):
    COMMANDS[fn.__name__] = fn
    return fn


def dispatch(cmd, params):
    fn = COMMANDS.get(cmd)
    if fn is None:
        raise ValueError(f"unknown command: {cmd}. Available: {sorted(COMMANDS)}")
    return fn(**params)


# ------------------------------------------------------------------ utilitarios

def jsonable(v, depth=0):
    if depth > 6:
        return repr(v)
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return round(v, 6) if math.isfinite(v) else None
    if isinstance(v, mathutils.Matrix):
        return [[round(x, 6) for x in row] for row in v]
    if isinstance(v, (mathutils.Vector, mathutils.Euler, mathutils.Quaternion, mathutils.Color)):
        return [round(x, 6) for x in v]
    if isinstance(v, bpy.types.ID):
        return v.name
    if isinstance(v, dict):
        return {str(k): jsonable(x, depth + 1) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [jsonable(x, depth + 1) for x in v]
    try:
        return [jsonable(x, depth + 1) for x in v]
    except TypeError:
        return repr(v)


def _scene():
    return bpy.context.scene


def _obj(name):
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ValueError(f"object not found: {name}")
    return obj


def _camera(name=None):
    scene = _scene()
    cam = _obj(name) if name else scene.camera
    if cam is None:
        raise ValueError("the scene has no active camera; create one or pass its name")
    if cam.type != "CAMERA":
        raise ValueError(f"{cam.name} is not a camera")
    return cam


def _r(v, n=4):
    return [round(x, n) for x in v]


def _fps(scene):
    return scene.render.fps / scene.render.fps_base


def _fcurves(id_block):
    """F-curves de um ID, nas actions antigas (<4.4) e nas com slots (4.4+/5.x)."""
    ad = getattr(id_block, "animation_data", None)
    action = ad.action if ad else None
    if action is None:
        return []
    slot = getattr(ad, "action_slot", None)
    if slot is not None:
        try:
            from bpy_extras import anim_utils
            bag = anim_utils.action_get_channelbag_for_slot(action, slot)
            if bag is not None:
                return list(bag.fcurves)
        except (ImportError, AttributeError):
            pass
    return list(getattr(action, "fcurves", []))


def _keyframe_summary(id_block):
    out = []
    for fc in _fcurves(id_block):
        frames = [round(k.co[0], 2) for k in fc.keyframe_points]
        out.append({"path": fc.data_path, "index": fc.array_index,
                    "keys": len(frames), "frames": frames[:40],
                    "interp": fc.keyframe_points[0].interpolation if frames else None})
    return out


def _world_bbox(obj):
    if obj.type not in {"MESH", "CURVE", "SURFACE", "FONT", "META", "CURVES", "POINTCLOUD", "VOLUME"}:
        return None
    pts = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    return {"min": _r([min(p[i] for p in pts) for i in range(3)]),
            "max": _r([max(p[i] for p in pts) for i in range(3)])}


def _object_brief(obj):
    d = {"name": obj.name, "type": obj.type,
         "location": _r(obj.matrix_world.translation),
         "rotation_deg": _r([math.degrees(a) for a in obj.matrix_world.to_euler()], 2),
         "scale": _r(obj.scale),
         "dimensions": _r(obj.dimensions),
         "parent": obj.parent.name if obj.parent else None,
         "collections": [c.name for c in obj.users_collection],
         "hidden": obj.hide_get() if bpy.context.view_layer.objects.get(obj.name) else True,
         "render_hidden": obj.hide_render,
         "animated": bool(_fcurves(obj))}
    if obj.type == "CAMERA":
        c = obj.data
        d["camera"] = {"lens_mm": round(c.lens, 2), "sensor_mm": round(c.sensor_width, 2),
                       "type": c.type, "clip": [c.clip_start, c.clip_end],
                       "dof": c.dof.use_dof, "animated": bool(_fcurves(c))}
    elif obj.type == "LIGHT":
        l = obj.data
        d["light"] = {"type": l.type, "energy": round(l.energy, 3), "color": _r(l.color, 3)}
    elif obj.type == "MESH":
        d["materials"] = [s.material.name for s in obj.material_slots if s.material]
        d["vertices"] = len(obj.data.vertices)
    return d


class Restore:
    """Guarda atributos antes de mudar e devolve tudo no fim, mesmo com erro."""

    def __init__(self):
        self.saved = []

    def set(self, obj, attr, value):
        self.saved.append((obj, attr, getattr(obj, attr)))
        setattr(obj, attr, value)

    def restore(self):
        for obj, attr, value in reversed(self.saved):
            try:
                setattr(obj, attr, value)
            except Exception as e:
                print(f"[Bridge] não restaurou {attr}: {e}")


def _set_first(st, obj, attr, *options):
    """Usa a primeira opção que esta versão do Blender aceitar."""
    for v in options:
        try:
            st.set(obj, attr, v)
            return v
        except (TypeError, ValueError):
            st.saved.pop() if st.saved and st.saved[-1][:2] == (obj, attr) else None
    raise RuntimeError(f"no valid option for {attr}: {options}")


def _undo_push(msg):
    try:
        bpy.ops.ed.undo_push(message=msg)
    except Exception:
        pass


# ---------------------------------------------------------------- informacao

@command
def ping():
    return {"pong": True, "blender": bpy.app.version_string}


@command
def status():
    s = _scene()
    return {"blender": bpy.app.version_string, "file": bpy.data.filepath or None,
            "dirty": bpy.data.is_dirty, "scene": s.name,
            "objects": len(s.objects), "background": bpy.app.background}


@command
def get_scene(limit=200):
    s = _scene()
    r = s.render
    objs = sorted(s.objects, key=lambda o: (o.type != "CAMERA", o.name))
    markers = sorted(s.timeline_markers, key=lambda m: m.frame)
    return {
        "scene": s.name, "file": bpy.data.filepath or None,
        "frame": {"start": s.frame_start, "end": s.frame_end, "current": s.frame_current,
                  "fps": round(_fps(s), 3)},
        "render": {"engine": r.engine, "resolution": [r.resolution_x, r.resolution_y],
                   "percentage": r.resolution_percentage},
        "units": {"system": s.unit_settings.system, "scale": s.unit_settings.scale_length},
        "active_camera": s.camera.name if s.camera else None,
        "markers": [{"name": m.name, "frame": m.frame,
                     "camera": m.camera.name if m.camera else None} for m in markers],
        "object_count": len(objs),
        "objects": [_object_brief(o) for o in objs[:limit]],
        "truncated": len(objs) > limit,
    }


@command
def get_object(name):
    obj = _obj(name)
    d = _object_brief(obj)
    d["bbox_world"] = _world_bbox(obj)
    d["modifiers"] = [{"name": m.name, "type": m.type} for m in getattr(obj, "modifiers", [])]
    d["constraints"] = [{"name": c.name, "type": c.type,
                         "target": getattr(getattr(c, "target", None), "name", None)}
                        for c in obj.constraints]
    d["keyframes"] = _keyframe_summary(obj)
    if obj.data is not None and obj.type in {"CAMERA", "LIGHT"}:
        d["data_keyframes"] = _keyframe_summary(obj.data)
    d["custom_props"] = {k: jsonable(obj[k]) for k in obj.keys() if not k.startswith("_")}
    return d


# --------------------------------------------------------------- codigo livre

def _ui_context():
    """Contexto de janela para o código rodado pelo timer.

    No timer, bpy.context.screen/window vêm vazios, e scripts que mexem no
    viewport (ou operadores como render.opengl) quebram. Com uma janela aberta,
    emprestamos a dela, e o viewport 3D quando existir.
    """
    if bpy.app.background:
        return contextlib.nullcontext()
    wm = bpy.context.window_manager
    if not wm or not wm.windows:
        return contextlib.nullcontext()
    win, space, region = _view3d()
    win = win or wm.windows[0]
    kw = {"window": win, "screen": win.screen}
    if region is not None:
        area = next(a for a in win.screen.areas if region in a.regions[:])
        kw.update(area=area, region=region)
    return bpy.context.temp_override(**kw)


@command
def execute_python(code):
    """Roda codigo bpy. Atribua a `result` para devolver dados."""
    ns = {"bpy": bpy, "mathutils": mathutils, "math": math, "result": None,
          "__name__": "__bridge__"}
    out = io.StringIO()
    try:
        import bmesh
        ns["bmesh"] = bmesh
    except ImportError:
        pass
    with contextlib.redirect_stdout(out), _ui_context():
        try:
            exec(compile(code, "<bridge>", "exec"), ns)
        except Exception:
            # Traceback com a linha do script enviado, para o modelo saber onde errou.
            raise RuntimeError(f"{traceback.format_exc()}\n--- stdout ---\n{out.getvalue()[-4000:]}")
    _undo_push("Bridge: execute_python")
    return {"stdout": out.getvalue()[-20000:], "result": jsonable(ns.get("result"))}


@command
def api_lookup(query, limit=25):
    """Procura tipos, operadores e propriedades do bpy pelo nome."""
    q = query.strip()
    if q.startswith("bpy.ops."):
        mod, _, op = q[len("bpy.ops."):].partition(".")
        rna = getattr(getattr(bpy.ops, mod), op).get_rna_type()
        return {"operator": q, "description": rna.description,
                "properties": [_prop_info(p) for p in rna.properties if p.identifier != "rna_type"]}
    tipo, _, prop = q.removeprefix("bpy.types.").partition(".")
    t = getattr(bpy.types, tipo, None)
    if t is not None and hasattr(t, "bl_rna"):
        props = [p for p in t.bl_rna.properties if p.identifier != "rna_type"]
        if prop:
            props = [p for p in props if p.identifier == prop]
        funcs = [f.identifier for f in t.bl_rna.functions]
        return {"type": tipo, "description": t.bl_rna.description,
                "base": t.bl_rna.base.identifier if t.bl_rna.base else None,
                "properties": [_prop_info(p) for p in props], "functions": funcs}
    ql = q.lower()
    tipos = [n for n in dir(bpy.types) if ql in n.lower()][:limit]
    ops = []
    for mod in dir(bpy.ops):
        for op in dir(getattr(bpy.ops, mod)):
            if ql in op.lower() or ql in mod.lower():
                ops.append(f"bpy.ops.{mod}.{op}")
    return {"types": tipos, "operators": ops[:limit],
            "hint": "consulte um item exato: 'Object', 'Object.location' ou 'bpy.ops.mesh.primitive_cube_add'"}


def _prop_info(p):
    d = {"id": p.identifier, "type": p.type, "description": p.description}
    if p.type == "ENUM":
        d["items"] = [i.identifier for i in p.enum_items][:40]
    if getattr(p, "is_array", False) or getattr(p, "array_length", 0):
        d["array_length"] = p.array_length
    if p.type in {"INT", "FLOAT"}:
        d["range"] = [p.hard_min, p.hard_max]
    if p.type in {"POINTER", "COLLECTION"} and p.fixed_type:
        d["fixed_type"] = p.fixed_type.identifier
    return d


# ------------------------------------------------------------------ captura

def _view3d():
    wm = bpy.context.window_manager
    for win in wm.windows if wm else []:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                if region:
                    return win, area.spaces.active, region
    return None, None, None


def _save_rgba8(buf, w, h, path):
    import numpy as np
    buf.dimensions = w * h * 4
    px = np.asarray(buf, dtype=np.float32) / 255.0
    img = bpy.data.images.new("bridge_capture", w, h, alpha=True)
    try:
        img.pixels.foreach_set(px.ravel())
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)


def _fit(w, h, max_size):
    s = min(1.0, max_size / max(w, h))
    return max(2, int(w * s) // 2 * 2), max(2, int(h * s) // 2 * 2)


@command
def screenshot(path, view="viewport", camera=None, max_size=1024, frame=None):
    """Captura o viewport ou a vista da câmera (OpenGL, sem render)."""
    import gpu
    s = _scene()
    if frame is not None:
        s.frame_set(int(frame))
    win, space, region = _view3d()
    if space is None or bpy.app.background:
        # Sem interface (blender -b): render rapido de Workbench pela camera.
        res = render_frames(mode="clay", camera=camera, frame_start=s.frame_current,
                            frame_end=s.frame_current, output_dir=str(pathlib.Path(path).parent),
                            max_size=max_size, prefix=pathlib.Path(path).stem + "_",
                            clay_color="MATERIAL")   # como o viewport sólido: com as cores
        os.replace(res["frames"][0], path)
        return {"path": path, "method": "workbench_render", "view": "camera",
                "camera": res["camera"], "frame": s.frame_current}
    view_layer = win.view_layer
    if view == "camera":
        cam = _camera(camera)
        w, h = _fit(s.render.resolution_x * s.render.pixel_aspect_x,
                    s.render.resolution_y * s.render.pixel_aspect_y, max_size)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        view_m = cam.matrix_world.inverted()
        proj_m = cam.calc_matrix_camera(depsgraph, x=w, y=h,
                                        scale_x=s.render.pixel_aspect_x,
                                        scale_y=s.render.pixel_aspect_y)
    else:
        r3d = space.region_3d
        w, h = _fit(region.width, region.height, max_size)
        view_m, proj_m = r3d.view_matrix, r3d.window_matrix
    off = gpu.types.GPUOffScreen(w, h)
    try:
        off.draw_view3d(s, view_layer, space, region, view_m, proj_m, do_color_management=True)
        buf = off.texture_color.read()
    finally:
        off.free()
    _save_rgba8(buf, w, h, path)
    return {"path": path, "method": "offscreen", "view": view, "width": w, "height": h,
            "camera": camera or (s.camera.name if s.camera and view == "camera" else None),
            "frame": s.frame_current}


# ------------------------------------------------------------------ render

def _depth_range(cam, frames, grid=(48, 27)):
    """Perto/longe do que a câmera VÊ: raios numa grade, no início, meio e fim.

    As caixas dos objetos exageram (um chão de 20 m começa atrás da câmera),
    o que achatava o mapa. Usa os percentis 1 e 99 para ignorar pontas.
    """
    s = _scene()
    atual = s.frame_current
    amostra = sorted({frames[0], frames[len(frames) // 2], frames[-1]})
    zs = []
    try:
        for f in amostra:
            s.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get()
            mw = cam.matrix_world
            inv = mw.inverted()
            tr, br, bl, tl = [mw @ v for v in cam.data.view_frame(scene=s)]
            origem = mw.translation
            for i in range(grid[0]):
                u = (i + 0.5) / grid[0]
                for j in range(grid[1]):
                    v = (j + 0.5) / grid[1]
                    alvo = bl.lerp(br, u).lerp(tl.lerp(tr, u), v)
                    if cam.data.type == "ORTHO":
                        o, d = alvo, (mw.to_3x3() @ mathutils.Vector((0, 0, -1))).normalized()
                    else:
                        o, d = origem, (alvo - origem).normalized()
                    hit, loc, *_ = s.ray_cast(dg, o, d)
                    if hit:
                        z = -(inv @ loc).z
                        if z > 0:
                            zs.append(z)
    finally:
        s.frame_set(atual)
    if len(zs) < 4:
        return cam.data.clip_start, min(cam.data.clip_end, 100.0)
    zs.sort()
    near = zs[int(len(zs) * 0.01)]
    far = zs[min(len(zs) - 1, int(len(zs) * 0.99))]
    return max(cam.data.clip_start, near * 0.9), max(far * 1.1, near * 1.5)


def _depth_material(near, far):
    mat = bpy.data.materials.get("Bridge_Depth") or bpy.data.materials.new("Bridge_Depth")
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    nt.nodes.clear()
    cam = nt.nodes.new("ShaderNodeCameraData")
    mr = nt.nodes.new("ShaderNodeMapRange")
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    mr.clamp = True
    mr.inputs[1].default_value = near
    mr.inputs[2].default_value = far
    mr.inputs[3].default_value = 1.0   # perto = branco
    mr.inputs[4].default_value = 0.0   # longe = preto
    nt.links.new(cam.outputs[1], mr.inputs[0])   # View Z Depth
    nt.links.new(mr.outputs[0], em.inputs[0])
    em.inputs[1].default_value = 1.0
    nt.links.new(em.outputs[0], out.inputs[0])
    return mat


@command
def render_frames(output_dir, mode="clay", camera=None, frame_start=None, frame_end=None,
                  step=1, max_size=1280, near=None, far=None, prefix="frame_",
                  clay_color="SINGLE"):
    """Renderiza quadros PNG pela câmera.

    mode: clay (Workbench cinza), depth (perto=branco), normal (matcap de
    normais), beauty (configuração atual da cena). Restaura tudo no fim.
    """
    s = _scene()
    cam = _camera(camera)
    a = int(frame_start if frame_start is not None else s.frame_start)
    b = int(frame_end if frame_end is not None else s.frame_end)
    frames = list(range(a, b + 1, max(1, int(step))))
    out = pathlib.Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    r = s.render
    w, h = _fit(r.resolution_x * r.resolution_percentage / 100,
                r.resolution_y * r.resolution_percentage / 100, max_size)

    st = Restore()
    vl = bpy.context.view_layer
    original_frame = s.frame_current
    info = {}
    try:
        st.set(s, "camera", cam)
        st.set(r, "resolution_x", w)
        st.set(r, "resolution_y", h)
        st.set(r, "resolution_percentage", 100)
        st.set(r.image_settings, "file_format", "PNG")
        st.set(r.image_settings, "color_mode", "RGB")
        st.set(r.image_settings, "color_depth", "8")
        st.set(r, "use_file_extension", True)
        st.set(r, "filepath", r.filepath)
        if mode in {"clay", "normal", "depth"}:
            st.set(s.view_settings, "look", "None")
            st.set(s.view_settings, "exposure", 0.0)
            st.set(s.view_settings, "gamma", 1.0)
        if mode in {"clay", "normal"}:
            sh = s.display.shading
            _set_first(st, r, "engine", "BLENDER_WORKBENCH")
            _set_first(st, s.view_settings, "view_transform", "Standard")
            st.set(r, "film_transparent", False)
            if mode == "clay":
                st.set(sh, "light", "STUDIO")
                st.set(sh, "color_type", clay_color)
                st.set(sh, "single_color", (0.8, 0.8, 0.8))
            else:
                st.set(sh, "light", "MATCAP")
                st.set(sh, "studio_light", "check_normal+y.exr")
            st.set(sh, "show_shadows", False)
            st.set(sh, "show_cavity", False)
        elif mode == "depth":
            if near is None or far is None:
                n, f = _depth_range(cam, frames)
                near = n if near is None else near
                far = f if far is None else far
            info = {"near": round(near, 4), "far": round(far, 4)}
            _set_first(st, r, "engine", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE")
            _set_first(st, s.view_settings, "view_transform", "Raw", "Standard")
            # Fundo transparente salvo em RGB vira preto: o "infinitamente longe".
            st.set(r, "film_transparent", True)
            st.set(vl, "material_override", _depth_material(near, far))
            if hasattr(s.eevee, "taa_render_samples"):
                st.set(s.eevee, "taa_render_samples", 4)
        elif mode != "beauty":
            raise ValueError("mode deve ser clay, depth, normal ou beauty")

        paths = []
        for i, f in enumerate(frames):
            s.frame_set(f)
            p = str(out / f"{prefix}{i:05d}.png")
            r.filepath = p
            bpy.ops.render.render(write_still=True)
            paths.append(p)
    finally:
        st.restore()
        s.frame_set(original_frame)
    return {"frames": paths, "frame_numbers": frames, "fps": round(_fps(s) / max(1, int(step)), 3),
            "resolution": [w, h], "camera": cam.name, "mode": mode, **info}


# ------------------------------------------------------------ trazer de volta

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


@command
def import_media(path, mode="camera_background", camera=None, opacity=0.6, channel=2,
                 frame_start=None):
    """Traz um resultado do Editor para a cena: fundo da câmera ou VSE."""
    p = pathlib.Path(path)
    if not p.is_file():
        raise ValueError(f"file does not exist: {path}")
    s = _scene()
    start = int(frame_start if frame_start is not None else s.frame_start)
    video = p.suffix.lower() in VIDEO_EXT
    if mode == "camera_background":
        cam = _camera(camera)
        bg = cam.data.background_images.new()
        if video:
            clip = bpy.data.movieclips.load(str(p))
            clip.frame_start = start
            bg.source = "MOVIE_CLIP"
            bg.clip = clip
        else:
            bg.source = "IMAGE"
            bg.image = bpy.data.images.load(str(p), check_existing=True)
        bg.alpha = float(opacity)
        bg.display_depth = "FRONT"
        cam.data.show_background_images = True
        _undo_push("Bridge: import_media")
        return {"camera": cam.name, "source": bg.source, "path": str(p),
                "hint": "olhe pela câmera (Numpad 0) para comparar com o blocking"}
    if mode == "vse":
        se = s.sequence_editor or s.sequence_editor_create()
        strips = getattr(se, "strips", None) or se.sequences   # 5.x: strips
        if video:
            strip = strips.new_movie(p.stem, str(p), channel=int(channel), frame_start=start)
        else:
            strip = strips.new_image(p.stem, str(p), channel=int(channel), frame_start=start)
        _undo_push("Bridge: import_media")
        return {"strip": strip.name, "channel": strip.channel,
                "frames": [strip.frame_final_start, strip.frame_final_end]}
    raise ValueError("mode deve ser camera_background ou vse")


@command
def temp_dir():
    return tempfile.gettempdir()
