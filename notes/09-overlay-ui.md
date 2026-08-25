# An overlay of your own

Notes for a mod that draws over the whole game rather than beside a block — a HUD,
an assistant, a status panel. [04](04-ui-factory.md) covers the widgets and
[05](05-docking-a-window.md) covers pinning a window to the block mapper; this is
about the canvas underneath them and the drawing on top.

## Use uGUI, not `OnGUI`

`OnGUI` is the obvious way to put something on screen from a mod, and it puts it
in the wrong place. Besiege's HUD and menus are uGUI canvases rendered Screen
Space - Overlay, and Unity composites those after IMGUI — so an `OnGUI` panel is
drawn *behind* the game's own UI, which is exactly where a mod's overlay must not
be. A `Canvas` of your own, with a `sortingOrder` above the game's, sits on top
instead. (The render mode is authored in the scenes rather than set in code, so
it is not visible in the assembly; this one was established in game.)

It buys a second thing, and that one *is* in the assembly. Besiege asks the
`EventSystem` whether the pointer is over UI before acting on a click —
`AddPiece.CheckHudOcclusion` calls `EventSystem.IsPointerOverGameObject()` before
placing a block. Any graphic with `raycastTarget = true`, on a canvas with a
`GraphicRaycaster`, answers that question, so an overlay built as uGUI occludes the
things that ask: clicking it does not also drop a block into the world behind it.
With `OnGUI` that has to be solved by hand, and every solution is a guess about
what the game is about to do with the click.

**"The things that ask" is a real limit, not a hedge.** Only two places in
`Assembly-CSharp` consult `IsPointerOverGameObject` at all, and most of Besiege's
own interface is not one of them — see the next section, which is the single
nastiest thing an overlay mod will hit.

Two canvas details, both from [04](04-ui-factory.md) but worth repeating where an
overlay will trip on them: `Make.ScreenCanvas` is rebuilt on every scene change,
so a persistent overlay needs its own `DontDestroyOnLoad` canvas; and the scaler
must match UI Factory's (1920×1080, `matchWidthOrHeight = 1`) or the game's own
widgets render at the wrong size.

## A canvas over Besiege's UI does not stop it being clicked

The whole of Besiege's own interface — popups, buttons, the file browser — is
colliders answering Unity's legacy `OnMouseOver`. `ClickBehaviour.OnMouseOver`
calls `OnCursorOver`, which tests `InputManager.LeftMouseButton()` and fires. Those
messages are raycast from the cameras by Unity itself and **know nothing about the
EventSystem**, so a uGUI window drawn over one hides it without stopping it. Git
View's window took clicks straight through to the "this machine uses keys also used
by your general control scheme" warning (a `WarningPopupBase`) sitting behind it.

Things that do not fix it:

- **Raising the canvas.** There is nothing to raise above; the two systems do not
  share an ordering. The window was already at `sortingOrder` 29000 and drawn on
  top.
- **Making sure the window is a solid raycast target.** It already was — UI
  Factory's `Window` root has an `Image` with `m_RaycastTarget` set. That stops
  uGUI events and nothing else.
- **Waiting for Unity to handle it.** `SendMouseEvents` does not consult the
  EventSystem in this version. Whatever you have read about `OnMouseDown`
  respecting uGUI, it does not here.

**`Camera.eventMask` is the lever.** The layer mask a legacy mouse raycast uses is
`cullingMask & eventMask`, so setting `eventMask = 0` on every camera makes the
whole game deaf to the mouse. Do it while the pointer is inside your window and put
each camera's own mask back the moment it leaves, and nothing about the game
changes except while it is covered. Hovers end cleanly too: the raycast returns
nothing, so Unity sends `OnMouseExit` to whatever was lit.

Three things to get right, all of which are ways to leave the game unusable:

- **Gather the cameras every frame while the shield is up**, not once. Cameras come
  and go with the scene, and one built while you are holding the mask down is the
  one hole in it.
- **Remember each camera's own mask** rather than restoring "everything". A mask is
  a set of layers and the game picks its own.
- **Release from `OnDisable` as well as when the pointer leaves.** A shield left up
  is a game whose buttons have stopped answering, with nothing on screen to say
  why.

Test for "is the pointer over my window" with
`RectTransformUtility.RectangleContainsScreenPoint(rect, Input.mousePosition, null)`
— the null camera is right for a Screen Space - Overlay canvas — and not with
`EventSystem.IsPointerOverGameObject()`, which is also true over Besiege's own uGUI
and would shield the game from itself.

## Two transparent Images that overlap composite darker

uGUI blends each `Image` separately, so two half-transparent graphics that overlap
give `1 - (1 - a)²`, not `a`. A speech bubble and its tail, drawn as two sprites,
show a visibly darker wedge everywhere they cross — and the usual fixes do not
work:

- **`CanvasGroup.alpha` does not flatten anything.** It multiplies into each
  child's own alpha; the children still blend one after another.
- **`RectMask2D` is rectangle-only**, so it cannot trim a tail to a bubble's edge.
- Turning one of them opaque and the other transparent just moves the seam.

What does work is not overlapping in the first place: draw the union as **one**
sprite. A 9-sliced rounded rectangle plus a separate dart whose base is notched to
sit exactly on the bubble's edge leaves only sub-pixel antialiasing overlapping —
in the case this note came from, the doubled area went from 169 px² to 4.5 px².

9-slicing is also what allows a bubble with three rounded corners and one square
one: the slices preserve per-corner artwork, so the corner nearest the speaker can
be square while the other three are round, at no cost in draw calls.

## Rich text is lowercase-only, and Besiege's captions are not

Unity's rich text parser accepts `<color=#RRGGBB>` and rejects `<COLOR=#RRGGBB>`.
Besiege's caption style upper-cases label text — so any helper that captions a
string will destroy markup applied before it. Apply markup **after** captioning,
never before, and set `supportRichText = true` on the label, which is not the
default on every prefab's `Text`.

The game's own convention, worth matching: block and feature names are written in
capitals and tinted the interface green; keys are drawn in a box. A tip that
follows it reads like part of the game instead of like a wiki.

## Read the player's real keybindings, do not print the defaults

A `<Keys>` element in `Mod.xml` gets the mod's own hotkeys into Besiege's controls
screen, where the player can rebind them like any other. The corollary is that the
mod may not then quote its own defaults back at them: ask the key system what is
bound at the moment you speak. The same applies to the game's own actions if your
UI mentions them — and a binding the player has cleared should be reported as
unbound rather than quoted from the default.

## Scene names tell you where the player is

`Application.loadedLevelName` is the cheapest context a UI mod has, and Besiege's
naming is regular enough to switch on:

| Scene | What it is |
| --- | --- |
| `MainMenu` | title screen |
| `LevelSelect…` | a zone's level select, one per island |
| `"1"` … `"70"` | campaign levels, bare numbers |
| `"71 TakeOff"` … `"82 Castle"` | the space levels, number then name |
| `MachineEditor`, sandbox names | the builder |

Which campaign level belongs to which island is not in the scene name, but it is
in the game's own level-select scenes — read it out of those rather than
fingerprinting terrain, which looks like it should work and does not (level 13 is
a space level, so any assumed contiguous build-index mapping is wrong).
