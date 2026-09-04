# Besiege modding notes, for agents

<img src="Thumbnail.png" alt="thumbnail" width="200" align="right">

Working notes on Besiege's built-in mod loader. Gathered writing mods, kept because
most of it written down nowhere else. For whoever — or whatever — must find it out
next.

Target: **Besiege on Unity 5.4.0f3**, built-in mod loader (third-party `spaar` loader
deprecated and unrelated).

Notes terse on purpose: articles and filler dropped, code and API names exact.

**Do not read whole set.** [notes/INDEX.md](notes/INDEX.md) lists every section of
every note with line number, plus symbol → note map. Look symbol up, read that
section:

```sh
grep -rn 'DisplayInMapper' notes/          # which notes name it
sed -n '451,466p' notes/04-ui-factory.md   # just that section
```

## How to use these

Every claim read out of game's own assemblies, measured in game, or both; ones that
cost something say how. Where a note records *wrong* answer as well as right one,
deliberate — wrong answer usually the plausible one, and knowing which plausible
answers are wrong is most of the value.

**These notes have been wrong before.** 08 stated flatly `BuildingUpdate` never
called; it is called every frame while nothing simulating, and claim corrected only
when a later mod took it at face value and nearly deleted working code. 01 said block
needs `modid` on its module element; it does not — loader resolves element without one
against mod owning the file, and claim inherited from wrong diagnosis of a real bug
whose cause was elsewhere. Where a note records correction it says so and shows IL
that settles it. Treat confident phrasing as strong prior, not proof — and when a note
would have you delete something, verify first.

**Plausible cause is not the cause.** Both corrections above began as confident story
explaining the symptom. What settled them: game's own log, then game's own IL, in that
order — log says which file it rejected and why, IL says what loader actually branches
on. Reach for those before reasoning about what *must* be happening.

**Hook with no callers not necessarily dead.** Besiege reaches modded block's overrides
through `InternalModding.Blocks.ModBlockBehaviourHandler`, and those calls built as
delegates — `ldvirtftn` into `ModdingUtil.PerformCallback` — so search for callers of
method token finds nothing. `BuildingUpdate`, `KeyEmulationUpdate`, `OnSimulateStart`
and `OnSimulateStop` all look dead to that search, all four live. Check handler for
`ldvirtftn` of the method before concluding anything.

**Check before you trust.** These notes snapshot one build. Two techniques verify
anything here in a minute or two, both in
[notes/06-reading-the-game.md](notes/06-reading-the-game.md):

- read metadata with **Mono.Cecil**, ships in `Besiege_Data/Managed/`;
- **compile throwaway file** against game's assemblies — if it compiles, member exists
  with signature you guessed.

First is in this repo as runnable tool, plus reader for Unity asset bundles. Neither
needs anything installed — build with Besiege's own compiler, run on its own embedded
Mono:

```sh
./tools/peek.sh sig FileBrowserSlot     # a type's fields, properties and methods
./tools/peek.sh check claims.txt        # "ok" or "MISSING" per line, for a whole document
python3 tools/unbundle.py <bundle> Window --fields
```

Every API named here checked with `peek.sh check` on Besiege 5.4.0f3 / UI Factory 3 as
of August 2026. Re-run before trusting any of this against newer build.

## The notes

| File | What is in it |
| --- | --- |
| [01-loader-and-blacklist.md](notes/01-loader-and-blacklist.md) | mod layout, namespace blacklist and its carve-outs, **reading and writing anywhere on disk through `ModIO`**, file dialog game ships and never uses, ancient C# compiler, module attributes |
| [02-blocks.md](notes/02-blocks.md) | block XML, meshes and handedness, icons, block's visual vs its transform, how a save names a modded block |
| [03-keys-and-automation.md](notes/03-keys-and-automation.md) | `MKey`, key emulation, variables, timer block, and two traps that silently swallow input |
| [04-ui-factory.md](notes/04-ui-factory.md) | why Besiege's own UI cannot be borrowed, what UI Factory ships, how to depend on it softly, and **house style for selectors and toggles** |
| [05-docking-a-window.md](notes/05-docking-a-window.md) | putting uGUI window against block mapper, with mapper's measured geometry |
| [06-reading-the-game.md](notes/06-reading-the-game.md) | Cecil, probe compiles, unpacking asset bundles, where logs are, build-time checks that keep working |
| [07-audio.md](notes/07-audio.md) | generating audio in a block, and why Unity's own 3D panning cannot be used for it |
| [08-block-lifecycle.md](notes/08-block-lifecycle.md) | which callbacks reach which object, hooks never called, holding the keyboard |
| [09-overlay-ui.md](notes/09-overlay-ui.md) | full-screen overlay of your own: uGUI vs `OnGUI`, **why a canvas does not stop Besiege's own buttons being clicked**, transparency that composites wrong, rich text, scene names |
| [10-resources-and-publishing.md](notes/10-resources-and-publishing.md) | `<Resources>` vs runtime loading, icons and textures, why uploading resets your Workshop preview, **the README shape every mod in this family uses** |
| [11-the-load-screen.md](notes/11-the-load-screen.md) | file browser is mesh UI, not uGUI: copying a slot's button, repainting it, `IVirtualObject` |
| [12-machines-and-saves.md](notes/12-machines-and-saves.md) | autosave folder, reading a `.bsg` without file access, `MachineInfo`/`BlockInfo`, blocks that are several blocks, **adding generated blocks as a selection**, writing a save when `XmlSaver.Save` forbidden |
| [13-drawing-over-the-machine.md](notes/13-drawing-over-the-machine.md) | marking blocks with game's own placement ghosts, and layer that makes your own shapes invisible |
| [14-recovering-lost-source.md](notes/14-recovering-lost-source.md) | rebuilding a mod whose C# was lost, from shipped assembly, and how to *check* the reconstruction |
| [15-level-state.md](notes/15-level-state.md) | reaching every body in the level rather than your own block, and undoing global state you changed |
| [16-cloning-a-built-in-block.md](notes/16-cloning-a-built-in-block.md) | when your block is variant of a base-game one: reading its behaviour class for numbers, what block XML cannot declare, API drift |
| [17-level-editor-objects.md](notes/17-level-editor-objects.md) | modded entities: single prefab hook, real sliders on SETTINGS tab, level variables, why modded event usually wrong tool |
| [18-vendoring-unity-code.md](notes/18-vendoring-unity-code.md) | bringing open-source Unity effect in: enum that segfaults compiler, shader bundles per graphics API, upstream's lifetime assumptions |
| [19-multiplayer.md](notes/19-multiplayer.md) | **reading chat when there is no chat event and no reflection**, docking to chat window, finding another player's machine and its core block, keying settings by name rather than network id |

## Mods these came from

All by same author, all with own `AGENTS.md` and `docs/MODDING-NOTES.md` if you want
specifics rather than general lesson:

- **Clippy** — assistant living on canvas over whole game. Most of 09 and 10,
  ScriptAssembly and `ModIO` sections of 01, tooltip, scaler, canvas-lifetime and
  press-animation findings in 04.
- **Git View** — shows what changed between two saved versions of a machine. All of 11,
  12 and 13, click-through finding in 09, most of second half of 04.
- **Moon** — gravity gun and placeable planet, source lost and recovered from 2018
  assembly. All of 14 and 15, adding-points section of 02, install section of 01,
  correction to `BuildingUpdate` in 08.
- **Multiplayer Text to Speech** — reads multiplayer chat aloud in Klatt formant voice
  synthesised from scratch, positioned at speaking player's core block. All of 19,
  P/Invoke and required-manifest-element sections of 01, pre-rendered fourth row in 07,
  `RegisterCommand` confirmation in 06.
- **Music** — twelve instrument blocks and a thirteenth that turns a MIDI file into a
  machine playing them; audio on mixer thread, docked UI Factory panel, machines
  generated from a score in game. Most of automation and docking notes, additive-load
  and save-writing sections of 12, `ModIO` and file-dialog sections of 01. Its
  **Braids** block — macro-oscillator synthesising every sample live — gave all of the
  audio notes, block-lifecycle ones, and mesh and icon additions to 02.
- **Return 2 Center** — steering hinge and steering block springing back to centre,
  source likewise recovered from 2018 assembly. All of 16, limits dial in 02,
  `IsReleased` trap and multi-key emulation rules in 03, hook-identity finding in 08.
- **Special Effects** — particle, light, glass and text blocks, level editor object,
  vendored volumetric-lighting pass. All of 17 and 18, key-emulation split in 03,
  deprecated-`IsDown` and staging-folder traps, third and last of dead
  `OnSimulateStart` resets 08 warns about.
- **Timer Plus** — one block that is up to thirty-two timer blocks, table-driven. Timer
  block section of 03, keyboard-holding section of 08, `onEndEdit` commit rule in 04,
  the own-type-name collisions in 01 and the correction to `Slider` in 04.

## Licence

GPL-3.0, as repo was set up. Nothing of Spiderling Studios' redistributed here — these
are notes about their game, not their code.
