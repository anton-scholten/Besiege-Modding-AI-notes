# When your block is a variant of a base-game one

Plenty of mod blocks are "the game's block, but…". Besiege makes that easy in a
non-obvious way: the base-game block's own behaviour class is in
`Assembly-CSharp.dll`, readable, and it is the **specification** for the copy. So is
the official *module* the modding API exposes. Between them there's almost nothing
left to guess, and guessing is what produces a block that feels subtly wrong.

Worked on Return 2 Center, a fork of the steering hinge and steering block.

## Read three things, in this order

1. **`Modding.Modules.Official.<Name>Module` / `<Name>ModuleBehaviour`** — the module
   the modding API ships for that block. What your module should look like today: same
   fields, same `[XmlElement]` markers, same lifecycle. If your mod was written years
   ago against an older copy, diffing the two is the shortest route to "what has
   changed since".
2. **The base-game block's own `MonoBehaviour`** — `SteeringWheel`,
   `CogMotorController`, `SensorBlock`. Where the *numbers* live: slider ranges,
   defaults, curves, mapper geometry. The official module is a simplification and
   leaves some out.
3. **`Modding.ModBlockBehaviour`** — for the `AddX` overload you're meant to call.

## The numbers are not guessable, and they are all right there

Two from the steering blocks, both of which a mod had wrong for years:

**The tension slider is the sixth power of its own value.** `SteeringWheel.Start`
reads `tensionSlider.Value` and multiplies it by itself five more times before scaling
the joint drive:

```csharp
float t = tensionSlider.Value;              // slider: default 1, min 0.5, max 2
t = t * t * t * t * t * t;
drive.positionDamper = 50f * t;
drive.positionSpring = 100000f * t;
```

A 0.5–2 slider therefore spans **1/64× to 64×** of stiffness. Anyone reimplementing it
as a linear multiplier gets a control that appears to do nothing, with no way to
discover the exponent except by reading this method.

**The slider is also declared `logScaling`**, which block XML cannot say — see below.

## What the block XML can and cannot declare

A modded block's mapper controls come from `<ModuleMapperTypes>`, deserialised into
`Modding.Serialization.*Definition`. Those classes carry **less** than the `AddX`
methods do:

| `MSliderDefinition` has | `SaveableDataHolder.AddSlider` also takes |
| --- | --- |
| `Key`, `DisplayName`, `ShowInMapper`, `Min`, `Max`, `Default`, `Unclamped` | prefix, suffix — and `MSlider.logScaling` is a field beside it |

`MSliderDefinition.Create` hardcodes `prefix = ""` and `suffix = "x"`, so every modded
slider reads `1.00x` whether that suits it or not. Anything else — log scaling, a
different suffix — is set **in code**, on the object `GetSlider` hands back:

```csharp
tensionSlider = GetSlider(Module.TensionSlider);
tensionSlider.logScaling = true;
```

Do that in `SafeAwake`, next to the `GetSlider`, where the base-game block does the
equivalent in its `Awake`.

## API drift is silent until you compile

`AddLimits` gained a seventh parameter, `bool enabled`, and the six-parameter overload
the 2018 build called is gone. That's the *good* kind of drift: the mod doesn't compile
and you go look. The bad kind is a method that still compiles and now means something
else — why rebuilding an old mod is worth doing against the current assemblies rather
than shipping the assembly you have.

`peek.sh check` over a claims file is the cheap version — see
[06-reading-the-game.md](06-reading-the-game.md). Listing every API a mod names, and
running it after a game update, turns drift into a list instead of a bug report.

## Match the mapper's shape too, not just the behaviour

Players compare your block against the one it copies, side by side, in the same mapper.
Two things reading as "broken" rather than "different":

- a control the original has and yours doesn't — the tension slider again;
- the limits dial's little block posed differently, which is `<LimitsDisplay>` and
  nothing else. See [02-blocks.md](02-blocks.md).

Both settled by opening the base-game block in the game and screenshotting its mapper
beside yours. A minute's work, and the only way to notice the absence of a control.

## What not to copy

The base-game class is the spec for the numbers, not a licence to copy its bugs into a
place they matter more. `SteeringModuleBehaviour` contains

```csharp
if (connected != null && connected.isKinematic && !HasRigidbody && Rigidbody.isKinematic)
```

where the last two clauses want to be `||` — as written, the branch dereferences
`Rigidbody` on the path where `HasRigidbody` is false. Reachable only when the joint's
far end is kinematic, so it has never fired in anger. Copy it verbatim if you're
reproducing that class, and *say in a comment that it is verbatim*, or the next reader
will "fix" it and diverge from the block you're meant to be matching.
