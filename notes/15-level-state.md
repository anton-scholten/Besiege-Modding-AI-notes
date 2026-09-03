# Reaching the whole level, and putting it back

From a mod whose blocks affect everything in the level rather than the machine they
sit on. Two problems: getting code onto objects that aren't yours, and undoing what
it did.

## A block behaviour only reaches its own block

`ModBlockBehaviour` gets you the block. To affect the enemy, scenery, arrows, debris
and other players' machines you need a component on **their** rigidbodies, and
nothing hands you those.

`SimBehaviour` is the base to use — what the game's own block scripts derive from,
not blacklisted, gives you `isSimulating`, `SimPhysics` and `ParentMachine`.

Bodies arrive by four routes and you need all four:

```csharp
Events.OnBlockInit    += b => Add(b.GameObject);         // blocks placed in the build area
Events.OnEntityPlaced += e => Add(e.GameObject);         // level entities
Events.OnLevelLoaded  += l => AddToEveryBody();          // a level being loaded
SceneManager.sceneLoaded += (s, m) => AddToEveryBody();  // a scene change
AddToEveryBody();                                        // the scene already up when the mod loads
```

`AddToEveryBody` is `Object.FindObjectsOfType<Rigidbody>()` plus a
`GetComponent<T>() == null` guard. That last direct call matters: a mod is enabled
partway through a session, and without it nothing works until the next scene load.

`FindObjectsOfType` on every scene load isn't cheap, but it runs once per load and
there's no cheaper enumeration exposed.

**Publish to one shared list rather than searching.** Different sources of the same
effect — a block, a projectile a block spawned — have nothing in common to search
for. Have each register itself in a `static Dictionary<string, T>` keyed by
`GetInstanceID().ToString()`, and let consumers iterate that. One loop then serves
every kind of source.

**Use the indexer, not `Add`.** `Dictionary.Add` throws `ArgumentException` on a
duplicate key. Reached from inside a coroutine that throw doesn't merely log — it
abandons the rest of the coroutine, so the entry is registered and never cleaned up.
`dict[key] = value` cannot fail.

## Level state is global, and nothing puts it back for you

`Physics.gravity`, `RenderSettings.ambientLight` and `RenderSettings.ambientIntensity`
belong to the level. Write them during a run and they stay written: through the build
area, through the next run, and into the **next level**. A mod that dims the sky and
forgets leaves the game dim until restart.

Not the sim clone's problem — see [08-block-lifecycle.md](08-block-lifecycle.md). The
clone is rebuilt every run, so its own fields need no resetting. What needs resetting
is precisely the things it touched that outlive it.

Shape that works: capture once, lazily, on the first write; restore from whichever
callback notices the run ended first; guard both with a flag so they're idempotent.

```csharp
private static bool captured;
private static Vector3 baseGravity;

public static void Capture()
{
    if (captured) return;
    baseGravity = Physics.gravity;   // read the level's value, do not hardcode one
    captured = true;
}

public static void Restore()
{
    if (!captured) return;
    Physics.gravity = baseGravity;
    captured = false;
}
```

**Capture the level's value; never hardcode it.** The mod this came from scaled
gravity from a literal `new Vector3(0f, -32.81f, 0f)`, so enabling the effect in any
level with different gravity snapped it to that number.

**Respect the player's own overrides.** `StatMaster.GodTools.GravityDisabled` is a
public static bool: gravity the player turned off themselves isn't yours to write, on
the way in *or* out.

**`SimBehaviour` has no `OnSimulateStop`.** A component on a level body gets no run
callbacks at all — those are `ModBlockBehaviour`'s. Watch `isSimulating` go false in
`FixedUpdate` and undo there, guarded so it happens once:

```csharp
if (!isSimulating)
{
    if (hasStarted) { hasStarted = false; /* ... */ Restore(); }
    return;
}
```

A block behaviour's `OnSimulateStop` is a good second path to the same `Restore()`,
since it's idempotent.

## Derived thresholds go stale

If a console command or mapper value feeds numbers other values are computed from,
don't compute them once at startup. The mod this came from built its altitude bands
on the eighth simulated frame **and only if the effect was already enabled** — and
the effect is off by default and enabled by a console command, so in practice every
boundary was zero and the first comparison sent gravity to nothing.

Recompute when inputs have moved, not once:

```csharp
if (cachedMin == Mod.minAltitude && cachedMax == Mod.maxAltitude) return;
// ... rebuild, and invalidate whatever "which band am I in" state you cache
```

Seed the cached copies with `float.NaN` so the first call always rebuilds.

## Do not log per body

A message about a global change, written from a component on every rigidbody in the
level, is that message a few hundred times. Log it from wherever owns the global, or
not at all.
