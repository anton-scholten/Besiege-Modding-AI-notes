# The load screen, and putting a button on it

All from **Git View**, which adds a button to every machine in the load screen. The
one part of Besiege's interface a mod is most likely to want and the one least like
the rest.

## The file browser is mesh UI, not uGUI

Slots are world-space mesh objects. `FileBrowserSlot` extends
`HoverableClickBehaviour`; its labels are `TextMesh`, its buttons `SimpleUIButton`
with colliders. No layout group to add a child to and no prefab of Besiege's to
instantiate, so a mod wanting a button there must copy one of the slot's own.

Public and useful:

| Member | Notes |
| --- | --- |
| `FileBrowserSlot.VirtualObject` | the file or folder the slot stands for |
| `FileBrowserSlot.VersionsClicked` etc. | `Action<FileBrowserSlot>` fields, assignable |
| `SimpleUIButton.ResetDelegates()` | clears every handler on a copied button |
| `SimpleUIButton.Click` | an **event whose type is also called `Click`** |
| `FileBrowserView.Close()`, `.IsOpen` | closing the screen from outside |

**A slot has nine buttons and shows one.** Private fields:
`loadAsSelectionButton`, `deleteButton`, `confirmDeleteButton`,
`steamUploadButton`, `wegameUploadButton`, `modIOUploadButton`, `cloudButton`,
`versionsButton`, `confirmDownloadButton`. Private, and reflection is blacklisted, so
**which button is which cannot be asked**. Copy whichever `SimpleUIButton` is active
and has a renderer.

Measured on a real folder slot: of those nine, exactly **one** is active — the delete
button, in a bottom corner at x = 1.2 in slot units. The other eight are inactive and
scattered, two of them 0.018 apart. Two consequences:

- **Filter on `activeInHierarchy` before measuring anything.** "The smallest gap
  between any two buttons" is not a usable pitch, and a scan for a free spot that
  doesn't filter first will decide the slot is entirely full.
- With one visible button in a corner, **its mirror through the slot's middle** is the
  obvious place for a second. Place the copy by reading the spacing of the buttons
  actually shown; a hardcoded offset is a guess that breaks on the next Besiege.

`SimpleUIButton.Click` is worth flagging. A *member named after its own type* is the
construct that sends Besiege's in-game compiler into infinite recursion and kills the
game — but that's about **declaring** one. Referring to somebody else's, as
`button.Click += new Click(handler)`, compiles fine, including under Besiege's own
compiler.

Instantiating a copy brings the prefab's serialised state but not its delegates, since
C# delegates aren't serialised — so a copied delete button deletes nothing. Call
`ResetDelegates()` anyway, against a future Besiege that wires them up differently.

## Repainting a copied slot button: three wrong answers and the right one

Cost more time than anything else in the mod, and every wrong answer is the obvious
one.

**`Renderer.material.mainTexture = mine` does nothing visible.** No error, no warning,
the copy keeps the icon it was cloned with. `mainTexture` writes `_MainTex`, and these
buttons are drawn by one of Besiege's own shaders (`Custom/Stencil/…` appears in
`Player.log`) which need not have that property or need not sample it — and nothing
outside tells you which.

**Parenting a quad of your own to the button's face** came out invisible. Which plane
the face lies in, which way its normal points and how big it is in its own local space
all have to be right, and none can be checked from outside a running game.

**A copied button has no face in the frame you copy it.** Looking for a `MeshFilter`
with a mesh found none at all, on every slot, every time. Whatever builds a slot
button's visuals runs in an `Awake` or `Start` of its own, so the clone is bare in the
frame `Instantiate` returns it and furnished a frame or two later. **Anything
repainting a clone must retry across frames.** A clone with nothing on it to draw is
what a too-early look produces, not a button that draws nothing — a distinction worth
keeping for any Besiege object you copy.

**The answer: a slot button's face is a `SpriteRenderer`.** So set
`spriteRenderer.sprite`; no material, mesh or shader comes into it. Arrived at by
logging the *kind* of every renderer on the clone — the technique to reach for first
next time.

Size the replacement against the sprite it replaces. A sprite draws
`rect.height / pixelsPerUnit` units tall and `Sprite.Create` assumes 100 pixels per
unit unless told otherwise, so a texture that isn't the size of Besiege's own arrives
at the wrong size. Read `pixelsPerUnit` off the sprite you're replacing and create
yours with the same one.

## A copied button shows the *original's* tooltip — but you can repoint it

`Tooltip` keeps what it shows in a `tooltipParent` Transform, and **that object is not
a child of the button**. Unity only redirects a copied reference when it points inside
the copy, so `Instantiate(button)` gives you a `Tooltip` still pointing at the
original's words: hovering the copy lights up the neighbour's tooltip, in the
neighbour's place, and rewriting every `TextMesh` under the copy changes nothing
because there are none.

`tooltipParent` is **public** though, along with `timeToProc`, `useFadeOut`,
`lerpPosDirection`, `Reset()` and `OnMouseExit()`. So: `Instantiate` the original's
`tooltipParent` object, hang it off your button at the same offset it has from its own,
point your `Tooltip` at the copy, call `Reset()`. That re-finds the renderers and texts
under the parent it's now been given, works out which way the arrow points, and leaves
everything switched off until the pointer arrives — and you get `LerpPosIn` and the
fades, the animation you'd otherwise be imitating. `TooltipOn` calls `ResizeBackground`
every time it opens, so writing new text into the copied `TextMesh`es is all that
changing the words takes.

Two traps:

- `TooltipOn` / `TooltipOff` are private, and `TooltipOff` is the only thing clearing
  the `on` flag. **A tooltip hidden by deactivating its button still thinks it is open
  and won't open again** — call the public `OnMouseExit()` before hiding the button.
- `OnDisable` only turns the renderers off, which is not the same thing.

## `IVirtualObject.Date` is a `Double`, and it is not an OLE automation date

`IVirtualObject` is what a slot hands you for the file it stands for: `Name`,
`ObjectPath`, `ThumbnailPath`, `Parent`, `Thumbnail`, `IsFolder`, `IsDeletable`,
`IsUploadable`, `Date`.

`Date` being a `double` invites `DateTime.FromOADate`, and that's wrong — the numbers
don't land in this century. **And on Linux it's `DateTime.Now` anyway**: the field is
filled from a file-time call the game's Linux build doesn't implement, so every file in
the browser claims to have been written just now.

Parse the timestamp out of the file's own name instead. Besiege writes autosaves as
`aut yy.MM.dd HH-mm-ss.bsg`, a real timestamp, written by the game, identical on every
platform.

## Do not join paths; follow the browser

`FileBrowserSlot.SetupVersionsButton` shows Besiege's own versions button when
`Directory.Exists(MachineAutosavePath/<name>)`, and `OnVersionsButtonClick` ends in
`FileBrowserView.OnPageViewSlotVersions`, which walks up to the collection root, finds
the `AutoSave` folder, opens it, finds the folder named after the machine and opens
*that*.

Copy that route rather than joining `MachineAutosavePath` to a name. The browser can be
showing local files, a Steam collection or mod.io, and only the `IVirtualObject` it
hands you knows which — a mod that builds paths works in testing and fails for anybody
with a Workshop collection open.

## Writing in Besiege's font without a `Text` or a `TextMesh`

A slot's labels are `TextMesh`, fine until you want a number drawn on a button face
that's a `SpriteRenderer`. Besiege's UI font is reachable through UI Factory
(`Besiege.UI.Make.Font`), but a font is not a picture: to get a glyph onto a sprite you
either render text into a texture yourself or draw the shape.

For anything as simple as a digit, drawing it is less work than it sounds and has no
dependency at all: a 3x5 bitmap per digit, packed one row per nibble, expands to a
clean glyph at any size. Git View draws its own digits, plus, minus and tilde that way.

Worth checking before you trust a font: Besiege writes its interface in capitals, so a
font baked for it **may have no digits or lowercase at all**. Test with
`font.HasCharacter('0')` and keep `Resources.GetBuiltinResource<Font>("Arial.ttf")` as
a fallback, or a timestamp draws as a blank row.
