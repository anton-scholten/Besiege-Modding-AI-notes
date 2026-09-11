# Rendering the scene yourself: cameras, render textures, drawing to the window

Found making Besiege render stereo eyes for a VR helper app. Nothing here needs VR;
it is what any mod rendering the scene a second time — a picture-in-picture, a
minimap, a camera feed — runs into. Linux player, OpenGL 4.5, Unity 5.4.0f3.

## Drawing to the window after `WaitForEndOfFrame` does nothing

The usual recipe for a full-window overlay — coroutine, `yield return new
WaitForEndOfFrame()`, `RenderTexture.active = null`, `GL.PushMatrix`,
`GL.LoadPixelMatrix`, `Graphics.DrawTexture` — **draws nothing** on Besiege's Linux
player. No error, no log line; the pixels simply never reach the screen, with either
pixel-matrix orientation. Measured by capturing the window from outside and reading
the pixels back.

**`OnPostRender` of a camera of your own does work.** A camera that renders nothing
itself and only hosts the callback:

```csharp
Camera cam = go.AddComponent<Camera>();
cam.clearFlags = CameraClearFlags.Nothing;
cam.cullingMask = 0;
cam.depth = 1000f;          // after every game camera
go.AddComponent<MyCompositor>();   // OnPostRender: GL.PushMatrix; GL.LoadPixelMatrix(); Graphics.DrawTexture(...); GL.PopMatrix
```

`GL.LoadPixelMatrix()` with no arguments is bottom-left origin; convert a top-left
rect with `y = Screen.height - y - height`.

**A camera's render texture is not opaque, and `DrawTexture` blends.** The main camera
renders deferred and leaves alpha well below 1, so a render texture drawn with
`Graphics.DrawTexture`'s default material lets whatever the window held show through —
here a ghost of the full-size HUD across the picture. Draw it with a material on
`Hidden/BlitCopy` (on the player's always-included shader list, so `Shader.Find` gets it),
which writes colour without blending. **BlitCopy samples the other way up** from
DrawTexture's own material: pass the rect flipped, `new Rect(x, y + h, w, -h)`. Both
measured.

**Nothing clears what no camera draws.** Squeeze the game's cameras into part of the window
(below) and the rest keeps its last contents indefinitely. Paint it yourself —
`DrawTexture` of `Texture2D.blackTexture` through the same opaque material.

`WaitForEndOfFrame` is still the right place to *render* — every game camera has its
final transform by then — just not to draw to the window. Render into textures there,
draw them from the compositor camera next frame.

## `Camera.Render` on the game's own cameras, then put them back

Copying a camera (`CopyFrom`) does not copy its image effects, and the main camera
carries several (`EdgeDetectEffectNormals`, `AntialiasingAsPostEffect`, bloom). Render
the game's cameras themselves instead, in depth order, into one texture:

- save each camera's `localPosition`, `localRotation`, `rect`;
- set `transform.position/rotation` to your pose (not `worldToCameraMatrix`: fog and
  effects read the transform), `targetTexture`, `rect = (0,0,1,1)`, and a
  `projectionMatrix` if you need one;
- `Render()`;
- restore `targetTexture = null`, `ResetProjectionMatrix()`, `rect`, and the **local**
  pose. Restoring world poses in depth order breaks when one camera is another's child
  — a parent restored after its child moves the child again. Local poses are
  order-independent.

Done within one `WaitForEndOfFrame`, the game never sees the change. Runs without error
on the title screen; image correctness in a level still to confirm.

## The title screen is all orthographic

`vr dump`-style inventory, `TITLE SCREEN`:

| Camera | depth | mask | clear | ortho |
| --- | --- | --- | --- | --- |
| `Main Camera` | -1 | `0xFF77DDDF` | Color | yes |
| `Title CAm` | 0 | layer 19 | Depth | yes |
| `HUD Cam` | 1.16 | layer 13 | Depth | yes |
| `FileBrowserView Cameras/Blur Camera (Late)/cam` | 1.3 | none | Depth | yes, inactive |
| `FileBrowserView Cameras/HUD Cam (Late)` | 1.5 | layer 19 | Depth | yes, inactive |

So "every perspective camera" is empty there; a mod filtering on `orthographic` needs a
fallback. Root canvases: `UIFactory` (layer 0), `JournalCanvas` (layer 5, order 10),
`FileBrowserView/Tabs` (layer 19), all Screen Space - Overlay.

## Squeezing the game into part of the window

Two changes move the whole game view and interface into a sub-rectangle, and the
result looked right on the title screen:

- nest every camera's `rect` inside the target viewport (`x' = vx + x * vw`, …);
- switch every root canvas from `ScreenSpaceOverlay` to `ScreenSpaceCamera` with a
  camera of yours whose `rect` is that viewport. An overlay canvas always covers the
  whole window and has no viewport to move.

Reconcile both every frame and remember originals — cameras and canvases come and go
with scenes (see [08](08-block-lifecycle.md), *reconcile, do not react*). Mouse
hit-testing inside the moved view: not yet checked.

## Finding Besiege's menus on screen

The in-game interface is mostly mesh UI under one scene object, `HUD`, drawn by the
orthographic `HUD Cam`. **Each menu is a direct child of `HUD`**; in the level editor:

| Child | What it is |
| --- | --- |
| `TopBar` | the top toolbar |
| `BottomBar` | the block bar |
| `Snap left` | the Level Editor window |
| `ZONE COMPLETE` | a banner — active, with renderers, **all the time** |

and some fifty more, most inactive (`FileBrowserView`, `OptionsMenu`, `SKIN PACK
WINDOW`, the warnings) or drawing nothing. A child's screen rectangle is the union of its
renderers' bounds projected through the topmost camera whose mask has their layer (the
recipe in [05](05-docking-a-window.md)).

Three things make that rectangle wrong as it stands:

- **Off-screen parts.** `BottomBar`'s renderers span about fifteen screen widths — every
  block in the game, laid out in a strip — and `TopBar`'s three. Clip to the screen.
- **Menus that are shown but invisible.** `ZONE COMPLETE` stays active with enabled
  renderers covering the whole screen, and a uGUI `GenericUIPopup` likewise.
  `Renderer.isVisible`, the material's `_Color`/`_TintColor` alpha, and parent
  `CanvasGroup` alpha **all failed to rule them out**. What worked is looking at the
  pixels: draw the menus over a solid clear colour and a menu whose own area (minus the
  smaller menus inside it) is all that colour has nothing to show.
- **Hit-testing the topmost.** A full-screen invisible overlay is topmost everywhere, so
  "which menu is under the mouse" wants the *smallest* rectangle containing the point.

## Steering the game's mouse picking without moving the mouse

Every world pick in Besiege is `camera.ScreenPointToRay(mouse)` and a physics raycast:
`AddPiece.Update` (placing and hovering blocks, via its `mainCam`), `LevelEditor.LateUpdate`
(`MouseOrbit.cam`), `TransformTool.CastMouseRay` and `SelectionTool` (`Camera.main`), the
key mapper, the god tools, `Modding.Game.BlockEntityMouseRaycast`. All the same camera.

`ScreenPointToRay` **honours an overridden `worldToCameraMatrix` and `projectionMatrix`**
— measured: with the main camera's view set to look down an arbitrary ray, the ray the
game computes at the viewport centre matched it to 0.00°. So a mod that can put the mouse
on a known pixel (from outside, or by the player) can aim all of the game's picking along
any ray, without touching the transform `MouseOrbit` drives, by giving the camera a small
viewport around that pixel, a narrow projection and the view matrix of the ray. Set
`cullingMask = 0` while it is aimed so it draws nothing, and put mask and matrices back
before anything renders from that camera for real.

**The ray starts on the camera's `nearClipPlane` property**, not on the near plane of
the overridden projection. With Besiege's main camera at 1.54 the picked ray began 1.54
units down the aimed one, missing everything closer. Stand the view that far behind the
ray's origin.

Nothing in Besiege resets those matrices each frame, with one exception:
`MouseOrbit.ApplyApproxOrthographic` / `ClearApproxOrthographic` set and reset the main
camera's projection for its approximate-orthographic view.

## A camera rendering to a texture gets no mouse events

`UnityEngine.SendMouseEvents.DoSendMouseEvents` skips any camera whose `targetTexture`
is set (when called with its skip-render-texture argument, as the player's input step
does) and any whose `pixelRect` does not contain the mouse. Besiege's own interface — the
file browser, popups, most buttons — is colliders answering `OnMouseOver`, so pointing
the HUD cameras at a render texture makes it deaf. Read from the IL of the shipped
`UnityEngine.dll`.

To have the interface in a texture *and* clickable, leave the cameras on the screen with
their own viewports, and render them a second time into the texture: set `targetTexture`,
call `Render()`, clear it again, all at end of frame.

If what they draw on the screen is going to be covered anyway, do not pay for it twice:
`Camera.onPreCull += c => { if (c is one of them && c.targetTexture == null) c.cullingMask = 0; }`
and `Camera.onPostRender` puts the mask back. Culling happens after `onPreCull`, so the
render draws nothing; mouse events read the mask outside rendering and still work.
Measured: 61 → 95 fps at 4K for Besiege's HUD cameras. Remember the masks per camera and
restore every one in `onPostRender`.

## The player pauses when its window loses focus

Observed, not read from the game: with another window focused, a mod polling every
frame (here, `UnityWebRequest` to a local helper) stopped dead — no requests, no log
lines, process still alive — and a real-time timeout in it fired. That is Unity's
behaviour with `Application.runInBackground` false. A mod whose player is looking at
something other than the game window — a headset, a second screen — sets it true while
it needs it and puts the old value back after. Confirmed: with it set, focusing another
window left the polling at full rate.

## `UnityWebRequest` polling a local process keeps up with the frame rate

One request in flight, the next started the moment one finishes:

```csharp
if (req != null && !req.isDone) return;        // also: Abort() after a real-time timeout
if (req != null) { /* req.isError, req.responseCode, req.downloadHandler.data */ req.Dispose(); }
req = UnityWebRequest.Get("http://127.0.0.1:47811/frame"); req.Send();
```

Against a small C++ server on loopback this made ~146 requests a second with the game
at 146 fps: it runs as fast as the frame loop polls it. 5.4 names: `Send()` (not
`SendWebRequest`), `isError` (not `isNetworkError`). It is the only network API the
blacklist leaves ([01](01-loader-and-blacklist.md)), and the way a mod talks to a
native program it cannot load.

## Checked

Besiege 5.4.0f3, Linux, September 2026. The `WaitForEndOfFrame` failure, the
`OnPostRender` compositor, the title-screen inventory, the nested panel, the focus pause
and the polling rate are measured; `Camera.Render` image correctness in levels and mouse
hit-testing in the nested view are not yet.
