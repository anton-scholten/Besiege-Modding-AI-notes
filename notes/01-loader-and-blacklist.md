# The loader, the blacklist, and the compiler

## Mod layout

Mod = folder with `Mod.xml`. Manifest declares metadata + each component:
`Assemblies`, `Blocks`, `Entities`, `Triggers`, `Events`, `Keys`, `Resources`.
Hand-installed mods live `Besiege_Data/Mods/`; Workshop subs
`steamapps/workshop/content/346010/`.

`<ID>` = GUID **game writes on first load**. Never hand-edit, never change after
publish — saved machines refer to blocks by it. Fresh clone has no ID until game
saw it once. Check that before blaming anything else for block not appearing.

### Five elements required, `MultiplayerCompatible` is the missed one

Manifest missing required element = refused whole, mod absent from list:

```
[Mods] ModInfo (at line 1, column 2 in Mod.xml) must contain MultiplayerCompatible element!
[Mods] There was an error loading the mod manifest: .../Mod.xml
[Mods] Not loading MyMod
```

Same rule as *Module attributes: required unless defaulted* below —
`InternalModding.Common.Serialization.Validate` applied to
`InternalModding.Mods.ModInfo`. Required set = every `[XmlElement]` property with
no `[DefaultValue]`:

```
REQUIRED   Name  Author  Version  Description  MultiplayerCompatible
optional   Debug  Icon  WorkshopThumbnail  LoadOrder  LoadInTitleScreen
           Resources  ID
```

**`MultiplayerCompatible` required, nothing suggests it.** Reads like something
single-player mod could omit. Hand-written manifests miss it.

**`Assemblies` not required at all.** Blocks-only mod needs none — so mod whose
entire content *is* assembly can omit it, load with no complaint, do nothing. If
mod is code, check yourself; loader won't.

Don't infer list from other mods. Every mod in wild carries `<Debug>`, looks
mandatory, isn't. Read attributes instead — ~20 lines Cecil over `ModInfo`
properties, find `XmlElementAttribute` with no `DefaultValueAttribute`. Note 06
technique applied to attributes not signatures. Difference between correct build
check and superstitious one.

Console commands: `show_logs true` routes log into in-game console.
`createmod` / `createblock` / `createentity` scaffold XML. `addmodsdir` adds
another mod search dir — how working copy outside `Besiege_Data/Mods/` loads
without copying in.

## Installing during development: symlink the mod folder

Besiege loads mods from `Besiege_Data/Mods/`, one folder per mod, **once at
startup** — every change needs restart, but no reinstall if entry is symlink:

```sh
ln -s /path/to/repo/MyMod "$BESIEGE/Besiege_Data/Mods/MyMod"
```

Link target = whatever folder holds `Mod.xml`. Both layouts work: repo root, or
subfolder beside sources and tools. Subfolder tidier — only mod ships, `.cs`,
`tools/`, `docs/` beside it obviously not part of it. Besiege reads only what
`Mod.xml` names, so sources inside mod folder ignored either way.

Build into install script:

- **`<ID>` generated into `Mod.xml` on first load.** With symlink that write
  lands in working copy — what you want, ID must stay stable for mod's life, so
  commit it. With copy, game writes into copy and repo never gets it.
- **Validate manifest before installing.** Malformed `Mod.xml` = no error in
  game: mod never appears, indistinguishable from not installed. Parse it, check
  every path named by `<Assembly>`, `<Block>`, `<Texture>`, `<Mesh>` exists.
  (Easy way to get there: `--` inside XML comment, which XML forbids.)
- **Build before copy.** Mod shipping prebuilt `<Assembly>` rather than
  `<ScriptAssembly>` needs a built DLL in checkout or it won't load — commit the
  DLL, and have `--copy` snapshot the folder only after a build.

## Where a mod may write

`Modding.ModIO` = sanctioned file API, and only one available: `System.IO.File`
and `Directory` blacklisted (below). Every method takes trailing `bool data`:

```csharp
Modding.ModIO.WriteAllText("config/settings.txt", text, true);   // data folder
Modding.ModIO.ReadAllText("Tips/builder.txt", false);            // the mod folder
```

- `data: false` → mod's own folder. Read-only in spirit, literally so for
  Workshop sub, which Steam overwrites.
- `data: true` → `Besiege_Data/Mods/Data/<ModName><_ID>/`, `ModName` = manifest
  name with spaces stripped, `ID` = manifest GUID:
  `Mods/Data/Clippy_e781508b-39fe-4a34-a98a-c2a2ab265775/`. Place for settings +
  anything mod writes. Survives updates, per-mod, so no namespacing inside it.

`ModIO` finds mod by walking back to **calling assembly** and matching against
manifest — `AssemblyLoader.GetModByAssembly` — else throws
`InvalidOperationException("ModIO called from an assembly not listed in the mod
manifest.")`. Helper DLL not declared in `Mod.xml` cannot do own file access;
hand work to a type in a declared assembly.

### ...and only inside its own folders. Two traps in one method

Both roots go through `ModPaths.GetFilePath(baseDir, path)`, which does more than
combine. **Read it before assuming what a mod can open** — this note said the
opposite for a while, on strength of its first half.

```csharp
Path.Combine(baseDir, path)          // a rooted `path` wins outright...
// ...then, if the result does not end in a separator, its *directory* is taken:
new FileInfo(result).Directory
// ...and that directory is walked upwards looking for baseDir:
throw new Exception("Path is not in mod directory! (" + path + ")");
```

**Mod may only reach own folders.** `Path.Combine` does hand absolute path
straight through — makes it look like it works — but final walk refuses it. So a
player-picked MIDI file, or Besiege's `SavedMachines`, is not something `ModIO`
opens. No other file API: `System.IO.File` blacklisted, `StreamWriter` not among
carve-outs, `XmlSaver.Save` forbidden by name. Mod can read what's under its own
folder or its `Mods/Data/<mod>_<guid>/` — so mod wanting a player file asks them
to put it there.

**Folder argument must end in slash.** Without one, resolved path treated as
*file* and folder acted on is its **parent**, which then usually fails
containment walk too:

```csharp
Modding.ModIO.GetFiles("Songs/", true);   // lists Songs
Modding.ModIO.GetFiles("Songs", true);    // lists the data folder above it
Modding.ModIO.GetFiles("", false);        // tries to list Mods/ -- and throws
```

Last one = natural way to ask "what is in my mod's folder", and the one that
cannot work. Orchestra used it to find block XMLs; catalogue came back empty, and
in game read as *instrument blocks could not be read*. Manifest already lists
every block — read list from there.

**Whatever passes through can land on disk.** `CreateDirectory` makes a folder of
any name at all, so a name from a text box wants checking first — one of these
collected a run of fullwidth digits from somewhere and made a folder of them
every time a panel opened, six before anybody noticed. Check name is plain, and
only ever create the one folder your mod owns; a player-named folder that isn't
there is a mistake to report, not a folder to make.

`ModIO.GetFiles` and `GetDirectories` return **relative** names (mapped back
through `MakeRelativePath`). `ModIO.OpenFolderInFileBrowser` = `Process.Start` on
the folder — not every Linux desktop answers.

### The system's own file dialog ships with the game

`SFB.StandaloneFileBrowser` — the well-known Standalone File Browser plugin — is
in `Assembly-CSharp`, with `Besiege_Data/Plugins/libStandaloneFileBrowser.so`
(GTK3) beside it on Linux. `SFB` namespace not blacklisted:

```csharp
string[] hit = SFB.StandaloneFileBrowser.OpenFilePanel("Choose a MIDI", "", "mid", false);
```

Also `OpenFilePanelAsync`, `OpenFolderPanel`, `SaveFilePanel`, and an
`ExtensionFilter` overload of each.

**Besiege itself never calls any of it** — caller search finds nothing outside
`SFB` — so shipped and unproven: modal GTK dialog over exclusive-fullscreen
Unity 5 window is exactly the sort of thing that hangs. Treat failure as
ordinary, and have a fallback needing no dialog (folder under
`Mods/Data/<mod>/` player drops files into, opened with
`OpenFolderInFileBrowser`).

Note what dialog is *for*: it shows player whole disk, and `ModIO` opens none of
it but mod's own folders. Either check what came back and say so, or don't offer
the dialog.

## `<LoadInTitleScreen />` decides when the mod's code first runs

Without it: mod loads on level entry. With it: mod loads during startup — only
way to be present on title screen before player entered anything.

Cost, not reversible from inside game: with the flag, Besiege runs mod code
*before* player can reach mods menu, so fatal error locks them out of the game,
not just the mod. Mods never unload once loaded, so mod without flag is still
present on main menu after first level — for anything not specifically about the
title screen, same result at none of the risk.

## The blacklist is a namespace prefix test, with carve-outs

`InternalModding.Assemblies.AssemblyScanner` refuses assembly referencing any of
these prefixes, tested as `(namespace + "." + typeName).StartsWith(prefix)`:

```
System.IO            System.Net           System.Xml          System.Reflection
System.Runtime.InteropServices           System.Diagnostics   System.Security
Mono.CSharp          Mono.Cecil           System.CodeDom.Compiler
CSharpCompiler       IKVM                 Microsoft           Mono.CompilerServices
UnityEngine.WWW      UnityEngine.MasterServer                 PlayFab
Steamworks           GameGrind            InternalModding     BesiegeDlc
```

and these **exact type names are exempted**:

```
System.IO.Stream        System.IO.TextWriter    System.IO.TextReader
System.IO.BinaryWriter  System.IO.BinaryReader  System.IO.MemoryStream
System.IO.Path          System.IO.SeekOrigin    System.Diagnostics.Stopwatch
System.Security.Cryptography                    Mono.CSharp.Tuple`2 / `3
```

plus four individually forbidden methods: `XmlSaver.Save`,
`LevelXMLSaver.Create`, `UnityEngine.AssetBundle.LoadFromFile`,
`LoadFromFileAsync`.

Read carefully — shape is not what people assume:

- **`File` and `Directory` refused, `Stream` and `Path` not.** Mod can handle
  bytes handed to it, cannot go find any. `StringReader` and `StringWriter` are
  `System.IO`, refused despite being pure string work.
- `System.Security.Cryptography` exempted **as a type name**, so individual
  cipher classes under it still refused.
- `UnityEngine.WWW` catches `WWWForm` too by prefix, leaves
  `UnityEngine.Networking.UnityWebRequest` alone.
- **`Type.Name` is a `System.Reflection` call.** `x.GetType().Name` compiles to
  `System.Reflection.MemberInfo::get_Name`; one reference in one method rejects
  whole assembly. Easiest way to trip blacklist without thinking about
  reflection: turns up in logging, in switches over an object's kind, in anything
  formatting a diagnostic. Test with `is` — compiles to `isinst`, costs nothing.

Scanner walks field types, locals, IL operands. Does **not** enumerate custom
attributes — why `[XmlRoot]`, `[XmlAttribute]` etc. are the supported way to name
what a module deserialises even though `System.Xml` is blacklisted as code.

### P/Invoke refused separately, closing the native-code door

`AssemblyScanner` carries a **dedicated P/Invoke check** as well as the namespace
test, own message:

```
"You are not allowed to use PInvoke!"
```

So `[DllImport]` refused on own terms, not merely as side effect of
`System.Runtime.InteropServices` being on prefix list. Read it out of scanner's
string literals:

```sh
./tools/peek.sh dump InternalModding.Assemblies.AssemblyScanner | grep ldstr
```

With `System.Diagnostics` blacklisted too — no `Process.Start` — **a mod cannot
reach native code at all**, by any route. No partial way in, no flag relaxing it.

Worth knowing early: many mod ideas have "wrap the library that already does
this" as obvious implementation. TTS mod cannot load DECtalk, eSpeak, Festival or
SAPI; anything that shape must be reimplemented in managed code or reached over
network — and `UnityEngine.Networking.UnityWebRequest` is the one network API
blacklist leaves alone, at cost of every player running a server.

Build-time check wants `MethodDefinition.IsPInvokeImpl` alongside namespace walk,
else it passes an assembly the loader refuses.

Build a check into the build script: scan produced assembly against that list
before game refuses it. Failure arrives with a line number instead of as a mod
that silently doesn't load.

## The compiler is Besiege's own, and it is ancient

Mod ships compiled DLL or C# sources compiled at load (`ScriptAssembly`). Either
way build against Besiege's own `mcs.dll` driven through `libmono.so` — then
build fails where game would.

It is **C# 4**, and old:

- no interpolated strings, no `?.`, no `nameof`, no expression-bodied members;
- **any `enum` declaration segfaults it** — use `int` constants;
- Besiege declares types in **global namespace** colliding with Unity's, and C#
  checks global namespace before `using` directives. Enumerated against
  `UnityEngine`, `UnityEngine.UI`, `UnityEngine.EventSystems`, four matter:
  **`Slider`, `Scrollbar`, `LOD`, `Particle`**. Spell those out in full. `Text`,
  `Image`, `Button`, `Canvas`, `Toggle`, `Dropdown`, `InputField` safe
  unqualified; `EventSystems` collides with nothing. (Fifth name,
  `UnityLogWriter`, collides too, named only so enumeration isn't silently short
  — nobody writes it.)
  Symptom = baffling error against `Assembly-CSharp.dll` — "Type `Slider' does
  not contain a definition for `value'";
- never name a member same as its own type; compiler resolves the member then
  fails to find the type.

Second instance of same shadowing hazard, easier to hit and harder to read:
Besiege bundles the **mod.io SDK**, occupying a global `ModIO` namespace
(`ModIO.APIMessage`, `ModIO.UI.*`), while modding API's file class is
`Modding.ModIO`. Inside a file with `using Modding;`, bare `ModIO` is ambiguous,
and the error names two things that look identical. Fully qualify every `Modding`
type — `Modding.ModIO`, `Modding.ModTexture` — rather than relying on the
`using`.

## Compiled DLL or ScriptAssembly: the difference that matters

`<Assemblies><Assembly path="X.dll" /></Assemblies>` ships built assembly.
`<ScriptAssembly>` points at folder of `.cs`, game compiles it. Second is far
more convenient; two properties decide the question.

**A ScriptAssembly cannot reference another mod.**
`AssemblyCompiler.ResolveScriptAssembly` builds reference list as

```csharp
AppDomain.CurrentDomain.GetAssemblies()
         .Where(a => !string.IsNullOrEmpty(a.Location))
         .Select(a => a.Location)
```

— everything already loaded into AppDomain. Catch is *when* it runs.
`AssemblyLoader.LoadMod` resolves (thus compiles) every mod's assemblies in
**load** phase; actual `Assembly.LoadFrom` happens in `LoadAssembly`, called from
`ActivateMod`, in **activate** phase. So when a ScriptAssembly compiles, no other
mod's assembly is in AppDomain and its types cannot resolve. Depending on UI
Factory — or any other mod — means shipping pre-built DLL, whose references bind
lazily on first use, by which point other mod is loaded. Every UI Factory
dependent on Workshop ships a `.dll` for this reason.

Symptom if you try anyway: `The type or namespace name 'UI' does not exist in the
namespace 'Besiege'` — reads like missing reference rather than timing problem.

**Compile cached once, never invalidated.** Result goes to
`Besiege_Data/Mods/.CompiledAssemblies/<mod>_<name>.dll`, and resolver's only
test is `File.Exists` on that path — no timestamp comparison against sources
anywhere in the method. ScriptAssembly compiles **once, ever**: edit sources and
game keeps running first build, silently. Delete `.CompiledAssemblies` between
runs, or accept iteration is not what the mode offers.

Either way build against Besiege's own compiler (above) — the one whose opinion
counts.

## Module attributes: required unless defaulted

For block module (`BlockModule` + `BlockModuleBehaviour<T>`),
`Serialization.Validate` builds check list as
`members.Where(m => !m.IsDefined(typeof(DefaultValueAttribute)))` and reports any
the XML didn't supply as *"... must have &lt;name&gt; attribute!"* — after which
**whole block XML is dropped and block never reaches toolbar**.

So: field with `[DefaultValue]` optional, field without one mandatory in every
element of that kind. Besiege's own modules mark optional attributes same way —
`Modding.Modules.Official.ShootingModule` marks eight. Cheap to get wrong,
expensive to diagnose (symptom = missing block, not error), so worth a build-time
check reading module source + block XMLs and holding them to each other.

**C# field initialiser does not make an attribute optional.** `public float Decay
= 2f;` still fails without the marker: initialiser is what the value *becomes*,
`[DefaultValue(2f)]` is what makes the attribute optional. Want both. Writing
initialisers and assuming they sufficed cost a mod nine blocks that wouldn't
load.

**`Validate` returns at first failure**, so log names one attribute in one file
even when a dozen are wrong. Fix from source, not one launch at a time.

**A `UnityEngine.Vector3` field on a module deserialises wrongly, and only
warns.** Before checking anything else, `Validate` walks members for that exact
type and logs

> `<Type>.<field>: UnityEngine.Vector3 does not deserialize correctly. Consider
> using Modding.Serialization.Vector3 instead.`

then carries on and loads the block. Block appears, works, quietly has wrong
numbers — the one failure in this area that isn't a missing block. Use
`Modding.Serialization.Vector3` in anything a module deserialises.

Knock-on: `using Modding.Serialization;` puts a second `Vector3` in scope, so a
file importing it *and* using Unity's `Vector3` no longer compiles. Keep module
classes in own file, import `Modding.Serialization` only there, let behaviour
files use Unity's.

## `modid` on a module element is optional

Widely got wrong, including an earlier version of this note.
`CustomModules.DeserializeBlockModules` reads element's `modid` attribute and
branches on whether it is there at all:

```csharp
// no modid: resolve against the mod that owns this block XML
registeredModules[elementName].FirstOrDefault(g => g.Mod == containingMod)

// modid present: resolve by mod GUID, and nothing else is consulted
registeredModules[elementName].FirstOrDefault(g => g.Mod.Info.Id.ToString() == modId)
```

So **omitting it is correct and normal** — loader already knows which mod the
file came from. It exists so a block XML can use a module a *different* mod
registered. `createblock` writes one — why most block XML in the wild has one and
why it looks compulsory.

Asymmetry is the trap: absent `modid` fine, **wrong** one fatal and silent,
because GUID lookup is then the only thing tried. `Mod.xml`'s `<ID>` is generated
by game on first load, so a value copied from another mod, or hand-written before
that first load, finds no module group at all. Check it at build time only where
present.

## When a block does not appear

Rough order of likelihood:

1. block XML didn't parse — XML comment may not contain two hyphens in a row,
   which prose written with a dash produces easily;
2. required element missing: `ID`, `Name`, `Mesh`, `Texture`, `Colliders`,
   `BasePoint`, `AddingPoints`. `BasePoint` is the one that bites;
3. module attribute missing per rule above;
4. block's `modid`, *if it has one*, doesn't match `Mod.xml`'s `<ID>` — absent
   `modid` is legal, see above;
5. assembly refused by blacklist.

None say anything useful in toolbar. All say something in `Player.log`, tag
`[Mods]`:

```sh
grep -a 'Mods\]' ~/.config/unity3d/Spiderling\ Games/Besiege/Player.log
```

**Search that tag, not your mod's name.** Loader messages name the *file* and the
*element* — `InstrumentType (at line 16, column 6 in Piano.xml) must have loops
attribute!` — never the mod, so grepping your mod name returns nothing and reads
exactly like a mod never loaded. That mistake cost one session an entire wrong
diagnosis: log had all nine errors in it the whole time. `-a` matters too — log
picks up bytes making grep treat it as binary.
