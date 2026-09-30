# Keys, emulation, variables and timers

## `MKey` carries the whole automation feature

`MSlider`, `MToggle`, `MMenu`, `MValue` have **nothing** variable-related — no
message, no emulation, no variable selector. Only `MKey` does.

Design constraint, not a gap to work around: a setting that must be automated must
be reachable through a key. A block whose *value* needs to vary over time needs
either one block per value, or a key per step.

## Reading an emulated key

Emulated presses don't arrive in `Update`. Besiege has a pass for them:

- `Machine.FixedUpdate` calls `SendEmulationUpdateBlock` on every block first, so
  every emulator raised its count for this step;
- then `EmulationUpdateBlock` on everything registered, reaching a modded block's
  `KeyEmulationUpdate` override. `BlockPrefabCreator.SetupBehaviour` sets
  `RegisterEmulationUpdate = true` for every modded block — no opting in needed.

**Latch edges there, consume them in the frame update:**

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

`MKey.CheckEmulation` keys its snapshot to `Time.fixedTime`: advances first time
called in a fixed step, returns same answer for the rest of it. Poll from `Update`
and a single variable press lands two or three times at high frame rate, or is
missed entirely at a low one.

Measured, block with two keys: modelling Besiege's 100 Hz step and the `everyOther`
gate in `Machine.FixedUpdate`, a variable held for **one** fixed step reached a
naive `Update`-side edge 7 times in 20 at 30 fps, 1 in 20 at 15 fps, 20 in 20 with
the latch. Above 60 fps the two agree — exactly why this survives testing.

**With more than one key, don't let `||` short-circuit past one.** Each `MKey`
advances *its own* snapshot, and only when one of *its own* edge methods is called
— `EmulationValue()` doesn't. So

```csharp
bool pressed = left.EmulationPressed() || right.EmulationPressed();   // WRONG
```

leaves `right` unpolled for every step `left` fired, and next step its
`wasEmulating` is two steps stale. Call all into locals first, then combine:

```csharp
bool lp = left.EmulationPressed(),  rp = right.EmulationPressed();
bool lr = left.EmulationReleased(), rr = right.EmulationReleased();
emulatedPress   |= lp || rp;
emulatedRelease |= lr || rr;
```

Calling both `EmulationPressed` and `EmulationReleased` on the same key in the same
step is fine — snapshot advance is inside `if (fixedTime != Time.fixedTime)`, so it
happens once however many times you ask.

Do **not** add an `OnSimulateStart` clearing the latches: a sim behaviour is a
fresh object every run, private fields already at defaults. See
[08-block-lifecycle.md](08-block-lifecycle.md).

Guard the override too. `SafeAwake` builds no mapper controls on a simulating
client without physics, but `EmulationUpdateBlock` checks only `isSimulating`, so
`KeyEmulationUpdate` runs there with every `MKey` field still null. Besiege's own
`SteeringModuleBehaviour` has the same hole; `if (key == null) return;` closes it.

## Variables are keys with names

A key can carry a *message* — one or more variable names. `KeyInputController`
keeps two tables, `usedKeys` from `KeyCode` and `usedMessages` from name, each to
the list of keys registered under it. An emulating key with `Message=foo` presses
every key naming `foo`. No limit on names, and they cost no keyboard.

In a save an `MKey` serialises as a `StringArray`: one entry per keycode, then
optionally `Ignored=True`, `Message=<names joined by ';'>` and `Use=True`
(`useMessage`, the flag saying listen to the name instead of the keyboard).

## A binding set in code needs `ApplyValue`, or it falls back

Every `MapperType` holds its value twice. On `MKey`: the live `_keyCodes`, `message`,
`useMessage`, and a load copy `_loadKeyCodes`, `_loadMessage`, `_loadUseMessage`.
`ApplyValue` copies live into load; `ResetValue` copies load back over live. The
constructor fills both; writing the public fields afterwards fills only the live one.

The load copy is what the game treats as committed. `SaveableDataHolder.GetLoadData`
serialises it (`SerializeLoadValue`) for `BlockMapper.EditField`, `OnEditField` and
`UpdateBlockData`, and on a multiplayer client `NetworkEditFieldHandler.OnCloseMapper`
calls `ResetValue` on every control. So a default name given in `SafeAwake` shows at
first and later comes back as the constructor's keycode -- seen in single player: two
rows meant to answer `var_1` and `var_2` both ended up pressing `C`.

```csharp
row.Emulate = AddEmulatorKey("Emulate", "Out0", KeyCode.C);
row.Emulate.message = new string[] { "var_1" };
row.Emulate.useMessage = true;
row.Emulate.ApplyValue();          // or the load copy still says C
```

`ApplyValue` only copies the fields and raises `KeysChanged`/`KeyCountChanged` -- no
input controller -- so it is safe in `SafeAwake`. `./tools/peek.sh dump MKey` shows it.

## The logic gate block, from the inside

Worth having written down: it is the other block a mod is likely to stand in for,
and its controls are not guessable.

`LogicGate` registers `activate-A` and `activate-B` (`MKey`, defaults `U` and
`I`), `Gate` (`MMenu`), `toggle-mode` and `inverted` (`MToggle`), and `emulate`
(`MKey`). In a save those are `bmt-` plus those names, the same as any block.

`GateType` is, in order: `NOT, AND, OR, NOR, NAND, XOR, XNOR, Random, SRLatch,
DLatch, Counter, EdgeDetect`. `EvaluateEmulation` is a switch on it:

| gate | what it returns |
| --- | --- |
| NOT | `!A` |
| AND / OR | `A && B` / `A \|\| B` |
| NAND / NOR | the negations of those |
| XOR / XNOR | `A != B` / `A == B` |
| Random, SRLatch, DLatch | `aToggled` -- the state machine in `UpdateState` does the work |
| Counter | `counter == 0 && lastCount == 3` |
| EdgeDetect | `aToggled`, and clears it in the same breath |

So the combinational gates are one line each and the other five are all one
latched flag, set by `UpdateState` from the keys, the toggle-mode switch and (for
edge detect) `inverted`. `toggle-mode` and `inverted` are never both shown: the
block's `UpdateHidden` swaps which one the mapper displays with the gate.

### The two passes, and what `UpdateState` is handed

The state machine runs **twice a tick** — once with the keyboard's edges, once with
the emulated ones — and the answer goes out on a third call. Reproducing a gate
means reproducing all three, and the arguments are where the mistakes are:

```csharp
UpdateBlock()                 // once a frame, and only while Time.timeScale > 0
    aPressed  = aKey.IsPressed;
    aHeld     = aPressed || aKey.IsHeld;
    aReleased = gateType == EdgeDetect && !aHeld && aKey.IsReleased;
    UpdateState(aPressed, bPressed, aHeld || emuAHeld, bHeld || emuBHeld, aReleased);

EmulationUpdateBlock()        // emulation tick, second of the two phases
    emuAPressed  = aKey.EmulationPressed();
    emuAHeld     = aKey.EmulationHeld(true);
    emuAReleased = aKey.EmulationReleased();
    UpdateState(emuAPressed, emuBPressed, emuAHeld || aHeld, emuBHeld || bHeld,
                emuAReleased);

SendEmulationUpdateBlock()    // emulation tick, first phase
    if (EvaluateEmulation()) StartEmulation(); else StopEmulation();
```

Three things there are easy to get wrong and invisible when you do:

- **a press counts as a hold** — `aHeld = aPressed || IsHeld`, not `IsHeld` alone;
- **the release is handed over only for the edge detector, and only when the key is
  not held at all.** A key bound to two codes reports a release while the other is
  still down, and an edge detector taking that would fire while its input was on;
- **each pass ORs in the other's held state**, so the gate sees one input whether
  it arrives from the keyboard or from a variable.

`StartEmulation`/`StopEmulation` guard on an `emulating` flag, so the key is raised
and dropped exactly once — which is what emulation's reference counting needs.

Because the send phase runs across the whole machine before the read phase (above),
**a signal takes one emulation tick to cross a gate**: it emits at the start of tick
N from what it worked out during tick N-1. A chain of gates settles one gate per
tick, and that is the timing any reproduction has to match.

The block's own controls are public — `LogicGate.AKey`, `BKey`, `ModeMenu`,
`ToggledInput`, `EmulateKey`, `Type` — even though the fields behind them are
private. For blocks with no such accessors, walk `SaveableDataHolder.MapperTypes`
and match on `MapperType.Key`; see
[12-machines-and-saves.md](12-machines-and-saves.md).

### Burn-out, and the one gate it eats

`burnoutProne` is set by `KeyInputController.CheckLoop(inputs, output, true)`
(public, reached through `BlockBehaviour.CheckLoop`, re-asked on
`ReferenceMaster.onMachinePostSim`): true when the gate's own answer can reach its
own inputs. `inputs` is the gate's `activationKeys`, or just `aKey` for NOT and
Random, which read no B.

Only a prone gate can burn out. `EmulationUpdateBlock` compares
`EvaluateEmulation()` with the last tick's answer; each consecutive tick it differs
counts one, and at `MAX_PULSES` (5) the gate is `burnedOut` — after which
`SendEmulationUpdateBlock` stops its emulation once and plays the sparks. Any press
or hold arriving resets the count.

Note what that costs the edge detector: `EvaluateEmulation` **clears** `aToggled` as
it reads it, and for a prone gate it is called in the read phase for the burn-out
check as well as in the send phase to emit. The flag set by the read phase is
consumed by the check in the same phase, so a burnout-prone edge detector never
emits at all. Read out of the IL rather than measured in game, but worth knowing
before reproducing one.

### Listing what variables exist

There is no registry to read in the build area. `KeyInputController.usedMessages`
is filled by `Machine.InitSimBlock` when a run starts and is empty before one, so
a menu offering "the variables available" has to walk `Machine.BuildingBlocks`,
scan each block's `MapperTypes` for `MKey`, and collect `key.message` — a
`string[]`, not a list, and not `CombineVariables` unless you want them joined the
way a save spells them. Names survive a key being switched back to the keyboard,
which is a feature: a name typed once is a name the player means to use.

### How many, how long, and how several are combined

One `MKey` holds a `List<KeyCode>` and a `string[]` of names, neither capped in the
data model — `AddKey` just appends, and a save can carry any number. The limits are
the mapper's:

| | limit | where |
| --- | --- | --- |
| keycodes on one key | **3** | `Selectors.KeySelector.MaxKeys`; the `+` on a key row is hidden once three are bound -- the mapper's cap only, below |
| variable names on one key | **100** | `StatMaster.KeyMapper.MaxDisplayedTags`; past it the tag editor refuses to split what is typed |
| length of one name | **32** | `StatMaster.KeyMapper.VariableCharLimit` |

**Past the mapper nothing counts keycodes to three.** `MaxKeys` is read by
`KeySelector.CenterKeys` and `LeftAlignKeys` (layout) and by
`OverviewBlockMapper.AdjustKey`, which checks it on the *add* path only: refuses a
fourth, never trims one already there. `Machine.InitSimBlock` registers every
keycode a key holds, and `KeyInputController.Emulate`, for an emulating key on
keycodes, walks `KeysCount` and presses every one. So a mod may bind more than three
to an input or to what a block presses, and it works in a run; the player just
cannot add past three in the game's own mapper. Node Editor uses five.

**Separators are `;` and `,` when typing, `;` alone in storage.**
`Selectors.TagSelector.SEPARATOR_CHARS` is both; `MKey.SplitVariable` reads on `;`
and `MKey.CombineVariables` writes on `;`. A mod with its own name field should
split on both and cut to 32, or it will write names the game's own mapper cannot
edit afterwards.

**Names match exactly, case included.** `KeyInputController.usedMessages` is a
`Dictionary<string, List<KeyEntry>>` built with the default comparer, so `Door` and
`door` are two variables. A mod that generates names should pick one case (lower
reads best) rather than trust the player to retype it.

**Several of either are OR-ed.** `MKey.IsHeld` walks the keycodes and returns on
the first one held; the names go through the emulation count, so the key is held
while *any* emulator holds *any* of its names. One consequence worth keeping in
mind for edge-driven blocks: because it is a count and not a set of flags, a press
edge is only the nought-to-one transition — two names raised overlapping give one
press and one release, not two (Trap 2 below).

### Trap 1: a key with no keycodes is never registered

`Machine.InitSimBlock` files a block's keys with `KeyInputController` from inside

```csharp
for (int i = 0; i < key.KeysCount; i++) { ... AddMKey(block, key, key.GetKey(i)); }
```

and `AddMKey` puts a key into `usedMessages`. **No keycodes, no iterations, no
registration** — key joins no table and hears nothing, silently.

So a key written into a `.bsg` as `Message=…` + `Use=True` and nothing else is
inert, and the symptom looks exactly like a block that doesn't support emulation.
Keep a keycode in the array; `AddMKey` files a key under its name *or* its keys,
never both, so with `Use=True` the keycode is never answered to. It's there to be
counted.

In game the case never arises — `KeySelector.SetVariable` sets the name and leaves
the block's own key alone. Only bites code that writes saves.

### Trap 2: emulated keys are reference counted

`MKey.UpdateEmulation` adds one on press, takes one away on release, and
`Emulating` is "count above nought". A press is the nought-to-one edge.

So a **second emulator firing while the first still holds the same name raises no
press at all**, and the key doesn't come up until the last one lets go. Anything
generating a stream of events onto one name — sequencer, repeated trigger — must
leave a gap. Sixty milliseconds is comfortably below what a player notices and
comfortably above a fixed step.

### Trap 2b: a block never drives the keys it hands to `EmulateKeys`

`BlockBehaviour.EmulateKeys(MKey[] own, MKey emulate, bool down)` ends at
`KeyInputController.Emulate(block, own, emulate, down)`, which walks every key
registered under the emitted name or keycode and calls `UpdateEmulation` on each —
**except** the ones in `own`. `EmulateEntry` is the filter, and it compares by
**reference**:

```csharp
foreach (MKey k in own) if (k == target) return false;   // skipped
```

That array is how the game stops a gate driving itself: `LogicGate` passes its own
`activationKeys` — its A and B and nothing else (just A for NOT and Random, which
read no B).

**Pass only the keys that would be a genuine self-loop.** A modded block that holds
several independent parts — rows of a table, each a gate in its own right — must
pass *that row's* inputs, not the block's. Hand over every key the block owns and
the game skips them all: nothing inside the block can drive anything else inside
it, and every wire between two of its own parts is dead the moment the machine
runs. It looks right in a mapper, converts correctly to real blocks, and does
nothing in a simulation — the failure is invisible outside a run.

### Trap 2c: `Emulate` presses names *or* keycodes, and looks each up unguarded

`KeyInputController.Emulate` tests the emitting key's `useMessage`, walks its
`message` names **and returns**; the keycodes are the other branch. A key bound to
names presses no keycode, whatever spare keycode it still holds. One emulator cannot
raise `C` and `door` together — that takes a second key, or an OR gate reading the
name and pressing the key (one fixed step later).

Each lookup is a bare `usedMessages[name]` / `usedKeys[code]` indexer, no
`TryGetValue`. The entries come from `Machine.InitSimBlock` calling
`KeyInputController.AddMKey(block, key, code)`, which creates the entry for every
name and keycode a block's key uses; for an emulator (`isEmulator`) it creates the
entry without listing the key as a listener. So a block's registered keys are safe
to emit. A key made at run time — `new MKey("Relay", "relay", KeyCode.C, true)`,
never registered — goes through `EmulateKeys` the same way (nothing in `Emulate`
checks where the emitter came from), but the indexer throws `KeyNotFoundException`
when nothing on the machine uses that keycode. Catch it: nothing would have heard
the press. `BlockBehaviour.inputController` is private, so registering such a key
yourself is not open.

**Confirmed in game:** a run-time key built in `OnSimulateStart` and bound by hand
(`BindVariable`, or keycodes) presses real blocks, variables, and other modded
blocks' keys, and lets go cleanly on `OnSimulateStop`. So a block whose rows only
*press* keys can keep those rows as its own data — one `MText` — rather than a
fixed pool of `MKey` controls, and build the pressing keys when a run starts.

**A key that listens can be filed by hand too (confirmed in game).** It is not the
block's registration that hears presses, it is `KeyInputController`'s tables, and
those are reachable: `BlockBehaviour.ParentMachine` is public, `Machine.Awake` adds
the controller as a component (`machine.GetComponents<KeyInputController>()`, the
last one where a network player's was added after), and the three calls
`Machine.InitSimBlock` makes per key are all public. In `OnSimulateStart`:

```csharp
key.SetInputController(controller);          // IsPressed and friends read through it
for (int k = 0; k < key.KeysCount; k++)
{
    controller.AddMKey(BlockBehaviour, key, key.GetKey(k));   // names too, if useMessage
    controller.Add(key.GetKey(k));
}
```

A key made with `new MKey(...)` and filed this way hears the keyboard, variables,
and other blocks' emulation, and a block's `EmulateKeys` own-key filter still
works on it by reference. So a table whose rows read keys can keep them as its own
data as well. (`MMenu`, `MToggle` and `MSlider` have public constructors too, and
`MSlider.Value` does not clamp.)

### Trap 3: `IsReleased` is the one key property that does not check `useMessage`

Binding a key to a variable is supposed to take the keyboard out of it, and three
of four properties implement that by testing `useMessage` first:

| property | tests `useMessage`? | with a variable bound |
| --- | --- | --- |
| `Value` | yes | `0` |
| `IsPressed` | yes | `false` |
| `IsHeld` | yes | `false` |
| **`IsReleased`** | **no** | **`true` when the keyboard key comes up** |

`get_IsReleased` guards on `ignored`, on `Value > 0` and on `MouseKeyBlocked()`,
then walks the keycodes. `Value` is 0 under a variable, so it walks them — and
`KeySelector.SetVariable` leaves the block's keycodes in place, so they're still
there to answer.

Effect: a block handed over to automation still reacts when the player brushes the
arrow key it used to use. Return 2 Center's side-to-side sweep stopped dead that
way. Anything reading a release edge wants

```csharp
bool released = !key.useMessage && key.IsReleased;
```

`useMessage` is a public field, so this needs nothing clever. Variable's own
release arrives through `EmulationReleased()` as usual.

### Trap 4: `MKey.IsDown` is deprecated and says so on every call

`get_IsDown` is

```
Debug.LogWarning("IsDown is deprecated, please use IsHeld");
return IsHeld;
```

so a block polling it per frame writes a log line every frame of every run. Easy
to miss because it works — value is right, console is just full.
`KeyInputController.KeyInfo` has an `IsDown` of its own that is *not* deprecated,
which is why the name still reads as current in the game's own code. Use
`MKey.IsHeld`.

## The timer block

`BlockType.Timer` = **66**. Mapper keys, from `TimerBlock.Awake`:

| Key | Type | What it does |
| --- | --- | --- |
| `activate` | `MKey` | starts the timer |
| `emulate` | `MKey` | what it presses when it fires |
| `automatic` | `MToggle` | start with the simulation instead of on the key |
| `hold-to-activate`, `can-stop`, `loop` | `MToggle` | as named |
| `wait` | `MSlider` | seconds before it fires, default 1 |
| `emulation-time` | `MSlider` | how long it holds the key, default 1 |

In a save: `bmt-activate`, `bmt-emulate`, `bmt-automatic`, `bmt-wait`,
`bmt-emulation-time`.

Both sliders declared with **`AddSliderUnclamped`**, so a value past their 60 s
maximum survives save and load. An event four minutes in is one timer with
`wait=240`, not a chain — which makes a timer per event a workable way to sequence
anything. `automatic` versus an `activate` key = "starts with the simulation"
versus "starts when I press this".

## `MSlider.Value` does not clamp, and `Min`/`Max` are settable

`MSlider::set_Value` compares to current value, stores, raises change event. No
clamp. `Min` and `Max` have setters too.

Worth knowing, not worth exploiting: a value stored outside the bounds its own
setting declares breaks quietly on load, or in any game code trusting the bounds.
Clean way to let a control reach further than comfortable to drag: **declare the
wide range on the setting and narrow the travel in your own UI** — map your slider
across the comfortable range, clamp the fraction to `[0, 1]` when displaying, let a
typed value use the setting's real limit. Handle rests against its stop, number
tells the truth, everything stored is inside declared bounds.

`AddSliderUnclamped` exists for when you want Besiege's own mapper widget to accept
a value past its maximum.

## Hiding a block's controls from Besiege's mapper

`MapperType.DisplayInMapper` (on `MSlider`, `MToggle`, `MMenu`, `MKey`) decides
whether a control appears in the block mapper. A mod drawing its own panel can set
it `false` on everything but the key, leaving the mapper as a key binder.

Besiege reads the flag while *building* the mapper's rows, so a change lands next
time the mapper opens, not while it's up. If the panel is a soft dependency,
everything must go back if the panel fails — else the block can't be set at all.
