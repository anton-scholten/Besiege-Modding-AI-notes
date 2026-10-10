# Machines, saves, and the autosave folder

How to read what the player built, and what the game already kept of it, without
being allowed to open a file. From **Git View**.

## Besiege autosaves already, and has for years

`AutoSave.MachineAutosaveController` is the base game's, not a mod's. It writes to
`StaticSettings.MachineAutosavePath` = `SavedMachines/AutoSave`:

```
SavedMachines/AutoSave/<machine name>/aut yy.MM.dd HH-mm-ss.bsg
SavedMachines/AutoSave/<machine name>/ver yy.MM.dd HH-mm-ss.bsg
SavedMachines/AutoSave/<machine name>/Thumbnails/<same name>.png
```

- `aut` is the timer. `AutosaveIntervalSeconds` is **60**, and a save is taken only
  if the machine changed (`MachineUpdatedSinceLastSave`).
- `ver` is `VersionMachine`, called when you save over an existing machine: the file
  about to be overwritten is copied here first. Gated on
  `OptionsMaster.BesiegeConfig.SavePreviousVersionsEnabled`, skipped entirely for
  machines already inside the AutoSave folder.
- Both pruned, by count and by age (`PruneFileCount`, `PruneOldFiles`).
- Thumbnails are 512x512 PNGs — a megabyte each as a texture, so hold only the ones
  on screen if you list them.
- The machine's own name is in the file, as `<String key="AutoSave">` in the
  machine's `Data` (`MachineAutosaveController.DATA_KEY`).

A lot of history sits on every player's disk that nothing surfaces.

## Retuning a block does not count as changing the machine

Worth knowing for any mod reacting to the machine changing, not just one reading
autosaves.

`MachineUpdatedSinceLastSave` is set by exactly one thing:
`ReferenceMaster.onMachineModified`, a plain `Action<Machine>` static field. Seven
places raise it —

```
Machine.FinishDraggedBlocks   Machine.OnAnalyzeComplete
PlayerMachine.RemoveBlock     UndoSystem.PostUndoAction
AddPiece.AddBlockTypeNoSound  AddPiece.PostRemoveBlock
SymmetryController.AddSymBlocks
```

— and **none is in the block mapper**. Remap a key, drag a slider, flip a toggle: the
flag stays clear, the sixty-second timer finds nothing to do, and the new setting is
never written to a version at all.

Hides well, because a tuning session nearly always moves a block eventually and the
settings ride along with that save.

Fix, if you need one: `BlockMapper.onMapperOpen` and `onMapperClose` are public static
`Action`s, and `BlockMapper.Current` is the `SaveableDataHolder` being edited — its
`MapperTypes` are live, each with a `Serialize()` giving the same `XData` the save
would. Fingerprint on open, compare on close, and **raise `onMachineModified`
yourself** if they differ. Raise the game's event rather than setting the autosave's
flag directly, so everything else listening (centre of mass, aerodynamics, block
counter) hears what it would have heard anyway.

Order is on your side: `Open` sets `Current` before invoking `onMapperOpen`, and
`Close` invokes `onMapperClose` before tearing anything down, so both callbacks see the
real thing.

## Reading a `.bsg` when `System.IO.File` is blacklisted

A mod can't open a file and can't use `System.Xml` (see
[01-loader-and-blacklist.md](01-loader-and-blacklist.md)), which sounds like it can't
read a save. It can — through the game.

- **Listing** goes through the browser's virtual folders: an `IVirtualObject` per
  entry, `IsFolder` to walk down.
- **Parsing** goes through Besiege's own `XmlLoader`, returning a `MachineInfo`. The
  game does the file access and the XML.

General shape of working inside the blacklist: the capability isn't missing, it's
behind an API of the game's, and finding that API is the job.

`Modding.ModIO` is no help here: it refuses any path outside the mod's own folders —
see [01-loader-and-blacklist.md](01-loader-and-blacklist.md) — and a save is never in
one.

## Writing another mod's block into a machine

A block written into a `.bsg` by hand carries `modId`, `localId` and `fallback`
per block, not per file — so one machine can hold blocks from two mods, with a
different fallback each. `XmlLoader.HandleMod` recomputes the numeric `id` from
`modId` + `localId`, which is what makes the file portable across installs that
number blocks differently.

The machine's own `requiredMods` then has to name **every** mod it holds a block
from, or the game quietly swaps the unnamed one for its fallback. One entry is
written inline, several as `<String>` children. Entry format and where the version
comes from: [01](01-loader-and-blacklist.md).

Adding blocks to the *live* machine needs none of this — `BlockInfo.ID` is already
the id this install resolved.

## `MachineInfo` and `BlockInfo`

`MachineInfo.Blocks` is a `List<BlockInfo>`; a `BlockInfo` carries `Guid`, `ID` (a
`BlockType`), `Position`, `Rotation`, `Scale`, `Flipped`, `Skin`, `BlockData`,
`EncodedSize`, `HasSimData`.

**The guid is per block, not per block type** — two identical girders have different
ones — making it the obvious key for "the same block, one save later". Not stable
though: over six real machines it moves for a handful of blocks per save, on blocks
otherwise untouched, and copying, mirroring and undo all appear to reissue it. **A tool
pairing blocks by guid alone will report inventions and deletions that didn't happen.**
Pair by guid first, then match what's left by everything-else-identical, then by
same-type-within-half-a-block.

`BlockData` is an `XDataHolder`. Read it with `ReadAll()` and each `XData`'s `Key`,
`Type`, `RawValue`:

- **Don't use `XDataHolder.Encode`.** It carries session flags — `WasLoadedFromFile`,
  `WasSimulationStarted` — making every block in every save read as different.
- **Don't use `XData.Encode` either**, tempting as an exact digest is. Some settings
  hold live physics values: a piston's `start-position` came back as `5.96047E-08` one
  minute and `2.842171E-14` the next in a real autosave folder, nobody having touched
  the machine. Go through `RawValue` so numbers can be rounded first.
- **Test `RawValue` with `is`, never `GetType().Name`.** `Type.Name` compiles to
  `System.Reflection.MemberInfo.get_Name`, and one reference is enough for the loader
  to refuse the whole assembly. `is` compiles to `isinst` and is free.

Per-block skin type is the nested `BlockSkinLoader.SkinPack.Skin`, with a `path` and an
`isDefault`. Whether it's resolved at all depends how the file was loaded — skins are
resolved when a save is loaded for real, not when merely parsed — so treat an
unresolved skin as "no skin" rather than guessing.

## Some blocks are several blocks

Two shapes in the palette aren't one block in the file, and anything that counts, pairs
or draws blocks must know it.

**Braces, fuel hoses and winch ropes** are one block writing `start-position` and
`end-position` — two `Vector3`s in the block's own local space, coming back through
`TransformPoint`, so rotation *and* scale apply. Nothing else writes those two keys, so
recognising them by the data rather than by a list of block types picks up modded blocks
that drag the same way.

**A build surface is nine blocks.** The surface (id 73) writes `edges`: a `String` of
four guids separated by `|`. Each edge (id 72) writes `start` and `end`: guids of two
corner nodes. Each node (id 71) is an ordinary block whose `Position` is where that
corner is, and it may be shared with the surface next door — one real machine had 44
surfaces, 137 edges and 109 nodes.

Consequences worth spelling out, because all are silent:

- The surface's own `Position` is one of its corners, so anything marking the block
  marks one corner of it.
- Nodes and edges have **no placement ghost** — nobody drags a corner out of the menu —
  so nothing is drawn for them either.
- Dragging a corner changes *only* the node. The surface's own position, rotation and
  `edges` list are identical before and after, so a surface whose shape was pulled about
  reads as unchanged unless corner positions are folded into whatever fingerprint you
  compare.

Resolving the shape needs the whole machine in hand — a guid means nothing until the
block it names has been read — so it's a pass after parsing, not something a block can
answer about itself. Walk the four edges as a loop rather than taking the nodes in the
order they're named: the file doesn't promise an order, and a fan of triangles through
four corners in the wrong order is a bow tie.

**A build surface collides as thin slabs, not as its mesh.** `BuildSurface.GenerateColliders`
makes, under `simColliderParent`, one `BoxCollider` per quad of a curved surface (`AddCollider`,
children named `coll…`), each as thick as `GetColliderThickness()` — the thickness slider, a few
centimetres. A planar surface (`SurfaceInfo.EdgesPlanar`, `UseMeshColliderInSim`) instead gets a
convex `MeshCollider` on a generated "Planar Mesh Collider" slab, and the build-mode collider is
a separate `meshCollider` whose `convex` is flipped round cloning (`OnBeforeClone`/`OnAfterClone`).
Two consequences for a mod that collides its own things with blocks: the slab's mesh bounds in the
block's frame are not the slab — the block's axes follow a corner, not the plane, so a tilted
surface's local AABB is a box as tall as the surface is long — and anything resolved by "nearest
face" against a slab that thin is pushed out the wrong side once it is past the middle, and out
the edge into the seam where two surfaces meet. Fit the plane from the mesh's vertices, and push
out the face the thing came from.

## Loading a machine from a mod

`Machine.Active().LoadMachineInfo(info, resetUndoActions)` is the same call the load
screen makes, so joints, clusters and physics are worked out exactly as for any other
machine, and an interrupted load cannot leave half a machine behind.

**It doesn't finish in the frame it's called.** `Machine.IsLoadingMachine` is public;
wait for it before touching anything hanging off the machine's blocks, because every one
has just been destroyed and rebuilt.

`Machine.BuildingBlocks` is the live list. Saving walks it — the guarantee that anything
you parent into the machine that is *not* a `BlockBehaviour` cannot end up in a save.

## Adding blocks to the machine, as a selection the player can move

`LoadMachineInfo` replaces the machine. To *add* to it — a mod generating blocks,
pasting something, building a structure — copy
`MachineFileBrowserController.LoadAdditive`, what the load screen's "add to machine"
button runs. Private, but every member it touches is public:

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

Blocks arrive selected, move tool up, and one undo takes them all away again — because
it's the game's own path, not an imitation.

Worth knowing:

- Third argument of `AddBlocksFromInfo` is **`ref`**, so the list must exist before the
  call. The signature reads as `out` and doesn't compile as one.
- `StatMaster.Tool` is an enum in the game; *referring* to one is fine, only
  **declaring** an enum segfaults Besiege's compiler.
- The `BlockInfo`s are built in memory — `Guid`, `ID` (a `BlockType`), `Position`,
  `Rotation`, `Scale`, `BlockData` — so nothing must be written to disk or parsed.
  Positions are in the machine's space:
  `machine.BuildingMachine.InverseTransformPoint(worldPoint)`.
- `LoadAdditive` also drops the first block when the machine data says
  `SavedWithoutStartingBlock`; blocks a mod invents have no starting block to drop.

## One undo step for an edit that touches several controls

`BlockMapper.OnEditField` files one undo action per control (see
[04-ui-factory.md](04-ui-factory.md)), so a mod window whose one gesture moves a
node, renames a wire and rebinds two keys costs four presses of undo and comes back
a piece at a time. Two ways to file it as one:

- `UndoSystem.AddActions(List<UndoAction>)` wraps anything longer than one entry in
  a `MultiUndoAction`, which undoes as a single step;
- `UndoSystem.EditBlock(BlockInfo after, BlockInfo before)` files one
  `UndoActionEdit`, whose undo is `block.OnLoad(before.BlockData)` — the block's
  **entire** mapper state, every control at once. For a window that edits many
  controls of one block this is the simpler of the two, and it restores things the
  window never touched as a bonus rather than a bug.

```csharp
XDataHolder ignored = new XDataHolder();
block.OnSave(ignored);                       // see below
BlockInfo before = BlockInfo.FromBlockBehaviour(block);
... write MapperType.Value, then ApplyValue() on each ...
block.OnSave(ignored);
BlockInfo after = BlockInfo.FromBlockBehaviour(block);
Machine.Active().UndoSystem.EditBlock(after, before);
```

**`BlockInfo.FromBlockBehaviour` does not serialise the block if it has saved
before.** It clones `SaveableDataHolder.LastState` whenever `hasLastState` is set,
and that flag is set by the first `OnSave` or `OnLoad` the block ever sees. So a
snapshot taken without calling `OnSave` first is whatever the block last happened to
write — silently a few edits stale. Call `block.OnSave(new XDataHolder())` before
each snapshot; it costs a serialise and is what makes the pair honest.

Do this **instead of** `OnEditField`, not beside it, or the edit is filed twice —
but keep `OnEditField` for the multiplayer path, where the network handler is the
only thing that sends the change to the other players.

## Reading another block's settings, and taking it off the machine

Two things a mod that imports from the machine needs, both public, neither obvious.

**Read the settings off the live mapper controls, not out of a save.** A built-in
block keeps its `MKey`s and `MMenu`s in **private** fields — `LogicGate` has
`aKey`, `bKey`, `modeMenu`, `emulateKey`, `toggledInput`, `inverted`, all private —
but `SaveableDataHolder.MapperTypes` is a public `List<MapperType>` and every entry
carries the name its block registered it under:

```csharp
foreach (MapperType m in block.MapperTypes)
    if (m.Key == "activate-A") { MKey a = m as MKey; ... }
```

**`MapperType.Key` is the bare name, not the `bmt-` one.** `LogicGate.Awake`
registers `activate-A`, `activate-B`, `Gate`, `toggle-mode`, `inverted`, `emulate`;
`bmt-` is `MapperType.XDATA_PREFIX`, and it goes on only when the value is written
to a save. Search the live controls with the save's spelling and every lookup
silently returns null — which reads, in a mod, as a block whose settings cannot be
read at all. Compare against `MapperType.XDATA_PREFIX + m.Key` if your own constants
are in the save's form.

That is the whole of it: no reflection, no `OnSave` round-trip, no parsing of the
`XStringArray` a key serialises to — and the objects you get back are the same
`MKey`/`MMenu`/`MToggle` your own block's controls are, so the same helpers work on
both. (`BlockBehaviour.OnSave` into an `XDataHolder` is the fallback if you ever
need a block's state as data rather than as controls.)

**`BlockSelectionTool.RemoveBlocks(List<BlockBehaviour>, bool)` is public**, takes
any list rather than the current selection, deletes the way the delete key does —
joints and all — and **returns its `List<UndoAction>` instead of filing it**.
`RemoveSelection` is the thin wrapper that runs it on the selection and files the
result. Getting the actions back is what lets a removal and your own edit undo
together:

```csharp
BlockInfo before = ...;                          // your block, before
// ... change your block's controls, ApplyValue each ...
List<UndoAction> undo = picker.RemoveBlocks(taken, true);
undo.Add(new UndoActionEdit(machine, after, before));   // public ctor: machine, after, before
machine.UndoSystem.AddActions(undo);             // >1 becomes one MultiUndoAction
```

Check `AdvancedBlockEditor.Instance.selectionController` is there **before** you
start, not after: a run that reads blocks into your own state and then cannot
remove them leaves the machine holding both.

## Your own steps in the machine's undo history

A mod can put changes of its own — terrain it paints, say — into the machine's history, so the game's
undo and redo buttons and keys take them back in order with block edits. Subclass `UndoAction` (its
constructor is reachable from a mod, and `Undo()` / `Redo()` are abstract `bool`s) and add it with
`Machine.Active().UndoSystem.AddAction(action)`, which, like any new edit, drops the redo tail past
`snapIndex`.

- **Leave every change flag false** (`changesTransform`, `changesCount`, `changesOBM`,
  `changesParameters`). `PreUndoAction` / `PostUndoAction` read only those, and with them off do nothing
  for the machine: no interpolation reset, no cluster rebuild, no `GetBlocks()` call. `info` and `machine`
  may stay null.
- **Returning false means "nothing done, try the next one".** `UndoSystem.Undo` loops back through
  `undoList` until an action returns true (and `Redo` forward). A step that can no longer apply — its
  world replaced since — returns false and the player's press goes to the step before it, rather than
  doing nothing.
- **Never add an action while one is being undone or redone.** `AddAction` logs
  `[UndoSystem]: trying to create undo while undoing.` (the static `processing` flag) and still adds it,
  after cutting the list at `snapIndex` — the redo of what was just undone is gone.
- **Add a long edit's step when it begins, not when it ends.** An edit that takes time to finish (a brush
  stroke whose pile settles over the next frames) added at its end lets anything the player does in
  between — a block placed — go in ahead of it, and undo takes them back out of order. Add the step empty
  at the start and fill it at the end; an `Undo()` that finds it still open finishes the edit first, then
  undoes it. That also never adds an action mid-undo.
- **Undo is building-only.** `Undo()` returns early unless `CanInteract()`: an active machine, no batch
  change, `stopHotkeys` down, and `Machine.ReadyForSim`. Steps recorded during a run are steps the player
  cannot reach until it ends, so don't record them.

## An undo closes the block mapper, and your panel with it

`UndoSystem.Undo` and `Redo` both end with `CheckOpenBlockMapper`, which calls
`AdvancedBlockEditor.CheckShowBlockMapper()`. With the Modify tool up that method is:

```
if (SelectionCount > 0)  BlockMapper.Open(selectionController.LastBlock);
else                     BlockMapper.Close();
```

Clicking a block to open its mapper does **not** put that block in
`BlockSelectionTool`'s selection, so the usual case — one block's menu open, nothing
selected — takes the `else`, and **every undo closes the mapper**. A window that shows
itself on `onMapperOpen` and hides on `onMapperClose` therefore vanishes when the
player presses undo, for an edit that only changed one of its own values. The other
branch is no gentler: `BlockMapper.Open` begins with `Close(true)`, so the reopen fires
`onMapperClose` too.

`UndoAction.ApplyInfo` also calls `SetActiveTool(StatMaster.Tool.Modify, false)` and,
if the mapper is on some *other* block, opens it on the block being restored.

If your window is not really part of the mapper — a floating editor, say — hold a flag
across your own call to `Undo`, ignore the close while it is set, and put the menu back
afterwards with the game's own call:

```csharp
stepping = true;
try
{
    machine.UndoSystem.Undo();
    // Nothing else claimed it: the step closed the menu, so open it again.
    if (BlockMapper.CurrentInstance == null || !BlockMapper.IsOpen)
    {
        BlockMapper.Open(block);     // BlockBehaviour is a SaveableDataHolder
    }
}
finally { stepping = false; }
```

Check `IsOpen` before reopening rather than reopening blindly: an undo made with
several blocks selected legitimately puts the mapper on the selection's last block, and
dragging it back to yours is fighting the player.

## Writing a `.bsg`: `XmlSaver.Save` is forbidden

Saving isn't symmetrical with loading. **`XmlSaver.Save` is one of the four methods the
blacklist forbids by name** (with `LevelXMLSaver.Create` and
`AssetBundle.LoadFromFile`/`Async`), and every entry point reaching it —
`MachineFileBrowserController.Save`, `.SaveSelection`,
`MachineAutosaveController.VersionMachine` — is private. No public route to the game's
writer, through the load screen or otherwise.

And a mod can't write the file itself either: `ModIO` refuses `SavedMachines` along with
everywhere else outside its own folders. What's left is **Besiege's own save screen**,
which is public:

```csharp
// The view is inactive while closed, so FindObjectOfType will not see it.
FileBrowserView view = Resources.FindObjectsOfTypeAll<FileBrowserView>()[0];
view.Open(FileBrowserType.LocalMachines, true, true);   // type, isSaveMenu, ...
```

Add the blocks to the machine first (above) and they're selected, so the screen's
SELECTION ONLY button saves exactly them — and Besiege names the file, asks about
overwriting, and renders the thumbnail. `Open` closes the block mapper on its way up,
taking any docked panel with it.

If you must produce the XML anyway — to write into your own data folder, or to compare
against a generator — two things make that far less work than it sounds:

- **`XData.Type` is already the element name.** `XSingle.Type` is `"Single"`,
  `XStringArray.Type` is `"StringArray"` — the same words the file uses. Walking
  `XDataHolder.ReadAll()` and writing `<Type key="...">RawValue</Type>` needs no table
  of kinds and cannot fall behind one. A `string[]` `RawValue` becomes `<String>`
  children.
- `StaticSettings.SanatizeFileName` (sic) is public, and is what the game puts a typed
  name through before saving it.

What you don't get is a thumbnail — the game renders those itself when it saves — so the
machine shows a blank tile in the load screen until the player saves it again.

## Steering the save and load screens, and changing what they write

Read from the IL; the Sand mod's sand files are built on it. Everything needed is public:

- **Into a folder of your own.** `view.Open(FileBrowserType.LocalMachines, isSaveMenu, false)`, then on the
  following frames `view.Controller.Collection` (`AbstractObjectCollection`): `GetRoot()`, `CurrentFolder`,
  and `VirtualFolder.GetObjects()` to find a child by `Name`; `view.Controller.CreateFolder(name)` makes one
  in the current folder (and tells the view), `view.Controller.OpenFolder(folder)` goes there (but to
  *open* the screen in your folder, prime its memory instead — below). The screen
  fills itself over a frame or two after `Open`, so retry rather than doing it in the same frame.
  `AbstractObjectCollection.CreateFolder` itself is the base class's, which only returns `CreateFailed`;
  go through the controller.
- **`XmlSaver.OnSave` runs before anything is written.** `XmlSaver.Save(MachineInfo, path)` invokes the
  `OnSave(MachineInfo)` event first, on the `MachineInfo` that `CreateMachineInfo(true)` just built (a copy,
  not the live machine), then writes it. A handler can add to `MachineData` or take blocks out of `Blocks`,
  and the file holds what it left. Subscribing (`add_OnSave`) passes the blacklist; only `Save` itself is
  forbidden. `Events.OnMachineSave` is the same moment wrapped in a `PlayerMachineInfo`.
- **`XmlLoader.OnLoad` runs as the file is read, before the game decides what to do with it.**
  `MachineFileBrowserController.LoadFile` parses first (`GetMachineInfo`, which ends in
  `LoadFromXmlDocument`, which raises `OnLoad`) and only then branches on load or "add to machine"
  (`LoadAdditive`), so the handler cannot tell which the player pressed. "Add to machine" drops the first
  block when `MachineData` has `SavedWithoutStartingBlock = true`, so a file of one starting block with
  that key adds nothing; a plain load replaces the machine with it. To keep the player's machine through
  a plain load, take `Machine.Active().CreateMachineInfo(true)` in the handler and, once
  `Machine.IsLoadingMachine` is false again, `LoadMachineInfo(it, false)` if the machine is now that one
  block.

**The screen reopens where the last save or load happened, and that is a field you cannot set directly.**
`FileBrowserController.OnFileSaved` and `OnFileLoaded` call `view.SetRestoreFolder(false)`, which copies
the view's private `currentFolder` into `restoreFolder` and the browser type into `lastBrowserType`; the
game's own buttons open with `Open(type, isSave, restore: true)`, which goes back there when the type
matches. So a mod that saves or loads in a folder of its own leaves the game's buttons opening in that
folder. To give them back their folder: remember it when you open (open with `restore: true` and read
`Controller.Collection.CurrentFolder` before navigating away), and after your save, in one frame,
`Open(type, false, false)`, `Controller.OpenFolder(remembered)` (which runs `Generate` and sets
`currentFolder`), `SetRestoreFolder(false)`, `Close()` — nothing of it is drawn. The view's
`Generate(VirtualFolder)` is public too, but called while the view is inactive it starts a coroutine on an
inactive object, which Unity logs as an error.

**To open the screen in a folder of your own, prime its memory instead of steering it after.** Taking the open
screen into another folder (`Controller.OpenFolder`) was reported not to hold in game — with a machine loaded
it came back to the machine's folder. The priming below is the fix, not yet confirmed in game either. What holds is the game's own path: set `restoreFolder` and
`restoreObject` and open with `restore: true`. In one frame: `Open(type, isSave, false)`, `OpenFolder(yours)`,
optionally `view.SelectObject(file)` (and `FileBrowserView.FieldValues[folder.ObjectPath.ToString()] = file`,
the public static map from a folder's path to its selected file, which `Generate` re-selects whenever the
folder is shown), `SetRestoreFolder(false)` (folder = the view's current folder, object = its selected
object), `Close()`; then `Open(type, isSave, true)` for real. A selected file's name goes into the name box,
so this is also how to pre-fill the name. Read the name box itself with
`view.GetComponentsInChildren<Selectors.TextHolder>(false)` and `ValueText` (the field holding it is private).
A file's `IVirtualObject.Name` is its name without `.bsg`.

**`AbstractObjectCollection.GetRoot()` is a new, empty folder every call.** `LocalFileCollection.GetRoot` builds a
`LocalFolder` for the root path each time it is asked, with nothing in it until its `Open()` reads the disk
(`LocalFolder.Open` is synchronous: `Clear`, list the directory, `AddRange`). Search it as it comes and every
folder is missing; compare it with `CurrentFolder` by reference and they never match. Call `Open()` on it
first (on the `LocalFolder`, whose `Open` is the one that reads), and compare folders by `ObjectPath.Path`.

**The thumbnail is taken after the save returns**, and can be re-aimed: see
[20](20-rendering-and-cameras.md) ("Re-aiming the game's thumbnail camera").

**The game loads machine files for itself, and `XmlLoader.OnLoad` fires for each.** Saving over an existing file
first loads the old one (`MachineAutosaveController.VersionMachine`, to copy it into `AutoSave` as a version);
`AddPiece`'s auto-load at start, `BesiegeContentHelper` and the performance test load files too. A handler that
acts on mod data in a loaded file must check that the player is loading — the load screen open and not a save
menu — or the old file's data lands in the middle of a save.
