# Keys, emulation, variables and timers

## `MKey` carries the whole automation feature

`MSlider`, `MToggle`, `MMenu` and `MValue` have **nothing** variable-related on
them — no message, no emulation, no variable selector. Only `MKey` does.

That is a design constraint, not a gap to work around: a setting that has to be
automated has to be reachable through a key. A block whose *value* needs to vary
over time either needs one block per value, or a key per step.

## Reading an emulated key

Emulated presses do not arrive in `Update`. Besiege has a pass for them:

- `Machine.FixedUpdate` calls `SendEmulationUpdateBlock` on every block first, so
  every emulator has raised its count for this step;
- then `EmulationUpdateBlock` on everything registered, which reaches a modded
  block's `KeyEmulationUpdate` override. `BlockPrefabCreator.SetupBehaviour` sets
  `RegisterEmulationUpdate = true` for every modded block, so no opting in is
  needed.

**Latch the edges there, consume them in the frame update:**

```csharp
public override void KeyEmulationUpdate()          // once per fixed step
{
    emulatedPress |= key.EmulationPressed();
    emulatedRelease |= key.EmulationReleased();
    emulatedHeld = key.EmulationHeld(true);
}

public override void SimulateUpdateAlways()        // once per frame
{
    bool pressed = key.IsPressed || emulatedPress;
    bool held = key.IsHeld || emulatedHeld;
    emulatedPress = false;                          // each edge handed out once
    emulatedRelease = false;
}
```

`MKey.CheckEmulation` keys its snapshot to `Time.fixedTime`: it advances the first
time it is called in a fixed step and returns the same answer for the rest of it.
Poll it from `Update` and a single variable press lands two or three times at a
high frame rate, or is missed entirely at a low one.

Reset the latches when a run starts or stops — Besiege keeps a behaviour alive
between runs, so an edge caught at the end of one otherwise fires at the start of
the next.

## Variables are keys with names

A key can carry a *message* — one or more variable names. `KeyInputController`
keeps two tables, `usedKeys` from `KeyCode` and `usedMessages` from name, each to
the list of keys registered under it. An emulating key with `Message=foo` presses
every key that names `foo`. There is no limit on names, and they cost no keyboard.

In a save, an `MKey` serialises as a `StringArray`: one entry per keycode, then
optionally `Ignored=True`, `Message=<names joined by ';'>` and `Use=True`
(`useMessage`, the flag that says listen to the name instead of the keyboard).

### Trap 1: a key with no keycodes is never registered

`Machine.InitSimBlock` files a block's keys with `KeyInputController` from inside

```csharp
for (int i = 0; i < key.KeysCount; i++) { ... AddMKey(block, key, key.GetKey(i)); }
```

and `AddMKey` is what puts a key into `usedMessages`. **No keycodes, no iterations,
no registration** — the key joins no table and hears nothing, silently.

So a key written into a `.bsg` as `Message=…` + `Use=True` and nothing else is
inert, and the symptom looks exactly like a block that does not support emulation.
Keep a keycode in the array; `AddMKey` files a key under its name *or* its keys,
never both, so with `Use=True` the keycode is never answered to. It is there to be
counted.

In game the case never arises, because `KeySelector.SetVariable` sets the name and
leaves the block's own key alone. It only bites code that writes saves.

### Trap 2: emulated keys are reference counted

`MKey.UpdateEmulation` adds one on press and takes one away on release, and
`Emulating` is "the count is above nought". A press is the nought-to-one edge.

So a **second emulator firing while the first still holds the same name raises no
press at all**, and the key does not come up until the last one lets go. Anything
generating a stream of events onto one name — a sequencer, a repeated trigger —
has to leave a gap between them. Sixty milliseconds is comfortably below what a
player notices and comfortably above a fixed step.

## The timer block

`BlockType.Timer` = **66**. Its mapper keys, from `TimerBlock.Awake`:

| Key | Type | What it does |
| --- | --- | --- |
| `activate` | `MKey` | starts the timer |
| `emulate` | `MKey` | what it presses when it fires |
| `automatic` | `MToggle` | start with the simulation instead of on the key |
| `hold-to-activate`, `can-stop`, `loop` | `MToggle` | as named |
| `wait` | `MSlider` | seconds before it fires, default 1 |
| `emulation-time` | `MSlider` | how long it holds the key, default 1 |

In a save those are `bmt-activate`, `bmt-emulate`, `bmt-automatic`, `bmt-wait`,
`bmt-emulation-time`.

Both sliders are declared with **`AddSliderUnclamped`**, so a value past their 60 s
maximum survives a save and a load. An event four minutes in is one timer with
`wait=240`, not a chain of them — which makes a timer per event a workable way to
sequence anything, and `automatic` versus an `activate` key is the difference
between "starts with the simulation" and "starts when I press this".

## `MSlider.Value` does not clamp, and `Min`/`Max` are settable

`MSlider::set_Value` compares to the current value, stores, and raises the change
event. There is no clamp in it. `Min` and `Max` have setters too.

That is worth knowing but not worth exploiting: a value stored outside the bounds
its own setting declares is the sort of thing that breaks quietly on load, or in
any game code that trusts the bounds. The clean way to let a control reach further
than it is comfortable to drag is to **declare the wide range on the setting and
narrow the travel in your own UI** — map your slider across the comfortable range,
clamp the fraction to `[0, 1]` when displaying, and let a typed value use the
setting's real limit. The handle rests against its stop and the number tells the
truth, and everything stored is inside the declared bounds.

`AddSliderUnclamped` exists for the case where you want Besiege's own mapper widget
to accept a value past its maximum.

## Hiding a block's controls from Besiege's mapper

`MapperType.DisplayInMapper` (on `MSlider`, `MToggle`, `MMenu`, `MKey`) decides
whether a control appears in the block mapper. A mod drawing its own panel can set
it `false` on everything but the key, leaving the mapper as a key binder.

Besiege reads the flag while *building* the mapper's rows, so a change lands the
next time the mapper opens, not while it is up. And if the panel is a soft
dependency, everything must go back if the panel fails — otherwise the block has no
way to be set at all.
