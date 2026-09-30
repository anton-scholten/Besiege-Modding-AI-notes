# An overlay of your own

For a mod drawing over the whole game rather than beside a block — a HUD, an
assistant, a status panel. [04](04-ui-factory.md) covers the widgets and
[05](05-docking-a-window.md) covers pinning a window to the block mapper; this is the
canvas underneath them and the drawing on top.

## Tab hides the game's interface, and yours is part of it

`StatMaster.hudHidden` is the flag. Anything a mod draws over the game -- a HUD, a
panel docked under the block mapper -- is part of what Tab is pressed to get rid
of, and a mod that ignores it leaves half an interface hanging over an empty
screenshot.

Reconcile it every frame (`canvas.enabled = !StatMaster.hudHidden` in `LateUpdate`)
rather than reacting to a key: Tab is not the only thing that sets it.

**Disable the canvas, not the window.** Switching a docked panel's window off is
usually the path that hands its controls back to the stock mapper or tears
something down; coming out of Tab then finds the panel gone. A disabled `Canvas`
draws nothing, keeps everything under it exactly as it was, and takes the mod's
tooltips and menus with it because they are on the same canvas.

## Use uGUI, not `OnGUI`

`OnGUI` is the obvious way to put something on screen from a mod, and it puts it in the
wrong place. Besiege's HUD and menus are uGUI canvases rendered Screen Space - Overlay,
and Unity composites those after IMGUI — so an `OnGUI` panel draws *behind* the game's
own UI, exactly where a mod's overlay must not be. Your own `Canvas`, with a
`sortingOrder` above the game's, sits on top instead. (Render mode is authored in the
scenes rather than set in code, so it isn't visible in the assembly; established in
game.)

It buys a second thing, and that one *is* in the assembly. Besiege asks the
`EventSystem` whether the pointer is over UI before acting on a click —
`AddPiece.CheckHudOcclusion` calls `EventSystem.IsPointerOverGameObject()` before
placing a block. Any graphic with `raycastTarget = true`, on a canvas with a
`GraphicRaycaster`, answers that question, so an overlay built as uGUI occludes the
things that ask: clicking it doesn't also drop a block into the world behind it. With
`OnGUI` that must be solved by hand, and every solution is a guess about what the game
is about to do with the click.

**"The things that ask" is a real limit, not a hedge.** Only two places in
`Assembly-CSharp` consult `IsPointerOverGameObject` at all, and most of Besiege's own
interface is not one of them — see the next section, the single nastiest thing an
overlay mod will hit.

Two canvas details, both from [04](04-ui-factory.md) but worth repeating where an
overlay will trip on them: `Make.ScreenCanvas` is rebuilt on every scene change, so a
persistent overlay needs its own `DontDestroyOnLoad` canvas; and the scaler must match
UI Factory's (1920×1080, `matchWidthOrHeight = 1`) or the game's own widgets render at
the wrong size.

## A canvas over Besiege's UI does not stop it being clicked

The whole of Besiege's own interface — popups, buttons, the file browser — is colliders
answering Unity's legacy `OnMouseOver`. `ClickBehaviour.OnMouseOver` calls
`OnCursorOver`, which tests `InputManager.LeftMouseButton()` and fires. Those messages
are raycast from the cameras by Unity itself and **know nothing about the
EventSystem**, so a uGUI window drawn over one hides it without stopping it. Git View's
window took clicks straight through to the "this machine uses keys also used by your
general control scheme" warning (a `WarningPopupBase`) sitting behind it.

Things that don't fix it:

- **Raising the canvas.** Nothing to raise above; the two systems don't share an
  ordering. The window was already at `sortingOrder` 29000 and drawn on top.
- **Making sure the window is a solid raycast target.** It already was — UI Factory's
  `Window` root has an `Image` with `m_RaycastTarget` set. That stops uGUI events and
  nothing else.
- **Waiting for Unity to handle it.** `SendMouseEvents` doesn't consult the EventSystem
  in this version. Whatever you've read about `OnMouseDown` respecting uGUI, it doesn't
  here.

**`Camera.eventMask` is the lever.** The layer mask a legacy mouse raycast uses is
`cullingMask & eventMask`, so setting `eventMask = 0` on every camera makes the whole
game deaf to the mouse. Do it while the pointer is inside your window and put each
camera's own mask back the moment it leaves, and nothing about the game changes except
while it's covered. Hovers end cleanly too: the raycast returns nothing, so Unity sends
`OnMouseExit` to whatever was lit.

Three things to get right, all ways to leave the game unusable:

- **Gather the cameras every frame while the shield is up**, not once. Cameras come and
  go with the scene, and one built while you're holding the mask down is the one hole in
  it.
- **Remember each camera's own mask** rather than restoring "everything". A mask is a
  set of layers and the game picks its own.
- **Release from `OnDisable` as well as when the pointer leaves.** A shield left up is a
  game whose buttons have stopped answering, with nothing on screen to say why.
- **Stand down with the canvas, not just with the window.** The section above says to
  answer Tab by disabling the `Canvas` and leaving the window alone — which means
  `gameObject.activeInHierarchy`, the obvious test for "am I still on screen", stays
  true for a panel nobody can see. Gate the shield on `canvas.enabled` too, or pressing
  Tab and moving the mouse across where the panel used to be makes the game deaf for as
  long as the pointer is there. Both halves are correct on their own; it is the pair
  that bites.

Test "is the pointer over my window" with
`RectTransformUtility.RectangleContainsScreenPoint(rect, Input.mousePosition, null)` —
the null camera is right for a Screen Space - Overlay canvas — and not with
`EventSystem.IsPointerOverGameObject()`, which is also true over Besiege's own uGUI and
would shield the game from itself.

**To shield uGUI as well, cover it; do not switch the EventSystem off.** Disabling
`EventSystem.current` makes `current` return null, and `AddPiece.CheckHudOcclusion`
dereferences it every frame without a check — a `NullReferenceException` per frame from
`AddPiece.Update` (and `NetworkAddPiece.Update`) for as long as it is off. A full-screen
`Image` with colour alpha 0 and `raycastTarget` on, on a canvas at `sortingOrder` 29000
with a `GraphicRaycaster`, stops every uGUI click *and* stops block placement, because
the placement check it makes then sees the pointer over UI. Together with `eventMask = 0`
on every camera and `StatMaster.SetInMenu(true)`, the game ignores the mouse entirely.
Measured: 1057 exceptions in a few seconds with the EventSystem off, none with the cover.

## A click goes to the first handler at or above what it hit

uGUI does not deliver a click to the object the ray struck. It walks up from that
object with `ExecuteEvents.GetEventHandler<IPointerClickHandler>` and delivers to the
first GameObject that *has* such a handler. Two consequences, and both are useful:

- A container gets clicks that land on its children as long as those children carry no
  handler of their own. Graphics with `raycastTarget` left on but nothing listening —
  labels, icons, a plain `Image` background — are transparent to this. So a node, a
  row, a card can take a click anywhere on itself, while the controls sitting on it
  (a `Button`, a `Toggle`, an `InputField`, anything deriving from `Selectable`) keep
  their own clicks. That rule needs no hit-testing code and no exceptions list.
- The same walk stops at a control **whether or not it acts**. `Selectable.interactable
  = false` does not hand the click on: the component is still there, the event is
  delivered to it, and it does nothing with it. Turning a control off is not a way to
  let clicks through to what is underneath.

To pass clicks through a control, switch off `raycastTarget` on its graphics instead.
For `InputField` that is `image`, `textComponent` and `placeholder` — name them rather
than sweeping `GetComponentsInChildren<Graphic>()`, which also catches the caret Unity
creates on activation; a caret that answers the ray is a thin dead stripe down the
middle of the text. Put the caret back by calling `ActivateInputField()` yourself when
the gesture that means "now type in this" arrives.

Drags follow the same rule with `IDragHandler`, and a drag that starts on an
`InputField` is a text selection: a text box on something draggable makes that thing
undraggable by its own middle until the box stops answering the ray. The way round that
is to put the drag handler on the box itself and set `interactable = false` for the
length of the drag — every `InputField` drag and pointer handler opens with
`if (!MayDrag(...)) return;`, and `MayDrag` asks `IsInteractable()`.

**But `interactable = false` deselects a focused field.** In the `UnityEngine.UI.dll`
Besiege ships, `Selectable.set_interactable` calls
`EventSystem.current.SetSelectedGameObject(null)` when the field being switched off is
the current selection — so an `InputField` loses focus, `DeactivateInputField` runs,
and **`onEndEdit` fires** in the middle of your drag's `OnBeginDrag`. If that handler
rebuilds anything, it destroys the object uGUI is dragging and the drag stops after
one frame. Write the field's text into your own model *before* switching the field
off, so the `onEndEdit` that follows has nothing new to say and stands down.

**And a drag still ends in a click when one object does both.** `PointerInputModule.
ProcessDrag` clears `eligibleForClick` only inside `if (pointerPress != pointerDrag)`
— so an object carrying both the click handler and the drag handler (a node, a card,
a list row) gets `OnPointerClick` on release *after* a real drag, and a click handler
that selects, or deselects, or opens something undoes what the drag just did. Read off
the shipped `UnityEngine.UI.dll`, not from the docs, which do not mention it.

The release order in `ProcessMousePress` is `pointerUp`, then the click, then `drop`,
then `endDrag`. So the flag that tells the click handler to stand down has to be one
raised at `OnBeginDrag` and lowered at `OnEndDrag` — a flag set when the drag *ends*
is set one call too late to be seen.

## What `StatMaster.inMenu` actually turns off, and what it doesn't

Raising the in-menu count (`StatMaster.SetInMenu(true)`, counted — give every hold
back exactly once) is how an overlay window stops the game reacting to the same
mouse and keyboard. It is worth knowing exactly which of the game's own code asks:

- **`MouseOrbit.Update` reads `StatMaster.inMenu` once, near the top, and skips its
  whole pan-and-orbit block when it is set.** That is what stops a drag over your
  window from also swinging the camera — `InputManager.PanCameraKeyHeld()` is never
  reached.
- **Raise it on the press, not on the drag.** uGUI sends `OnBeginDrag` only past the
  drag threshold, and never for a click that stays put — so an overlay holding in
  `OnBeginDrag` lets a plain middle *click* through and the camera pans under your
  window, which reads as "sometimes the middle button passes through". Hold in
  `OnPointerDown`, give it back in `OnPointerUp` unless your own drag is still
  running; the hold is idempotent, so the drag's grip costs nothing and either order
  uGUI sends up and end-drag in is safe. These events reach only what is under the
  pointer and its parents: without a handler on the window **root**, a press on your
  title bar or margins reaches nothing of yours.
- **But it eases the zoom before it asks, and reads the wheel after.** Above that
  early exit, `Update` lerps `zoomSmoothDelegate` towards `scrl * distance`; the
  wheel is read into `scrl` — `disableCameraZoom ? 0 : InputManager.ZoomValue()` —
  only below it. Raise `inMenu` while the wheel is turning, as a pointer scrolled
  onto your window does, and `scrl` is frozen at its last non-zero reading: the
  camera goes on zooming for as long as the menu is held. `scrl` is private, so
  hold `StatMaster.DisableCameraZoom` the moment the pointer arrives and raise the
  menu a few frames later; one pass of `Update` then sees zoom disabled and no menu,
  and puts `scrl` to nought.
- **`BlockSelectionTool.LateUpdate` returns immediately when `inMenu` is set**, so
  select-all, invert, duplicate, break-surface, delete and export-obj are all off
  while your window claims a menu. (`InputManager.AdvancedBuilding.DuplicateKeys`
  also checks `StatMaster.stopHotkeys` for itself.)
- **The camera's movement keys do not ask about `inMenu` either.**
  `InputManager.Camera.ForwardKeyHeld` / `BackwardKeyHeld` / `LeftKeyHeld` /
  `RightKeyHeld` / `RollLeftKeyHeld` / `RollRightKeyHeld`, and `MouseOrbit.WASD`,
  return false on `stopHotkeys` or `stopWASDcamMovement` alone. A focused UI Factory
  `Input Field` raises `stopHotkeys`, so typing is covered; a key selector of your
  own is not, and binding **A** nudges the camera. `StatMaster.StopCameraKeys(bool)`
  is public, counted like `SetInMenu`, and the only writer of `stopWasdCounter` —
  but **holding it from a key selector (while listening, and until the caught key
  came up) made the camera behave worse in game, not better**, and was taken out.
  Why is not known; do not reach for it as the fix without testing.
- **`BlockMapper.LateUpdate` does not ask about `inMenu`.** Its Ctrl+C / Ctrl+V —
  `InputManager.CopyKeys` / `PasteKeys`, which copy and paste a *block's mapper
  settings* — are gated on `stopHotkeys` alone. A mod window open beside a block
  mapper cannot shadow those two by raising the menu count, and `stopHotkeys` is
  not a good thing to hold: `UndoSystem.CanInteract` refuses while it is set, so
  holding it costs the player Ctrl+Z. Pick different keys instead.

**A key your window takes can still reach the game.** The hover hold is only up while
the pointer is over the window, and keyboard shortcuts do not care where the pointer
is. A mod window that deletes its own selection on Delete, pressed with the pointer
over the machine, also lets `BlockSelectionTool.LateUpdate` delete the *game's*
selection — and while a block's mapper is open that selection is usually the block
itself. Raise the menu count in your `Update` in the frame the key goes down and drop
it a frame later: every `LateUpdate` runs after every `Update`, so the selection tool's
early return on `inMenu` sees it in time. `AddPiece`'s hover delete (with nothing
selected) runs in `Update` instead, so it is not guaranteed to be beaten the same way;
clearing your own selection on any click outside your window keeps the two
selections from being live at once.

**Hold the count for the length of a drag, not for the length of the hover.** The
obvious place to raise and drop it is `OnPointerEnter`/`OnPointerExit`, and uGUI
sends the exit as soon as the pointer leaves the rect — **mid-drag included**. Pan
your window's view to its edge and keep dragging and the pointer is outside, the
hold is given back, and the game's camera picks up the same drag. So take a second
hold in `OnBeginDrag`, give it back in `OnEndDrag`, and give it back in `OnDisable`
too, or a window torn down mid-drag leaves the game believing a menu is open for
ever.

## Two transparent Images that overlap composite darker

uGUI blends each `Image` separately, so two half-transparent graphics that overlap give
`1 - (1 - a)²`, not `a`. A speech bubble and its tail, drawn as two sprites, show a
visibly darker wedge everywhere they cross — and the usual fixes don't work:

- **`CanvasGroup.alpha` does not flatten anything.** It multiplies into each child's own
  alpha; the children still blend one after another.
- **`RectMask2D` is rectangle-only**, so it can't trim a tail to a bubble's edge.
- Turning one opaque and the other transparent just moves the seam.

What works is not overlapping in the first place: draw the union as **one** sprite. A
9-sliced rounded rectangle plus a separate dart whose base is notched to sit exactly on
the bubble's edge leaves only sub-pixel antialiasing overlapping — in the case this note
came from, the doubled area went from 169 px² to 4.5 px².

9-slicing is also what allows a bubble with three rounded corners and one square one:
the slices preserve per-corner artwork, so the corner nearest the speaker can be square
while the other three are round, at no cost in draw calls.

## Rich text is lowercase-only, and Besiege's captions are not

Unity's rich text parser accepts `<color=#RRGGBB>` and rejects `<COLOR=#RRGGBB>`.
Besiege's caption style upper-cases label text — so any helper that captions a string
destroys markup applied before it. Apply markup **after** captioning, never before, and
set `supportRichText = true` on the label, which isn't the default on every prefab's
`Text`.

The game's own convention, worth matching: block and feature names in capitals, tinted
the interface green; keys drawn in a box. A tip following it reads like part of the game
instead of like a wiki.

## Read the player's real keybindings, do not print the defaults

A `<Keys>` element in `Mod.xml` gets the mod's own hotkeys into Besiege's controls
screen, where the player can rebind them like any other. Corollary: the mod may not then
quote its own defaults back at them — ask the key system what's bound at the moment you
speak. Same applies to the game's own actions if your UI mentions them, and a binding
the player has cleared should be reported as unbound rather than quoted from the
default.

## A mod key's default may collide with the game's, and nothing will say so

The loader checks a `<Keys>` default against **other mods' keys only** — that is the
"Keybinding conflict on X+Y. Disabling one of the conflicting keys." warning — and
never against Besiege's own bindings. So `Ctrl+C`, `Ctrl+V`, `Ctrl+Z`, `Ctrl+Y` are
accepted, appear in the controls screen, and fire at the same time as the game's
copy, paste, undo and redo: a mod's paste that also duplicates the selected block.
Pick a modifier the game does not use, and treat the collision as your bug rather
than the player's to rebind.

`ModKey.IsPressed` is the modifier under `Input.GetKey` and the trigger under
`GetKeyDown` — an edge, safe to poll in `Update`. `IsDown` is both held; `IsReleased`
is either going up. A key with no modifier answers on the trigger alone.

The player's bindings are saved in the mod's own configuration under `modkeys`, and
the defaults in `Mod.xml` are read only for names that are not in there yet.
**Changing a default in a later version does not move a key somebody's game has
already saved** — say so in the release notes rather than expecting the new default
to take.

## Scene names tell you where the player is

`Application.loadedLevelName` is the cheapest context a UI mod has, and Besiege's naming
is regular enough to switch on:

| Scene | What it is |
| --- | --- |
| `MainMenu` | title screen |
| `LevelSelect…` | a zone's level select, one per island |
| `"1"` … `"70"` | campaign levels, bare numbers |
| `"71 TakeOff"` … `"82 Castle"` | the space levels, number then name |
| `MachineEditor`, sandbox names | the builder |

Which campaign level belongs to which island isn't in the scene name, but it is in the
game's own level-select scenes — read it out of those rather than fingerprinting
terrain, which looks like it should work and doesn't (level 13 is a space level, so any
assumed contiguous build-index mapping is wrong).

## Hundreds of lines: one `MaskableGraphic` mesh, not an `Image` each

A line drawn as a thin, rotated `Image` is a GameObject. Curved wires at a dozen such
pieces each came to ~700 objects on a modest node board, all destroyed and rebuilt on
every edit and all re-laid on every frame of a pan or a drag: that was the stutter.

One `MaskableGraphic` subclass overriding `OnPopulateMesh(VertexHelper vh)` draws every
segment as a quad — four `AddVert`, two `AddTriangle` — and costs one object and one
mesh upload however many lines there are. Refill its segment list and call
`SetVerticesDirty()`. The loader accepts it; `UnityEngine.UI` is not blacklisted.

- **Give its rect the size of the area the lines cover.** A graphic is culled by its
  own rect, and a zero-size one at a corner goes out of sight with that corner.
- **Lines on content that pans or zooms need no redraw for it.** Their coordinates
  are the content's own; only a loose end that follows the pointer moves.
- **Cache per line, pour into the mesh.** Working a line out (port positions, a bezier,
  a colour) is the cost; copying cached segments into the mesh is not. A drag need
  only work out the lines on what it moves.

Besiege 5.4.0f3, September 2026: Node Editor's `WireMesh`, seen drawing in game.
