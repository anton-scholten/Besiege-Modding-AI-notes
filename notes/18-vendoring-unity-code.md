# Vendoring third-party Unity code, and shipping shaders

Sometimes the effect you want already exists as an open-source Unity script — a
volumetric lighting pass, a post effect, a mesh generator. Bringing one into a
Besiege mod is mostly ordinary work, with four traps that are not.

## The compiler will reject code that compiles anywhere else

Besiege's `mcs.dll` is ancient. Beyond the usual C# 4 limits
(see [01-loader-and-blacklist.md](01-loader-and-blacklist.md)), the one that bites
when vendoring is that **an `enum` declaration segfaults it**. Upstream Unity code
is full of small mode enums. Replace each with `const int`s, or with a `bool` if it
only has two states, and say in a comment why — the next person will try to tidy it
back.

Optional parameters, `out`/`ref`, generics and `partial` are all fine.

## A prebuilt asset bundle is per graphics API, and Linux is not Windows

Compiled shaders cannot be built without a Unity editor, so a vendored effect
usually arrives as `.shader` source you cannot compile and a prebuilt
`AssetBundle` you can. Bundles are built per platform, and the split that matters
is the graphics API, not the OS:

- a Windows bundle carries D3D variants;
- a Mac bundle carries OpenGL/Metal variants;
- **Besiege on Linux is an OpenGL build and wants the Mac bundle.**

Mods that test `Application.platform == RuntimePlatform.WindowsPlayer ? win : mac`
therefore work on Linux by accident. Do it on purpose, and better: load the
platform's bundle, check a shader actually compiled, and fall back to the other.

```csharp
private static ModAssetBundle Usable(string name)
{
    ModAssetBundle bundle = ModResource.GetAssetBundle(name);
    if (bundle == null || bundle.HasError) return null;
    Shader probe = bundle.LoadAsset<Shader>("Assets/Whatever/Raymarch.shader");
    return probe != null && probe.isSupported ? bundle : null;
}
```

`Shader.isSupported` is the only honest test. A shader that did not compile for
this API loads fine and silently draws nothing.

Asset paths inside a bundle are the **project-relative paths they were built from**
— `Assets/LightShafts-master/Depth.shader`, folder name and all. Read them out of
the bundle rather than guessing; `tools/unbundle.py` in this repository lists them.

Bundles record the Unity version they were built with. One built for 5.4.0f3 loads;
anything newer does not, which quietly rules out most modern effects.

## Upstream's lifetime assumptions are wrong here

An effect written for a Unity scene assumes its owner is placed once in an editor
and lives as long as the level. A Besiege block or level object is built, aimed,
copied and destroyed constantly. Three things follow, and all three were real bugs:

- **Nothing collects what it allocates.** `HideFlags.HideAndDontSave` render
  textures, materials, meshes and helper cameras are exactly the objects Unity will
  *not* clean up. Upstream has no `OnDestroy` because it never needed one. Write
  one. Watch for fields that hold a `RenderTexture.GetTemporary` result — those
  were handed back already and releasing one twice is an error.
- **Modes are picked before play, not during it.** Upstream code often handles one
  direction of a mode switch and not the other, because in the editor you set the
  mode and then press play. A setting a mod puts on a toggle gets switched both ways
  at runtime.
- **Cameras change.** Anything that latches `Camera.main` in `Start` stops working
  the moment Besiege swaps between the build area, the level editor and a running
  level. Re-point it when it changes.

## Read the shader before believing a setting does something

An exposed C# field with a slider on it is not proof the shader uses it. In the
effect this note came from, the falloff strength reached only the shader's
directional branch; its spot branch had a hardcoded curve and no setting behind it
at all, so the slider did nothing on the common light type. Nothing in the C#
suggested that.

`grep` the `.shader` sources for the uniform name. If it appears once, in a
declaration, the setting is dead. Shaders often carry an unused alternate path — a
lookup-table branch, say — that can be filled in from C# to make the setting mean
something without touching the shader at all.

## Provenance is not optional

Record where the code came from, under what licence, and every change made to it,
in a header comment on the file itself. Then a later reader can diff against
upstream and knows which deviations are deliberate.

Art is the part to be careful with. Code and shaders often carry a clear licence;
the icons and textures in someone's mod usually carry none at all. Fold a borrowed
effect into your own blocks rather than shipping their object wholesale, and the
question does not arise.

## Checked

Besiege 5.4.0f3, August 2026: `Modding.ModResource::GetAssetBundle`,
`Modding.ModAssetBundle::LoadAsset`. The `enum` segfault, the OpenGL bundle on
Linux and the `isSupported` behaviour are measured, not read.
