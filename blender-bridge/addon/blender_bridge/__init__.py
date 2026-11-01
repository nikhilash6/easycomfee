bl_info = {
    "name": "Blender Bridge",
    "author": "EasyComfee",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar (N) > Bridge",
    "description": "Lets an AI assistant (any MCP client) work in the open scene and talk to EasyComfee",
    "category": "System",
}

import bpy
from bpy.app.handlers import persistent

from . import server


def _prefs():
    addon = bpy.context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


class BridgePreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    port: bpy.props.IntProperty(name="Porta", default=9877, min=1024, max=65535)
    auto_start: bpy.props.BoolProperty(
        name="Ligar ao abrir o Blender", default=True,
        description="Inicia o servidor local automaticamente")

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "port")
        col.prop(self, "auto_start")


class BRIDGE_OT_start(bpy.types.Operator):
    bl_idname = "bridge.start"
    bl_label = "Start Bridge"

    def execute(self, context):
        p = _prefs()
        srv = server.start(port=p.port if p else 9877)
        if not srv.running:
            self.report({"ERROR"}, srv.last_error)
            return {"CANCELLED"}
        return {"FINISHED"}


class BRIDGE_OT_stop(bpy.types.Operator):
    bl_idname = "bridge.stop"
    bl_label = "Stop Bridge"

    def execute(self, context):
        server.stop()
        return {"FINISHED"}


class BRIDGE_PT_panel(bpy.types.Panel):
    bl_label = "Bridge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Bridge"

    def draw(self, context):
        col = self.layout.column()
        srv = server.get_server()
        if srv and srv.running:
            col.label(text=f"On at {srv.host}:{srv.port}", icon="LINKED")
            col.operator("bridge.stop", icon="CANCEL")
        else:
            col.label(text="Off", icon="UNLINKED")
            if srv and srv.last_error:
                col.label(text=srv.last_error, icon="ERROR")
            col.operator("bridge.start", icon="PLAY")


CLASSES = (BridgePreferences, BRIDGE_OT_start, BRIDGE_OT_stop, BRIDGE_PT_panel)


def _auto_start():
    p = _prefs()
    if p and p.auto_start and not bpy.app.background:
        server.start(port=p.port)
    return None


@persistent
def _on_load(_):
    srv = server.get_server()
    if not (srv and srv.running):
        bpy.app.timers.register(_auto_start, first_interval=0.5)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.app.handlers.load_post.append(_on_load)
    bpy.app.timers.register(_auto_start, first_interval=1.0)


def unregister():
    server.stop()
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
