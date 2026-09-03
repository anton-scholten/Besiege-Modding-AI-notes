# What Besiege does not tell a block

Four facts about the block lifecycle, each costing a wrong fix before it was
established — one of which was itself recorded wrongly here for a while. They compose
into one rule, at the bottom.

All read out of `Assembly-CSharp`; technique in
[06-reading-the-game.md](06-reading-the-game.md).

## A simulation runs on a clone, so the run callbacks go to a different object

`Machine::StartPhysics` builds a `simulationClone`; `DestroySimMachine` takes it down.
`OnSimulateStart`, `OnSimulateStop` and `SimulateUpdateAlways` arrive on the
**clone's** blocks — never on the block the block mapper and any panel of your own are
editing.

So anything a *building* block needs to know about a run must come from elsewhere.
State it holds — a preview flag, an "is sounding" flag — isn't cleared by the run
callbacks, because those never reach it.

**The clone is rebuilt every run, not pooled.** `Machine.StartSimulation` does
`tempSim = Instantiate(buildingMachine, ...)`; `StartPhysics` moves it to
`simulationClone` and nulls `tempSim`; `DestroySimMachine` does
`Destroy(simulationClone.gameObject)` and clears `simBlocks`. So a sim behaviour is a
fresh object each run.

Two things follow, pulling in opposite directions:

- **Don't write per-run reset code for a sim behaviour's own private fields.** Already
  at their defaults: Unity doesn't serialise a private field without
  `[SerializeField]`, so `Instantiate` doesn't copy it. An `OnSimulateStart` clearing
  them is dead code. (Written three times now, in three mods, from the
  plausible-but-wrong belief that behaviours are kept between runs. The third time it
  also came with a changelog entry claiming a bug fixed that had never existed.)
- **Anything the clone reaches *outside* itself does persist**, and that's what needs
  undoing: statics, `Physics.gravity`, `RenderSettings`, a `GameObject` the block
  spawned at the scene root, components the mod added to level objects. See
  [15-level-state.md](15-level-state.md).

**`OnSimulateStart` *is* `Start`, and `OnSimulateStop` *is* `OnDisable`.** They read as
a pair of run events distinct from the Unity ones; they aren't:

- `Modding.ModBlockBehaviour.OnSimulateStart` has exactly one caller,
  `InternalModding.Blocks.ModBlockBehaviourHandler.Start`, inside `if (isSimulating)`;
- `OnSimulateStop` has exactly one caller,
  `InternalModding.Blocks.ModBlockBehaviourHandler.OnDisable`.

Worth knowing for its own sake and as a *check*. Any belief of the form "behaviours
survive a run, so I will reset in `OnSimulateStart`" is self-refuting: if they
survived, `Start` wouldn't run again, so neither would the reset. Whenever the
reasoning for a hook and the identity of the hook disagree, one is wrong — and
`peek.sh sig` plus a caller search settles it in a minute.

What the two hooks *are* good for is what `Start` and `OnDisable` are:
`OnSimulateStart` = "my sim copy exists and the run has begun", `OnSimulateStop` =
"put back anything I changed outside myself". The second is real work; see
[15-level-state.md](15-level-state.md).

**A public field pointing outside the machine survives the clone.** `Instantiate`
copies a public reference field, and if the target isn't inside the hierarchy being
copied it's left pointing at the original. That's how a block can spawn one scene
object in `SafeAwake`, guard with `if (thing == null)`, and have every run's clone
share the one the building block made rather than making its own.

## `IsSimulating` is false on a building block, even mid-run

`ModBlockBehaviour.IsSimulating` reads `handler.isSimulating`, which only
`BasicInfo::UpdateSimState` writes, and that method opens with

```
if (isBuildBlock) { isSimulating = false; SimPhysics = false; }
else if (_hasParentMachine) { isSimulating = _parentMachine.isSimulating; ... }
else if (!StatMaster.isMP) { isSimulating = StatMaster.levelSimulating; ... }
```

Two things follow. A build block answers **false** for the whole run — so guarding
"don't do this during a simulation" on `IsSimulating` never fires there. And it's
**cached**: `UpdateSimState` is called from `Awake`, `OnEnable` and
`UpdateParentMachine`, nowhere else. A per-block snapshot, not a live global.

**`StatMaster.levelSimulating`** (public static bool) is the global flag, and the only
simulation signal a building block can see.

## `BuildingUpdate` runs — but only while nothing is simulating

**Corrected August 2026.** This note previously said `BuildingUpdate` is never called.
Wrong, and wrong for exactly the reason the corollary below warns about: a search for
callers of the method token finds none, because the call is built as a delegate.

`InternalModding.Blocks.ModBlockBehaviourHandler.UpdateBlock()` ends with

```
if (!started) return;
...
if (BasicInfo.isSimulating)  { foreach b in behaviours: b.SimulateUpdateAlways(); ... }
else                         { foreach b in behaviours: b.BuildingUpdate(); }
```

reached as `ModdingUtil.PerformCallback(new Action(b.BuildingUpdate))` over a
`ldvirtftn` — same shape as `KeyEmulationUpdate`, invisible to a token search for the
same reason.

`UpdateBlock` is itself driven by `Machine.Update()`, which picks its list by the
machine's state:

```
if (isSimulating) { foreach b in simUpdate:   b.UpdateBlock(); }
else              { foreach b in buildUpdate: b.UpdateBlock(); }
```

So the real behaviour:

- **not simulating** — a building block is in `buildUpdate`, and
  `BasicInfo.isSimulating` is false on a build block (above), so `BuildingUpdate` is
  called **every frame**.
- **during a run** — only `simUpdate` is driven, so a building block gets no
  `UpdateBlock` at all and `BuildingUpdate` stops. The clone's blocks get
  `SimulateUpdateAlways` instead, and never take the `BuildingUpdate` branch because
  their `isSimulating` is true.

That's the grain of truth behind the old claim: a per-frame reconcile placed in
`BuildingUpdate` really does stop dead the moment you press simulate, and the build
machine is hidden and deactivated for the run as well (next section). For a loop that
survives a run, use Unity's own `Update` — `ModBlockBehaviour` and
`BlockModuleBehaviour<T>` declare no `Update`, `OnEnable`, `OnDisable` or `OnDestroy`,
so all four are free to implement and hide nothing.

For a build-area-only animation — preview spin, placement hint — `BuildingUpdate` is
exactly right and needs nothing else.

Corollary for searching, now doubly earned: **a hook with no IL callers is not proof
it is dead.** `BuildingUpdate` and `KeyEmulationUpdate` both show zero callers to a
token search and both are alive. Check `ModBlockBehaviourHandler` for a `ldvirtftn` of
the method before concluding anything.

## The build machine is hidden for the run

Which deactivates the object. `Update` stops, an `AudioSource` on it stops, and
nothing tells the component any of that happened. Whatever it was holding comes back
stale when the machine reappears.

## The rule: reconcile, do not react

Given all four, a block shouldn't switch state from whichever callback noticed
something — most don't arrive. Derive the state from one rule and re-check every
frame:

```csharp
private void Update()
{
    bool simulating = StatMaster.levelSimulating;   // the only signal that reaches here
    bool wanted = previewing || simulating;
    if (wanted != source.isPlaying)
    {
        if (wanted) { source.Play(); } else { source.Stop(); }
    }
}
```

A rule that's re-checked cannot be left on the wrong side of an event that went
missing. Same for anything else held across a run: material, renderer, cached child.
**Check it, don't remember it.**

Not a style preference — every one of these was found as a bug first:

- a preview that stopped making sound and couldn't be restarted, because the flag
  clearing it lived in a callback reaching a different object;
- a per-frame reconcile that stopped the instant a run started, because it was in
  `BuildingUpdate` — which runs only while nothing is simulating;
- a block's material replaced after the mod had dressed it once, leaving the change
  invisible with no error.

## Holding the keyboard while a mod types

Besiege's own key handler, the camera orbit and both selection tools stand down for
**`StatMaster.inMenu`**, and `StatMaster.SetInMenu(bool)` is public static. Raise it
while a text field of your own has focus, or the letters typed drive the camera and
fire block keys.

It is **counted** on Besiege's side, so raise and drop exactly once — and drop it when
the panel closes, or the game is left believing a menu is open.

`StatMaster.textFieldSelected` looks like the flag for this and is **not**: only
`ScaleOnMouseOver` and `Selectors.KeySelectorExtender` read it.

UI Factory's own `Input Field` prefab already carries this behaviour, so none of the
above is needed if you use it — see [04-ui-factory.md](04-ui-factory.md).
