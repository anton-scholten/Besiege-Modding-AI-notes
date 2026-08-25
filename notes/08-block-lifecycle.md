# What Besiege does not tell a block

Four facts about the block lifecycle, each of which cost a wrong fix before it was
established. They compose into one rule, which is at the bottom.

All read out of `Assembly-CSharp`; the technique is in
[06-reading-the-game.md](06-reading-the-game.md).

## A simulation runs on a clone, so the run callbacks go to a different object

`Machine::StartPhysics` builds a `simulationClone` and `DestroySimMachine` takes it
down. `OnSimulateStart`, `OnSimulateStop` and `SimulateUpdateAlways` arrive on the
**clone's** blocks — never on the block the block mapper and any panel of your own
are editing.

So anything a *building* block needs to know about a run has to come from
somewhere else. State it holds — a preview flag, an "is sounding" flag — is not
cleared by the run callbacks, because those never reach it.

## `IsSimulating` is false on a building block, even mid-run

`ModBlockBehaviour.IsSimulating` reads `handler.isSimulating`, which only
`BasicInfo::UpdateSimState` writes, and that method opens with

```
if (isBuildBlock) { isSimulating = false; SimPhysics = false; }
else if (_hasParentMachine) { isSimulating = _parentMachine.isSimulating; ... }
else if (!StatMaster.isMP) { isSimulating = StatMaster.levelSimulating; ... }
```

Two things follow. A build block answers **false** for the whole run — so guarding
"don't do this during a simulation" on `IsSimulating` never fires there. And it is
**cached**: `UpdateSimState` is called from `Awake`, `OnEnable` and
`UpdateParentMachine`, and nowhere else. It is a per-block snapshot, not a live
global.

**`StatMaster.levelSimulating`** (public static bool) is the global flag, and it is
the only simulation signal a building block can see.

## `BuildingUpdate` is never called

`ModBlockBehaviour` declares it and **nothing in the game invokes it**: no caller
anywhere in `Assembly-CSharp`, and `InternalModding.Blocks.ModBlockBehaviourHandler`
— which forwards `UpdateBlock`, `FixedUpdateBlock`, `LateUpdateBlock`,
`EmulationUpdateBlock` and the rest — has no `BuildingUpdate` and no `Update` at
all. Code put in that override does not run, silently.

Use Unity's own `Update`. `ModBlockBehaviour` and `BlockModuleBehaviour<T>` declare
no `Update`, `OnEnable`, `OnDisable` or `OnDestroy`, so all four are free to
implement and hide nothing. (Check that before relying on it: hiding a private base
Unity message means Unity calls yours and the base's cleanup never runs.)

Corollary for searching: a hook with **no IL callers is not proof it is dead**.
`KeyEmulationUpdate` also shows zero callers and is very much alive — the handler
reaches it through `ModdingUtil::PerformCallback` over a closure, and the call
lives in a compiler-generated class. Check the handler for a forwarder before
concluding either way.

## The build machine is hidden for the run

Which deactivates the object. `Update` stops, an `AudioSource` on it stops, and
nothing tells the component any of that happened. Whatever it was holding comes
back stale when the machine reappears.

## The rule: reconcile, do not react

Given all four, a block should not switch state from whichever callback noticed
something — most of them do not arrive. Derive the state from one rule and
re-check it every frame:

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

A rule that is re-checked cannot be left on the wrong side of an event that went
missing. The same applies to anything else held across a run: material, renderer,
cached child. **Check it, do not remember it.**

That is not a style preference — every one of these was found as a bug first:

- a preview that stopped making sound and could not be restarted, because the flag
  clearing it lived in a callback that reached a different object;
- a per-frame reconcile that never ran, because it was in `BuildingUpdate`;
- a block's material replaced after the mod had dressed it once, leaving the change
  invisible with no error.

## Holding the keyboard while a mod types

Besiege's own key handler, the camera orbit and both selection tools stand down for
**`StatMaster.inMenu`**, and `StatMaster.SetInMenu(bool)` is public static. Raise it
while a text field of your own has focus or the letters being typed drive the
camera and fire block keys.

It is **counted** on Besiege's side, so raise and drop it exactly once — and drop it
when the panel closes, or the game is left believing a menu is open.

`StatMaster.textFieldSelected` looks like the flag for this and is **not**: only
`ScaleOnMouseOver` and `Selectors.KeySelectorExtender` read it.

UI Factory's own `Input Field` prefab already carries this behaviour, so none of
the above is needed if you use it — see [04-ui-factory.md](04-ui-factory.md).
