# Besiege modding notes, for agents

Working notes on Besiege's built-in mod loader, gathered while writing mods and
kept because most of it is not written down anywhere else. Written for whoever —
or whatever — has to find it out next.

Target: **Besiege on Unity 5.4.0f3**, built-in mod loader (the third-party `spaar`
loader is deprecated and unrelated).

## How to use these

Every claim here was read out of the game's own assemblies, measured in game, or
both, and the ones that cost something to establish say how they were established.
Where a note records a *wrong* answer as well as the right one, that is deliberate:
the wrong answer is usually the plausible one, and knowing which plausible answers
are wrong is most of the value.

**These notes have been wrong before.** 08 stated flatly that `BuildingUpdate` is
never called; it is called every frame while nothing is simulating, and the claim
was corrected only when a later mod took it at face value and nearly deleted
working code. 01 said a block needs a `modid` on its module element; it does not —
the loader resolves an element without one against the mod that owns the file, and
that claim had been inherited from a wrong diagnosis of a real bug whose cause was
elsewhere. Where a note now records a correction, it says so and shows the IL that
settles it. Treat confident phrasing here as a strong prior, not as proof — and
when a note would have you delete something, verify it first.

**The plausible cause is not the cause.** Both corrections above began as a
confident story that explained the symptom. What settled them was the game's own
log and the game's own IL, in that order — the log says which file it rejected and
why, and the IL says what the loader actually branches on. Reach for those before
reasoning about what *must* be happening.

**A hook with no callers is not necessarily dead.** Besiege reaches a modded
block's overrides through `InternalModding.Blocks.ModBlockBehaviourHandler`, and
those calls are built as delegates — `ldvirtftn` into
`ModdingUtil.PerformCallback` — so a search for callers of the method token finds
nothing. `BuildingUpdate`, `KeyEmulationUpdate`, `OnSimulateStart` and
`OnSimulateStop` all look dead to that search and all four are live. Check the
handler for a `ldvirtftn` of the method before concluding anything.

**Check before you trust.** These notes are a snapshot of one build. Two techniques
verify anything here in a minute or two, and both are described in
[notes/06-reading-the-game.md](notes/06-reading-the-game.md):

- read the metadata with **Mono.Cecil**, which ships in `Besiege_Data/Managed/`;
- **compile a throwaway file** against the game's assemblies — if it compiles, the
  member exists with the signature you guessed.

The first of those is in this repository as a runnable tool, along with a reader
for Unity asset bundles. Neither needs anything installed — they build with
Besiege's own compiler and run on its own embedded Mono:

```sh
./tools/peek.sh sig FileBrowserSlot     # a type's fields, properties and methods
./tools/peek.sh check claims.txt        # "ok" or "MISSING" per line, for a whole document
python3 tools/unbundle.py <bundle> Window --fields
```

Every API named in these notes was checked with `peek.sh check` on
Besiege 5.4.0f3 / UI Factory 3 as of August 2026. Re-run it before trusting any of
this against a newer build.

## The notes

| File | What is in it |
| --- | --- |
| [01-loader-and-blacklist.md](notes/01-loader-and-blacklist.md) | mod layout, the namespace blacklist and its carve-outs, **reading and writing anywhere on the disk through `ModIO`**, the file dialog the game ships and never uses, the ancient C# compiler, module attributes |
| [02-blocks.md](notes/02-blocks.md) | block XML, meshes and handedness, icons, a block's visual vs its transform, how a save names a modded block |
| [03-keys-and-automation.md](notes/03-keys-and-automation.md) | `MKey`, key emulation, variables, the timer block, and the two traps that silently swallow input |
| [04-ui-factory.md](notes/04-ui-factory.md) | why Besiege's own UI cannot be borrowed, what UI Factory ships, how to depend on it softly, and **the house style for selectors and toggles** |
| [05-docking-a-window.md](notes/05-docking-a-window.md) | putting a uGUI window against the block mapper, with the mapper's measured geometry |
| [06-reading-the-game.md](notes/06-reading-the-game.md) | Cecil, probe compiles, unpacking asset bundles, where the logs are, and build-time checks that keep working |
| [07-audio.md](notes/07-audio.md) | generating audio in a block, and why Unity's own 3D panning cannot be used for it |
| [08-block-lifecycle.md](notes/08-block-lifecycle.md) | which callbacks reach which object, the hooks that are never called, and holding the keyboard |
| [09-overlay-ui.md](notes/09-overlay-ui.md) | a full-screen overlay of your own: uGUI vs `OnGUI`, **why a canvas does not stop Besiege's own buttons being clicked**, transparency that composites wrong, rich text, scene names |
| [10-resources-and-publishing.md](notes/10-resources-and-publishing.md) | `<Resources>` vs runtime loading, icons and textures, and why uploading resets your Workshop preview |
| [11-the-load-screen.md](notes/11-the-load-screen.md) | the file browser is mesh UI, not uGUI: copying a slot's button, repainting it, `IVirtualObject` |
| [12-machines-and-saves.md](notes/12-machines-and-saves.md) | the autosave folder, reading a `.bsg` without file access, `MachineInfo`/`BlockInfo`, blocks that are several blocks, **adding generated blocks as a selection**, and writing a save when `XmlSaver.Save` is forbidden |
| [13-drawing-over-the-machine.md](notes/13-drawing-over-the-machine.md) | marking blocks with the game's own placement ghosts, and the layer that makes your own shapes invisible |
| [14-recovering-lost-source.md](notes/14-recovering-lost-source.md) | rebuilding a mod whose C# was lost, from the shipped assembly, and how to *check* the reconstruction |
| [15-level-state.md](notes/15-level-state.md) | reaching every body in the level rather than your own block, and undoing the global state you changed |
| [16-cloning-a-built-in-block.md](notes/16-cloning-a-built-in-block.md) | when your block is a variant of a base-game one: reading its behaviour class for the numbers, what block XML cannot declare, API drift |
| [17-level-editor-objects.md](notes/17-level-editor-objects.md) | modded entities: the single prefab hook, putting real sliders on the SETTINGS tab, level variables, and why a modded event is usually the wrong tool |
| [18-vendoring-unity-code.md](notes/18-vendoring-unity-code.md) | bringing an open-source Unity effect in: the enum that segfaults the compiler, shader bundles per graphics API, and upstream's lifetime assumptions |
| [19-multiplayer.md](notes/19-multiplayer.md) | **reading chat when there is no chat event and no reflection**, docking to the chat window, finding another player's machine and its core block, and keying settings by name rather than network id |

## Mods these came from

All by the same author, all with their own `AGENTS.md` and `docs/MODDING-NOTES.md`
if you want the specifics rather than the general lesson:

- **Orchestra** — nine instrument blocks and a MIDI loader; audio on the mixer
  thread, a docked UI Factory panel, machines generated from a score in game.
  Most of the automation and docking notes, the additive-load and save-writing
  sections of 12, and the `ModIO` and file-dialog sections of 01.
- **Special Effects** — particle, light, glass and text blocks, a level editor
  object, and a vendored volumetric-lighting pass. All of 17 and 18, the
  key-emulation split in 03, the deprecated-`IsDown` and staging-folder traps, and
  the third and last of the dead `OnSimulateStart` resets that 08 warns about.
- **Clippy** — an assistant that lives on a canvas over the whole game. Most of
  09 and 10, the ScriptAssembly and `ModIO` sections of 01, and the tooltip,
  scaler, canvas-lifetime and press-animation findings in 04.
- **Git View** — shows what changed between two saved versions of a machine. All
  of 11, 12 and 13, the click-through finding in 09, and most of the second half
  of 04.
- **Braids Synth** — a macro-oscillator block that synthesises every sample live.
  All of the audio notes, the block-lifecycle ones, and the mesh and icon
  additions to 02.
- **Moon** — a gravity gun and a placeable planet, whose source was lost and
  recovered from the 2018 assembly. All of 14 and 15, the adding-points section of
  02, the install section of 01, and the correction to `BuildingUpdate` in 08.
- **Return 2 Center** — a steering hinge and steering block that spring back to
  centre, source likewise recovered from a 2018 assembly. All of 16, the limits
  dial in 02, the `IsReleased` trap and the multi-key emulation rules in 03, and
  the hook-identity finding in 08.
- **Multiplayer Text to Speech** — reads multiplayer chat aloud in a Klatt
  formant voice synthesised from scratch, positioned at the speaking player's
  core block. All of 19, the P/Invoke and required-manifest-element sections of
  01, the pre-rendered fourth row in 07, and the `RegisterCommand` confirmation
  in 06.

## Licence

GPL-3.0, as the repository was set up. Nothing of Spiderling Studios' is
redistributed here — these are notes about their game, not their code.
