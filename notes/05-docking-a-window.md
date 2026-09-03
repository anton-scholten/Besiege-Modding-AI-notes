# Docking a uGUI window to the block mapper

## The problem

Besiege's block mapper is mesh UI drawn in world space; a panel built from UI
Factory prefabs is uGUI on a `Canvas`. The two **cannot share a hierarchy** — you
can't parent a `RectTransform` into the mapper and have it render, sort or lay out.
No "add my rows to the mapper" API either: its widgets are pooled objects bound to a
data holder (see [04-ui-factory.md](04-ui-factory.md)).

So a panel wanting to look like part of the mapper must be a separate window
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

The whole difficulty, and guessing wrong is easy. Make the panel log every part it
measures, once, and read it back out of the log. With a block open at 4K:

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
width, making width robust; only the frame reaches the bottom edge.

Three rules that look right and aren't — two were shipped:

- *the widest thing the mapper draws* is `WideShadow`, an eleventh wider than the
  window, bottom ~98 px above the window's. A panel docked to it is visibly too wide
  and lies across the mapper's lower half.
- *`Visual`, by name* sounds like a frame and is a 93-pixel button. A panel docked to
  it becomes a narrow strip beside the mapper.
- **`BlockMapper.upperLeft` and `lowerRight`** are public `Transform`s and look
  exactly like the window's corners. They aren't: `Awake` finds them with
  `GameObject.FindWithTag("upperLeft")` and `UpdateBackground` clamps the window
  against them. They are corners of the *screen area* the mapper may be dragged
  within.

Not available: `BlockMapper.background` is the frame and is private, and
`System.Reflection` is blacklisted. The `ContainerDetails` components under the
mapper (with public `Background`, `Top`, `Bottom`, `BackgroundPos`,
`BackgroundScale`) are **one per row**, not one per window, and
`BlockMapper.Container` is typed `IWidgetContainer`, exposing only `TopValue()` and
`ZValue()`.

## A docked panel wants no title bar

A panel docked to the mapper is the mapper's lower half, not its own window, so the
`Window` prefab's `TopBar` goes — and with it the drag handle (dragging the lower
half away from the upper half makes no sense) and the close cross, which would shut
only half of what looks like one window.

Hiding the bar is one `SetActive(false)`. Easy to miss: **the `ScrollView` is
anchored below the bar**, so hiding the bar alone leaves a bar's worth of empty frame
at the top. Stretch it over the whole window afterwards:

```csharp
rect.anchorMin = Vector2.zero; rect.anchorMax = Vector2.one;
rect.offsetMin = Vector2.zero; rect.offsetMax = Vector2.zero;
```

Leave the bar in place and the panel also carries the prefab's authored title —
"SAMPLE WINDOW" — which looks exactly like a label that failed to load.

## Closing with the mapper needs polling, not the close event

`BlockMapper.onMapperClose` doesn't fire for every way a mapper goes away — clicking
off the block, or the block being deselected, leaves a docked panel hanging over the
world with nothing behind it. Reconcile in `LateUpdate` instead, the way
[08-block-lifecycle.md](08-block-lifecycle.md) says to treat all these callbacks:

```csharp
BlockMapper mapper = BlockMapper.CurrentInstance;
bool up = mapper != null && BlockMapper.IsOpen && mapper.Block != null
          && ServesThisBlock(mapper);
```

**`BlockMapper.IsOpen` is static** while `CurrentInstance`, `Block` and `Current`
are instance members — `mapper.IsOpen` doesn't compile, and reaching for it is the
natural thing to write.

Keep the events too: cheap path for the common case. The poll is what makes the panel
honest.

## Recolouring a UI Factory Slider's track

The `Slider` prefab's children aren't named what a guess would guess, so
`transform.Find("Background")` misses and a hue band silently never appears. Find the
track by elimination — the `Slider` component already knows the other two:

```csharp
foreach (Image image in bar.GetComponentsInChildren<Image>(true))
{
    if (bar.fillRect != null && image.transform.IsChildOf(bar.fillRect)) continue;
    if (bar.handleRect != null && image.transform.IsChildOf(bar.handleRect)) continue;
    // this one is the track
}
```

## Bringing an `Options` selector's arrows in

Arrows are anchored to the ends of the control, so a full-width selector puts them at
the window's edges with the name marooned in the middle. No layout group to fight:
make the **control** narrower than its row and centre it, and the arrows come in with
it. 250 units against a ~434-wide panel reads well.

## Three things that are not obvious once the geometry is right

1. **Dock in `LateUpdate`.** The mapper is dragged by its own behaviour, so a panel
   placed in `Update` is placed against where the mapper *was* — one frame behind,
   reading as the join coming apart while dragging.
2. **Take the width before laying out the rows.** Rows sized to a width the mapper
   doesn't have means the panel is built wrong and must be rebuilt.
3. **Never return from the placement path without placing.** The costliest bug: on a
   width change the code set its rebuild flag and returned — and that same flag gated
   the placement call, so the panel never docked again and never followed a drag.
   Rebuild *and* place in the same frame.

## Moving the mapper's own rows: `Top` destroys `Z`

A mod re-laying-out the mapper's rows — compacting into two columns, say — places
them with `ContainerDetails.Top`. That setter is

```csharp
transform.position = new Vector3(BackgroundPos.x, value - TopOffset);
```

the **two**-argument `Vector3` constructor, so it silently sets the row's **z to 0**.
The mapper is mesh UI in world space, so z is the whole of a row's depth.

Besiege never suffers this because it always pairs the two.
`WidgetController`'s own layout loop:

```csharp
c.Top = lastBottom;                     // zeroes c's z
lastBottom = c.Bottom;
c.Z = widgetContainer.ZValue();         // ...and puts it straight back
```

and `BlockMapper.ZValue()` is `transform.position.z - 0.1f` — the mapper floats its
rows a tenth of a unit in front of its own window.

So **save `Z`, write `Top`, restore `Z`**:

```csharp
float z = row.Z;
row.Top = top;
row.Z = z;
```

Read it back from the row rather than calling `mapper.ZValue()`: a row owned by a
nested controller takes its depth from that controller's own container, not from the
mapper.

Symptom of getting this wrong is depth sorting that looks arbitrary — in the mod this
came from, an open menu selector's autocomplete option list drew *behind* the toggle
rows underneath it. Nothing about that suggests a row placement bug, which is why
it's worth knowing `Top` has a side effect at all. `Bottom` has the same shape and
the same problem.

## Make it say what it found

Log `docking to '<name>' at <rect>` once a session. Log output lands in `Player.log`
and in the in-game console with `show_logs true`. When the geometry is wrong that
single line is the difference between a diagnosis and another guess — the table above
came out of exactly that line.

## Related useful pieces

- `BlockMapper.CurrentInstance`, `.IsOpen`, `.Block`, and the static `onMapperOpen` /
  `onMapperClose` events are how a panel knows when to show itself and on what.
- `MapperType.DisplayInMapper` strips the mapper's own rows so the two windows don't
  show the same settings twice — see
  [03-keys-and-automation.md](03-keys-and-automation.md).
