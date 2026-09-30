# Dangers: read this before writing any code

One-line index of the things in these notes that cost the most when missed. Each line
points at the section holding the evidence; this file argues nothing. Most are **silent**
— the game loads, nothing is logged, and the symptom shows up somewhere else.

Section names, not line numbers, because line numbers rot: find one with
`grep -n '^## ' notes/<file>`.

## The mod will not load, or the build lies

- **The blacklist refuses the whole assembly over one reference** — `System.IO`,
  `System.Reflection`, `System.Xml`, `System.Diagnostics`, `System.Net`, `Mono.*` and more.
  `GetType().Name` is a `System.Reflection` call. →
  01 *The blacklist is a namespace prefix test*
- **The compiler is C# 4 and any `enum` declaration segfaults it.** Global-namespace
  `Slider`, `Scrollbar`, `LOD`, `Particle` shadow Unity's. →
  01 *The compiler is Besiege's own*; 04 *`Scrollbar` is one of Besiege's own type names*
- **A short public type name of yours can collide** with `Keys`, `Convert` and others, and
  the error names somebody else's assembly. →
  01 *A short public type name of your own collides three ways*
- **A `ScriptAssembly` cannot reference another mod.** →
  01 *Compiled DLL or ScriptAssembly*
- **`ModIO` is the mod.io SDK**, not a file helper; `XmlSaver.Save` and
  `AssetBundle.LoadFromFile` are forbidden by name. →
  01 *`ModIO` is the mod.io SDK*; 01 *Where a mod may write*;
  12 *Writing a `.bsg`: `XmlSaver.Save` is forbidden*
- **Builds quietly stop checking** — a check that cannot run should fail loudly. →
  06 *Build checks, and how they quietly stop checking*

## A block or module does not appear, or appears as something else

- **`<LoadInTitleScreen />` can turn your block into another mod's block.** Block ids are
  numbered at load by GUID order and frozen into the prefab once; mods loaded later that
  sort earlier make your prefab point at their block, and it takes their mapper and
  behaviour. Leave the flag off unless the mod is about the title screen. →
  01 *`<LoadInTitleScreen />` decides when the mod's code first runs*
- **A `modid` that is present is the only thing consulted, and a wrong one is fatal and
  silent.** Absent is fine. →
  01 *`modid` on a module element is optional*
- **Module attributes are required unless they carry a `[DefaultValue]`.** →
  01 *Module attributes: required unless defaulted*
- **A block needs `<AddingPoints>`; `hasAddingPoint="true"` is not a substitute.** `--`
  inside an XML comment kills the file. →
  02 *A block needs `<AddingPoints>`*; 01 *When a block does not appear*
- **Finding your block's id at runtime: four plausible ways are wrong** (`locID`,
  arithmetic from one known block, `GetComponent` on a prefab, `BlockPrefab.name`). →
  02 *Finding your own block's id at runtime*
- **The toolbar icon is cached on disk and never invalidated.** →
  02 *The toolbar icon is cached on disk*
- **A generated mesh has to be wound right the first time.** →
  02 *A generated mesh has to be wound right the first time*
- **When a block misbehaves and stock blocks do not, bisect with an empty control block
  before theorising.** →
  02 *Bisect a block fault with an empty block*

## Saves and identity

- **`<ID>` is immutable once the game has seen the mod** — changing it, a block's id or
  an entity's id orphans saved machines, levels and Workshop subscribers. →
  10 *`<ID>` and what breaks*; 02 *How a machine save names a modded block*
- **Tuning a block's settings does not mark the machine as changed.** →
  12 *Retuning a block does not count as changing the machine*
- **An undo closes the block mapper and any panel of yours with it.** →
  12 *An undo closes the block mapper*

## Lifecycle and global state

- **A simulation runs on a clone;** run callbacks never reach the block the player is
  editing. `IsSimulating` is false on a building block even mid-run. →
  08 *A simulation runs on a clone*; 08 *`IsSimulating` is false on a building block*
- **`BuildingUpdate` is live** despite looking uncalled; hooks reached through
  `ldvirtftn` have no visible callers. → 08 *`BuildingUpdate` runs*; README
- **Level state is global and nothing restores it** — `Physics.gravity`,
  `RenderSettings.*` written during a run stay written into the next level. →
  15 *Level state is global*
- **A block behaviour only reaches its own block.** → 15 *A block behaviour only reaches its own block*
- **Entity hooks:** `OnEntityPrefabCreation` reaches only the mod that owns the entity, and
  none of the block lifecycle applies to entities. →
  17 *There is exactly one hook* (subsection *The hook reaches only the mod that owns the entity*)
- **A binding set in code needs `ApplyValue`** or it falls back on load. →
  03 *A binding set in code needs `ApplyValue`*
- **`MSlider.Value` does not clamp**, but loading does. →
  02 *`MSlider` does not clamp, but loading does*; 03 *`MSlider.Value` does not clamp*

## Input and UI

- **A mod key's default may collide with the game's own and nothing says so** (`Ctrl+C`,
  `Ctrl+Z`…). → 09 *A mod key's default may collide with the game's*
- **A canvas over Besiege's UI does not stop it being clicked**, and the wheel over your
  panel also zooms the camera. →
  09 *A canvas over Besiege's UI does not stop it being clicked*;
  04 *The wheel over your panel also zooms the camera*
- **Do not churn `DisplayInMapper`** — each change rebuilds every mapper widget. →
  04 *Do not churn `DisplayInMapper`*
- **One owner per `SetActive`**, or the last writer wins. →
  04 *One owner per `SetActive`*
- **Besiege's own interface cannot be borrowed; UI Factory is soft dependency** and the
  mod must cope with its absence. → 04 *Besiege's own interface cannot be borrowed*;
  04 *Depend on it softly*
- **Tab hides the game's interface, yours included.** → 09 *Tab hides the game's interface*

## Rendering, physics, audio

- **`Shader.Find` only finds shaders shipped in the player's build**; text in the world
  draws through everything until its shader is changed. →
  13 *`Shader.Find` only finds shaders*; 02 *Text in the world draws through everything*
- **A prebuilt asset bundle is per graphics API; Linux is OpenGL and wants the Mac
  bundle.** → 18 *A prebuilt asset bundle is per graphics API*
- **`detectCollisions = false` makes a block nothing can be built on.** →
  02 *`detectCollisions = false`*
- **Physics runs at 100 Hz, halving every budget you assumed.** →
  21 *Besiege's physics runs at 100 Hz*
- **`OnAudioFilterRead` runs after the 3D stage, on the audio thread**; the master volume
  slider does not reach a block's `AudioSource`. →
  07 *`OnAudioFilterRead` runs* after the source's 3D stage; 07 *The audio thread*
- **Drawing after `WaitForEndOfFrame` does nothing.** →
  20 *Drawing to the window after `WaitForEndOfFrame` does nothing*

## Publishing

- **Uploading resets the Workshop preview image; a preview over 1 MiB, or a read-only
  file in the staging folder, fails every upload.** →
  10 *Uploading resets your Workshop preview image*; 10 *A preview over 1 MiB*;
  10 *A read-only file in the staging folder*

## Working method

- **These notes have been wrong before, three times** (`BuildingUpdate`, `modid`, and the
  entity-hook broadcast claim). A confident story that fits a symptom is not the cause;
  the game's log and then its IL settle it. → README; note 06
- **Before editing a note to add a cause, check it against the IL.** The entity-hook
  claim was written from a plausible explanation and stood until the loader was read.
