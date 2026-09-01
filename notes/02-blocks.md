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


## Finding your own block's id at runtime

A mod that writes blocks into a machine -- a generator, a paste, anything building
a `BlockInfo` -- needs the **id this Besiege gave each of its blocks**, which is
assigned at load and is not in your XML. Two ways of getting it are wrong and one
is right.

**Wrong: `BlockPrefab.locID`.** It is a public int sitting next to `Type` and `ID`
and it reads exactly like the block's local id. `BlockPrefab`'s constructor sets it
to **-1**, and nothing in the game ever writes it for a modded block -- the only
readers are a tooltip and a name translation. Anything computed from it is out by
whatever your local ids are.

**Wrong: arithmetic from one known block.** A mod's blocks are numbered from a base
in manifest order, so `base = myType - myLocalId` and `base + otherLocalId` looks
sound. It is not stable across installs: with other mods loaded the ranges are not
contiguous, and the id you compute is somebody else's block. A song generator that
did this filled its machines with another mod's sound blocks -- which looks like an
id *conflict* and is really an id *guess*.

**Wrong: looking for your own behaviour on the prefab.** This one is subtle.
`BlockPrefabCreator.SetupBehaviour` *does* `AddComponent` a behaviour on the
prefab — but only the one a block declares with `<Script>`. A **module's** behaviour
is added by `ModBlockBehaviourHandler.Awake`, on the *instance*; a prefab is an
inactive object whose Awake has never run, so `GetComponent<MyModuleBehaviour>()`
on a prefab returns null every time. Nor is the module any help:
`RawModule` is set in that same Awake.

**Wrong: `BlockPrefab.name` is the block's `<Name>`.** It is, for about a
microsecond. `BlockPrefabCreator.SetupBehaviour` sets `BlockPrefab.name` to
`ModdedBlock.Name`, and then `BlockLoader.RegisterPrefab` — the method that puts
the prefab in the table you are about to read — calls
`BlockPrefab.SetNameFromGameObject()`, which copies the prefab *object's* name over
it. Matching on "Bass" therefore finds nothing at all, for any modded block, ever.
That is not a near miss: every block comes back unresolved and a generator that
refuses to guess (rightly) refuses to do anything.

**Right: the prefab's name is `<mod guid>-<local id>`.**
`BlockPrefabCreator.CreatePrefab` names the prefab object
`Info.Mod.Info.Id + "-" + LocalId`, and `SetNameFromGameObject` puts that on the
`BlockPrefab`. It is exact, it is unique to your mod, and both halves come out of
files you already read:

```csharp
foreach (KeyValuePair<int, BlockPrefab> pair in PrefabMaster.BlockPrefabs)
{
    BlockPrefab prefab = pair.Value;
    if (prefab == null || string.IsNullOrEmpty(prefab.name)) continue;
    int cut = prefab.name.LastIndexOf('-');       // the guid has its own hyphens;
    if (cut <= 0) continue;                       // the last one is the separator
    if (string.Compare(prefab.name.Substring(0, cut), myModGuid, true) != 0) continue;
    int localId;
    if (int.TryParse(prefab.name.Substring(cut + 1), out localId))
        ids[localId] = (int)prefab.Type;
}
```

**The table is not filled when your `OnLoad` runs.** Blocks are registered after
mod assemblies are loaded, so a single lookup at load finds nothing. Retry from a
`MonoBehaviour` — once a second until every block is accounted for — and say
something only when the answer changes.

**Second best: `nameKeywords` carries the author.** `BlockPrefabCreator` fills
`BlockPrefab.nameKeywords` with the block's `<SearchKeywords>` **plus the owning
mod's `<Author>`**, and that survives the rename. It is the fallback worth keeping
for a Besiege that does not rename the prefab, paired with the `<Name>` match:

```csharp
foreach (string keyword in prefab.nameKeywords)      // may be null
    if (keyword == myModAuthor) { id = (int)prefab.Type; }
```

And when a block cannot be found, **do not fall back to a guess**. Refuse. A wrong
block id is silent, and the machine it produces looks like a bug in whichever mod
owns the id you landed on.

## The toolbar icon is cached on disk, and nothing invalidates it

`BlockTypeIconCreator` renders a modded block's toolbar thumbnail once and writes
it to

```
Besiege_Data/Mods/Thumbnails/Blocks/<mod guid>_<local block id>.png
```

and every later run loads that PNG. **Changing the mesh, the texture or the
`<Icon>` pose does not invalidate it** — the block in the world updates and its
icon does not, which reads as the icon having a different (wrong) model or
texture from the block.

Delete the file, or the whole `Thumbnails/Blocks` folder, and it is rendered again
on the next load. A mod cannot do that for itself: `ModIO` only reaches its own
folders, and this is not one of them.

Worth knowing while iterating on a mesh, and worth telling anyone who reports that
"the icon looks wrong but the block looks right".

## A generated mesh has to be wound right the first time

The usual safety net does not apply. A converter that reads a model can compare
each triangle's winding with the **shading normal** the file gave it and turn the
ones that disagree; a mesh you build out of boxes has no such normal -- you work
it out from the winding -- so the two always agree and a face put together the
wrong way round sails through.

In Besiege that face is back-face culled: you see straight through the block, and
what is left is lit as though it were inside out. It reads as a texture fault
rather than as a geometry one, which is why it is worth stating.

Check instead that every face points **away from the middle of the solid it
belongs to**, per primitive rather than per model -- a bar off to one side of a
mesh will fail a test against the whole model's centre while being perfectly
correct:

```python
n = face_normal(points)
mid = centroid(points)
assert dot(n, mid - centre_of_this_box) > 0
```

Orchestra's download-arrow block shipped with all six triangles of its arrowhead
inverted; the check above is now in the tool that generates it.

## A block needs `<AddingPoints>`, and `hasAddingPoint="true"` is not a substitute

A block with no `<AddingPoints>` list cannot be built on properly, and the failure
looks like a placement bug rather than a missing element: whatever you attach lands
*inside* the block and intersects it.

`InternalModding.Blocks.BlockPrefabCreator.SetupAddingPoints` treats the two
sources completely differently.

`<BasePoint hasAddingPoint="true">` creates one point, hardcoded:

```
localPosition    = (0, 0, 0.5)      // the block's own centre
localEulerAngles = (90, 0, 0)
trigger collider  center (0, -0.58, 0), size (0.6, 0, 0.6)
```

A declared `<AddingPoint>` takes its `Position` and `Rotation` from the XML and
then does something the implicit one never does:

```
transform.position -= transform.forward * 0.5f;
```

So the implicit point sits **half a block deeper** than any declared point would,
facing -Y. If it is the only adding point a block has, everything attaches into the
middle of it.

The five points every stock and modded block uses, which put a block on the same
1-unit grid as a base-game one:

```xml
<BasePoint hasAddingPoint="false">
  <Stickiness enabled="true" radius="1" />
  <Motion x="false" y="false" z="false" />
</BasePoint>
<AddingPoints>
  <AddingPoint><Position x="0.0" y="0.0"  z="1.0"/><Rotation x="0.0"  y="0.0"  z="0.0"/><Stickiness enabled="false" radius="0"/></AddingPoint>
  <AddingPoint><Position x="0.0" y="-0.5" z="0.5"/><Rotation x="90.0" y="0.0"  z="0.0"/><Stickiness enabled="false" radius="0"/></AddingPoint>
  <AddingPoint><Position x="0.0" y="0.5"  z="0.5"/><Rotation x="-90.0" y="0.0" z="0.0"/><Stickiness enabled="false" radius="0"/></AddingPoint>
  <AddingPoint><Position x="0.5" y="0.0"  z="0.5"/><Rotation x="0.0"  y="90.0" z="0.0"/><Stickiness enabled="false" radius="0"/></AddingPoint>
  <AddingPoint><Position x="-0.5" y="0.0" z="0.5"/><Rotation x="0.0" y="-90.0" z="0.0"/><Stickiness enabled="false" radius="0"/></AddingPoint>
</AddingPoints>
```

**Setting `hasAddingPoint="false"` does not stop the block attaching to a parent.**
That is a separate mechanism — the `TriggerForJoint` child and the block's
`ConfigurableJoint`, which `SetupAddingPoints` drives from `BasePoint.Sticky` and
`BasePoint.BreakForce`. A block with `hasAddingPoint="false"` and `Stickiness
enabled="true"` attaches normally and simply has no stray centre point.

Match the side offsets to the block's real width when it is not a 1-unit cube: a
thin glass pane uses `±0.05`. Keep the top at `z = 1.0` regardless, or it comes off
the grid.

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

## Taking the skin picker off a block

`BlockMapper.RefreshLists` shows the skin control when `OptionsMaster.skinsEnabled`,
the block is the only one selected, `Prefab.hasBVC`, `Prefab.CanGetNewVisuals`, and
`VisualController.Options.Count > 1`. `CanGetNewVisuals` is
`SkinCanBeChanged && (CanChangeMesh || CanChangeTexture)`, and `SkinCanBeChanged`
is a public field on `BlockPrefab`. So a block that should not be repainted -- one
wearing a mesh of its own, say -- clears it and the row goes away.

**Do not do that.** It works, and it breaks the block menu:

```csharp
BlockBehaviour.Prefab.SkinCanBeChanged = false;   // WRONG -- see below
```

`BlockPrefab.SetIcons` reads the same flag, and calls
`VisualController.SetPrefabIcons()` only when it is **true**. `SetPrefabIcons` is
what puts your block's own mesh and material on its button in the block menu.
Without it the button keeps what `BlockButtonCreator.CreateBlockButton` painted on
while the mod's resources were still loading -- `BlockLoader.LoadingMaterial`, with
no mesh -- so the block shows the **loading texture** in the menu. It survives
until something repaints the button, which `BlockButtonControl.Set` ->
`UpdateLimitText` -> `SetMaterial` does on a click, and at that point
`SetMaterialFromSkin` restores `defaultMat`, captured in `Setup()` -- which is the
loading material again. Clicking the block makes it worse, not better.

The symptom is specific enough to name: *the block in the menu is the loading
texture, and clicking it puts it back to the loading texture.* Clearing the flag
early -- for every prefab as soon as they are registered -- does not fix that, it
generalises it to every block in the mod.

**Right: hide the mapper control instead.** `GenericController.CreateContainers`
skips any MapperType whose `DisplayInMapper` is false. The control has to exist
before the mapper first opens, or the game builds it there and shows it once, so
make the same call `RefreshLists` would; `RefreshLists` then takes its reuse path,
which leaves `DisplayInMapper` alone.

```csharp
public static void Hide(BlockBehaviour block)                 // in SafeAwake
{
    if (block == null) return;
    if (block.Visual == null)
    {
        BlockVisualController visuals = block.VisualController;
        if (visuals == null || visuals.Options == null || visuals.Options.Count == 0) return;
        block.Visual = new MVisual(visuals, visuals.Options.IndexOf(visuals.selectedSkin),
                                   visuals.Options, "_CurrentSkin", null);
    }
    block.Visual.DisplayInMapper = false;
}
```

`"_CurrentSkin"` is the key the game itself gives the control: keep it, and a
machine saved before the change still finds its stored value.

With `StatMaster.collapseSkinMapper` on, the *collapsed* skin button is registered
before the gate `RefreshLists` applies and can still appear; clicking it marks the
mapper dirty, and the full path then finds nothing to show.

## A block's visual is not its transform

`BlockBehaviour.VisualController.renderers` lists the block's `MeshRenderer`s.
Their transforms are children carrying the `<Mesh>` offset and scale; the block's
**own** transform is the physics body the colliders are placed against.

Anything that moves a block for show — an animation, a swell, a wobble — writes to
the former and must not touch the latter, or the machine's collision changes with
the animation. And a simulation runs on a **clone** of the machine, so read the
renderer list from the instance that is running rather than caching it at load.

## The limits dial's little block is posed by `<LimitsDisplay>` alone

A block with `AddLimits` gets a mapper row with two dials and a small render of the
block between them. That render is posed by **nothing but** the `<LimitsDisplay>`
transform in the block XML, which becomes `MLimits.iconInfo`:

```csharp
// Selectors.LimitsSelector.Init, paraphrased
visual = Instantiate(Limits.LimitsDisplay.GetLimitsDisplay());   // the MeshRenderer's transform
visual.transform.parent = visHolder;
visual.transform.localPosition = Limits.iconInfo.localPosition;  // overwritten
visual.transform.localRotation = Limits.iconInfo.localRotation;  // overwritten
visual.transform.localScale    = Limits.iconInfo.localScale;     // overwritten
```

`GetLimitsDisplay()` is `MeshRenderer.transform` for base-game and modded blocks
alike, and all three of its local components are then overwritten. **The `<Mesh>`
element's own position, rotation and scale have no effect on this render.** So a
mesh that looks right in the world can be posed end-on in the dial, and the fix is
never in `<Mesh>`.

If the block is a variant of a base-game one, take the numbers from
`SteeringWheel.Awake`, which builds a `FauxTransform` per `BlockType`:

| | steering hinge | steering block |
| --- | --- | --- |
| position | `(0, -0.342, 0)` | `(0, 0.1, 0)` |
| rotation | `(90, 0, 0)` | `(0, 0, 0)` |
| scale | `0.5` | `0.33` |

Rotation is Euler degrees — `TransformValues.ToFauxTransform` is
`new FauxTransform(Position, Quaternion.Euler(Rotation), Scale)`.

The hinge's 90° about X is the whole lesson in one number. Its mesh is a body of
revolution about **local Z**, so with no rotation the dial looks straight down the
barrel and renders a featureless square — which reads as a missing texture, not as
a wrong pose. Whether the plate ends up above or below is checkable without
launching: measure the mesh's Z extent, work out which end the mounting plate is
on, and rotating +90° about X sends local −Z to world +Y.

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


## Text in the world draws through everything, until you change its shader

`DynamicText` (Besiege ships `DynamicText.dll` and uses it for its own in-level
signs) takes a `Font` and assigns that font's **shared** material to the renderer.
A `Font`'s material uses Unity's `GUI/Text Shader`, which is

```
Lighting Off Cull Off ZTest Always ZWrite Off
```

`ZTest Always` is right for a HUD and wrong for a sign standing in the level: the
text draws over the machine, the terrain and the sky, from every angle.

The fix is Unity's other built-in text shader, **`GUI/3D Text Shader`** — the same
fixed-function `combine primary, texture * primary` with no `ZTest` line, so it
depth-tests normally. It is present in Besiege's build (`sharedassets0.assets`,
and named in `globalgamemanagers`), so `Shader.Find` returns it, but keep a null
check: `Shader.Find` only finds what a build happens to include.

```csharp
text.autoSetFontMaterial = false;            // or it puts the shared one back
Material m = new Material(font.material);    // keeps the atlas and everything else
m.shader = Shader.Find("GUI/3D Text Shader");
GetComponent<MeshRenderer>().sharedMaterial = m;
```

Two things worth knowing that go with it:

- **`autoSetFontMaterial` is a public field on `DynamicText`, and it defaults
  true.** `GenerateMesh` re-assigns `Renderer.sharedMaterial = font.material`
  whenever the flag *changes*, so setting it false once is enough — but leave it
  true and your material is replaced behind you.
- **The two shaders take the colour from different places, so write it twice.**
  `DynamicText` bakes its own `color` into `Mesh.colors32` and sets no material
  property at all; a Font's stock material reads those vertex colours.
  `GUI/3D Text Shader` **does not** — its vertex program declares only `POSITION`
  and `TEXCOORD0`, with no `COLOR` input, and takes the whole colour from the
  `_Color` uniform. (Compare `Particles/Additive` in the same file, whose inputs
  are `in_POSITION0`, `VCOLOR`, `TEXCOORD0`.) Swap the shader and set only
  `DynamicText.color` and the text comes out flat white at full opacity. Set both
  `DynamicText.color` and `material.SetColor("_Color", tint)`: it cannot
  double-tint, because neither shader reads the other's source.

  This was got wrong first time from the plausible reading that Unity's text
  shaders are the old fixed-function `combine primary, texture * primary`. In this
  build they are compiled vertex/fragment programs, and the input lists are what
  settle it. `Shader "GUI/3D Text Shader"` and its GLSL are stored as readable text
  in `sharedassets0.assets` — the shader source is the check, and it is right
  there.

- **A mod tinting `font.material` is doing nothing useful**, and doing it to a
  material every other block using that font shares. Neither text shader has a
  `_TintColor`; both declare `_Color ("Text Color")`.

## `MSlider` does not clamp, but loading does

`MSlider.Value`'s setter stores whatever it is given — there is no clamp in it — so
a mod can put a value outside `Min`..`Max` and it works for the rest of the
session. `DeSerialize` is where it is taken away: loading a machine clamps the
value back into the range unless the slider is `Unclamped`, or the player has the
game's own *disable slider limits* option on (`StatMaster.KeyMapper.disableSliderLimits`).

So a settings box that accepts a number past the end of its slider should check
before keeping it, or the setting works today and is quietly lost on the next load:

```csharp
private static bool Free(MSlider slider)
{
    return slider.Unclamped || StatMaster.KeyMapper.disableSliderLimits;
}
```

`AddSliderUnclamped` is what sets that flag, and `Min`/`Max` are re-declared in
`SafeAwake` every session, so widening a range at runtime with `SetRange` does not
survive either. If going past the end is meaningful for a setting, declare it
unclamped when you add it.

## A block that previews itself needs a clock every block shares

Anything animated wants to look right in the build menu as well as in a run, and
the natural shape -- pin a start time the first time the block draws -- is wrong
the moment there are two of them. A run gives every block the same origin for
free, because the clones are made together; a preview starts when each block is
*placed*, so two lamps built a minute apart are a minute out of step.

Use a `static` origin, pinned by whichever instance previews first, and let the
per-run one stay per-instance:

```csharp
private static float previewStarted;
private static bool previewPinned;
```

Where the animation is a ping-pong, offset the **phase** rather than the time if
you want each block to start somewhere different. `Mathf.PingPong(t * speed, 1f)`
has a period of `2 / speed`, so an offset in seconds lands each of several settings
somewhere different when their speeds differ, while an offset in the ping-pong's
own 0..2 units is the same fraction of the sweep for all of them.

## Values that only some settings can use

Where one setting decides whether another means anything -- a light type that
governs which shaft controls apply, a mode that governs which numbers are read --
the block's own `Toggled` and `ValueChanged` handlers are the place to hide the
dead ones, with `Controls.Show`. Two things to know before leaning on that:

- Every `DisplayInMapper` change dirties the block mapper, which rebuilds all of
  its widgets. See [04-ui-factory.md](04-ui-factory.md).
- A setting that is merely *replaced* rather than added to -- a fixed value that an
  Auto sweep supersedes -- reads as live if it is left on screen. The stock mapper
  hides it; anything you build should too.

## A lamp block shadows itself, and `shadowNearPlane` is the way out

A `Light` added to a block sits at the block's origin, so the block's own housing
mesh surrounds it. It is then the nearest shadow caster the light has, and with
`Light.shadows` set to anything but `None` it blacks out the whole beam. Any child
mesh in front of the light does the same, if its shader has a ShadowCaster pass at
all -- the additive `_TintColor` materials a glowing lens tends to use do not.

Three ways out, and only one of them is free:

- **`Light.shadowStrength = 0`** turns the shadow off. What it fixes and what it
  breaks are the same thing.
- **`Renderer.shadowCastingMode = ShadowCastingMode.Off`** on the block's own
  renderers. It stops the self-shadow, but it stops the block casting from *every*
  light in the scene, the sun included -- the block stands there shadowless in
  daylight.
- **`Light.shadowNearPlane`**, set just past the furthest of the block's own
  meshes, clips them out of *this* light's shadowmap and nothing else's. Unity
  5.4 has it on spot and point lights; directional ignores it and takes
  `QualitySettings.shadowNearPlaneOffset` instead. Its one cost is that nothing
  within that distance casts into the light either, so a block pressed flat
  against the lamp's face will not shadow.

Directional needs none of this. With no apex, the housing only shadows a
block-sized patch behind itself instead of closing off a cone.

Two things that will make the shadow silently not appear at all: a light demoted
to vertex (`LightRenderMode.Auto` does this once `QualitySettings.pixelLightCount`
is used up -- force `ForcePixel` if the shadow matters), and anything past
`QualitySettings.shadowDistance`.

Cost is a depth-only re-render of the casters in range, once per lit light per
frame; six times over for a point light, and cascades plus a screen-space collect
pass for a directional one. It is charged in draw calls rather than fill, which
on a machine of hundreds of small blocks is the expensive half.

Note this is unrelated to the shadows in a volumetric shaft effect, which renders
its own shadowmap from its own camera and needs its own answer to the same
geometry problem -- typically flipping `Renderer.enabled` off around that one
render, which a real light cannot do without making the block vanish.

## The terrain does not take shadows from a light you add

A light a block carries will shadow other blocks and leave the ground untouched,
lit but with nothing drawn onto it. That is the engine, not the block.

Levels stand on a real Unity `Terrain` -- `TerrainModifierController` holds a
`Terrain` and a `TerrainCollider` -- and it draws with the built-in splatmap
shaders, which ship in `sharedassets11.assets`: `Nature/Terrain/Diffuse`,
`Specular` and `Standard`, each with its own `Hidden/TerrainEngine/Splatmap/*-AddPass`.

A second light on a surface is a `ForwardAdd` pass, and whether that pass can
sample a shadowmap depends on which keywords it was compiled with. In
`Hidden/TerrainEngine/Splatmap/Diffuse-AddPass` the only shadow keyword anywhere
is `SHADOWS_SCREEN`, which belongs to the `ForwardBase` pass and the sun; the
`ForwardAdd` pass carries no `SHADOWS_DEPTH` and no `SHADOWS_CUBE`, so a spot or
point light lights the ground through it and cannot shadow it. The `Standard`
variant does carry `SHADOWS_CUBE`, so which of the three a level uses may matter.

To confirm which end is at fault, aim the light so the same object casts onto a
block and onto the ground. A shadow on the block and none on the ground is this;
no shadow anywhere is your own light, and worth checking against
`QualitySettings.pixelLightCount`, `shadowDistance`, and whether the light is
`LightRenderMode.ForcePixel` -- a vertex light casts nothing. Note Unity decides
pixel-versus-vertex per renderer, so one light can be a pixel light on a nearby
block and a vertex light on the terrain behind it.

Short of handing the `Terrain` a `materialTemplate` of your own -- a splatmap
shader you would have to write, and which would change how every level looks --
there is nothing a mod can do about it.
