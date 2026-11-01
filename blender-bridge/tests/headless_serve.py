"""Sobe a Bridge num Blender sem interface, com uma cena de teste.

    blender -b --factory-startup --python bridge/tests/headless_serve.py -- [porta]

Timers não rodam em modo background, então o laço de fila é manual.
"""

import pathlib
import sys

import bpy

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "addon"))
from blender_bridge import server  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
port = int(args[0]) if args else 9878

# Cena: chão, dois blocos e uma câmera em travelling de 48 quadros a 24 fps.
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
s = bpy.context.scene
s.frame_start, s.frame_end = 1, 48
s.render.fps = 24
s.render.resolution_x, s.render.resolution_y = 1920, 1080
bpy.ops.mesh.primitive_plane_add(size=20)
bpy.context.object.name = "Chao"
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))
bpy.context.object.name = "Predio_A"
bpy.ops.mesh.primitive_cube_add(size=1, location=(3, 2, 0.5))
bpy.context.object.name = "Caixa"
bpy.ops.object.camera_add(location=(8, -8, 3))
cam = bpy.context.object
cam.name = "CAM_01"
c = cam.constraints.new("TRACK_TO")
c.target = bpy.data.objects["Predio_A"]
s.camera = cam
cam.keyframe_insert("location", frame=1)
cam.location = (2, -9, 2)
cam.keyframe_insert("location", frame=48)

server.start(port=port, use_timer=False).running or sys.exit(1)
srv = server.get_server()
while srv.running:
    srv._drain()
    import time
    time.sleep(0.02)
