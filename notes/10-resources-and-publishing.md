# Resources, icons, and publishing to the Workshop

## `<Resources>` is a manifest, and that is a design decision

Every texture, sound or asset the resource system can hand you has to be listed in
`Mod.xml` up front:

```xml
<Resources>
    <Texture name="my-icon" path="icon.png" />
</Resources>
```

`<Icon name="…" />` and `<WorkshopThumbnail name="…" />` then refer to those names.
The consequence is worth thinking about before committing to it: anything declared
this way can only be added by **editing the manifest**. For a mod whose content is
meant to be extended — character packs, skins, sound sets — that turns "drop a
folder in" into "drop a folder in and edit XML", which no one will do.

The alternative is to declare nothing and read the files at runtime through
`Modding.ModIO` (see [01](01-loader-and-blacklist.md)), decoding textures yourself
with `Texture2D.LoadImage`. The mod then discovers its own content by listing
directories, and installing an addition really is a folder drop.

**Textures are decoded by Unity, which reads PNG and JPG only.** Everything in the
resource path ends at `Texture2D.LoadImage(byte[])`. A GIF, animated or not, loads
as nothing at all — no error worth reading, just a blank texture.

**Resource loading is case-sensitive on Linux.** Workshop mods authored on Windows
fail on this constantly (`Fire.ogg` declared, `fire.ogg` on disk). If a resource
"cannot be opened", check the case before anything else.

## Uploading resets your Workshop preview image

Steam accepts an animated GIF as an item's preview (under 1 MB) and it makes a
mod's Workshop page far more informative than a still. Besiege will overwrite it
every time you upload.

`SteamWorkshopManager.UploadItem` calls `SteamUGC.SetItemPreview` whenever the
upload carries a thumbnail, and for a mod the path comes from
`ModListUI.GetThumbnailPath`, which is:

```csharp
WorkshopThumbnail?.Info.Path ?? Icon?.Info.Path ?? null
```

So it is not enough to leave `<WorkshopThumbnail>` out of the manifest — it falls
back to `<Icon>`, which every mod has. In practice: **every publish and every
update replaces the preview with a still**, and the animated one has to be set
again afterwards.

Doing that by hand means the Workshop's own edit page. Doing it from a script
means `SteamUGC`: `StartItemUpdate` → `SetItemPreview` → `SubmitItemUpdate`, then
pump `SteamAPI_RunCallbacks` until `GetAPICallResult` returns. That is about fifty
lines of `ctypes` against the `libsteam_api` **the game already ships**
(`Besiege_Data/Plugins/x86_64/`), so there is no SDK to install and it runs
wherever the game does. Three details that are not obvious:

- `SteamAPI_Init` only adopts an app id from a `steam_appid.txt` in the **working
  directory** — write one into a temp directory and `chdir` there, rather than
  leaving it in the repository;
- `SubmitItemUpdateResult_t` is packed to 8 bytes on 64-bit, putting
  `PublishedFileId` at offset 8, not 5 — get this wrong and you read a garbage
  result code;
- give every 64-bit handle an explicit `restype`, or ctypes truncates it to 32
  bits and the failure looks random rather than like a type error.

The same job on Windows is
[SteamChangePreview](https://github.com/TechnologicNick/SteamChangePreview),
which is where the approach came from.

## `<ID>` and what breaks

The `<ID>` GUID is written by the game on first load. Saved machines and levels
refer to a mod's blocks by it, so changing it after anything has been saved breaks
those files, and republishing under a new one orphans every subscriber. Treat it
as immutable from the first time the game has seen the mod.

## What ships and what is fetched

Two of the mods these notes came from build their character art out of assets that
are not theirs — Microsoft's Office Assistants, and Besiege's own entity art and
audio. Neither is in the repository. The pattern that keeps it that way, and is
worth copying for anything similar:

- a script fetches or extracts the assets **on the player's machine**, at install
  time, from a public source or from the copy of the game they already own;
- `.gitignore` keeps the results out of the repository, so a published build
  redistributes nothing;
- the mod treats a missing pack as a normal state and falls back to art it does
  own, so a fresh clone works before anything has been fetched.

Building the game's own art from the player's install has a second benefit beyond
licensing: the art matches the version they are playing.
