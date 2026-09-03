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
