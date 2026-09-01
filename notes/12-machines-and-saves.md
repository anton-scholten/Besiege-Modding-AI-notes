# Machines, saves, and the autosave folder

How to read what the player has built, and what the game has already kept of it,
without being allowed to open a file. From **Git View**.

## Besiege autosaves already, and has for years

`AutoSave.MachineAutosaveController` is the base game's, not a mod's. It writes to
`StaticSettings.MachineAutosavePath`, which is `SavedMachines/AutoSave`:

```
SavedMachines/AutoSave/<machine name>/aut yy.MM.dd HH-mm-ss.bsg
SavedMachines/AutoSave/<machine name>/ver yy.MM.dd HH-mm-ss.bsg
SavedMachines/AutoSave/<machine name>/Thumbnails/<same name>.png
```

- `aut` is the timer. `AutosaveIntervalSeconds` is **60**, and a save is only taken
  if the machine changed (`MachineUpdatedSinceLastSave`).
- `ver` is `VersionMachine`, called when you save over an existing machine: the
  file about to be overwritten is copied here first. Gated on
  `OptionsMaster.BesiegeConfig.SavePreviousVersionsEnabled`, and skipped entirely
  for machines already inside the AutoSave folder.
- Both are pruned, by count and by age (`PruneFileCount`, `PruneOldFiles`).
- Thumbnails are 512x512 PNGs — a megabyte each as a texture, so hold only the ones
  on screen if you list them.
- The machine's own name is in the file, as `<String key="AutoSave">` in the
  machine's `Data` (`MachineAutosaveController.DATA_KEY`).

There is a lot of history sitting on every player's disk that nothing surfaces.

## Retuning a block does not count as changing the machine

Worth knowing for any mod that reacts to the machine changing, not just one that
reads autosaves.

`MachineUpdatedSinceLastSave` is set by exactly one thing:
`ReferenceMaster.onMachineModified`, a plain `Action<Machine>` static field. Seven
places in the game raise it —

```
Machine.FinishDraggedBlocks   Machine.OnAnalyzeComplete
PlayerMachine.RemoveBlock     UndoSystem.PostUndoAction
AddPiece.AddBlockTypeNoSound  AddPiece.PostRemoveBlock
SymmetryController.AddSymBlocks
```

— and **none of them is in the block mapper**. Remap a key, drag a slider, flip a
toggle: the flag stays clear, the sixty-second timer finds nothing to do, and the
new setting is never written to a version at all.

It hides well, because a tuning session nearly always moves a block eventually and
the settings ride along with that save.

The fix, if you need one: `BlockMapper.onMapperOpen` and `onMapperClose` are public
static `Action`s, and `BlockMapper.Current` is the `SaveableDataHolder` being edited
— its `MapperTypes` are live, each with a `Serialize()` giving the same `XData` the
save would. Fingerprint on open, compare on close, and **raise
`onMachineModified` yourself** if they differ. Raise the game's event rather than
setting the autosave's flag directly, so everything else listening (centre of mass,
aerodynamics, the block counter) hears what it would have heard anyway.

Order is on your side: `Open` sets `Current` before invoking `onMapperOpen`, and
`Close` invokes `onMapperClose` before tearing anything down, so both callbacks see
the real thing.

## Reading a `.bsg` when `System.IO.File` is blacklisted

A mod cannot open a file and cannot use `System.Xml` (see
[01-loader-and-blacklist.md](01-loader-and-blacklist.md)), which sounds like it
cannot read a save. It can — through the game.

- **Listing** goes through the browser's virtual folders: an `IVirtualObject` for
  each entry, `IsFolder` to walk down.
- **Parsing** goes through Besiege's own `XmlLoader`, which returns a
  `MachineInfo`. The game does the file access and the XML.

This is the general shape of working inside the blacklist: the capability is not
missing, it is behind an API of the game's, and finding that API is the job.

`Modding.ModIO` is no help here: it refuses any path outside the mod's own
folders — see [01-loader-and-blacklist.md](01-loader-and-blacklist.md) — and a
save is never in one.

## `MachineInfo` and `BlockInfo`

`MachineInfo.Blocks` is a `List<BlockInfo>`, and a `BlockInfo` carries `Guid`,
`ID` (a `BlockType`), `Position`, `Rotation`, `Scale`, `Flipped`, `Skin`,
`BlockData`, `EncodedSize` and `HasSimData`.

**The guid is per block, not per block type** — two identical girders have
different ones — which makes it the obvious key for "the same block, one save
later". It is not stable, though: over six real machines it moves for a handful of
blocks per save, on blocks otherwise untouched, and copying, mirroring and undo all
appear to reissue it. **A tool that pairs blocks by guid alone will report
inventions and deletions that did not happen.** Pair by guid first, then match what
is left by everything-else-identical, then by same-type-within-half-a-block.

`BlockData` is an `XDataHolder`. Read it with `ReadAll()` and each `XData`'s `Key`,
`Type` and `RawValue`:

- **Do not use `XDataHolder.Encode`.** It carries session flags —
  `WasLoadedFromFile`, `WasSimulationStarted` — which make every block in every
  save read as different.
- **Do not use `XData.Encode` either**, tempting as an exact digest is. Some
  settings hold live physics values: a piston's `start-position` came back as
  `5.96047E-08` one minute and `2.842171E-14` the next in a real autosave folder,
  with nobody having touched the machine. Go through `RawValue` so numbers can be
  rounded first.
- **Test `RawValue` with `is`, never `GetType().Name`.** `Type.Name` compiles to
  `System.Reflection.MemberInfo.get_Name`, and one reference to it is enough for the
  loader to refuse the whole assembly. `is` compiles to `isinst` and is free.

The per-block skin type is the nested `BlockSkinLoader.SkinPack.Skin`, with a `path`
and an `isDefault`. Whether it is resolved at all depends on how the file was
loaded — skins are resolved when a save is loaded for real, and not when it is
merely parsed — so treat an unresolved skin as "no skin" rather than guessing.

## Some blocks are several blocks

Two shapes in the palette are not one block in the file, and anything that counts,
pairs or draws blocks has to know it.

**Braces, fuel hoses and winch ropes** are one block that writes `start-position`
and `end-position` — two `Vector3`s in the block's own local space, which come back
through `TransformPoint`, so rotation *and* scale apply. Nothing else writes those
two keys, so recognising them by the data rather than by a list of block types
picks up modded blocks that drag the same way.

**A build surface is nine blocks.** The surface (id 73) writes `edges`: a `String`
of four guids separated by `|`. Each edge (id 72) writes `start` and `end`: the
guids of two corner nodes. Each node (id 71) is an ordinary block whose `Position`
is where that corner is, and it may be shared with the surface next door — one real
machine had 44 surfaces, 137 edges and 109 nodes.

The consequences are worth spelling out, because they are all silent:

- The surface's own `Position` is one of its corners, so anything that marks the
  block marks one corner of it.
- The nodes and edges have **no placement ghost** — nobody drags a corner out of
  the menu — so nothing is drawn for them either.
- Dragging a corner changes *only* the node. The surface's own position, rotation
  and `edges` list are identical before and after, so a surface whose shape was
  pulled about reads as unchanged unless the corner positions are folded into
  whatever fingerprint you compare.

Resolving the shape needs the whole machine in hand — a guid means nothing until
the block it names has been read — so it is a pass after parsing, not something a
block can answer about itself. Walk the four edges as a loop rather than taking the
nodes in the order they are named: the file does not promise an order, and a fan of
triangles through four corners in the wrong order is a bow tie.

## Loading a machine from a mod

`Machine.Active().LoadMachineInfo(info, resetUndoActions)` is the same call the load
screen makes, so joints, clusters and physics are worked out exactly as for any
other machine, and an interrupted load cannot leave half a machine behind.

**It does not finish in the frame it is called.** `Machine.IsLoadingMachine` is
public; wait for it before touching anything hanging off the machine's blocks,
because every one of them has just been destroyed and rebuilt.

`Machine.BuildingBlocks` is the live list. Saving walks it, which is the guarantee
that anything you parent into the machine that is *not* a `BlockBehaviour` cannot
end up in a save.

## Adding blocks to the machine, as a selection the player can move

`LoadMachineInfo` replaces the machine. To *add* to it — a mod that generates
blocks, pastes something, or builds a structure — copy
`MachineFileBrowserController.LoadAdditive`, which is what the load screen's "add
to machine" button runs. It is private, but every member it touches is public:

```csharp
machine.isLoadingInfo = true;                       // public field
StatMaster.mergeSurfaceTypesOnDeselect = false;     // put back afterwards
BlockSelectionTool.Duplicating = true;              // static

List<UndoAction> undo = new List<UndoAction>();
Dictionary<Guid, BlockBehaviour> made;
machine.AddBlocksFromInfo(blocks, out made, ref undo);   // NB: ref, not out

BlockSelectionTool picker = AdvancedBlockEditor.Instance.selectionController;
picker.DeselectAll(true, true);
AdvancedBlockEditor.Instance.SetActiveTool(StatMaster.Tool.Translate);
machine.UndoSystem.AddActions(undo);
picker.Select(new List<BlockBehaviour>(made.Values), true, true);
AddPiece.Instance.UpdateMiddleOfObject(true);
if (machine.onBatchOperationComplete != null) machine.onBatchOperationComplete();

BlockSelectionTool.Duplicating = false;
machine.isLoadingInfo = false;
```

The blocks arrive selected, with the move tool up, and one undo takes them all
away again — because it is the game's own path, not an imitation of it.

Worth knowing:

- The third argument of `AddBlocksFromInfo` is **`ref`**, so the list has to exist
  before the call. The signature reads as `out` and does not compile as one.
- `StatMaster.Tool` is an enum in the game; *referring* to one is fine, only
  **declaring** an enum segfaults Besiege's compiler.
- The `BlockInfo`s are built in memory — `Guid`, `ID` (a `BlockType`), `Position`,
  `Rotation`, `Scale`, `BlockData` — so nothing has to be written to disk or
  parsed. Positions are in the machine's space:
  `machine.BuildingMachine.InverseTransformPoint(worldPoint)`.
- `LoadAdditive` also drops the first block when the machine data says
  `SavedWithoutStartingBlock`; blocks a mod invents have no starting block to drop.

## Writing a `.bsg`: `XmlSaver.Save` is forbidden

Saving is not symmetrical with loading. **`XmlSaver.Save` is one of the four
methods the blacklist forbids by name** (with `LevelXMLSaver.Create` and
`AssetBundle.LoadFromFile`/`Async`), and every entry point that reaches it —
`MachineFileBrowserController.Save`, `.SaveSelection`,
`MachineAutosaveController.VersionMachine` — is private. There is no public route
to the game's writer, through the load screen or otherwise.

And a mod cannot write the file itself either: `ModIO` refuses `SavedMachines`
along with everywhere else outside its own folders. What is left is **Besiege's own
save screen**, which is public:

```csharp
// The view is inactive while closed, so FindObjectOfType will not see it.
FileBrowserView view = Resources.FindObjectsOfTypeAll<FileBrowserView>()[0];
view.Open(FileBrowserType.LocalMachines, true, true);   // type, isSaveMenu, ...
```

Add the blocks to the machine first (above) and they are selected, so the screen's
SELECTION ONLY button saves exactly them — and Besiege names the file, asks about
overwriting, and renders the thumbnail. `Open` closes the block mapper on its way
up, which takes any docked panel with it.

If you must produce the XML anyway — to write it into your own data folder, or to
compare against a generator — two things make that far less work than it sounds:

- **`XData.Type` is already the element name.** `XSingle.Type` is `"Single"`,
  `XStringArray.Type` is `"StringArray"` — the same words the file uses. Walking
  `XDataHolder.ReadAll()` and writing `<Type key="...">RawValue</Type>` needs no
  table of kinds and cannot fall behind one. A `string[]` `RawValue` becomes
  `<String>` children.
- `StaticSettings.SanatizeFileName` (sic) is public, and is what the game puts a
  typed name through before saving it.

What you do not get is a thumbnail — the game renders those itself when it saves —
so the machine shows a blank tile in the load screen until the player saves it
again.
