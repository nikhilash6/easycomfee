# Blender blocking → video (EasyComfee)

**Blender locks the motion. The AI builds the world around it.**

Block the shot with colored boxes, let the user watch it in the viewport and, once they
approve, turn the greybox into a video with EasyComfee's **3D render → Video** (LTX 2.5).
The blocking is the only authority on camera, cuts and timing; the prompt only *dresses*
what the blocking already does.

Adapted from `seedance-blocking` (MIT, Thomas Lundström / Grove Media).

Tools: `blender_status`, `blender_get_scene`, `blender_execute_python`,
`blender_screenshot`, `blender_render`, `blender_import_media`, `previz_load_core`,
`previz_solve`, `editor_status`, `style_frame`, `blockout_to_video`, `editor_free_memory`.
More reading: `blocking_guide(topic="camera_rules" | "shot_grammar")`.

## Five rules

1. **No place named? A checkerboard and done.** `PV.checker()` is the default set: one
   line, real parallax on every axis. `posts=12` if a crane or orbit needs reference above
   the floor. **Only build a place when the request NAMES one.**
2. **Place named? There is no library: compose it from pieces.** `checker`, `slab`,
   `row`, `cyl`, `ground`, `light`, `light_row`, `sun`, `marker`, `actor`. A corridor, a
   street, a subway platform and a forest are the same six ideas arranged differently.
3. **Solve the camera in arithmetic before opening Blender.** Whip pans, hero out of
   frame, camera inside a wall: it all shows in the numbers. `previz_solve` finds it in a
   fraction of a second.
4. **Deliver in the VIEWPORT, never in a render.** Build, call `PV.viewport_ready()` and
   say it is ready to play. **Render nothing until the user approves the motion.**
5. **The conversation is the interface.** Notes arrive in chat ("start slower", "lower at
   the end"). Edit the spec, solve again, rebuild and say so. The user never opens the spec.

## Pipeline

### 0 — Check the connection
`blender_status`. If it fails, ask the user to open Blender and turn the Bridge on
(3D Viewport → N → Bridge → Start Bridge). If the scene has unsaved work (`dirty: true`)
that is not an earlier blocking, warn before `PV.wipe()`: it only deletes previz objects,
but `PV.reset()` changes the scene's fps, length and resolution.
`editor_status` gives the length limit: `limites.maquete.quadros` frames at 24 fps.

### 1 — Intake. Always start here.
A shot is specified when you know: **action · place · length · camera intent · framing arc.**
- **There is a request:** anything that names an action or directs the camera is enough.
  **Ask nothing.** Fill the gaps with the defaults, sum the shot up in four lines and build
  in the same turn.
- **No request at all:** ask once, in plain text, with the defaults: *"What's the shot?
  Action and camera are enough, e.g. 'the block runs, the camera passes it at knee
  height'. Default: checkerboard void, 10 s, calm camera."* One question, never more.

**Defaults:** checkerboard void · **10 s** (or less if `editor_status` says so) · rig
`gimbal` · single shot · hero = red block.

### 1b — Pick the RIG. The highest-leverage choice.
| the request says | rig | character |
|---|---|---|
| *(nothing about camera)* | `gimbal` **default** | smooth, never whips or stops |
| "steadicam", "floating", "oner" | `steadicam` | heavier, calmer, soft arcs |
| "handheld", "documentary", "raw" | `handheld` | looser, corrects, close |
| "locked", "just a pan", "tripod" | `tripod` | pan/tilt only, **no travel** |
| "dolly", "tracking", "push in" | `dolly` | straight rail, calm |
| "crane", "rises over" | `crane` | big arcs through height |
| "robot arm", "motion control", "Bolt" | `robo_arm` | **whips**, hard stops |
| "macro", "probe lens", "inside the object" | `probe_macro` | centimeters away, fixed lens |
| "FPV", "drone", "dive", "flies through" | `fpv_drone` | never hovers, huge speed, ultra wide |
| "cable cam", "zipline", "flies alongside" | `cable_cam` | straight line at speed |
| "car mount", "chase" | `car_mount` | travels fast, barely turns |

`previz_solve(name="", rigs=True)` lists the numbers. A `limits` block overrides the rig
field by field. Unknown rig = error.

### 2 — Write the spec (Python text). The set is `checker()` unless a place was named.
```python
SHOT = {
  "name": "myshot", "fps": 24, "seconds": 10,
  "rig": "gimbal",
  "subject": {
    "mode": "profile",            # walk/car on a straight axis; speed is the control
    "size": [0.50, 0.35, 1.80], "axis": "y", "start": [0, 0, 0],
    "speed": [(0.0, 1.4), (10.0, 1.4)],        # (t, m/s), interpolated and integrated
    # optional: "anchor": {"at_t": 10.2, "coord": -4.2}, "lateral_drift": [0.08, 4.0],
    # "yaw_events": [{"t0":9.9,"t1":11.3,"t2":12.7,"t3":14.3,"angle":0.95}]
  },
  # or "mode": "waypoints" with "waypoints": [(t, x, y, z), ...] for a free path.
  # STANDING subject: "speed": [(0.0, 0.0), (T, 0.0)].
  "shots": [                      # single shot == list of one
    {"t0": 0.0, "t1": 10.0, "name": "wide", "camera": {
        "fit": 0.80,              # bigger = subject fills more of the frame
        "aim_distance": 5.0, "subject_smooth": 6, "lens_smooth": 8,
        # "bounds": {"x": [lo, hi], "z": [lo, hi]},   # clamping FAILS a gate
        "waypoints": [            # ABSOLUTE times on the master timeline
          {"t": 0.0, "pos": [3.5, -4.0, 1.6], "lens": 35, "aim": [0, 0, 0.95]},
          {"t": 10.0, "pos": [3.0, 12.0, 1.4], "lens": 35, "aim": [0, 0, 0.95]},
        ]}},
  ],
  "beats": [(0.0, "what the frame says here")],
}
```
`pos` is **world space**; `aim` is an **offset from the subject**. Author the camera as
offsets from a moving subject and convert (`pos = [ox, subject_y(t) + oy, oz]`).
The keys `build` and `lights` do nothing: the set only exists when you call `PV.*` in step 5.

### 3 — Solve. Iterate here, not in Blender.
`previz_solve(name="myshot", spec="<the whole SHOT text>")`. Six gates **per shot**:
subject in frame, rotation rate, distance to the subject's BODY, camera never parks,
camera never beats the rig's top speed, no bounds clamping. `passed: true` (exit 0) = all
gates pass and `bake` holds the bake.json path. **Do not open Blender until it passes.**
On a failed gate, read `blocking_guide(topic="camera_rules")`.

### 4 — Load the core in Blender (once per Blender session)
`previz_load_core()`. Afterwards every `blender_execute_python` starts with
`PV = bpy.app.driver_namespace["PV"]`. A `KeyError` means Blender restarted: run it again.

### 5 — Build and hand over the viewport, in one call
```python
PV = bpy.app.driver_namespace["PV"]
PV.wipe()                       # clears the previous pass, nothing else
PV.reset(fps=24, seconds=10)
PV.checker()                    # THE SET. posts=12 for crane/orbit
PV.sun()
PV.actor("HERO", color="red", oriented=True)
PV.load_bake(r"<bake path from previz_solve>")   # subject + one camera per shot + cut markers
PV.viewport_ready()
result = PV.audit()
```
`PV.audit()` re-measures rotation, distance and framing from Blender's *evaluated*
matrices. If `PASS` is false, go back to step 3. Then **look**:
`blender_screenshot(view="camera", frame=...)` at the start, middle and end of each shot.
Only then tell the user: **ready, press Space in the viewport.** Do not render.

### 6 — Notes, solve again, rebuild
Edit the spec, `previz_solve`, build again. Seconds per iteration.
`PV.backup("S02_camera_v2")` after anything worth keeping.

### 7 — Only after approval: the look, then the video
Ask now (not at intake) for the style layer: photoreal, stylized, animation.
1. **Style image — `style_frame(prompt=...)`.** Renders the FIRST frame of the shot in the
   blocks' colors and has FLUX 3 turn it into a photo, keeping the framing and every object
   (Qwen Image 2.1 takes over if FLUX 3 is missing). Tell the user which model made it
   and that they can pick another with `engine`: `qwen21`, `kroma` (more illustrated),
   `klein`, `mage`, `qwen_edit` (also on Comfy Cloud) or `control`. This image is the anchor of the whole
   video: whatever it adds or moves, the video repeats. ~1 min: iterate here, not on the
   video. Prompt: "Turn this 3D blockout into a real cinematic photograph of <place, light>.
   The red box becomes ..., the blue box becomes ...", one description per block.
   **Compare it with the guide (`guia`) before going on:** same framing, every block there
   once, nothing new. If something is off, change the prompt or the `seed` and run it again.
   Show the image; go on only when approved.
2. **Video — `blockout_to_video(prompt=..., style_image=<approved image>)`.** Renders the
   animation, sends it to **3D render → Video** and puts the result behind the camera
   (`import_mode`). Do NOT add `keyframes` by default: style frames made separately each
   drift in their own way and the video follows all of them. Use them only when each one
   was checked against its guide frame. `effect="profundidade"` (Follow depth) when the
   blocks' colors or the checkerboard leak into the video.

### 8 — Deliver
In chat: the final video path, the style image, both prompts (each in its own code block,
ready to copy) and the asset list as a table (block → what it became). The video is
already behind the camera: Numpad 0 to compare with the blocking.

## The prompt for EasyComfee
- **One paragraph, 60–200 words, present tense, English.**
- **Say what each block IS.** The model doesn't know the color code: "the red box is a
  woman in a long red coat walking away from camera; the grey slabs are wet concrete walls".
- Environment, materials, light, time of day, weather, lens and film stock.
- For the **video**, add the action and the camera move in words that match the blocking
  ("slow tracking shot from behind, camera rising at the end").
- **Name what the proxies never were:** "the upright posts are low bollards, never people".
- The checkerboard is only a parallax reference: describe the real floor you want
  ("cracked asphalt") so it does not become a checkered floor.

`style_frame` prompt = the first frame only (no motion). `blockout_to_video` prompt = the same
world + action + camera.

## Limits that change the blocking
- **Length:** `editor_status` → `limites.maquete.quadros` (353 frames ≈ 14.7 s on a 16 GB
  GPU). A longer sequence → one `blockout_to_video` per group of shots.
- **8k+1 frames:** `blockout_to_video` pads the guide to the next 8k+1 so a 10 s shot comes
  out at 10 s. The last 2 frames lose a little sharpness: put nothing important there.
- **One GPU for both:** the tools render in Blender first, then generate. If memory runs
  out, `editor_free_memory` and try again. Rendering freezes Blender's UI while it runs.
- **Sequences with cuts:** the safe path is one `blockout_to_video` per shot (its
  `frame_start`/`frame_end` and `camera`), the same style image for all, `import_mode="vse"`.

## Camera moves around still objects
3D render → Video only sees motion it can read in the guide. If the objects stand still and
only the camera moves (orbit, dolly, crane), the guide MUST show the world moving: keep
`PV.checker(posts=12)` and add something behind the subject (a `row` of slabs for buildings
or walls). With a plain floor and an empty background the model invents a still background
and moves the objects instead. In both prompts say the objects stand still and name the
move: "the objects stand still; the camera slowly orbits the crate from right to left, the
buildings slide behind it". Give each block ONE identity in the prompt, or the model adds a
second object for the extra description.

## Build defaults — never ask
- **The hero is a red block**, 0.50 × 0.35 × 1.80 m for a person. Never a character or rig.
- **Color is identity.** Extra subjects get contrasting colors from `PV.PALETTE`; the
  prompt says what each color is. `oriented=True` paints the direction (+Y red, −Y black).
- **Build only what gives the camera parallax.** Repeated verticals, a clear destination,
  ceiling lines for the fast parts, a floor line for perspective. Then stop.
- 24 fps, 1920×1080, EEVEE, Z up, meters, radians.

## Traps that already cost time
- **Blender 5.x slotted actions:** `animation_data_clear()` only unlinks; `PV.bake()`
  destroys first. `action.fcurves` does not exist in 5.2.
- **Lens keys live on `camera.data`**, not on the object.
- **Track To flips near the nadir.** Approach a top view from ONE azimuth and stop ~86°.
- **Catmull-Rom, not per-segment easing** (smootherstep zeroes speed at every waypoint).
- **Don't cross the subject** in anything narrower than ~6 m: it forces a whip or a very
  long lens. Stay on one side; vary height, side, distance and lens.
- **Never two opaque faces on the same plane** (z-fighting). `ground()` already sits 2 cm down.
- With markers bound to cameras, the render follows the markers even if you pass `camera`;
  to isolate one shot use its `frame_start`/`frame_end`.
