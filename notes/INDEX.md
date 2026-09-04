# Section index

Every `##` heading in every note, with line number. Read one section, not whole
note:

```sh
sed -n '186,265p' notes/01-loader-and-blacklist.md    # "The blacklist is a namespace..."
grep -n '^## ' notes/04-ui-factory.md                 # sections of one note
grep -rn 'DisplayInMapper' notes/                     # which notes name a symbol
```

Regenerate after editing a note: `./tools/index.sh`. Symbol map hand-kept, lives at
bottom.

## 01-loader-and-blacklist.md

- `3` Mod layout
- `53` Installing during development: symlink the mod folder
- `80` Where a mod may write
- `175` `<LoadInTitleScreen />` decides when the mod's code first runs
- `186` The blacklist is a namespace prefix test, with carve-outs
- `265` The compiler is Besiege's own, and it is ancient
- `297` A short public type name of your own collides three ways
- `334` Compiled DLL or ScriptAssembly: the difference that matters
- `371` Module attributes: required unless defaulted
- `410` `modid` on a module element is optional
- `435` When a block does not appear

## 02-blocks.md

- `3` Geometry conventions
- `24` Finding your own block's id at runtime
- `97` The toolbar icon is cached on disk, and nothing invalidates it
- `115` A generated mesh has to be wound right the first time
- `139` A block needs `<AddingPoints>`, and `hasAddingPoint="true"` is not a substitute
- `192` The toolbar icon
- `239` A mesh may be an outer skin with no inside
- `247` Colouring part of a block's mesh, without a second material
- `268` Taking the skin picker off a block
- `327` A block's visual is not its transform
- `338` The limits dial's little block is posed by `<LimitsDisplay>` alone
- `378` How a machine save names a modded block
- `421` Text in the world draws through everything, until you change its shader
- `474` `MSlider` does not clamp, but loading does
- `497` A block that previews itself needs a clock every block shares
- `519` Values that only some settings can use
- `532` A lamp block shadows itself, and `shadowNearPlane` is the way out
- `572` The terrain does not take shadows from a light you add
- `602` Making a block decoration: collider, visibility, mass

## 03-keys-and-automation.md

- `3` `MKey` carries the whole automation feature
- `12` Reading an emulated key
- `82` Variables are keys with names
- `167` The timer block
- `189` `MSlider.Value` does not clamp, and `Min`/`Max` are settable
- `205` Hiding a block's controls from Besiege's mapper

## 04-ui-factory.md

- `3` Besiege's own interface cannot be borrowed
- `30` What UI Factory is
- `165` Four more that cost something to find
- `197` Two that stop a panel dead
- `230` Dragging a number in an `Input Field`
- `275` One owner per `SetActive`, or the last writer wins
- `290` Two rows governed by one control
- `297` Rows that come and go, and closing up the gap
- `322` Tooltips
- `368` A window sized to its contents needs an edge to grow from
- `377` Depend on it softly
- `409` If you build a text field by hand
- `434` Committing a setting is not the same as setting it
- `442` Rebuild or rebind, but write every caption every time
- `475` Do not churn `DisplayInMapper`
- `490` The `Window` prefab's Viewport masks nothing until you size it
- `532` Hover swell does not ask whether the control works
- `546` The wheel over your panel also zooms the camera
- `566` `Scrollbar` is one of Besiege's own type names
- `575` The Bridge components, in full
- `593` Any part of a window can be a drag handle
- `612` Keep your canvas below `sortingOrder` 30000
- `619` Own the window's anchors before remembering where it is
- `633` You cannot colour a UI Factory graphic; put one of your own in front of it
- `653` A button inside a button works; a heading that fits its own button is the work
- `667` Whether a prefab's label is the prefab
- `676` UI Factory has no colour picker, and Besiege's is out of reach
- `706` Borrowing a prefab's own corners
- `718` What is in UI Factory's sprite bundle cannot be listed
- `731` Committing a typed value
- `747` The house style: how a selector and a toggle are built

## 05-docking-a-window.md

- `3` The problem
- `14` The recipe
- `47` Which renderer is the window
- `85` A docked panel wants no title bar
- `104` Closing with the mapper needs polling, not the close event
- `124` Recolouring a UI Factory Slider's track
- `139` Bringing an `Options` selector's arrows in
- `146` Three things that are not obvious once the geometry is right
- `158` Moving the mapper's own rows: `Top` destroys `Z`
- `200` Make it say what it found
- `207` Related useful pieces

## 06-reading-the-game.md

- `7` 1. Mono.Cecil against the game's assemblies
- `77` 2. A throwaway compile
- `97` 3. Strings and asset files
- `131` 4. Taking art and audio out of the game
- `151` 5. Make the mod tell you
- `166` 6. Build checks, and how they quietly stop checking
- `190` Things that bit, or nearly did

## 07-audio.md

- `7` `OnAudioFilterRead` runs *after* the source's 3D stage
- `67` The source must be playing at all
- `73` The audio thread
- `85` Let the source outlive the gate
- `94` DC is not always a bug
- `102` The master volume slider does not reach a block's AudioSource
- `134` A limiter has to live where the sum is
- `162` Sample rate

## 08-block-lifecycle.md

- `10` A simulation runs on a clone, so the run callbacks go to a different object
- `65` `IsSimulating` is false on a building block, even mid-run
- `84` `BuildingUpdate` runs — but only while nothing is simulating
- `136` The build machine is hidden for the run
- `142` The rule: reconcile, do not react
- `173` Holding the keyboard while a mod types

## 09-overlay-ui.md

- `8` Use uGUI, not `OnGUI`
- `38` A canvas over Besiege's UI does not stop it being clicked
- `82` Two transparent Images that overlap composite darker
- `102` Rich text is lowercase-only, and Besiege's captions are not
- `114` Read the player's real keybindings, do not print the defaults
- `123` Scene names tell you where the player is

## 10-resources-and-publishing.md

- `3` `<Resources>` is a manifest, and that is a design decision
- `45` Uploading resets your Workshop preview image
- `80` A read-only file in the staging folder stops every upload
- `98` `<ID>` and what breaks
- `105` What ships and what is fetched
- `122` The README every mod in this family uses
- `145` Install
- `146` <one section per thing the player does>
- `147` Notes
- `148` Credits
- `149` Licence

## 11-the-load-screen.md

- `7` The file browser is mesh UI, not uGUI
- `52` Repainting a copied slot button: three wrong answers and the right one
- `86` A copied button shows the *original's* tooltip — but you can repoint it
- `112` `IVirtualObject.Date` is a `Double`, and it is not an OLE automation date
- `127` Do not join paths; follow the browser
- `140` Writing in Besiege's font without a `Text` or a `TextMesh`

## 12-machines-and-saves.md

- `6` Besiege autosaves already, and has for years
- `31` Retuning a block does not count as changing the machine
- `66` Reading a `.bsg` when `System.IO.File` is blacklisted
- `84` `MachineInfo` and `BlockInfo`
- `116` Some blocks are several blocks
- `150` Loading a machine from a mod
- `163` Adding blocks to the machine, as a selection the player can move
- `207` Writing a `.bsg`: `XmlSaver.Save` is forbidden

## 13-drawing-over-the-machine.md

- `6` Use the game's own placement ghosts
- `33` Anything you build yourself has to be put on the machine's layer
- `43` Where to parent it
- `55` Blocks that are in two places
- `80` `Shader.Find` only finds shaders that shipped in the player's build
- `85` Scale a shell about its own middle

## 14-recovering-lost-source.md

- `9` You already have a decompiler's worth of tooling
- `26` What survives compilation, and what does not
- `37` The original was probably not built by Besiege's compiler
- `56` The check that is worth doing
- `72` Keep the harness for the cleanup afterwards
- `122` Two things this does not prove

## 15-level-state.md

- `7` A block behaviour only reaches its own block
- `44` Level state is global, and nothing puts it back for you
- `100` Derived thresholds go stale
- `117` Do not log per body

## 16-cloning-a-built-in-block.md

- `11` Read three things, in this order
- `24` The numbers are not guessable, and they are all right there
- `45` What the block XML can and cannot declare
- `67` API drift is silent until you compile
- `79` Match the mapper's shape too, not just the behaviour
- `91` What not to copy

## 17-level-editor-objects.md

- `12` There is exactly one hook, and it fires on the prefab
- `41` The SETTINGS tab takes the same controls a block's mapper does
- `93` Level variables are the way a level drives one object
- `129` A modded event gets a much poorer set of controls
- `140` Entity XML notes
- `153` Checked

## 18-vendoring-unity-code.md

- `7` The compiler will reject code that compiles anywhere else
- `17` A prebuilt asset bundle is per graphics API, and Linux is not Windows
- `52` Upstream's lifetime assumptions are wrong here
- `71` Read the shader before believing a setting does something
- `83` Provenance is not optional
- `94` Checked

## 19-multiplayer.md

- `7` Reading chat: the only hook is a log line
- `53` The chat window is uGUI, and a mod can dock to it
- `96` Finding another player's machine, and its core block
- `125` Players
- `145` `StatMaster` says which side you are on

# Symbol map

Which note names a thing. Notes by number; open section index above, then note.

| Symbol / topic | Notes |
| --- | --- |
| `Modding.ModIO`, file access | 01, 02, 06, 10, 12 |
| `AssemblyScanner`, blacklist, P/Invoke | 01 |
| `ScriptAssembly` vs prebuilt DLL | 01 |
| global type names, `Slider`/`Scrollbar`/`Keys`/`Convert` collisions | 01, 04 |
| `[DefaultValue]`, module attributes | 01, 06 |
| `Mod.xml`, `<ID>`, required elements | 01, 10 |
| `BlockPrefab`, `PrefabMaster`, block ids | 02, 03, 13 |
| `BlockTypeIconCreator`, toolbar icon cache | 02 |
| `<AddingPoints>`, `<BasePoint>` | 01, 02 |
| `<LimitsDisplay>`, limits dial | 02, 16 |
| `<Icon>`, icon camera, mesh scale | 02 |
| `MKey`, emulation, variables, timer | 03 |
| `MSlider`, clamping, `logScaling` | 02, 03, 04, 06, 16 |
| `MapperType`, `DisplayInMapper` | 02, 03, 04, 05, 12, 16, 17 |
| `BlockMapper`, docking, row layout | 02, 04, 05, 12 |
| `SaveableDataHolder`, `GetMapperType` | 04, 12, 16, 17 |
| UI Factory prefabs, `Besiege.UI.Make` | 04 |
| `ScaleAnimation`, `Translator`, Bridge components | 04 |
| `Chooser` / `Swell` house style | 04 |
| `StatMaster.DisableCameraZoom`, `SetInMenu` | 04, 08 |
| `StatMaster` flags generally | 02, 04, 06, 08, 12, 15, 19 |
| `OnAudioFilterRead`, audio thread, `AudioMixer` | 07 |
| `OnSimulateStart` / `Stop`, sim clone | 03, 06, 08, 17 |
| `BuildingUpdate`, `IsSimulating`, `levelSimulating` | 08 |
| `SimBehaviour`, level-wide components | 15 |
| `Physics.gravity`, global state restore | 08, 15 |
| `Camera.eventMask`, `IsPointerOverGameObject` | 06, 09 |
| own canvas, `sortingOrder`, `OnGUI` | 09 |
| `<Resources>`, `ModResource`, Workshop upload | 10, 18 |
| `AssetBundle`, shader per graphics API | 01, 12, 18 |
| `FileBrowserSlot`, `SimpleUIButton`, load screen | 06, 11 |
| `IVirtualObject`, `.Date` | 11, 12 |
| `MachineInfo`, `BlockInfo`, `.bsg` format | 02, 06, 12 |
| `XDataHolder`, `XData`, `XmlSaver.Save` | 01, 06, 12 |
| `LoadMachineInfo`, `AddBlocksFromInfo` | 06, 12 |
| `GhostTrigger`, placement ghosts, overlays | 13 |
| `Mono.Cecil`, `peek.sh`, `unbundle.py` | 01, 04, 06, 08, 14, 16, 17, 18 |
| recovering source, IL diffing | 14 |
| `LevelEntity`, `GenericEntity`, level variables | 17 |
| `ChatController`, `PlayerData`, `Playerlist` | 19 |
| `Shader.Find`, `DynamicText`, world text | 02, 13 |
