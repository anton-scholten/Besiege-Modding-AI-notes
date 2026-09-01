# The loader, the blacklist, and the compiler

## Mod layout

A mod is a folder containing `Mod.xml`, which declares metadata and each
component: `Assemblies`, `Blocks`, `Entities`, `Triggers`, `Events`, `Keys`,
`Resources`. Hand-installed mods live in `Besiege_Data/Mods/`; Workshop
subscriptions in `steamapps/workshop/content/346010/`.

`<ID>` is a GUID **the game writes on first load**. Do not hand-edit it, and never
change it after publishing — saved machines refer to blocks by it. A fresh clone
has no ID until the game has seen it once, which is worth checking before blaming
anything else for a block that will not appear.

### Five elements are required, and `MultiplayerCompatible` is the one people miss

A manifest without a required element is refused whole, and the mod does not
appear in the list:

```
[Mods] ModInfo (at line 1, column 2 in Mod.xml) must contain MultiplayerCompatible element!
[Mods] There was an error loading the mod manifest: .../Mod.xml
[Mods] Not loading MyMod
```

This is the same rule as *Module attributes: required unless defaulted* below —
`InternalModding.Common.Serialization.Validate` applying it to
`InternalModding.Mods.ModInfo` — so the required set is every `[XmlElement]`
property without a `[DefaultValue]`:

```
REQUIRED   Name  Author  Version  Description  MultiplayerCompatible
optional   Debug  Icon  WorkshopThumbnail  LoadOrder  LoadInTitleScreen
           Resources  ID
```

**`MultiplayerCompatible` is required and nothing about it suggests that.** It
reads like a declaration a single-player mod could leave out, and it is the one
element a hand-written manifest misses.

**`Assemblies` is not required at all.** A blocks-only mod needs none — so a mod
whose entire content *is* an assembly can omit it, load with no complaint, and do
nothing whatsoever. If your mod is code, check for it yourself; the loader will
not.

And do not infer this list from what other mods ship. Every mod in the wild
carries a `<Debug>`, which makes it look mandatory; it is not. Read the
attributes instead — about twenty lines of Cecil over `ModInfo`'s properties,
looking for an `XmlElementAttribute` with no `DefaultValueAttribute`. That is
the technique of note 06 applied to attributes rather than signatures, and it is
the difference between a build check that is correct and one that is merely
superstitious.

Console commands worth knowing: `show_logs true` routes log output into the in-game
console, and `createmod` / `createblock` / `createentity` scaffold the XML.
`addmodsdir` adds another directory to search for mods, which is how a working
copy outside
`Besiege_Data/Mods/` gets loaded without copying it in.

## Installing during development: symlink the mod folder

Besiege loads mods from `Besiege_Data/Mods/`, one folder per mod, and reads them
**once at startup** — so every change needs a game restart, but not a reinstall if
the entry is a symlink:

```sh
ln -s /path/to/repo/MyMod "$BESIEGE/Besiege_Data/Mods/MyMod"
```

The link target is whatever folder holds `Mod.xml`. Both layouts are in use and
both work: the repository root itself, or a subfolder beside the sources and tools.
A subfolder is tidier, because then only the mod ships and the `.cs`, `tools/` and
`docs/` beside it are obviously not part of it. Besiege reads only what `Mod.xml`
names, so sources left inside the mod folder are ignored either way.

Three things worth building into an install script:

- **`<ID>` is generated into `Mod.xml` on first load.** With a symlink that write
  lands in your working copy, which is what you want — the ID must stay stable for
  the life of the mod, so commit it. With a copy, the game writes into the copy and
  your repository never gets it.
- **Validate the manifest before installing.** A malformed `Mod.xml` produces no
  error in game: the mod simply never appears in the list, which is
  indistinguishable from not having installed it. Parse it, and check that every
  path named by `<Assembly>`, `<Block>`, `<Texture>` and `<Mesh>` exists. (An easy
  way to get there is `--` inside an XML comment, which XML does not allow.)
- **Build before you copy.** If the mod ships a prebuilt `<Assembly>` rather than a
  `<ScriptAssembly>`, a checkout has to carry a built DLL or it does not load —
  so commit the DLL, and have `--copy` snapshot the folder only after a build.

## Where a mod may write

`Modding.ModIO` is the sanctioned file API — and the only one available, since
`System.IO.File` and `Directory` are blacklisted (below). Every method takes a
trailing `bool data`:

```csharp
Modding.ModIO.WriteAllText("config/settings.txt", text, true);   // data folder
Modding.ModIO.ReadAllText("Tips/builder.txt", false);            // the mod folder
```

- `data: false` resolves inside the mod's own folder — read-only in spirit, and
  literally so for a Workshop subscription, which Steam will overwrite.
- `data: true` resolves to `Besiege_Data/Mods/Data/<ModName><_ID>/`, where
  `ModName` is the manifest name with spaces stripped and `ID` is the manifest
  GUID: `Mods/Data/Clippy_e781508b-39fe-4a34-a98a-c2a2ab265775/`. This is the
  place for settings and anything else the mod writes. It survives updates, and
  it is per-mod, so nothing needs namespacing inside it.

`ModIO` finds the mod by walking back to the **calling assembly** and matching it
against the manifest — `AssemblyLoader.GetModByAssembly` — and throws
`InvalidOperationException("ModIO called from an assembly not listed in the mod
manifest.")` otherwise. A helper DLL that is not declared in `Mod.xml` cannot do
its own file access; hand the work to a type in a declared assembly.

### ...and only inside its own folders. Two traps in one method

Both roots go through `ModPaths.GetFilePath(baseDir, path)`, and it does more than
combine them. **Read it before assuming anything about what a mod can open** —
this note said the opposite for a while, on the strength of its first half.

```csharp
Path.Combine(baseDir, path)          // a rooted `path` wins outright...
// ...then, if the result does not end in a separator, its *directory* is taken:
new FileInfo(result).Directory
// ...and that directory is walked upwards looking for baseDir:
throw new Exception("Path is not in mod directory! (" + path + ")");
```

**A mod may only reach its own folders.** `Path.Combine` does hand an absolute path
straight through, which is what makes this look like it works — but the walk at the
end refuses it, so a MIDI file the player picked, or Besiege's `SavedMachines`, is
not something `ModIO` will open. There is no other file API: `System.IO.File` is
blacklisted, `StreamWriter` is not among the carve-outs, and `XmlSaver.Save` is
forbidden by name. What a mod can read is what is under its own folder or its
`Mods/Data/<mod>_<guid>/` — so a mod that wants a file from the player asks them to
put it there.

**A folder argument must end in a slash.** Without one the resolved path is treated
as a *file* and the folder acted on is its **parent**, which then usually fails the
containment walk as well:

```csharp
Modding.ModIO.GetFiles("Songs/", true);   // lists Songs
Modding.ModIO.GetFiles("Songs", true);    // lists the data folder above it
Modding.ModIO.GetFiles("", false);        // tries to list Mods/ -- and throws
```

That last one is the natural way to ask "what is in my mod's folder", and it is the
one that cannot work. Orchestra used it to find its block XMLs; the catalogue came
back empty, and in game that read as *the instrument blocks could not be read*. The
manifest already lists every block — read the list from there.

**Whatever you pass through it can end up on disk.** `CreateDirectory` will make
a folder of any name at all, so a name that came from a text box wants checking
before it gets there -- one of these collected a run of fullwidth digits from
somewhere and made a folder out of them every time a panel opened, six of them
before anybody noticed. Check the name is plain, and only ever create the one
folder your mod owns; a folder the player named and that is not there is a mistake
to report, not a folder to make.

`ModIO.GetFiles` and `GetDirectories` return **relative** names (they map their
results back through `MakeRelativePath`), and `ModIO.OpenFolderInFileBrowser` is
`Process.Start` on the folder — which not every Linux desktop answers.

### The system's own file dialog ships with the game

`SFB.StandaloneFileBrowser` — the well-known Standalone File Browser plugin — is
in `Assembly-CSharp`, with `Besiege_Data/Plugins/libStandaloneFileBrowser.so`
(GTK3) beside it on Linux. The `SFB` namespace is not blacklisted:

```csharp
string[] hit = SFB.StandaloneFileBrowser.OpenFilePanel("Choose a MIDI", "", "mid", false);
```

There are also `OpenFilePanelAsync`, `OpenFolderPanel`, `SaveFilePanel` and an
`ExtensionFilter` overload of each.

**Besiege itself never calls any of it** — a search for callers finds nothing
outside `SFB` — so it is shipped and unproven: a modal GTK dialog over an
exclusive-fullscreen Unity 5 window is exactly the sort of thing that hangs. Treat
a failure as ordinary rather than exceptional, and have a fallback that needs no
dialog (a folder under `Mods/Data/<mod>/` the player can drop files into, opened
with `OpenFolderInFileBrowser`).

And note what the dialog is *for*: it can show the player the whole disk, and
`ModIO` can open none of it but the mod's own folders. Either check what came back
and say so, or do not offer the dialog at all.

## `<LoadInTitleScreen />` decides when the mod's code first runs

Without it, the mod is loaded when a level is entered. With it, the mod is loaded
during startup, which is the only way to be present on the title screen before the
player has entered anything.

The cost is worth stating plainly, because it is not reversible from inside the
game: with the flag, Besiege runs the mod's code *before* the player can reach the
mods menu, so a fatal error in it locks them out of the game rather than out of the
mod. Mods are never unloaded once loaded, so a mod without the flag is still
present on the main menu after the first level — for anything that is not
specifically about the title screen, that is the same result at none of the risk.

## The blacklist is a namespace prefix test, with carve-outs

`InternalModding.Assemblies.AssemblyScanner` refuses an assembly that references
any of these prefixes, tested as `(namespace + "." + typeName).StartsWith(prefix)`:

```
System.IO            System.Net           System.Xml          System.Reflection
System.Runtime.InteropServices           System.Diagnostics   System.Security
Mono.CSharp          Mono.Cecil           System.CodeDom.Compiler
CSharpCompiler       IKVM                 Microsoft           Mono.CompilerServices
UnityEngine.WWW      UnityEngine.MasterServer                 PlayFab
Steamworks           GameGrind            InternalModding     BesiegeDlc
```

and these **exact type names are exempted** from it:

```
System.IO.Stream        System.IO.TextWriter    System.IO.TextReader
System.IO.BinaryWriter  System.IO.BinaryReader  System.IO.MemoryStream
System.IO.Path          System.IO.SeekOrigin    System.Diagnostics.Stopwatch
System.Security.Cryptography                    Mono.CSharp.Tuple`2 / `3
```

plus four individually forbidden methods: `XmlSaver.Save`, `LevelXMLSaver.Create`,
`UnityEngine.AssetBundle.LoadFromFile` and `LoadFromFileAsync`.

Read that carefully, because the shape of it is not what people assume:

- **`File` and `Directory` are refused, `Stream` and `Path` are not.** A mod can
  handle bytes it is handed and cannot go and find any. `StringReader` and
  `StringWriter` are `System.IO` and are refused despite being pure string work.
- `System.Security.Cryptography` is exempted **as a type name**, so the individual
  cipher classes under it are still refused.
- `UnityEngine.WWW` catches `WWWForm` too, by prefix, but leaves
  `UnityEngine.Networking.UnityWebRequest` alone.
- **`Type.Name` is a `System.Reflection` call.** `x.GetType().Name` compiles to
  `System.Reflection.MemberInfo::get_Name`, and one reference to it in one method
  rejects the whole assembly. This is the easiest way to trip the blacklist without
  going anywhere near reflection in your head: it turns up in logging, in switches
  over an object's kind, in anything that formats a diagnostic. Test with `is`,
  which compiles to `isinst` and costs nothing.

The scanner walks field types, locals and IL operands. It does **not** enumerate
custom attributes, which is why `[XmlRoot]`, `[XmlAttribute]` and friends are the
supported way to name what a module deserialises even though `System.Xml` is
blacklisted as code.

### P/Invoke is refused separately, and that closes the native-code door

`AssemblyScanner` carries a **dedicated P/Invoke check** as well as the namespace
test, with its own message:

```
"You are not allowed to use PInvoke!"
```

So a `[DllImport]` is refused on its own terms, not merely as a side effect of
`System.Runtime.InteropServices` being on the prefix list. Read it out of the
scanner's string literals:

```sh
./tools/peek.sh dump InternalModding.Assemblies.AssemblyScanner | grep ldstr
```

Taken together with `System.Diagnostics` being blacklisted — so no
`Process.Start` either — this means **a mod cannot reach native code at all**,
by any route. There is no partial way in and no flag that relaxes it.

That is worth knowing early, because a great many mod ideas have "wrap the
library that already does this" as their obvious implementation. A text-to-speech
mod cannot load DECtalk, eSpeak, Festival or SAPI; anything of that shape has to
be reimplemented in managed code or reached over the network — and
`UnityEngine.Networking.UnityWebRequest` is the one network API the blacklist
leaves alone, at the cost of every player needing to run a server.

A build-time check wants `MethodDefinition.IsPInvokeImpl` alongside the namespace
walk, or it will pass an assembly the loader refuses.

Worth building a check into the build script: scan the produced assembly against
that list before the game refuses it, and the failure arrives with a line number
instead of as a mod that silently does not load.

## The compiler is Besiege's own, and it is ancient

A mod can ship a compiled DLL or C# sources compiled at load (`ScriptAssembly`).
Either way it is worth building against Besiege's own `mcs.dll` driven through
`libmono.so`, because then the build fails where the game would.

It is **C# 4**, and old:

- no interpolated strings, no `?.`, no `nameof`, no expression-bodied members;
- **any `enum` declaration segfaults it** — use `int` constants;
- Besiege declares types in the **global namespace** that collide with Unity's,
  and C# checks the global namespace before `using` directives. Enumerated against
  `UnityEngine`, `UnityEngine.UI` and `UnityEngine.EventSystems`, four are worth
  knowing: **`Slider`, `Scrollbar`, `LOD` and `Particle`**. Spell those out in
  full; `Text`, `Image`, `Button`, `Canvas`, `Toggle`, `Dropdown` and `InputField`
  are safe unqualified, and `EventSystems` collides with nothing. (A fifth name,
  `UnityLogWriter`, collides too, and is named here only so the enumeration is not
  silently short — nobody writes it.)
  The symptom is a baffling error against `Assembly-CSharp.dll` — "Type `Slider'
  does not contain a definition for `value'";
- never name a member the same as its own type; the compiler resolves the member
  and then fails to find the type.

The same shadowing hazard has a second instance that is easier to hit and harder
to read: Besiege bundles the **mod.io SDK**, which occupies a global `ModIO`
namespace (`ModIO.APIMessage`, `ModIO.UI.*`), while the modding API's file class
is `Modding.ModIO`. Inside a file with `using Modding;`, the bare name `ModIO` is
ambiguous, and the error names two things that look identical. Fully qualify
every `Modding` type — `Modding.ModIO`, `Modding.ModTexture` — rather than
relying on the `using`.

## Compiled DLL or ScriptAssembly: the difference that matters

`<Assemblies><Assembly path="X.dll" /></Assemblies>` ships a built assembly.
`<ScriptAssembly>` points at a folder of `.cs` and has the game compile it. The
second is far more convenient and has two properties that decide the question.

**A ScriptAssembly cannot reference another mod.** `AssemblyCompiler.
ResolveScriptAssembly` builds its reference list as

```csharp
AppDomain.CurrentDomain.GetAssemblies()
         .Where(a => !string.IsNullOrEmpty(a.Location))
         .Select(a => a.Location)
```

— everything already loaded into the AppDomain. The catch is *when* it runs.
`AssemblyLoader.LoadMod` resolves (and therefore compiles) every mod's assemblies
in the **load** phase; the actual `Assembly.LoadFrom` happens in `LoadAssembly`,
called from `ActivateMod`, in the **activate** phase. So at the moment a
ScriptAssembly is compiled, no other mod's assembly is in the AppDomain, and its
types cannot be resolved. Depending on UI Factory — or on any other mod — means
shipping a pre-built DLL, whose references bind lazily on first use, by which
point the other mod is loaded. Every UI Factory dependent on the Workshop ships a
`.dll` for this reason.

The symptom, if you try it anyway, is `The type or namespace name 'UI' does not
exist in the namespace 'Besiege'`, which reads like a missing reference rather
than like a timing problem.

**The compile is cached once and never invalidated.** The compiled result goes to
`Besiege_Data/Mods/.CompiledAssemblies/<mod>_<name>.dll`, and the resolver's only
test is `File.Exists` on that path — there is no timestamp comparison against the
sources anywhere in the method. A ScriptAssembly is therefore compiled **once,
ever**: edit the sources and the game keeps running the first build, silently.
Delete `.CompiledAssemblies` between runs, or accept that iteration is not what
the mode offers.

Either way, build against Besiege's own compiler (below), because that is the one
whose opinion counts.

## Module attributes: required unless defaulted

For a block module (`BlockModule` + `BlockModuleBehaviour<T>`),
`Serialization.Validate` builds its list of members to check as
`members.Where(m => !m.IsDefined(typeof(DefaultValueAttribute)))` and reports any
the XML did not supply as *"... must have &lt;name&gt; attribute!"* — after which
**the whole block XML is dropped and the block never reaches the toolbar**.

So: a field with `[DefaultValue]` is optional, a field without one is mandatory in
every element of that kind. Besiege's own modules mark their optional attributes
the same way — `Modding.Modules.Official.ShootingModule` marks eight. This is
cheap to get wrong and expensive to diagnose, because the symptom is a missing
block rather than an error, so it is worth a build-time check that reads the
module source and the block XMLs and holds them to each other.

**A C# field initialiser does not make an attribute optional.** `public float
Decay = 2f;` still fails without the marker: the initialiser is what the value
*becomes*, `[DefaultValue(2f)]` is what makes the attribute optional, and you
want both. Writing the initialisers and assuming they were enough cost a mod nine
blocks that would not load.

**`Validate` returns at the first failure**, so the log names one attribute in one
file even when a dozen are wrong. Fix them from the source, not one launch at a
time.

**A `UnityEngine.Vector3` field on a module deserialises wrongly, and only warns.**
Before it checks anything else, `Validate` walks the members looking for that exact
type and logs

> `<Type>.<field>: UnityEngine.Vector3 does not deserialize correctly. Consider
> using Modding.Serialization.Vector3 instead.`

then carries on and loads the block. So the block appears, works, and quietly has
the wrong numbers in it — the one failure in this whole area that is not a missing
block. Use `Modding.Serialization.Vector3` in anything a module deserialises.

That has a knock-on worth planning for: `using Modding.Serialization;` puts a
second `Vector3` in scope, so a file that imports it *and* uses Unity's own
`Vector3` no longer compiles. Keep the module classes in their own file, import
`Modding.Serialization` only there, and let the behaviour files use Unity's.

## `modid` on a module element is optional

This one is widely got wrong, including in an earlier version of this note.
`CustomModules.DeserializeBlockModules` reads the element's `modid` attribute and
branches on whether it is there at all:

```csharp
// no modid: resolve against the mod that owns this block XML
registeredModules[elementName].FirstOrDefault(g => g.Mod == containingMod)

// modid present: resolve by mod GUID, and nothing else is consulted
registeredModules[elementName].FirstOrDefault(g => g.Mod.Info.Id.ToString() == modId)
```

So **omitting it is correct and normal** — the loader already knows which mod the
file came from. It exists so a block XML can use a module that a *different* mod
registered. `createblock` writes one, which is why most block XML in the wild has
one and why it looks compulsory.

The asymmetry is the trap: an absent `modid` is fine, a **wrong** one is fatal and
silent, because the GUID lookup is then the only thing tried. `Mod.xml`'s `<ID>`
is generated by the game on first load, so a value copied from another mod, or
written by hand before that first load, finds no module group at all. If you check
it at build time, check it only where it is present.

## When a block does not appear

In rough order of likelihood:

1. the block XML did not parse — an XML comment may not contain two hyphens in a
   row, which prose written with a dash produces easily;
2. a required element is missing: `ID`, `Name`, `Mesh`, `Texture`, `Colliders`,
   `BasePoint`, `AddingPoints`. `BasePoint` is the one that bites;
3. a module attribute is missing per the rule above;
4. the block's `modid`, *if it has one*, does not match `Mod.xml`'s `<ID>` — an
   absent `modid` is legal, see above;
5. the assembly was refused by the blacklist.

None of these say anything useful in the toolbar. All of them say something in
`Player.log`, under the tag `[Mods]`:

```sh
grep -a 'Mods\]' ~/.config/unity3d/Spiderling\ Games/Besiege/Player.log
```

**Search for that tag, not for your mod's name.** The loader's messages name the
*file* and the *element* — `InstrumentType (at line 16, column 6 in Piano.xml)
must have loops attribute!` — and never the mod, so grepping for what you called
it returns nothing and reads exactly like a mod that was never loaded. That
mistake cost one debugging session an entire wrong diagnosis: the log had all nine
errors in it the whole time. `-a` matters too, because the log picks up bytes that
make grep treat it as binary.
