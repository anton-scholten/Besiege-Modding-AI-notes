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

## The README every mod in this family uses

A player arrives at the repository, not at the code. Same shape every time, so a
reader who has seen one mod knows where to look in the next, and so the Workshop
description can be lifted straight off the top of the file:

```markdown
# Besiege <Mod Name>

<img src="<ModFolder>/Resources/<icon>.png" alt="thumbnail" width="200" align="right">

<One sentence: what it does>, in [Besiege](https://store.steampowered.com/app/346010/Besiege/).

![<what the picture shows>](Promo_1.jpg)

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
