# Blender Bridge (optional)

Describe a shot in words. An AI assistant blocks it out in Blender with colored boxes and
a solved camera move, you watch it in the viewport, and EasyComfee turns the greybox into a
finished video with **3D render → Video** (LTX 2.5), on your own GPU.

```
your AI assistant ──MCP (stdio)── Bridge server ──local socket── Blender (add-on)
  (any MCP client)                      └────────HTTP 127.0.0.1:8600──── EasyComfee
```

It speaks **MCP**, an open standard, so it is not tied to one AI. Use what you like:
Claude Desktop / Claude Code, LM Studio with an open-weights model, VS Code (Copilot,
Cline, Continue), Cursor... The blocking method ships inside the server (`blocking_guide`),
so every client gets the same instructions, and the steps that would need a terminal are
tools (`previz_solve`, `previz_load_core`).

> Tested with **Qwen 3.5 9B in LM Studio**: from one request it read the guide, solved the
> camera, built the shot in Blender, checked it and made the style image, with no tool
> errors. Smaller models may need you to drive them step by step.
>
> A local LLM shares the GPU with ComfyUI. On a 16 GB card, the style image took ~12 min
> with the 9B model loaded instead of ~35 s. Unload the model in LM Studio (or run it on
> CPU) before `style_frame` and `blockout_to_video`, or use a cloud AI for the chat.

## Install

Needs EasyComfee installed, **Blender 4.2+** (tested on 5.2), Python 3.11–3.13 and
**ffmpeg** on PATH (`winget install ffmpeg`).

1. Run `blender-bridge\install.bat`. It creates the server environment, packs
   `blender_bridge_addon.zip` and writes `mcp-config.json` with the paths of your PC.
2. **Blender:** Edit → Preferences → Add-ons → *Install from Disk* →
   `blender_bridge_addon.zip`, turn it on. In the 3D Viewport press **N** → **Bridge** →
   **Start Bridge**.
3. **Your MCP client:** `install.bat` finds **LM Studio** and **Claude Desktop** and offers
   to add the Bridge to them (it keeps your other servers and saves a `.bak` copy first);
   restart the client afterwards. For other clients, add the `blender-bridge` entry of
   `mcp-config.json` yourself:
   - Claude Desktop: Settings → Developer → Edit Config (`claude_desktop_config.json`).
   - Claude Code: `.mcp.json` in your project, or `claude mcp add`.
   - LM Studio: Program → Install → Edit `mcp.json`.
   - VS Code / Cursor: their `mcp.json` (VS Code calls the key `servers`).
4. Keep EasyComfee open (port 8600; set `EDITOR_URL` if you changed it) and ask:
   *"Block out a shot: a woman walks down a rainy street, the camera tracks her at knee
   height, then make it a video."*

## Tools

| Group | Tools |
|---|---|
| Method | `blocking_guide`, `previz_solve` (offline camera solver, six gates per shot), `previz_load_core` |
| Blender | `blender_status`, `blender_get_scene`, `blender_get_object`, `blender_execute_python`, `blender_api_lookup`, `blender_screenshot`, `blender_render` (clay, depth, normal, beauty), `blender_import_media` |
| EasyComfee | `editor_status` (health and this PC's video length limit), `editor_upload`, `editor_generate`, `editor_task`, `editor_free_memory` |
| Flows | `style_frame` (one frame → final-look image, structure-guided), `blockout_to_video` (animation → 3D render → Video, result back behind the camera) |

Files go to `blender-bridge/output/`.

## Notes

- One GPU for everything: the tools render in Blender first, then generate. Rendering
  freezes Blender's interface while it runs.
- Video length: up to 353 frames (~14.7 s at 24 fps) on a 16 GB GPU; `editor_status` shows
  your PC's limit. Split longer sequences.
- The add-on only listens on 127.0.0.1 and checks a token saved in
  `~/.blender_bridge/connection.json`. `blender_execute_python` runs code in your Blender:
  use a client and model you trust.
- Test without the interface: `blender -b --factory-startup --python tests/headless_serve.py`,
  then `server\.venv\Scripts\python.exe tests\smoke_test.py --editor`.

## Credits

The blocking method (`blocking/`) is adapted from **seedance-blocking** by Thomas
Lundström / Grove Media (MIT, see `blocking/LICENSE` and `blocking/NOTICE`). Parts of the
add-on are adapted from **blender-mcp** by Siddharth Ahuja (MIT, see `NOTICE`).
