# Docking a uGUI window to the block mapper

## The problem

Besiege's block mapper is mesh UI drawn in world space; a panel built from UI
Factory prefabs is uGUI on a `Canvas`. The two **cannot share a hierarchy** — you
cannot parent a `RectTransform` into the mapper and have it render, sort or lay
out. There is no "add my rows to the mapper" API either: its widgets are pooled
objects bound to a data holder (see [04-ui-factory.md](04-ui-factory.md)).

So a panel that wants to look like part of the mapper has to be a separate window
*positioned against it*, in screen space, every frame.

## The recipe

```csharp
// 1. The mapper's window is a renderer named "Background" -- the tallest one.
BlockMapper mapper = BlockMapper.CurrentInstance;
Renderer[] parts = mapper.GetComponentsInChildren<Renderer>(false);

// 2. Find the camera that draws it, by layer: the mapper is in the world, and
//    only the camera whose culling mask includes its layer knows where on screen
//    it lands. Take the topmost such camera -- the interface is drawn last.
Camera eye = null;
foreach (Camera c in Camera.allCameras)
    if ((c.cullingMask & (1 << part.gameObject.layer)) != 0
        && (eye == null || c.depth > eye.depth)) eye = c;

// 3. Project that renderer's world bounds to screen pixels.
Bounds box = part.bounds;
Vector3 a = eye.WorldToScreenPoint(new Vector3(box.min.x, box.min.y, box.center.z));
Vector3 b = eye.WorldToScreenPoint(new Vector3(box.max.x, box.max.y, box.center.z));

// 4. Screen pixels to canvas units. With a CanvasScaler matching on height
//    against a 1080-tall reference, one unit is one pixel at 1080p.
float scale = 1080f / Screen.height;

// 5. Place the window. Anchors and pivot at the centre, so anchoredPosition is
//    the window's centre relative to the screen's.
float left   = (frame.xMin - Screen.width  * 0.5f) * scale;
float bottom = (frame.yMin - Screen.height * 0.5f) * scale;
windowRect.sizeDelta = new Vector2(frame.width * scale, height);
windowRect.anchoredPosition = new Vector2(left + windowRect.sizeDelta.x * 0.5f,
                                          bottom - windowRect.sizeDelta.y * 0.5f);
```

## Which renderer is the window

This is the whole difficulty, and guessing wrong is easy. Make the panel log every
part it measures, once, and read it back out of the log. With a block open at 4K:

| Name | Size (px) | Bottom (px) | What it is |
| --- | --- | --- | --- |
| `Background` | 874.80 × 389.88 | 1540.87 | **the window** |
| `Background` | 874.80 × 281.88 | 1540.87 | a section inside it |
| `Background` | 874.80 × 174.96 | 1658.59 | a section inside it |
| `WideShadow` | 972.00 × 194.40 | 1638.37 | the shadow behind it |
| `Mask` | 874.80 × 1555.20 | 267.55 | the scroll region |
| `Visual` | 93.31 × 93.31 | — | a button |
| `BG`, `TooltipText`, `KeyPrefab(Clone)`, … | small | — | rows and widgets |

**The window is the tallest renderer named `Background`.** They all share its
width, which makes the width robust; only the frame reaches the bottom edge.

Three rules that look right and are not — two of them were shipped:

- *the widest thing the mapper draws* is `WideShadow`, an eleventh wider than the
  window and with its bottom ~98 px above the window's. A panel docked to it is
  visibly too wide and lies across the mapper's lower half.
- *`Visual`, by name* sounds like a frame and is a 93-pixel button. A panel docked
  to it becomes a narrow strip beside the mapper.
- **`BlockMapper.upperLeft` and `lowerRight`** are public `Transform`s and look
  exactly like the window's corners. They are not: `Awake` finds them with
  `GameObject.FindWithTag("upperLeft")` and `UpdateBackground` clamps the window
  against them. They are the corners of the *screen area* the mapper may be
  dragged within.

What is not available: `BlockMapper.background` is the frame and is private, and
`System.Reflection` is blacklisted. The `ContainerDetails` components under the
mapper (with their public `Background`, `Top`, `Bottom`, `BackgroundPos`,
`BackgroundScale`) are **one per row**, not one per window, and
`BlockMapper.Container` is typed `IWidgetContainer`, which exposes only
`TopValue()` and `ZValue()`.

## Three things that are not obvious once the geometry is right

1. **Dock in `LateUpdate`.** The mapper is dragged by its own behaviour, so a panel
   placed in `Update` is placed against where the mapper *was* — one frame behind,
   which reads as the join coming apart while dragging.
2. **Take the width before laying out the rows.** If the rows are sized to a width
   the mapper does not have, the panel is built wrong and has to be rebuilt.
3. **Never return from the placement path without placing.** The bug that cost the
   most: on a width change the code set its rebuild flag and returned — and that
   same flag gated the placement call, so the panel never docked again and never
   followed a drag. Rebuild *and* place in the same frame.

## Make it say what it found

Log `docking to '<name>' at <rect>` once a session. Log output lands in
`Player.log` and in the in-game console with `show_logs true`. When the geometry is
wrong that single line is the difference between a diagnosis and another guess —
the table above came out of exactly that line.

## Related useful pieces

- `BlockMapper.CurrentInstance`, `.IsOpen`, `.Block`, and the static
  `onMapperOpen` / `onMapperClose` events are how a panel knows when to show
  itself and on what.
- `MapperType.DisplayInMapper` strips the mapper's own rows so the two windows do
  not show the same settings twice — see
  [03-keys-and-automation.md](03-keys-and-automation.md).
