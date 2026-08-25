# UI Factory, and why you need it

## Besiege's own interface cannot be borrowed

The block mapper — the panel that appears when you click a block — is **not** uGUI.
It is mesh UI drawn in world space: `Modding.Mapper.SelectorElements` hands out
`MakeText` (a `DynamicText`), `MakeBox` and `MakeTexture` (`MeshRenderer`s)
positioned by `Vector3`, and `BlockMapper` places the lot with `COMPONENT_Z`,
`upperLeft` and `lowerRight`.

`MSlider`, `MToggle` and friends are *data models* — `MapperType` subclasses with
`Value`/`IsActive` and serialisation, not widgets. The widgets are pooled
`BlockMapperInternal.ParameterWidget` objects bound to a `SaveableDataHolder`, i.e.
to one specific block or entity.

For a mod that wants a window of its own, that means:

- the mapper's widgets cannot be reused for non-block settings; they are bound to
  a data holder and to the mapper's own container;
- `SelectorMaterials` — which exposes `LightBackground`, `DarkBackground`,
  `DarkElement`, `RedHighlight` — has a non-public constructor taking
  `InternalModding.Mapper.CustomSelectorReferences`, and **`InternalModding` is
  blacklisted**, so those materials are only reachable from inside a custom mapper
  selector.

So a standalone panel cannot reuse the machinery and cannot sample the real
colours either. Reproducing the look by hand gets close and no closer — the usual
result is a panel of the wrong shade that is never quite as transparent as the
game's.

## What UI Factory is

[UI Factory 3](https://gitlab.com/dagriefaa/ui-factory-3) (Workshop item
`2913469777`) ships Besiege's widgets as ordinary **uGUI prefabs** with the colours
baked in. It is the way to have a window that looks like part of the game.

`Besiege.UI.Mod.OnAllResourcesLoaded` registers them under the package name
`UIFactory3`:

```
Empty     Icon        Text          Text Button   Text Toggle   Text Dropdown
Icon Button           Icon Toggle   Button Dropdown             Input Field
Slider    Options     Scroll View   Blur          Panel         Mask     Window
Text Tooltip (Vis Only)             Custom Tooltip (Vis Only)
WorldCanvas           KeymapCanvas
```

Twenty-one, and the names are the exact strings the call wants — note that the two
tooltips really are registered as `(Vis Only)` while the asset they come from is
named `(Visual)`. One sprite is registered alongside them, `Masked Background`.
That list was read out of `OnAllResourcesLoaded`'s IL; the way to re-read it for a
newer UI Factory is in [06-reading-the-game.md](06-reading-the-game.md).

Instantiate one with `Besiege.UI.Make.Prefab(package, name, parent)`.

Ones worth knowing:

- **`Options`** (carrying `Besiege.UI.Bridge.Option`) is the game's own
  `< choice >` selector, the control the mapper itself uses for a menu. Its
  public surface is `previous` and `next` (`Button`), `label` (`Text`), `options`
  (`List<string>`, not an array), and the `Index` / `Value` properties;
  `onValueChanged` is a nested `Option.OptionEvent : UnityEvent<int>`, so it
  reports the **index** even though `Value` is a string. The arrows are anchored
  to the ends of the control with no layout group to fight; the way to move them
  nearer the label is to make the whole control narrower.

  **Assigning `options` does not redraw the label.** Only `Index`'s setter writes
  `label.text`, so a new list has to be followed by `option.Index = i` *even when
  the index has not changed* — otherwise the control keeps showing the placeholder
  the prefab was authored with ("Option A"), which looks exactly like a list that
  failed to load. Setting `Index` also fires `onValueChanged`, so guard against
  reentry.
- **`Text Toggle`** is a real toggle, not a button painted to look like one.
- **`Input Field`** carries the behaviour that stops Besiege acting on whatever is
  being typed. A hand-built box has to solve that itself, and a field must not be
  written to while `isFocused` or the caret jumps out from under the typist.
- **`Window`** is more than a frame: `Window` (Image, `StopsZoomWhenHovered`) with
  three children — `Blur`, `TopBar` (Image, a `Drag` already targeting the window,
  holding `Text` and `CloseButton`) and `ScrollView`, a full `ScrollRect` over
  `Viewport/Content` with both scrollbars, set to hide them when the contents fit.

Two consequences of that last one. Build rows into **`ScrollRect.content`** and
size the content to what was built: rows put on the window instead leave the
scroll view holding the prefab's own 500-unit placeholder, which is taller than
any panel, so the scrollbar sits there permanently beside an empty scroll area.
And do not add your own `Drag` or `StopsZoomWhenHovered` — they are already there.

If you hide the `TopBar` (for a window with no title of its own), stretch the
scroll view over the whole window afterwards; it is anchored below the bar and
will otherwise leave a bar's worth of empty frame at the top.

Small things: UI Factory's `Text` carries a `Translator` that will put the
prefab's own wording back at the next language change, so take it off any label
you write into. Its controls carry a `ScaleAnimation` that swells them on hover,
which is right for a button and wrong for a full-width row: `ButtonHoverScale` and
`ButtonPressedScale` are non-public and serialised into the prefab, and reflection
is blacklisted, so the numbers cannot be read or written — but `Target` **is**
public, so the animation can be pointed at a decorative child instead of disabled
outright.

## Four more that cost something to find

**`Make.Prefab` throws if the resources are not loaded.** Gate construction on
`Make.OnReady(package, action)` rather than on your own idea of when the game is
ready.

**`Make.ScreenCanvas` is recreated on every scene change.** Anything parented into
it disappears at the next load, which reads as the panel "randomly" vanishing. A
persistent overlay needs its own `DontDestroyOnLoad` canvas; UIF3 prefabs parent
into one perfectly well.

**Match the canvas scaler.** UIF3 authors against 1920×1080 with
`matchWidthOrHeight = 1`. Any other setting renders the game's own widgets at the
wrong size beside the game's own UI, which is the one thing borrowing the prefabs
was supposed to prevent.

**The press animation eats clicks at a control's edge.** `ScaleAnimation` writes
`Target.localScale`, and on UI Factory's buttons `Target` is the control's own
`RectTransform` — which is also what the raycaster tests. Pressing shrinks the
click target out from under the pointer, and uGUI only turns a press into a click
if the pointer is still over the same control when the button comes up. So the
outer few percent of every such control animates on press and then never fires.
It goes unnoticed wherever the artwork sits well inside its box (an icon drawn at
42% of a generous button) and is obvious wherever the artwork runs to the edge (a
20px icon button, a toggle lit across a whole row).

The fix is a transparent child with `raycastTarget` on, anchored *outside* 0..1 by
half the press shrink, so that at the pressed scale it still covers the control's
resting bounds — proportional anchors mean it survives later resizes, and a hit on
a child dispatches to the first handler above it. Assume a deeper press than the
prefab uses, since the number cannot be read and erring deep costs nothing.
Beware applying it to controls that tile: the child reaches past its parent, and
two of them meeting will argue over the seam. Sliders are unaffected — they act on
press and drag, not on release.

## Tooltips

`Besiege.UI.Bridge.Tooltip` is a hover handler that goes on the hovered control;
the panel it opens is a separate prefab (`Text Tooltip (Vis Only)`) which is inert
on its own — background, label, triangle, no behaviour. Public surface worth
knowing: `TooltipParent` and `Triangle` (`RectTransform`), `Direction`
(`Tooltip.Dir`), `FadeSpeed`, `IsOpen`, `ExtendedPosition`, and a **static**
`Func<bool> TooltipsActive` that switches tooltips off globally.

For a panel that has to open on something other than hover, spawn the visual
prefab, place it, and toggle `SetActive` — its renderers are opaque, and it is
`OnValidate` → `OnDisable` that hides them. The only part of the handler worth
copying is the triangle, which is two assignments: `Dir.Up` anchors it to
`(0.5, 0)` and rotates 180°, `Dir.Down` to `(0.5, 1)` at 0°, `Left` / `Right` to
`(1, 0.5)` / `(0, 0.5)` at 270° / 90°.

The prefab lays itself out: the root carries a `VerticalLayoutGroup` and a
`ContentSizeFitter`, and the `Background` child is sized from the root rather than
from the label — which is a **sibling** of it, not a child. Two consequences.
Sizing the panel by hand does nothing, because the fitter overwrites it on the
next layout pass; and to reserve room inside the panel (for an icon beside the
text, say), pad the layout group rather than resizing anything.

## A window sized to its contents needs an edge to grow from

The `Window` prefab is pivoted in its middle, which is right for dragging and
wrong for resizing: a row that appears moves the title bar up by half the row's
height, and the window
slides out from under the pointer that just caused it. Keep the last height and
offset `anchoredPosition.y` by half the difference on every resize, so the top
edge holds still and the bottom does the moving. Exempt the first pass, or the
window opens somewhere other than where it was placed.

## Depend on it softly

A mod that requires UI Factory is a mod that does not load without it. The
alternative costs one rule: **every mention of `Besiege.UI` lives in one file.**

A type that cannot be resolved fails when the method mentioning it is compiled, so
confining the mentions to one wrapper class means a single guarded call decides
whether the panel can exist:

```csharp
public static bool Available
{
    get
    {
        if (asked) { return available; }
        try
        {
            available = Besiege.UI.Make.Instance != null
                     && Modding.ModResource.AllResourcesLoaded;
        }
        catch (Exception) { available = false; }
        asked = available;      // only cache a yes: "not yet" is not "not installed"
        return available;
    }
}
```

Two details in that: UI Factory loads its bundle a moment after the mod does, so a
single early ask answers "no" wrongly — cache only the affirmative. And while it is
genuinely absent, each ask costs a caught `TypeLoadException`, so ask on a timer
rather than every frame if the answer drives per-block behaviour.

## If you build a text field by hand

There is no input prefab in some builds, and a value you want typed over may be a
label you already drew. A `Text` with a `UnityEngine.UI.InputField` built round it
works, with the `Text` as a **child** of the field rather than the same object —
an InputField moves a caret about inside itself. From then on the field drives that
Text, so write values through `InputField.text`, never to the label, or the field
overwrites you on its next update.

Two behaviours have to be added back, both of which UI Factory's own `Input Field`
already carries:

- **hold Besiege's keyboard off** while the field has focus, or the letters drive
  the camera and fire block keys. `StatMaster.SetInMenu(bool)` is the lock — see
  [08-block-lifecycle.md](08-block-lifecycle.md) for the counting rule;
- **do not write to the field while `isFocused`**, or the caret jumps out from
  under the typist. Skip the refresh for whichever control has focus.

For "a click selects the contents, a second click puts the caret where you
clicked": set `selectionAnchorPosition = 0` and `selectionFocusPosition =
text.Length`, but **a frame after** you notice focus. The click that focused the
field places its caret *after* your `Update` runs, so a selection made in the same
frame is dropped. Deferring one frame lands it last, and works whether you observe
the focus in the click frame or the one after.

## Committing a setting is not the same as setting it

A mapper value is stored twice: the live one, and the one the block loads from.
Assigning `MapperType.Value` writes only the first, so a panel that stops there is
heard now and forgotten on save. `BlockMapper.OnEditField` reconciles them —
reserialising the block and adding an undo entry, which is not free. Write live on
every drag frame and commit once, when the mouse comes up.

## Rebuild or rebind, but write every caption every time

If you keep one window and reuse it for the next block with the same *shape* — the
same number of rows and toggles — then a block with the same shape but different
control names will show the previous block's captions. Write every caption from
`MapperType.DisplayName` on every open, the fixed rows included. The symptom
otherwise is a piano with a PALM MUTE where its SUSTAIN should be.

## The Bridge components, in full

`Besiege.UI.Bridge.dll` is where the behaviours live, and most of them are public
and reusable on objects of your own. The whole list, so you know what exists before
building one yourself:

```
Drag                Resize              Tooltip             ScaleAnimation
BlurHandler         CustomMaterialHandler                   LetterSpacing
GraphicRaycaster    Option
Behaviours.Translator                   Behaviours.HoverListener
Behaviours.StopsZoomWhenHovered         Behaviours.FollowsQuadWithinKeymapperBounds
Effects.FocusListener                   Effects.StopsHotkeysWhenInputFieldFocused
```

`Effects.StopsHotkeysWhenInputFieldFocused` is the one that makes `Input Field`
worth using: without it, typing `255` also fires whatever Besiege has bound to 2, 5
and 5. It is a UI Factory component, not one of Besiege's — searching
`Assembly-CSharp` for it finds nothing.

## Any part of a window can be a drag handle

UI Factory puts a `Drag` on the `Window` prefab's `TopBar` and nowhere else. It is
a plain public component and can go on anything:

- give it a **raycast target** to sit on — an `Image` with an alpha of zero is
  enough, and an invisible `Image` is still a raycast target;
- set **`Target`** (a `RectTransform`) to the rect you want moved;
- set `UseSnap = false` unless you want sibling/parent snapping.

**Set `Target` in the same breath as `AddComponent`.** `Drag.Start` fills a null one
in with its own transform, and you would then be dragging the handle out of the
window. `OnDrag` writes `Target.transform.position`, so an anchored, pivoted rect
follows correctly and `anchoredPosition` stays consistent.

A title bar 50 units tall is a small target on a window most of a screen high.
Adding a second handle — a strip along the bottom, in the band a status line
occupies — costs four lines and is the sort of thing players notice.

## Keep your canvas below `sortingOrder` 30000

`UnityEngine.UI.Dropdown` hardcodes 30000 for the canvas it spawns its popup list
on. A canvas that ties with it wins on draw order and leaves the list unclickable —
so an overlay that wants to be above everything should sit just under, not at some
larger round number. Git View uses 29000.

## Own the window's anchors before remembering where it is

A prefab's rect can be anchored and pivoted any way its author liked, so "the
window's position" means nothing until you have decided what it is measured from.
Set `anchorMin = anchorMax = pivot = (0.5, 0.5)` yourself after instantiating, and
a stored position means one thing — canvas units from the middle of the screen —
rather than something only true of the prefab version you tested against.

Then clamp it on the way back in. A window restored onto a monitor narrower than
the one it was stored on, or dragged off the edge before quitting, is a window with
no way back to it: the title bar is the thing that moves it, and it is off screen.
Keep enough of the bar on screen to grab — Git View keeps 120 units across and 34
down — and clamp so the **top** survives, not the bottom.

## You cannot colour a UI Factory graphic; put one of your own in front of it

Setting `Button.colors` on a UI Factory prefab, or `color` on the image it draws
itself with, does not reliably show: the prefab's own material and the animation
driving it own that channel.

What works is a plain uGUI `Image` of your own, parented inside the control and
stretched over it: default UI shader, takes a colour, one assignment. Borrow the
prefab image's `sprite` and `type` and it keeps Besiege's rounded corners too.

Two related traps:

- **A colour transition multiplies, it does not replace.** uGUI drives the tint
  onto the graphic's canvas renderer, so the image's own colour stops mattering
  once a `Button` is tinting it — pass every state explicitly rather than setting
  one and expecting the others to follow.
- **Mark a control by tinting its own background graphic** (`Button.targetGraphic`)
  rather than by putting a rectangle in front of it, which will have square corners
  the button does not.

## A button inside a button works; a heading that fits its own button is the work

A `Text Button` dropped inside another one does the right thing untold: uGUI walks
up from whatever the pointer hit until it finds something that handles the click and
stops at the first, so the inner button fires and the row it sits in does not. Hover
is the exception and is also what you want — `OnPointerEnter` goes to everything in
the chain, so the row still lights up under a pointer that is over the small button.

The hover swell is the thing to watch. A hovered button grows about 15%, which is
right for a button and carries the text at both ends of a 700-unit row tens of
pixels sideways. `ScaleAnimation.Target` is public, so point it at a decorative
child; or move the control's **pivot** to the edge its text is aligned to, which
holds that edge still (moving a pivot moves the rect, so put the offsets back
after).

## Whether a prefab's label is the prefab

`Text Button`'s label is a child, authored at a fixed width for the prefab's own
size, so it has to be stretched to whatever you resized the control to. `Text`'s
label **is** the prefab — and stretching that throws away wherever you just placed
it. Same call, opposite treatment, and the failure is silent: a status line ends up
anchored across the middle of the window looking like a placement bug. Check whether
the `Text` you found is on the root before touching its rect.

## UI Factory has no colour picker, and Besiege's is out of reach

Besiege's own is the block mapper's paint selector, behind `InternalModding`, and it
only opens for a block. What it *is*, though, is worth copying:
`Selectors.ColourSliderSelector` is a knob dragged along a `Texture colourPicker` —
a strip of the colours it can choose — with `ColorToPixelPos` / `ClosestColorPos`
mapping between the two. The texture is private and mapper-only, but the widget is
a slider with a picture behind it, and UI Factory supplies the slider.

Draw your own strip, put it on a `Slider`, and turn **both** of the prefab's bars
off — the fill *and* the track. A fill bar means "this much"; a colour slider means
"this one", and a track under the strip makes the strip read as a sticker.

Four things measured off the game's own, from a screenshot of the rocket block's
settings:

- **The strip is pale and the answer is not.** Sampled across the bar its saturation
  runs about 0.62 the whole way, while the value beside it reads `#FF4C00` — full
  strength. Draw the ramp washed out and hand back `Hue(t, 1f)`.
- **It is a smooth ramp of every hue**, not a row of swatches, and there is no black
  or white on it.
- **Inset the strip by half the knob's width at each end.** A knob's centre stops
  half a knob short of both ends of its track, so a strip drawn edge to edge points
  at the wrong colour near the ends.
- **Leave something on the slider that is a raycast target.** A `Slider` is dragged
  through whatever graphic under the pointer catches the ray; turn off the fill
  *and* the track and there is nothing left, so the control goes completely dead and
  looks like a picture of a slider. The strip that replaced them has to take the
  job: `raycastTarget = true`.

## What is in UI Factory's sprite bundle cannot be listed

`Make.Sprites` is keyed `"package::name"` and is **not public**, and `Make.Sprite`
only answers for a name you already know, warning into the log when you are wrong.
So a mod cannot ask what artwork the bundle holds; it can only try names and read
`Player.log` for the misses. Worth doing anyway for anything Besiege draws itself:
its own cog beats a drawn one, and the cost of being wrong is a log line and a
fallback.

If you do end up drawing your own icons, note that a repeating sprite has to be
created at the canvas's `referencePixelsPerUnit` (Unity's default, and UI Factory's,
is 100) or it tiles at the wrong size.

## Committing a typed value

For a box that drives a slider, or a slider that drives a box:

- Commit on **`onEndEdit`**, not `onValueChanged` — the latter applies the `2` of a
  `255` while it is still being typed, very visible when a slider is following along.
- **Write the parsed value back into the box** afterwards, so `300` becoming 255
  happens in front of the player rather than silently, and put the real value back
  when the text will not parse at all.
- A box and a slider driving each other need **one "I am writing to this" flag**
  between them, or each hears the other's callback as the player having moved it.

A slider clipped to a sensible range with a box that accepts a wider one is a good
pattern: the slider covers what is worth dragging through and the box covers the
cases that are not worth a third of the slider's travel.
