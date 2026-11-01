"""Servidor socket local da Bridge.

Protocolo: uma mensagem JSON por linha (UTF-8, terminada em "\n").
    pedido:   {"id": 1, "token": "...", "cmd": "get_scene", "params": {...}}
    resposta: {"id": 1, "ok": true, "result": ...}
              {"id": 1, "ok": false, "error": {"type", "message", "traceback"}}

O bpy so pode ser tocado no thread principal. As conexoes rodam em threads
proprias e apenas colocam os pedidos numa fila; um unico timer persistente
(registrado no thread principal) esvazia a fila. Registrar um timer por
comando, a partir do thread da conexao, perde callbacks sem erro no Windows.
Padrao adaptado do blender-mcp (MIT, Siddharth Ahuja) — ver NOTICE.
"""

import json
import os
import pathlib
import queue
import secrets
import socket
import threading
import time
import traceback

import bpy

PROTOCOL = 1
CONNECTION_FILE = pathlib.Path.home() / ".blender_bridge" / "connection.json"


class BridgeServer:
    def __init__(self, host="127.0.0.1", port=9877):
        self.host = host
        self.port = port
        self.token = secrets.token_hex(16)
        self.running = False
        self.sock = None
        self.thread = None
        self.queue = queue.Queue()
        self.clients = set()
        self.lock = threading.Lock()
        self.last_error = ""

    # ---------------------------------------------------------------- ciclo

    def start(self, use_timer=True):
        if self.running:
            return
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.bind((self.host, self.port))
            self.sock.listen(5)
            self.sock.settimeout(1.0)
        except OSError as e:
            self.last_error = f"porta {self.port} indisponível: {e}"
            print(f"[Bridge] {self.last_error}")
            self.sock = None
            return
        self.running = True
        self.last_error = ""
        self.thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.thread.start()
        if use_timer and not bpy.app.timers.is_registered(self._drain):
            bpy.app.timers.register(self._drain, persistent=True)
        self._write_connection_file()
        print(f"[Bridge] ouvindo em {self.host}:{self.port}")

    def stop(self):
        self.running = False
        try:
            if bpy.app.timers.is_registered(self._drain):
                bpy.app.timers.unregister(self._drain)
        except Exception:
            pass
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        # Sem fechar as conexoes, as threads ficam presas no recv() e, ao
        # religar, derrubam conexoes do servidor novo (WinError 10054).
        with self.lock:
            clients, self.clients = list(self.clients), set()
        for c in clients:
            for fn in (lambda: c.shutdown(socket.SHUT_RDWR), c.close):
                try:
                    fn()
                except Exception:
                    pass
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.5)
        self.thread = None
        self._remove_connection_file()
        print("[Bridge] parado")

    def serve_blocking(self):
        """Modo headless (blender -b): timers nao rodam, entao o laco e manual."""
        self.start(use_timer=False)
        while self.running:
            self._drain()
            time.sleep(0.02)

    # ------------------------------------------------------- arquivo de conexao

    def _write_connection_file(self):
        CONNECTION_FILE.parent.mkdir(parents=True, exist_ok=True)
        dados = {"host": self.host, "port": self.port, "token": self.token,
                 "pid": os.getpid(), "protocol": PROTOCOL,
                 "blender": bpy.app.version_string}
        tmp = CONNECTION_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(dados), encoding="utf-8")
        os.replace(tmp, CONNECTION_FILE)

    def _remove_connection_file(self):
        try:
            if json.loads(CONNECTION_FILE.read_text(encoding="utf-8")).get("pid") == os.getpid():
                CONNECTION_FILE.unlink()
        except Exception:
            pass

    # ----------------------------------------------------------------- rede

    def _accept_loop(self):
        while self.running:
            try:
                client, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._client_loop, args=(client,), daemon=True).start()

    def _client_loop(self, client):
        client.settimeout(1.0)
        with self.lock:
            self.clients.add(client)
        buf = b""
        try:
            while self.running:
                try:
                    data = client.recv(65536)
                except socket.timeout:
                    continue
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    linha, buf = buf.split(b"\n", 1)
                    if linha.strip():
                        self._accept_line(client, linha)
        except OSError:
            pass
        finally:
            with self.lock:
                self.clients.discard(client)
            try:
                client.close()
            except Exception:
                pass

    def _accept_line(self, client, linha):
        try:
            pedido = json.loads(linha.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            self._send(client, {"id": None, "ok": False,
                                "error": {"type": "ProtocolError", "message": str(e)}})
            return
        if not secrets.compare_digest(str(pedido.get("token", "")), self.token):
            self._send(client, {"id": pedido.get("id"), "ok": False,
                                "error": {"type": "AuthError", "message": "token inválido"}})
            return
        self.queue.put((pedido, client))

    @staticmethod
    def _send(client, resposta):
        try:
            client.sendall((json.dumps(resposta, default=str) + "\n").encode("utf-8"))
        except OSError:
            pass

    # ------------------------------------------------------ thread principal

    def _drain(self):
        if not self.running:
            return None
        from . import commands
        while True:
            try:
                pedido, client = self.queue.get_nowait()
            except queue.Empty:
                break
            rid = pedido.get("id")
            try:
                resultado = commands.dispatch(pedido.get("cmd", ""), pedido.get("params") or {})
                resposta = {"id": rid, "ok": True, "result": resultado}
            except Exception as e:
                resposta = {"id": rid, "ok": False,
                            "error": {"type": type(e).__name__, "message": str(e),
                                      "traceback": traceback.format_exc()}}
            self._send(client, resposta)
        return 0.05


_server = None


def get_server():
    return _server


def start(port=9877, use_timer=True):
    global _server
    if _server and _server.running:
        return _server
    _server = BridgeServer(port=port)
    _server.start(use_timer=use_timer)
    return _server


def stop():
    global _server
    if _server:
        _server.stop()
    _server = None
