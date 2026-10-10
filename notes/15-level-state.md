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

## The level's people decide "grounded" by their own layer mask

Knights, peasants and animals are `EntityAI` (on the body's root; `GetComponentInParent<EntityAI>()` from
any of its colliders). It walks by its own physics and asks whether it is on the ground with a downward
`Physics.Raycast` against **`groundLayerMask`, a public per-instance field**, not against whatever it
collides with. A surface a mod adds — on the floor's layer or any other — that is not in that mask is
air to it. Its `OnCollisionEnter` also knocks it over (`FallOver`) when a contact's relative velocity
passes its `SelfRighting.FallImpactThreshold`. On the Sand mod's sand, knights glided and often died just
walking; the mask is the likely cause, read from the IL, and the fix — adding the layer to the mask of each
one that touches the surface, `ai.groundLayerMask = ai.groundLayerMask.value | 1 << layer` — is not yet
confirmed in game.

Friction too is a pair's, not the entity's: a slippery ground material combined by `Minimum` (see
[21](21-many-particles-and-gpgpu.md), "Ground you deform") makes them skate. Give the entity's collider a material combined by `Maximum` while it touches, and its own back on
`OnCollisionExit`. And leave them out of anything that reacts to weight or contact: a walking ragdoll's
feet are dozens of contacts a step.

**Slopes are a cosine, and walking force is a friction.** An entity takes a contact whose normal's dot with
up is below `movement.MaxAscent` for a wall (`CostumOnCollisionStay`), and only climbs a slope it counts as
ground when `movement.walkUpSlopes` is set; a mod surface standing at thirty degrees with steeper facets is
a wall to most of them. Both fields are public, as is `movement.slopeClimbingSpeed`, what the AI adds
along a slope's normal each step to carry it up; with a low value a slope it counts as ground is still
climbed very slowly. Its drive is `-gravity.y × mass × CombineFrictions()`, where
`CombineFrictions` takes its own collider's `sharedMaterial` against each touched collider's with Unity's
combine rules (Average, Minimum, Multiply, Maximum, by priority) — and returns 0 if its own collider has no
material at all — so a low-friction ground leaves it too weak to climb whatever its limits.

**The god tool raycasts against colliders only.** `GodExplodeOnClick.Update`: on a left click while
`StatMaster.GodTools.ExplodeOnClick` and simulating, `Physics.Raycast` from the cursor against
`LayerMask.GetMask("Default","DontCollideSelf","AddPoint","AddPoint2","WaterCannon","Brace","Environment",
"MachineVis","Sharp","BrickWall","Floor","EnemyProjectile")`, then the public `Explodey(point)`. A mod surface
without a collider under the cursor is clicked through; give it one there each frame while the tool is on.

**An entity measures an obstacle by its collider's bounding box.** `EntityAI.CalculateCollisionHight` is
`collider.bounds.max` (in its gravity frame) less its own feet: one big mesh collider — a terrain-like
surface a mod builds in chunks — reads as tall as its highest point everywhere. With
`movement.canJump` set, a grounded entity jumps what is between 0.2 and `jumpHeight` and sets
`hitHighObject` (turns away) for what is higher; with `canJump` off neither check runs and it walks into the
surface as a slope. Raising `slopeClimbingSpeed` to help it up made it fast enough to die hitting the next
rise.
