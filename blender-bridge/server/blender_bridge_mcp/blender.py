"""Cliente do socket que o addon abre dentro do Blender."""

import itertools
import json
import pathlib
import socket

CONNECTION_FILE = pathlib.Path.home() / ".blender_bridge" / "connection.json"
_ids = itertools.count(1)


class BlenderError(RuntimeError):
    pass


def _connection():
    try:
        return json.loads(CONNECTION_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BlenderError(
            "Blender is not connected: open Blender with the 'Blender Bridge' add-on "
            "on (3D Viewport > N sidebar > Bridge > Start Bridge).") from None


def call(cmd, timeout=60.0, **params):
    """Envia um comando e espera a resposta. Uma conexão por chamada."""
    conn = _connection()
    rid = next(_ids)
    pedido = {"id": rid, "token": conn["token"], "cmd": cmd, "params": params}
    try:
        with socket.create_connection((conn["host"], conn["port"]), timeout=5) as s:
            s.settimeout(timeout)
            s.sendall((json.dumps(pedido) + "\n").encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                data = s.recv(1 << 20)
                if not data:
                    raise BlenderError("Blender closed the connection without answering")
                buf += data
    except ConnectionRefusedError:
        raise BlenderError(
            f"nothing listening on {conn['host']}:{conn['port']}. Was Blender closed? "
            "Open it and start the Bridge.") from None
    except socket.timeout:
        raise BlenderError(
            f"'{cmd}' got no answer in {timeout:.0f}s. Blender may still be working; "
            "check the scene before repeating.") from None
    resposta = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
    if not resposta.get("ok"):
        e = resposta.get("error") or {}
        msg = f"{e.get('type', 'Erro')}: {e.get('message', '')}"
        if e.get("traceback") and e.get("type") != "RuntimeError":
            msg += "\n" + e["traceback"][-3000:]
        raise BlenderError(msg)
    return resposta.get("result")
