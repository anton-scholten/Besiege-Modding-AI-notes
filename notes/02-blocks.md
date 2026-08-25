# Blocks: XML, meshes, icons, visuals, saves

## Geometry conventions

A block mesh is **Z-up**, centred on the origin, and typically worn at half scale
from `z = 0.5` — the convention Besiege's own generated blocks use.

**glTF is right-handed and Unity is left-handed, so the map between them must flip
the handedness.** `(x, y, z) -> (-x, -z, y)` does it: the up axis swaps in and two
are negated, which is a reflection. A swap that *preserves* handedness — the
obvious `(x, -z, y)` — produces a model that measures correctly and is **mirrored**,
which is invisible on a drum and plain on a piano once you look at the keyboard.

Two consequences worth knowing before changing that line:

- a reflection does not commute with a rotation, so mirroring the model reverses
  which way a given yaw carries its face. Fixing handedness means revisiting every
  pose angle, and the sign flips.
- if you render previews to judge a pose, the preview projects into the same
  left-handed frame: screen right is `cross(eye, up)`, **not** the `cross(up, eye)`
  a right-handed frame wants. Get that backwards and every render is a mirror of
  the game, which is invisible until it matters and then costs a round of poses
  turned the wrong way.

## The toolbar icon

`<Icon>` gives a position, rotation and scale for a second camera that photographs
the block for its toolbar tile. Two things are not obvious:

- **the icon camera looks along +z**, not the -z a Unity camera looks along by
  default. Undo the icon rotation to find where the camera stands in the block's
  frame and you get the *opposite* of the truth unless you negate. Measured, not
  reasoned: a pose worked out on the un-negated assumption drew every block from
  behind and below — legs, undersides, bottom drum heads.
- **the Euler triple cannot roll the picture.** The rotation is Y, then X, then Z
  of the *block*, and the camera is fixed; nothing in that chain tilts the image.
  A roll has to be applied to the whole rotation and the result decomposed back
  into that order, which is where odd triples like `-31.3, 156.7, -151.6` come
  from. Anything round — a drum head, a cymbal — can only be turned by rolling the
  picture, since spinning it about its own axis renders identically.

`<Icon>` **Scale is measured against the raw model**, not multiplied by the
`<Mesh>` scale above it. The game's own blocks settle it: they are modelled at a
hundred times size and carry `Mesh 0.01` with `Icon 0.008`, which would be
invisible if the two compounded. So swapping a block's mesh for one authored at a
different size means re-scaling the icon with it — a mesh spanning two units where
the old one spanned nine tenths draws the tile more than twice too large.

Anything a behaviour adds to a block **at runtime is absent from the toolbar
tile**, because the tile is photographed from the block's mesh. A decoration that
has to appear in the toolbar has to be part of the mesh, not a child object added
in `SafeAwake`.

## A mesh may be an outer skin with no inside

A frame or cage modelled as a shell has faces pointing outward only, so from
inside it the far side is back-face culled and the block reads hollow. Emit a
reversed copy of every face with its normal turned round and it is solid from any
angle; the cost is double the faces, which for a block is nothing. Worth checking
before assuming a mesh is wrong: count the faces whose normal points back toward
the centroid, and if that is zero, this is why.

## Colouring part of a block's mesh, without a second material

A block's renderer gets one material, and Besiege's OBJ loading gives no submeshes
to hang a second one on. But a **texel** is addressable: give the part its own
corner of the UV space, and repaint that corner at runtime.

A two-by-two `Texture2D` with `filterMode = Point` is enough if the two unwraps sit
in different quadrants — one texel for the block, one for the part, and point
sampling means they cannot bleed into one another. Per block that is twelve bytes,
so each block can be lit independently.

Two things this needs:

- **the block's material has to be re-checked, not remembered.** Besiege may build
  the visual after `SafeAwake` has already looked, and a repaint replaces the
  material outright. Dress the block once and trust it and the change is silently
  undone. Re-apply whenever the renderer is not wearing yours, copying from
  whatever is on it at that moment so a paint colour survives;
- **pick the renderer whose material already has a `mainTexture`.** That finds the
  mesh the block is really seen as, and settles in passing that the shader reads
  its picture from `_MainTex`, which is otherwise a guess that fails silently.

## A block's visual is not its transform

`BlockBehaviour.VisualController.renderers` lists the block's `MeshRenderer`s.
Their transforms are children carrying the `<Mesh>` offset and scale; the block's
**own** transform is the physics body the colliders are placed against.

Anything that moves a block for show — an animation, a swell, a wobble — writes to
the former and must not touch the latter, or the machine's collision changes with
the animation. And a simulation runs on a **clone** of the machine, so read the
renderer list from the instance that is running rather than caching it at load.

## How a machine save names a modded block

A `.bsg` is XML. A block from a mod looks like:

```xml
<Block id="1005" guid="<per-instance uuid>" modId="<the mod's GUID>" localId="1" fallback="35">
    <Transform>
        <Position x="0" y="0" z="0" />
        <Rotation x="-0.7071068" y="0" z="0" w="0.7071068" />
        <Scale x="1" y="1" z="1" />
    </Transform>
    <Data>
        <Integer key="bmt-version">1</Integer>
        <StringArray key="bmt-Activate">N</StringArray>
        <Single key="bmt-NoteKey">60</Single>
    </Data>
</Block>
```

- `modId` + `localId` (the block XML's own `<ID>`) are what resolve it:
  `XmlLoader.HandleMod` recomputes the numeric `id` from them through
  `ModIds.GetEffectiveBlockId`, so the `id` attribute in the file is not what
  finds the block. `fallback` is the vanilla block shown when the mod is absent.
- every mapper control is `bmt-` + its key, with the element naming the type:
  `Single`, `Integer`, `Boolean`, `StringArray`.
- a `StringArray` with several entries is written as `<String>` children instead
  of inline text.
- a block's `<Data>` may omit any key; the block falls back to its default. This
  is what lets a mod add controls without breaking old saves.
- the machine's own `<Data>` carries `requiredMods` as
  `<guid>~L~<version>~<name>`.
- the machine needs a starting block (`BlockType.StartingBlock` = 0).
- `(-0.7071068, 0, 0, 0.7071068)` — a quarter turn about X — is what the game
  writes for a block placed on a flat surface, i.e. standing up. Identity leaves a
  block lying on its side.

Blocks in a save do **not** have to be connected to anything. Besiege loads them
where they are put; unattached ones simply fall when the simulation starts, which
is fine for anything whose job is not structural.

Vanilla block ids come from the `BlockType` enum — `StartingBlock` 0, `Ballast` 35,
`Log` 63, `Sensor` 65, **`Timer` 66**, `Altimeter` 67, `LogicGate` 68, and so on.
Dump it rather than trusting a list (see
[06-reading-the-game.md](06-reading-the-game.md)).
