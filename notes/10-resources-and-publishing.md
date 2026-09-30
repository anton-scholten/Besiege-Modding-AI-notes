# Resources, icons, and publishing to the Workshop

## `<Resources>` is a manifest, and that is a design decision

Every texture, sound or asset the resource system can hand you must be listed in
`Mod.xml` up front:

```xml
<Resources>
    <Texture name="my-icon" path="icon.png" />
</Resources>
```

`<Icon name="…" />` and `<WorkshopThumbnail name="…" />` then refer to those names.
Consequence worth thinking about before committing: anything declared this way can only
be added by **editing the manifest**. For a mod whose content is meant to be extended —
character packs, skins, sound sets — that turns "drop a folder in" into "drop a folder
in and edit XML", which no one will do.

Alternative: declare nothing and read files at runtime through `Modding.ModIO` (see
[01](01-loader-and-blacklist.md)), decoding textures yourself with
`Texture2D.LoadImage`. The mod then discovers its own content by listing directories,
and installing an addition really is a folder drop.

**A declared texture goes straight into uGUI as a `RawImage`.**
`ModResource.GetTexture(name)` hands back a `Texture`, which is exactly what
`RawImage.texture` takes — no `Sprite` to build, nothing to own, nothing assumed
about the texture's type. `Image` is the wrong component here for the same reason.
Worth knowing before writing sprite-making code: a mod's own artwork in a panel is
two lines. Draw white artwork on transparency and tint it with `RawImage.color`,
and one file serves every colour the interface uses it in.

Nothing checks the manifest against the disk, either, and a texture the code loads
by name is mentioned nowhere the game validates: a mistyped `path` shows up as a
control that is simply not drawn. Worth a line in whatever checks the XML.

**Textures are decoded by Unity, which reads PNG and JPG only.** Everything in the
resource path ends at `Texture2D.LoadImage(byte[])`. A GIF, animated or not, loads as
nothing at all — no error worth reading, just a blank texture.

**Resource loading is case-sensitive on Linux.** Workshop mods authored on Windows fail
on this constantly (`Fire.ogg` declared, `fire.ogg` on disk). If a resource "cannot be
opened", check case before anything else.

## Uploading resets your Workshop preview image

Steam accepts an animated GIF as an item's preview (under 1 MB), and it makes a mod's
Workshop page far more informative than a still. Besiege overwrites it every time you
upload.

`SteamWorkshopManager.UploadItem` calls `SteamUGC.SetItemPreview` whenever the upload
carries a thumbnail, and for a mod the path comes from `ModListUI.GetThumbnailPath`:

```csharp
WorkshopThumbnail?.Info.Path ?? Icon?.Info.Path ?? null
```

So leaving `<WorkshopThumbnail>` out of the manifest isn't enough — it falls back to
`<Icon>`, which every mod has. In practice: **every publish and every update replaces
the preview with a still**, and the animated one must be set again afterwards.

By hand that means the Workshop's own edit page. From a script it means `SteamUGC`:
`StartItemUpdate` → `SetItemPreview` → `SubmitItemUpdate`, then pump
`SteamAPI_RunCallbacks` until `GetAPICallResult` returns. About fifty lines of `ctypes`
against the `libsteam_api` **the game already ships** (`Besiege_Data/Plugins/x86_64/`),
so no SDK to install and it runs wherever the game does. Three non-obvious details:

- `SteamAPI_Init` only adopts an app id from a `steam_appid.txt` in the **working
  directory** — write one into a temp directory and `chdir` there, rather than leaving it
  in the repository;
- `SubmitItemUpdateResult_t` is packed to 8 bytes on 64-bit, putting `PublishedFileId`
  at offset 8, not 5 — get this wrong and you read a garbage result code;
- give every 64-bit handle an explicit `restype`, or ctypes truncates it to 32 bits and
  the failure looks random rather than like a type error.

Same job on Windows is
[SteamChangePreview](https://github.com/TechnologicNick/SteamChangePreview), where the
approach came from.

## A preview over 1 MiB fails every upload as "limit exceeded"

Steam caps a Workshop item's preview image at **1 MiB (1048576 bytes)** and refuses a
bigger one with `k_EResultLimitExceeded` — surfaced in Besiege as a bare "limit
exceeded" that names no file. Nothing local complains: the game loads the image fine,
the mod runs, and only the upload fails.

Which file it is comes from `ModListUI.GetThumbnailPath`:

```csharp
WorkshopThumbnail?.Info.Path ?? Icon?.Info.Path ?? null
```

So **the cap lands on `<Icon>` for any mod without a `<WorkshopThumbnail>`**, which is
most of them. An icon is a small thing on screen and easy to leave oversized — a
1625x1625 PNG is comfortably past the cap at about 1.3 MiB, and it is a plausible
export straight out of an image editor. The mods menu draws it at icon size either
way, so nothing in game hints at the problem.

Downscaling the icon is the better fix than adding a `<WorkshopThumbnail>` to dodge
it: the oversized file is also decoded at load for a thing drawn a couple of hundred
pixels across. 768x768 lands around half the cap and leaves headroom for the art to
change.

Worth a check in whatever validates the manifest, since the failure is remote,
delayed, and blames nothing: resolve `<WorkshopThumbnail>` else `<Icon>` to its
declared texture path and assert the file is under 1048576 bytes.

## A read-only file in the staging folder stops every upload

`WorkshopManager.CreateUploadFolder` empties `Besiege_Data/WorkshopUpload/` before each
publish, and Mono's `File.Delete` refuses a file with the read-only attribute rather
than clearing it. So one unwritable file left in there blocks not just its own mod but
**every** upload from then on, with an error naming the delete and not the reason.

How it happens: a previous upload copied a mod folder with a `.git` directory in it, and
git writes its object files `0444`. The whole staging tree is then undeletable.

Two consequences worth designing for:

- Keep the folder Besiege uploads free of anything version-controlled. Put the mod in a
  subfolder of the repository — `MyMod/` beside `docs/` and `tools/` — so the uploaded
  folder is only ever the mod and `.git` sits outside it.
- If it has already happened, `chmod -R u+w` on `Besiege_Data/WorkshopUpload/` and delete
  it by hand. Nothing in the game will do it for you.

## `<ID>` and what breaks

The `<ID>` GUID is written by the game on first load. Saved machines and levels refer to
a mod's blocks by it, so changing it after anything has been saved breaks those files,
and republishing under a new one orphans every subscriber. Treat it as immutable from
the first time the game has seen the mod.

## What ships and what is fetched

Two of the mods these notes came from build their character art out of assets that aren't
theirs — Microsoft's Office Assistants, and Besiege's own entity art and audio. Neither
is in the repository. The pattern that keeps it that way, worth copying for anything
similar:

- a script fetches or extracts the assets **on the player's machine**, at install time,
  from a public source or from the copy of the game they already own;
- `.gitignore` keeps the results out of the repository, so a published build
  redistributes nothing;
- the mod treats a missing pack as a normal state and falls back to art it does own, so a
  fresh clone works before anything has been fetched.

Building the game's own art from the player's install has a second benefit beyond
licensing: the art matches the version they're playing.

## The words your mod shows: Besiege's localisation cannot hold them

Besiege translates itself by **number**. `LocalisationManager.GetTranslation(int id)`
reads the current `TranslationFile`, and a language file — one per language, in
`StaticSettings.LocalisationPath` ("Localisation Files") — is a text file whose own
header says it plainly:

```
[Besiege Language File]
systemLanguage = "{0}"
languageName = "{1}"
[Begin Translations]
//At each value replace the text between the quotes to change the in-game text.
//Leave the number in place, as that is how Besiege knows which text to replace.
```

Those numbers are the game's. There is no range a mod may claim: pick some and you
are one patch, or one other mod, away from overwriting somebody's text.

**`LocalisationManager.ExternalLocalisations` is not the hook it looks like.** It is
a `public static List`, and nothing in `Assembly-CSharp` reads or writes it —
`peek member ExternalLocalisations` returns the declaration and nothing else. Adding
to it achieves nothing.

So a mod keeps its own catalogue: keys to strings, English compiled in as the
fallback, a file per language beside the mod. Two parts of the game's system are
still worth using:

- **The language the player chose.** `LocalisationManager` is a `SingleInstance`, so
  `hasInstance()` then `Instance.currLangISO` names it — but **not as an ISO code**,
  whatever the property is called. It returns
  `currentTranslationFile.SystemLanguage`, which is Unity's `SystemLanguage`
  spelling: `French`, `ChineseSimplified`, `Japanese`. That is also what the game
  calls its own files in `Localisation Files`, so name yours the same and the two
  line up with no table in between.
- **`LanguageChanged`**, a public static event with `add_`/`remove_` accessors, for
  reloading when they switch mid-session. `ResetTranslations` raises it, and the
  game's own `BlockTooltipController.Awake` subscribes to it — so it is a supported
  hook, not an accident. Subscribe once at `OnLoad` and swallow anything your
  handler throws: it runs inside the game's event, and an exception there stops
  whatever listens after you.

**A mapper control can be renamed while the mapper is open.**
`MapperType.DisplayName` has a public setter, and setting it calls
`InvokeNameChanged`; `BlockMapper.RefreshLists` subscribes to that `NameChanged`.
So the words on your own `MKey`/`MToggle`/`MSlider` are not frozen at
`SafeAwake` — a language change can put new ones on live blocks, provided you kept
a list of them. Everything *else* your mod has drawn is your own problem: a caption
does not remember the key it came from, so either store the key beside each label
or rebuild the window, and if you rebuild, remember that any list your builder
appends to needs clearing first or you will be laying the new furniture out behind
the old.

And if the words you want are already the game's — gate names, tool names — then
`GetTranslation(id)` hands them to you translated, for free. Keep your own spelling
as the fallback and wrap the call, since a missing id returns empty rather than
throwing.

## Translating the words is only half of it: the font has to draw them

`Besiege.UI.Make.Font` is not a font UI Factory ships. `Make.Awake` does
`Resources.FindObjectsOfTypeAll<TextMesh>().First(t => t.font.name == "GOST Common").font`
— it scrapes the font off a scene `TextMesh`, so what you get is the game's own
**GOST Common**. That matters because the fonts Besiege bundles are not
interchangeable. All of them are dynamic (`m_FontData` set, no baked
`m_CharacterRects`), so what each can draw is just its `cmap`:

| font | glyphs | draws |
| --- | --- | --- |
| GOST Common (and Italic, 2, Hinted Smooth, Workshop) | ~675 | Latin, Polish/Turkish extended Latin, Cyrillic |
| Besiege Font Regular | 397 | Latin, Polish/Turkish — **no Cyrillic** |
| Source Code Pro | 863 | Latin, Polish/Turkish — **no Cyrillic** |
| Passion One | 307 | Latin-1 only |
| Orbitron (Light/Medium/Bold/Black) | ~237 | Latin-1 only |

**None of them has a single CJK glyph.** That is why `LocalisationManager` keeps
`mediumCJKFont` and `boldCJKFont`, and why you should not reimplement the swap by
hand. `Instance.GetFont(font)` is the whole rule: outside the languages it marks
`isAsian` it hands your font straight back, and inside them it returns
`mediumCJKFont` when the font you passed is named `GOST*` and `boldCJKFont`
otherwise. Pass it `Make.Font` and use what comes back. Rolling your own
"if Asian use `mediumCJKFont`" picks the wrong weight the moment the base font is
not a GOST one, and picking the font once at build time leaves every label you have
already drawn in boxes after a mid-session language change.

So a label wants its font from one place in your mod, that place wants to call
`GetFont`, and a language change has to re-run it — the same rebuild that puts the
new words up.

**Auditing a translation before anyone plays it**: extract the fonts and check the
characters you actually use against the `cmap`. `UnityPy` reads `resources.assets`
and `sharedassets0.assets` and hands you each `Font`'s `m_FontData` as a real TTF
(byte-carving those files mangles all but a couple of them); `fontTools` then gives
you the coverage. Cross-checking against the game's own language files is a weaker
test than it looks — Besiege's French writes `noeuds`, but its files do contain
`Œ`, so a character the translators avoided is not thereby a character the font
lacks.

One rule that is a bug the first time you get it wrong: **never translate a string
you write into a save file.** A machine saved in one language has to open in
another, so mapper keys and any token in your own file format stay English, and only
what is *displayed* goes through the catalogue.

## `ModIO` reads and writes UTF-8, so a translation file needs no encoding of its own

`ReadAllText(path, data)` and `ReadAllLines` pass `Encoding.UTF8` explicitly to
`File.ReadAllText`, rather than taking the platform default — so an accented or
Cyrillic or CJK string in a file beside your mod arrives intact, and a garbled
label is a font problem (above) rather than a decoding one. The three-argument
overloads take an `Encoding` if you need another. Worth knowing which it is before
you go looking: the two failures look identical on screen, and only one of them is
yours to fix.

## `ModIO`'s second argument: the mod's folder, or its data folder

`Modding.ModIO.ReadAllText(path, data)` and its neighbours take a relative path and a
flag:

- `false` — the mod's **own folder**, the one holding `Mod.xml`. Where files that
  ship with the mod live.
- `true` — `Besiege_Data/Mods/Data/<ModName>_<guid>/`, created on demand. Where
  files the mod writes live, and where a player can drop a file to override one that
  shipped.

The trap: `ModIO` resolves through `ModPaths.GetFilePath(ModInfo, path, bool)`, whose
own third argument means **"Resources"** — it appends that subfolder when true — and
`ModIO` always passes it `false`. Read the IL of the inner one, assume it is the flag
you passed, and you will put your files one directory too deep.

## The README every mod in this family uses

A player arrives at the repository, not at the code. Same shape every time, so a
reader who has seen one mod knows where to look in the next, and so the Workshop
description can be lifted straight off the top of the file:

```markdown
# Besiege <Mod Name>

<img src="<ModFolder>/Resources/<icon>.png" alt="thumbnail" width="200" align="right">

<One sentence: what it does>, in [Besiege](https://store.steampowered.com/app/346010/Besiege/).

<A paragraph or two on what it is for and why it is not the obvious thing.>

**[UI Factory](https://steamcommunity.com/sharedfiles/filedetails/?id=2913469777)**
(another Besiege mod which enables the nice UI, see workshop item `2913469777`)
<... or the mod won't load. | ... is optional here. Without it, ...>

<br clear="right">

## Install
## <one section per thing the player does>
## Notes
## Credits
## Licence
```

The parts that are not obvious:

- **The thumbnail is the mod's own `<Icon>` texture**, floated right at 200px, not
  a copy kept beside the README. One image, and it cannot drift from what the mods
  menu shows. Point it at the icon, never at a block's UV texture.
- **Screenshots go under the `##` heading they illustrate, not at the top.** One
  per section, immediately after the heading, with alt text naming what is actually
  on screen -- the panel, the values, the blocks -- so the picture is findable and
  readable with images off. A hero shot above `## Install` fights the floated
  thumbnail and shows a reader a picture of something they have not been told about
  yet; every mod in this family puts them in the sections instead.
- **`<br clear="right">` before `## Install`.** Without it a heading or a fenced
  code block runs up beside the floated image and the install commands wrap into a
  narrow column.
- **The UI Factory sentence says which of the two it is** — hard requirement
  ("or the mod won't load") or soft ("is optional here", and then what happens
  without it). A mod that does not use UI Factory omits the sentence entirely.
- **`## Credits` only when something is actually owed** — a model, a soundfont, a
  vendored library, artwork that isn't yours. Writing "nothing of anyone else's is
  in this mod" is a sentence that has to be re-checked every time the mod grows an
  asset, and is wrong the moment nobody does.
- **`## Licence` is last and states the same licence as `LICENSE`.** Worth
  actually reading the file: two of these repositories claimed MIT in the README
  over a GPL-3.0 `LICENSE`, which nobody noticed for a year.
- Everything an agent needs goes in `AGENTS.md`, everything the modding API cost
  goes in `docs/MODDING-NOTES.md`, and `## Notes` carries a one-line pointer at
  both. The README stays the player's document.
