# Blocks: XML, meshes, icons, visuals, saves

## Geometry conventions

Block mesh is **Z-up**, centred on origin, typically worn at half scale from
`z = 0.5` — convention Besiege's own generated blocks use.

**glTF right-handed, Unity left-handed, so the map must flip handedness.**
`(x, y, z) -> (-x, -z, y)` does it: up axis swaps in, two negated = reflection. A
swap that *preserves* handedness — obvious `(x, -z, y)` — gives a model that
measures correctly and is **mirrored**: invisible on a drum, plain on a piano once
you look at the keyboard.

Two consequences before changing that line:

- reflection doesn't commute with rotation, so mirroring reverses which way a
  given yaw carries its face. Fixing handedness means revisiting every pose angle;
  signs flip.
- if you render previews to judge a pose, preview projects into same left-handed
  frame: screen right is `cross(eye, up)`, **not** `cross(up, eye)` a
  right-handed frame wants. Backwards = every render is a mirror of the game,
  invisible until it matters, then costs a round of poses turned wrong way.

## Finding your own block's id at runtime

Mod writing blocks into a machine (generator, paste, anything building
`BlockInfo`) needs **id this Besiege gave each of its blocks** — assigned at load,
not in your XML. Two ways wrong, one right.

**Wrong: `BlockPrefab.locID`.** Public int sitting next to `Type` and `ID`, reads
exactly like block's local id. `BlockPrefab` constructor sets it **-1**; nothing
ever writes it for a modded block — only readers are a tooltip and a name
translation. Anything computed from it is out by whatever your local ids are.

**Wrong: arithmetic from one known block.** Mod's blocks numbered from a base in
manifest order, so `base = myType - myLocalId` and `base + otherLocalId` looks
sound. Not stable across installs: with other mods loaded, ranges aren't
contiguous and the id you compute is somebody else's block. A song generator doing
this filled machines with another mod's sound blocks — looks like id *conflict*,
really an id *guess*.

**Wrong: looking for your own behaviour on the prefab.** Subtle.
`BlockPrefabCreator.SetupBehaviour` *does* `AddComponent` a behaviour on the
prefab — but only the one a block declares with `<Script>`. A **module's**
behaviour is added by `ModBlockBehaviourHandler.Awake`, on the *instance*; a
prefab is an inactive object whose Awake never ran, so
`GetComponent<MyModuleBehaviour>()` on a prefab returns null every time. Module is
no help either: `RawModule` set in that same Awake.

**Wrong: `BlockPrefab.name` is the block's `<Name>`.** True for about a
microsecond. `BlockPrefabCreator.SetupBehaviour` sets `BlockPrefab.name` to
`ModdedBlock.Name`, then `BlockLoader.RegisterPrefab` — the method putting the
prefab in the table you're about to read — calls
`BlockPrefab.SetNameFromGameObject()`, copying the prefab *object's* name over it.
Matching on "Bass" finds nothing, for any modded block, ever. Not a near miss:
every block comes back unresolved and a generator that refuses to guess (rightly)
refuses to do anything.

**Right: prefab's name is `<mod guid>-<local id>`.**
`BlockPrefabCreator.CreatePrefab` names the prefab object
`Info.Mod.Info.Id + "-" + LocalId`; `SetNameFromGameObject` puts that on the
`BlockPrefab`. Exact, unique to your mod, both halves from files you already read:

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

**Table not filled when your `OnLoad` runs.** Blocks registered after mod
assemblies load, so single lookup at load finds nothing. Retry from a
`MonoBehaviour` — once a second until every block accounted for — and say
something only when the answer changes.

**Second best: `nameKeywords` carries the author.** `BlockPrefabCreator` fills
`BlockPrefab.nameKeywords` with block's `<SearchKeywords>` **plus owning mod's
`<Author>`**, and that survives the rename. Fallback worth keeping for a Besiege
that doesn't rename the prefab, paired with `<Name>` match:

```csharp
foreach (string keyword in prefab.nameKeywords)      // may be null
    if (keyword == myModAuthor) { id = (int)prefab.Type; }
```

When a block can't be found, **don't fall back to a guess**. Refuse. Wrong block
id is silent, and the machine it produces looks like a bug in whichever mod owns
the id you landed on.

## The toolbar icon is cached on disk, and nothing invalidates it

`BlockTypeIconCreator` renders a modded block's toolbar thumbnail once, writes to

```
Besiege_Data/Mods/Thumbnails/Blocks/<mod guid>_<local block id>.png
```

Every later run loads that PNG. **Changing mesh, texture or `<Icon>` pose does not
invalidate it** — block in world updates, icon doesn't, which reads as the icon
having a different (wrong) model or texture from the block.

Delete the file, or whole `Thumbnails/Blocks` folder, and it re-renders next load.
Mod cannot do that itself: `ModIO` only reaches its own folders, this isn't one.

Worth knowing while iterating on a mesh, and worth telling anyone reporting "the
icon looks wrong but the block looks right".

## A generated mesh has to be wound right the first time

Usual safety net doesn't apply. A converter reading a model can compare each
triangle's winding with the **shading normal** the file gave it and turn the
disagreeing ones; a mesh built out of boxes has no such normal — you derive it
from the winding — so the two always agree and a face put together the wrong way
sails through.

In Besiege that face is back-face culled: you see straight through the block, and
what's left is lit as though inside out. Reads as texture fault, not geometry one.

Check instead that every face points **away from the middle of the solid it
belongs to**, per primitive not per model — a bar off to one side of a mesh fails
a test against the whole model's centre while being perfectly correct:

```python
n = face_normal(points)
mid = centroid(points)
assert dot(n, mid - centre_of_this_box) > 0
```

Music's download-arrow block shipped with all six arrowhead triangles
inverted; check above is now in the tool that generates it.

## A block needs `<AddingPoints>`, and `hasAddingPoint="true"` is not a substitute

Block with no `<AddingPoints>` list can't be built on properly, and failure looks
like a placement bug rather than a missing element: whatever you attach lands
*inside* the block and intersects it.

`InternalModding.Blocks.BlockPrefabCreator.SetupAddingPoints` treats the two
sources completely differently.

`<BasePoint hasAddingPoint="true">` creates one point, hardcoded:

```
localPosition    = (0, 0, 0.5)      // the block's own centre
localEulerAngles = (90, 0, 0)
trigger collider  center (0, -0.58, 0), size (0.6, 0, 0.6)
```

A declared `<AddingPoint>` takes `Position` and `Rotation` from XML, then does
something the implicit one never does:

```
transform.position -= transform.forward * 0.5f;
```

So implicit point sits **half a block deeper** than any declared point, facing -Y.
If it's the block's only adding point, everything attaches into its middle.

The five points every stock and modded block uses, putting a block on the same
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

**`hasAddingPoint="false"` does not stop the block attaching to a parent.**
Separate mechanism — the `TriggerForJoint` child and the block's
`ConfigurableJoint`, which `SetupAddingPoints` drives from `BasePoint.Sticky` and
`BasePoint.BreakForce`. Block with `hasAddingPoint="false"` and `Stickiness
enabled="true"` attaches normally, just has no stray centre point.

Match side offsets to block's real width when not a 1-unit cube: thin glass pane
uses `±0.05`. Keep top at `z = 1.0` regardless, or it comes off the grid.

## The toolbar icon

`<Icon>` gives position, rotation, scale for a second camera photographing the
block for its toolbar tile. A few non-obvious things:

- **icon camera looks along +z**, not the -z a Unity camera defaults to. Undo the
  icon rotation to find where camera stands in block's frame and you get the
  *opposite* of the truth unless you negate. Measured, not reasoned: a pose worked
  out on the un-negated assumption drew every block from behind and below — legs,
  undersides, bottom drum heads.
- **X is what leans the block in the tile.** Unity applies an Euler triple Z, then
  X, then Y, and for a block whose face is turned towards the camera it is X's
  departure from -90 that tips the picture over; Y decides how much of that
  departure shows as lean, and Z spins the block about its own axis rather than
  turning the image. Measured on a preview grid, lean from vertical:

  | | `y 0` | `y -20` | `y -45` | `y -70` | `y -90` |
  | --- | --- | --- | --- | --- | --- |
  | **`x -90`** | 0° | 0° | 0° | 0° | 0° |
  | **`x -100`** | 0° | 5° | 10° | 10° | 10° |
  | **`x -110`** | 1° | 11° | 19° | 20° | 20° |
  | **`x -120`** | 1° | 18° | 29° | 30° | 30° |

  So **`x = -90` is upright at any turn**, and past `y -45` the lean is simply how
  far x is from -90. A block standing on a machine reads as upright even though the
  game's camera draws it leaning, and an icon that leans looks wrong beside the
  other tiles — so keep x within a few degrees of -90 and get the three-quarter out
  of y. (An earlier version of this note said the triple could not roll the picture
  and a later one said Z did; both were wrong, from reasoning rather than
  measuring.)
- **Y turns the block on its stand**, and how much of its side shows peaks around
  `y -45`: at `y -90` the near side has swung far enough round to start hiding
  again. A few degrees of x buys the top face without a visible lean.
- Anything round (drum head, cymbal) renders identically however it is spun, so
  the only knobs on it are the two that move the camera.

`<Icon>` **Scale is measured against the raw model**, not multiplied by `<Mesh>`
scale above it. Game's own blocks settle it: modelled at 100× size, carry
`Mesh 0.01` with `Icon 0.008`, which would be invisible if the two compounded. So
swapping a block's mesh for one authored at a different size means re-scaling the
icon with it — a mesh spanning two units where the old spanned 0.9 draws the tile
more than twice too large.

Anything a behaviour adds **at runtime is absent from the toolbar tile** — tile is
photographed from the block's mesh. Decoration that must appear in toolbar must be
part of the mesh, not a child object added in `SafeAwake`.

## A mesh may be an outer skin with no inside

Frame or cage modelled as a shell has outward-only faces, so from inside the far
side is back-face culled and the block reads hollow. Emit a reversed copy of every
face with normal turned round → solid from any angle; cost is double the faces,
nothing for a block. Check before assuming a mesh is wrong: count faces whose
normal points back toward the centroid; zero = this is why.

## Colouring part of a block's mesh, without a second material

Block's renderer gets one material, and Besiege's OBJ loading gives no submeshes
to hang a second one on. But a **texel** is addressable: give the part its own
corner of UV space, repaint that corner at runtime.

A 2×2 `Texture2D` with `filterMode = Point` suffices if the two unwraps sit in
different quadrants — one texel for block, one for part, point sampling means no
bleed. Twelve bytes per block, so each block lights independently.

Needs two things:

- **block's material must be re-checked, not remembered.** Besiege may build the
  visual after `SafeAwake` already looked, and a repaint replaces the material
  outright. Dress the block once and trust it = change silently undone. Re-apply
  whenever renderer isn't wearing yours, copying from whatever is on it at that
  moment so a paint colour survives;
- **pick the renderer whose material already has a `mainTexture`.** Finds the mesh
  the block is really seen as, and settles in passing that the shader reads its
  picture from `_MainTex` — otherwise a guess that fails silently.

## Taking the skin picker off a block

`BlockMapper.RefreshLists` shows skin control when `OptionsMaster.skinsEnabled`,
block is only one selected, `Prefab.hasBVC`, `Prefab.CanGetNewVisuals`, and
`VisualController.Options.Count > 1`. `CanGetNewVisuals` is
`SkinCanBeChanged && (CanChangeMesh || CanChangeTexture)`; `SkinCanBeChanged` is a
public field on `BlockPrefab`. So a block that shouldn't be repainted — one
wearing its own mesh — clears it and the row goes away.

**Don't.** It works, and it breaks the block menu:

```csharp
BlockBehaviour.Prefab.SkinCanBeChanged = false;   // WRONG -- see below
```

`BlockPrefab.SetIcons` reads the same flag and calls
`VisualController.SetPrefabIcons()` only when **true**. `SetPrefabIcons` puts your
block's own mesh and material on its button in the block menu. Without it the
button keeps what `BlockButtonCreator.CreateBlockButton` painted on while the
mod's resources were still loading — `BlockLoader.LoadingMaterial`, no mesh — so
the block shows the **loading texture** in the menu. Survives until something
repaints the button, which `BlockButtonControl.Set` -> `UpdateLimitText` ->
`SetMaterial` does on click, and at that point `SetMaterialFromSkin` restores
`defaultMat`, captured in `Setup()` — the loading material again. Clicking makes
it worse, not better.

Symptom, specific enough to name: *block in menu is the loading texture, and
clicking it puts it back to the loading texture.* Clearing the flag early — for
every prefab as soon as registered — doesn't fix that, it generalises it to every
block in the mod.

**Right: hide the mapper control instead.** `GenericController.CreateContainers`
skips any MapperType whose `DisplayInMapper` is false. Control must exist before
mapper first opens, or the game builds it there and shows it once, so make the
same call `RefreshLists` would; `RefreshLists` then takes its reuse path, leaving
`DisplayInMapper` alone.

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
Their transforms are children carrying `<Mesh>` offset and scale; the block's
**own** transform is the physics body the colliders are placed against.

Anything moving a block for show — animation, swell, wobble — writes to the former
and must not touch the latter, else machine collision changes with the animation.
A simulation runs on a **clone** of the machine, so read the renderer list from
the running instance rather than caching at load.

## The limits dial's little block is posed by `<LimitsDisplay>` alone

Block with `AddLimits` gets a mapper row with two dials and a small render of the
block between them. That render is posed by **nothing but** the `<LimitsDisplay>`
transform in block XML, which becomes `MLimits.iconInfo`:

```csharp
// Selectors.LimitsSelector.Init, paraphrased
visual = Instantiate(Limits.LimitsDisplay.GetLimitsDisplay());   // the MeshRenderer's transform
visual.transform.parent = visHolder;
visual.transform.localPosition = Limits.iconInfo.localPosition;  // overwritten
visual.transform.localRotation = Limits.iconInfo.localRotation;  // overwritten
visual.transform.localScale    = Limits.iconInfo.localScale;     // overwritten
```

`GetLimitsDisplay()` is `MeshRenderer.transform` for base-game and modded blocks
alike, and all three local components are then overwritten. **`<Mesh>`'s own
position, rotation and scale have no effect on this render.** So a mesh that looks
right in the world can be posed end-on in the dial, and the fix is never in
`<Mesh>`.

If the block is a variant of a base-game one, take numbers from
`SteeringWheel.Awake`, which builds a `FauxTransform` per `BlockType`:

| | steering hinge | steering block |
| --- | --- | --- |
| position | `(0, -0.342, 0)` | `(0, 0.1, 0)` |
| rotation | `(90, 0, 0)` | `(0, 0, 0)` |
| scale | `0.5` | `0.33` |

Rotation is Euler degrees — `TransformValues.ToFauxTransform` is
`new FauxTransform(Position, Quaternion.Euler(Rotation), Scale)`.

Hinge's 90° about X is the whole lesson in one number. Its mesh is a body of
revolution about **local Z**, so with no rotation the dial looks straight down the
barrel and renders a featureless square — reads as missing texture, not wrong
pose. Whether the plate ends above or below is checkable without launching:
measure mesh Z extent, work out which end the mounting plate is on; rotating +90°
about X sends local −Z to world +Y.

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

- `modId` + `localId` (block XML's own `<ID>`) resolve it:
  `XmlLoader.HandleMod` recomputes numeric `id` from them through
  `ModIds.GetEffectiveBlockId`, so the `id` attribute in the file isn't what finds
  the block. `fallback` = vanilla block shown when mod absent.
- every mapper control is `bmt-` + its key, element names the type: `Single`,
  `Integer`, `Boolean`, `StringArray`.
- `StringArray` with several entries written as `<String>` children, not inline
  text.
- block's `<Data>` may omit any key; block falls back to default. This lets a mod
  add controls without breaking old saves.
- machine's own `<Data>` carries `requiredMods` as `<guid>~L~<version>~<name>`.
- machine needs a starting block (`BlockType.StartingBlock` = 0).
- `(-0.7071068, 0, 0, 0.7071068)` — quarter turn about X — is what the game writes
  for a block placed on a flat surface, i.e. standing up. Identity leaves a block
  lying on its side.

Blocks in a save need **not** be connected to anything. Besiege loads them where
put; unattached ones fall when simulation starts — fine for anything whose job
isn't structural.

Vanilla block ids come from `BlockType` enum — `StartingBlock` 0, `Ballast` 35,
`Log` 63, `Sensor` 65, **`Timer` 66**, `Altimeter` 67, `LogicGate` 68, etc. Dump
it rather than trusting a list (see [06-reading-the-game.md](06-reading-the-game.md)).

## Text in the world draws through everything, until you change its shader

`DynamicText` (Besiege ships `DynamicText.dll`, uses it for in-level signs) takes
a `Font` and assigns that font's **shared** material to the renderer. A `Font`'s
material uses Unity's `GUI/Text Shader`:

```
Lighting Off Cull Off ZTest Always ZWrite Off
```

`ZTest Always` is right for HUD, wrong for a sign in the level: text draws over
machine, terrain and sky, from every angle.

Fix = Unity's other built-in text shader, **`GUI/3D Text Shader`** — same
fixed-function `combine primary, texture * primary` with no `ZTest` line, so it
depth-tests normally. Present in Besiege's build (`sharedassets0.assets`, named in
`globalgamemanagers`), so `Shader.Find` returns it — keep a null check anyway;
`Shader.Find` only finds what a build happens to include.

```csharp
text.autoSetFontMaterial = false;            // or it puts the shared one back
Material m = new Material(font.material);    // keeps the atlas and everything else
m.shader = Shader.Find("GUI/3D Text Shader");
GetComponent<MeshRenderer>().sharedMaterial = m;
```

Two things that go with it:

- **`autoSetFontMaterial` is a public field on `DynamicText`, defaults true.**
  `GenerateMesh` re-assigns `Renderer.sharedMaterial = font.material` whenever the
  flag *changes*, so setting false once is enough — leave it true and your
  material is replaced behind you.
- **The two shaders take colour from different places, so write it twice.**
  `DynamicText` bakes its own `color` into `Mesh.colors32` and sets no material
  property; a Font's stock material reads those vertex colours. `GUI/3D Text
  Shader` **does not** — its vertex program declares only `POSITION` and
  `TEXCOORD0`, no `COLOR` input, and takes the whole colour from the `_Color`
  uniform. (Compare `Particles/Additive` in the same file, inputs
  `in_POSITION0`, `VCOLOR`, `TEXCOORD0`.) Swap shader, set only
  `DynamicText.color`, and text comes out flat white at full opacity. Set both
  `DynamicText.color` and `material.SetColor("_Color", tint)`: cannot double-tint,
  because neither shader reads the other's source.

  Got wrong first time from the plausible reading that Unity's text shaders are
  the old fixed-function `combine primary, texture * primary`. In this build they
  are compiled vertex/fragment programs, and the input lists settle it.
  `Shader "GUI/3D Text Shader"` and its GLSL are stored as readable text in
  `sharedassets0.assets` — the shader source is the check, right there.

- **A mod tinting `font.material` does nothing useful**, and does it to a material
  every other block using that font shares. Neither text shader has a
  `_TintColor`; both declare `_Color ("Text Color")`.

## `MSlider` does not clamp, but loading does

`MSlider.Value`'s setter stores whatever it's given — no clamp — so a mod can put
a value outside `Min`..`Max` and it works for the rest of the session.
`DeSerialize` takes it away: loading a machine clamps back into range unless the
slider is `Unclamped`, or player has the game's *disable slider limits* option on
(`StatMaster.KeyMapper.disableSliderLimits`).

So a settings box accepting a number past the end of its slider should check
before keeping it, else the setting works today and is quietly lost next load:

```csharp
private static bool Free(MSlider slider)
{
    return slider.Unclamped || StatMaster.KeyMapper.disableSliderLimits;
}
```

`AddSliderUnclamped` sets that flag, and `Min`/`Max` are re-declared in
`SafeAwake` every session, so widening a range at runtime with `SetRange` doesn't
survive either. If going past the end is meaningful, declare it unclamped when you
add it.

## A block that previews itself needs a clock every block shares

Anything animated wants to look right in the build menu as well as a run, and the
natural shape — pin a start time the first time the block draws — is wrong the
moment there are two. A run gives every block the same origin free, because clones
are made together; a preview starts when each block is *placed*, so two lamps
built a minute apart are a minute out of step.

Use a `static` origin, pinned by whichever instance previews first, and let the
per-run one stay per-instance:

```csharp
private static float previewStarted;
private static bool previewPinned;
```

Where animation is a ping-pong, offset the **phase** rather than the time if you
want each block starting somewhere different. `Mathf.PingPong(t * speed, 1f)` has
period `2 / speed`, so an offset in seconds lands each of several settings
somewhere different when their speeds differ, while an offset in the ping-pong's
own 0..2 units is the same fraction of the sweep for all.

## Values that only some settings can use

Where one setting decides whether another means anything — light type governing
which shaft controls apply, mode governing which numbers are read — the block's
own `Toggled` and `ValueChanged` handlers are the place to hide the dead ones,
with `Controls.Show`. Two things first:

- Every `DisplayInMapper` change dirties the block mapper, rebuilding all its
  widgets. See [04-ui-factory.md](04-ui-factory.md).
- A setting merely *replaced* rather than added to — a fixed value an Auto sweep
  supersedes — reads as live if left on screen. Stock mapper hides it; anything
  you build should too.

## A lamp block shadows itself, and `shadowNearPlane` is the way out

A `Light` added to a block sits at block's origin, so the block's own housing mesh
surrounds it. It's then the nearest shadow caster the light has, and with
`Light.shadows` anything but `None` it blacks out the whole beam. Any child mesh
in front of the light does the same, if its shader has a ShadowCaster pass at all
— the additive `_TintColor` materials a glowing lens tends to use don't.

Three ways out, one free:

- **`Light.shadowStrength = 0`** turns the shadow off. What it fixes and what it
  breaks are the same thing.
- **`Renderer.shadowCastingMode = ShadowCastingMode.Off`** on block's own
  renderers. Stops self-shadow, but stops the block casting from *every* light in
  the scene, sun included — block stands shadowless in daylight.
- **`Light.shadowNearPlane`**, set just past the furthest of the block's own
  meshes, clips them out of *this* light's shadowmap and nothing else's. Unity 5.4
  has it on spot and point lights; directional ignores it and takes
  `QualitySettings.shadowNearPlaneOffset` instead. One cost: nothing within that
  distance casts into the light either, so a block pressed flat against the lamp's
  face won't shadow.

Directional needs none of this. With no apex, the housing only shadows a
block-sized patch behind itself instead of closing off a cone.

Two things making the shadow silently not appear at all: a light demoted to vertex
(`LightRenderMode.Auto` does this once `QualitySettings.pixelLightCount` is used
up — force `ForcePixel` if the shadow matters), and anything past
`QualitySettings.shadowDistance`.

Cost = depth-only re-render of casters in range, once per lit light per frame; six
times over for a point light, and cascades plus a screen-space collect pass for a
directional one. Charged in draw calls rather than fill, which on a machine of
hundreds of small blocks is the expensive half.

Unrelated to shadows in a volumetric shaft effect, which renders its own shadowmap
from its own camera and needs its own answer to the same geometry problem —
typically flipping `Renderer.enabled` off around that one render, which a real
light can't do without making the block vanish.

## The terrain does not take shadows from a light you add

A light a block carries shadows other blocks and leaves the ground untouched, lit
but with nothing drawn onto it. That's the engine, not the block.

Levels stand on a real Unity `Terrain` — `TerrainModifierController` holds a
`Terrain` and a `TerrainCollider` — drawn with built-in splatmap shaders shipping
in `sharedassets11.assets`: `Nature/Terrain/Diffuse`, `Specular`, `Standard`, each
with its own `Hidden/TerrainEngine/Splatmap/*-AddPass`.

A second light on a surface is a `ForwardAdd` pass, and whether that pass can
sample a shadowmap depends which keywords it was compiled with. In
`Hidden/TerrainEngine/Splatmap/Diffuse-AddPass` the only shadow keyword anywhere
is `SHADOWS_SCREEN`, belonging to the `ForwardBase` pass and the sun; the
`ForwardAdd` pass carries no `SHADOWS_DEPTH` and no `SHADOWS_CUBE`, so a spot or
point light lights the ground through it and cannot shadow it. The `Standard`
variant does carry `SHADOWS_CUBE`, so which of the three a level uses may matter.

To confirm which end is at fault, aim the light so the same object casts onto a
block and onto the ground. Shadow on block and none on ground = this; no shadow
anywhere = your own light, worth checking against
`QualitySettings.pixelLightCount`, `shadowDistance`, and whether the light is
`LightRenderMode.ForcePixel` — a vertex light casts nothing. Unity decides
pixel-versus-vertex per renderer, so one light can be a pixel light on a nearby
block and a vertex light on the terrain behind it.

Short of handing the `Terrain` a `materialTemplate` of your own — a splatmap
shader you'd have to write, changing how every level looks — there is nothing a
mod can do about it.

## Making a block decoration: collider, visibility, mass

A block meant as decoration -- a lamp, a sign, a pane of glass -- usually wants
three separate things, and they are worth keeping separate because they fail
separately:

- `Rigidbody.detectCollisions = false` stops it interacting with the world.
- `VisualController.SetInvisible()` stops it being drawn.
- `Rigidbody.mass = 0f` stops it hanging weight off the machine.

**A zero mass does not take the block off its joint.** Worth saying because the
opposite is easy to believe: Unity documents mass as needing to be positive, and
PhysX reads a zero mass as infinite rather than as nothing, so the theory sounds
right. Tested in Besiege, the block stays put and a run starts normally.

If a decorative block *does* come off, look at the joint before the mass. A
modded block that is heavier than its mounting suggests needs its own break force,
and Besiege's default is not enough:

```csharp
ConfigurableJoint joint = GetComponent<ConfigurableJoint>();
joint.breakForce = 16500f;
joint.breakTorque = 16500f;
```

Set that unconditionally, at the block's start frame. It is easy to bury it inside
some other branch -- past an early return for a light that happens to be switched
off, say -- and then the block snaps off in exactly the configuration nobody
tested, while holding fine in every other.
