# Reading the game: how any of this was found out

Besiege's modding documentation covers the mod manifest and block XML and stops well
short of the parts a mod actually collides with. Everything here came from five
techniques, all cheap, all offline.

## 1. Mono.Cecil against the game's assemblies

`Mono.Cecil.dll` ships in `Besiege_Data/Managed/`. A ~30-line tool listing a type's
members, or dumping a method's IL, answers most questions in a minute:

```csharp
AssemblyDefinition asm = AssemblyDefinition.ReadAssembly(args[0]);
foreach (TypeDefinition t in asm.MainModule.Types)
{
    if (t.Name != args[1]) continue;
    foreach (FieldDefinition f in t.Fields)
        if (f.IsPublic) Console.WriteLine("field  " + f.FieldType.Name + " " + f.Name);
    foreach (PropertyDefinition p in t.Properties)
        Console.WriteLine("prop   " + p.PropertyType.Name + " " + p.Name);
    foreach (MethodDefinition m in t.Methods)
        if (m.IsPublic && !m.IsSpecialName)
            Console.WriteLine("method " + m.ReturnType.Name + " " + m.Name);
}
```

Variants worth having: dump one method's instructions; find every method whose IL
mentions a string or a member (how "who writes this field?" and "who calls this?" get
answered); dump an enum's constants (`f.HasConstant`), where the `BlockType` ids come
from.

Run it with the game's own mono against `Assembly-CSharp.dll`. This established
`DisplayInMapper`, `VisualController`, `ContainerDetails`, the timer's mapper keys,
the emulation reference counting, the blacklist and the meaning of `upperLeft`.

**That tool is in this repository**, with a runner that builds it with Besiege's own
compiler and runs it on Besiege's own embedded Mono — no toolchain to install:

```sh
./tools/peek.sh sig FileBrowserSlot          # fields, properties, methods
./tools/peek.sh dump ClickBehaviour          # the same, plus every IL body
./tools/peek.sh member conflict              # who declares a member of that name
./tools/peek.sh calls IsPointerOverGameObject
./tools/peek.sh str "control scheme"         # who loads a string containing it
./tools/peek.sh types Selector -- UIFactory  # UI Factory's assemblies too
```

The mode that matters for notes like these is **`check`**: one `Type` or
`Type::Member` per line in a file, prints `ok` or `MISSING` for each.

```sh
printf 'ClickBehaviour::OnMouseOver\nMachine::LoadMachineInfo\n' > claims.txt
./tools/peek.sh check claims.txt
```

Every API named in these notes is in `tools/claims-besiege.txt` and
`tools/claims-uifactory.txt` for exactly that:

```sh
./tools/peek.sh check tools/claims-besiege.txt
./tools/peek.sh check tools/claims-uifactory.txt -- UIFactory
```

Both clean as of the build named at the top of the README. Run them again before
trusting any of this against a newer Besiege — about a minute, and the difference
between notes that age and notes that mislead. When you learn something new, add its
API to the list along with the prose.

**Read the IL, not just the names.** `upperLeft` looks like a window corner from its
name and type; only `Awake` (finds it by tag) and `UpdateBackground` (clamps against
it) say what it is.

**A nested type is spelled with `/` in a claims file**, the way Cecil's `FullName`
gives it: `StatMaster/GodTools::GravityDisabled`, not the `StatMaster.GodTools.…` you
would write in C#. Bare `GodTools::GravityDisabled` resolves too.

## 2. A throwaway compile

If a member exists with the signature you guessed, a file mentioning it compiles.

```csharp
public class Probe : BlockModuleBehaviour<SomeModule>
{
    public void Look(MSlider s)
    {
        s.DisplayInMapper = false;
        BlockVisualController vc = BlockBehaviour.VisualController;
        Debug.Log(vc.renderers.Length.ToString());
    }
}
```

Compile against the same references the mod uses. Costs seconds, distinguishes "this
member exists" from "this member is what I hope it is" — and catches
static-versus-instance mistakes, which the IL dump doesn't make obvious.

## 3. Strings and asset files

`strings -t d resources.assets` lists GameObject names in file order, and a prefab's
children cluster near it. That's where the block mapper's furniture (`TopBar`,
`WideShadow`, `CrossButton`, `CopyButton`, `Visual`) came from before the in-game log
confirmed which was which.

Asset **bundles** (UI Factory's prefabs, for instance) are a `UnityFS` container:
header, block-info table that may be LZ4 or LZMA and may sit at the end of the file,
then data blocks. Getting the strings out is ~80 lines of Python.

Getting the *structure* out is worth the extra hundred, and `tools/unbundle.py` does
it:

```sh
python3 tools/unbundle.py <bundle>                    # every root
python3 tools/unbundle.py <bundle> Window             # one, with its children
python3 tools/unbundle.py <bundle> Window --fields    # ... and every serialised field
```

It prints the hierarchy, components on each object, each `RectTransform`'s anchors,
size, position and pivot, and with `--fields` the serialised value of every field on
every `MonoBehaviour`. That's how the `Window` prefab's layout in
[04-ui-factory.md](04-ui-factory.md) was established, and how "is this prefab's
background a raycast target?" gets answered in seconds instead of by trying it in
game.

Technique underneath is worth knowing on its own: **Unity's serialized files carry
type trees**, a description of every field of every class in the file, so an object
can be decoded generically without knowing the class. Walk the tree and read the
primitives it names, respecting the align-after flag (`meta & 0x4000`) and the 4-byte
alignment after every string and array. That's the whole trick, and it works for any
asset bundle from this era of Unity, not just UI Factory's.

## 4. Taking art and audio out of the game

If a mod wants to look or sound like Besiege, the material is already on the player's
disk, and two things make it cheaper to reuse than to redraw.

**The level editor renders a thumbnail of every entity**, cut out against
transparency, so a picture of the sheep, the peasant and everything else already
exists. A still under an affine transform about the character's feet — squash,
stretch, tilt, spin — is most of the animation such a thing needs.

**Which audio belongs to what is readable, not guessable.** Walk the level-editor
scene's prefab for an entity and read the `AudioClip` references off its components:
the sheep bleats because `SheepV2` really does carry `SheepBleet1..4`. Unity keeps the
audio in one-sample FMOD banks rather than plain samples; the PCM ones unwrap to
`.wav`. Expect to trim to where they're audible and level them to a common loudness —
the game's own mix spans about 21 dB, compensated for elsewhere.

Anything built this way belongs on the player's machine, not in the repository; see
[10-resources-and-publishing.md](10-resources-and-publishing.md).

## 5. Make the mod tell you

The game is the only authority on anything visual or timing-related, and it answers
questions asked in the log. Print what a measurement *found*, once per session, rather
than only what it decided:

```
[MyMod] mapper part 'Background' at (x:2508.60, y:1540.87, width:874.80, height:389.88)
[MyMod] docking to 'Visual' at (x:3195.42, y:1831.61, width:93.31, height:93.31)
```

The second line diagnosed a bug two rounds of reasoning had failed to. Output goes to
`Player.log` — on Linux `~/.config/unity3d/Spiderling Games/Besiege/Player.log` — and
to the in-game console with `show_logs true`.

## 6. Build checks, and how they quietly stop checking

Most of what goes wrong in a Besiege mod is invisible at runtime — a block that's
absent, a module that never attached, an assembly the loader refused — so answer those
questions at build time instead. All three are cheap: parse the block XML and assert
the elements Besiege requires; read the module class's `[XmlAttribute]`/
`[DefaultValue]` markers and hold the XML to them; walk the built assembly for
blacklisted namespaces. Each well under a hundred lines, each replaces a launch.

Two ways that machinery rots, both of which happened here:

- **A checker whose own compile is silenced stops being a checker.** These tools are
  themselves C# built by the same ancient compiler, and a build script compiling them
  with `>/dev/null 2>&1` and carrying on will, the day one fails to compile, silently
  run the *previous* build's binary — or skip the check and still print nothing. A
  stale checker reporting "OK" is worse than no checker. Delete the old binary first,
  and fail the build if the checker won't compile.
- **Don't share a scratch directory between mods.** A build script copied from a
  neighbouring repo keeps its `/tmp/besiege-<other-mod>-build` path, and two repos
  then overwrite each other's compiled checkers. Name it after the mod.

When a check fires, make it say what to *do*: "give the field a `[DefaultValue]` to
make it optional" beats "missing attribute".

## Things that bit, or nearly did

- `mod.besiege.co.uk` serves docs over plain HTTP with a broken TLS handshake on
  HTTPS. Fetch over HTTP.
- Resource loading is **case-sensitive on Linux**, and Workshop mods authored on
  Windows regularly fail on it (`Fire.ogg` declared, `fire.ogg` on disk). If a
  resource "cannot be opened", check the case before anything else.
- `Modding.Configuration` persists settings through `XDataHolder`, whose write method
  (`AddValue`) has an unconfirmed signature. Reachable, undocumented — check the IL
  before depending on it.
- `ModConsole.RegisterCommand(string, CommandHandler, string)` is confirmed:
  `CommandHandler` is a `void(string[])` delegate, and a method group converts to it
  implicitly, so `RegisterCommand("mycmd", OnCommand, "help")` is all it takes. Empty
  help text and a colon in the name both throw, and it resolves the calling assembly
  against the manifest the same way `ModIO` does — so a helper DLL the manifest
  doesn't list cannot register commands.
- A simulation runs on a **clone** of the machine. `OnSimulateStart` and
  `OnSimulateStop` land on the copy, never on the block an editor panel is editing.
  Anything that must be true for both has to be re-checked per frame rather than
  switched from those callbacks.
