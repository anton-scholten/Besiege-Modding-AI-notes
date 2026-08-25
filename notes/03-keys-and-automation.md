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

Measured, on a block with two keys: modelling Besiege's 100 Hz step and the
`everyOther` gate in `Machine.FixedUpdate`, a variable held for **one** fixed step
reached a naive `Update`-side edge 7 times in 20 at 30 fps, 1 time in 20 at 15 fps,
and 20 times in 20 with the latch. Above 60 fps the two agree, which is exactly why
this survives testing.

**With more than one key, do not let `||` short-circuit past one of them.** Each
`MKey` advances *its own* snapshot, and only when one of *its own* edge methods is
called — `EmulationValue()` does not do it. So

```csharp
bool pressed = left.EmulationPressed() || right.EmulationPressed();   // WRONG
```

leaves `right` unpolled for every step in which `left` fired, and on the next step
its `wasEmulating` is two steps stale. Call all of them into locals first, then
combine:

```csharp
bool lp = left.EmulationPressed(),  rp = right.EmulationPressed();
bool lr = left.EmulationReleased(), rr = right.EmulationReleased();
emulatedPress   |= lp || rp;
emulatedRelease |= lr || rr;
```

Calling both `EmulationPressed` and `EmulationReleased` on the same key in the same
step is fine — the snapshot advance is inside an `if (fixedTime != Time.fixedTime)`,
so it happens once however many times you ask.

Do **not** add an `OnSimulateStart` that clears the latches: a sim behaviour is a
fresh object every run and its private fields are already at their defaults. See
[08-block-lifecycle.md](08-block-lifecycle.md).

Guard the override, too. `SafeAwake` builds no mapper controls on a simulating
client without physics, but `EmulationUpdateBlock` checks only `isSimulating`, so
`KeyEmulationUpdate` runs there with every `MKey` field still null. Besiege's own
`SteeringModuleBehaviour` has the same hole; `if (key == null) return;` closes it.

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

### Trap 3: `IsReleased` is the one key property that does not check `useMessage`

Binding a key to a variable is supposed to take the keyboard out of it, and three
of the four properties implement that by testing `useMessage` first:

| property | tests `useMessage`? | with a variable bound |
| --- | --- | --- |
| `Value` | yes | `0` |
| `IsPressed` | yes | `false` |
| `IsHeld` | yes | `false` |
| **`IsReleased`** | **no** | **`true` when the keyboard key comes up** |

`get_IsReleased` guards on `ignored`, on `Value > 0` and on `MouseKeyBlocked()`,
and then walks the keycodes. `Value` is 0 under a variable, so it walks them — and
`KeySelector.SetVariable` leaves the block's keycodes in place, so they are still
there to answer.

The effect is a block that has been handed over to automation still reacting when
the player brushes the arrow key it used to use. Return 2 Center's side-to-side
sweep stopped dead that way. Anything reading a release edge wants

```csharp
bool released = !key.useMessage && key.IsReleased;
```

`useMessage` is a public field, so this needs nothing clever. The variable's own
release arrives through `EmulationReleased()` as usual.

### Trap 4: `MKey.IsDown` is deprecated and says so on every call

`get_IsDown` is

```
Debug.LogWarning("IsDown is deprecated, please use IsHeld");
return IsHeld;
```

so a block polling it per frame writes a line to the log every frame of every run.
It is easy to miss because it works — the value is right, the console is just full.
Note that `KeyInputController.KeyInfo` has an `IsDown` of its own that is *not*
deprecated, which is why the name still reads as current in the game's own code.
Use `MKey.IsHeld`.

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
