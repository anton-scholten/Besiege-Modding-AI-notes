# Simulating a lot of something: what the 5.4 graphics and physics API leaves you

Written surveying whether granular material — sand, gravel, a dust field — can be a
mod. The survey is the useful part: it is an inventory of what a mod has to work with
when the thing it wants is *many small bodies*, and where Unity 5.4.0f3 stops being
the engine every tutorial assumes. Read before designing anything whose cost scales
with a particle count.

## Besiege's physics runs at 100 Hz, which halves every budget you assumed

Measured from a probe mod: `Time.fixedDeltaTime` is **0.01**, not Unity's default
0.02. `FixedUpdate` therefore runs a hundred times a second, and a mod stepping a
simulation from it has half the wall-clock per step that the usual arithmetic
suggests. Alongside it: `Physics.gravity` is `(0, -32.8, 0)`,
`defaultSolverIterations` 20, `defaultSolverVelocityIterations` 1,
`sleepThreshold` 0.005 — a deliberately expensive solver configuration, because
the machine is the game.

Consequence for anything particle-shaped: **do not step it from every
`FixedUpdate`.** Give the simulation its own rate — every second or fourth fixed
step, with its own substeps — and interpolate the visuals between. One readback
per simulation step instead of a hundred per second is the difference between the
coupling being free and the coupling being the cost.

## Rigidbodies are the obvious answer and they run out early

PhysX 3.3, and Besiege's own machine is already spending the budget. A mod adding a
few hundred colliding `Rigidbody` spheres is adding them *beside* a machine, a level
and whatever the player built. Treat the low thousands as the wall, not a target, and
design the thing that matters — the look, the pile, the way it pushes a wheel — to
not need them.

Everything below is the alternative: own the state in arrays, own the integration,
and touch PhysX only where the two worlds meet.

## Graphics API census: what 5.4 has, and the five things it does not

Measured against the shipped `UnityEngine.dll` with `tools/peek.sh sig <type> --
.../Managed/UnityEngine.dll`. Present:

- `ComputeShader` with `FindKernel`, `SetBuffer`, `SetTexture`, `Dispatch`,
  `DispatchIndirect`; `ComputeBuffer` with `SetData`, `GetData`, `SetCounterValue`;
- `SystemInfo.supportsComputeShaders` and `SystemInfo.supportsInstancing`;
- `Material.SetBuffer`, `SetFloatArray`, `SetVectorArray`;
- `Graphics.DrawProcedural`, `DrawProceduralIndirect`, `ExecuteCommandBuffer`;
- `Mesh.SetVertices`, `SetColors`, `SetUVs`, `SetNormals`, `MarkDynamic`;
- `Physics.OverlapSphereNonAlloc`, `RaycastNonAlloc`, `OverlapCapsuleNonAlloc`;
- `ParticleSystem.SetParticles` / `GetParticles` / `maxParticles`.

Absent, and each one kills a standard recipe:

- **`Graphics.DrawMeshInstanced` does not exist** — it is 5.6. The whole "batch 1023
  transforms per call" pattern is unavailable, and so is every sample built on it.
  Drawing many copies means one big dynamic `Mesh` you rebuild, or a vertex shader
  reading a `StructuredBuffer`.
- **`MaterialPropertyBlock.SetBuffer` does not exist**, though `Material.SetBuffer`
  does. Per-renderer buffer overrides are out; a material instance per buffer is in.
- **`Physics.ComputePenetration` does not exist** (5.6), and `Collider.ClosestPoint`
  is later still. Depenetrating your own particles against the game's colliders has
  to be done from shapes you derive yourself, not from a PhysX query.
- A `Mesh` is 16-bit indices only — **65535 vertices**, so 16383 billboard quads per
  mesh. More than that is more meshes.
- **`new Material(string)`, a shader built from source at runtime, is gone.** There is
  no GPU route without a bundle from a 5.4.0f3 editor.

## Two GPGPU routes, and Besiege ships a worked example of both

Besiege's water is CodeAnimo's *Surface Waves*, and its classes are in
`Assembly-CSharp`, not blacklisted, readable with `peek.sh`:

- `CodeAnimo.GPGPU.ComputeKernel` / `ComputeKernel1D` / `ComputeKernel2D` — a thin
  wrapper over `ComputeShader.Dispatch` with a `SupportedBySystem()` test;
- `CodeAnimo.GPGPU.SM3Kernel` — **the same simulation step as a fragment shader**
  rendering into a `RenderTexture`, chosen when compute is not supported.

That second one is the finding worth keeping. A ping-pong texture simulation in a
plain `.shader` needs no compute support, no `ComputeBuffer`, and ships in exactly
the asset bundle a mod already knows how to ship (see
[18-vendoring-unity-code.md](18-vendoring-unity-code.md)). It is the portable floor
under any GPU simulation, and the game's own water falls back to it.

Also in there: `TerrainHeightRenderer`, `WaveDepthRenderer`, `BufferSaveDepthMap` —
the level's collision geometry rendered top-down into a height/depth texture so the
simulation can read the world without a physics query. Same trick serves anything
that needs "how high is the ground here" a million times a frame.

### Compute is actually available, and the shader still needs an editor

Measured by probe mod on the Linux player, OpenGL 4.5, NVIDIA:
`SystemInfo.supportsComputeShaders` is **true**, `SystemInfo.supportsInstancing` is
true, a `ComputeBuffer` survives a `SetData`/`GetData` round-trip, and a
`RenderTexture` in `ARGBFloat` with `enableRandomWrite` creates. The player binary
carries `glDispatchCompute`, `GL_ARB_compute_shader` and
`GL_ARB_shader_storage_buffer_object`, so the GL compute path is compiled in rather
than merely declared. `Resources.FindObjectsOfTypeAll<ComputeShader>()` returns
nothing at the title screen — the water's shaders arrive with a level.

There is no Unity `Terrain` in a Besiege level, either: `Terrain.activeTerrains` is
empty and not one `TerrainCollider` appears in any scene measured. The ground is
mesh geometry, so there is no `TerrainData` heightmap to sample and "how high is
the ground here" has to be rendered rather than queried — which is precisely why
Surface Waves carries a `TerrainHeightRenderer`. What a level does carry is mostly
boxes, spheres and capsules: 212 colliders in level 30 (131 box, 41 sphere, 37
concave mesh), 427 in level 45 (364 box, 34 sphere, 16 capsule, 12 concave mesh).
Analytic shapes cover the movable world; the concave meshes are scenery and belong
in a baked height texture.

The blocks themselves are the same story, and more strongly. Counted over every
prefab in `PrefabMaster.BlockPrefabs`: **104 blocks, 342 box colliders, 138 sphere,
67 capsule, 5 convex mesh, 1 concave mesh, no `WheelCollider` at all**, with a worst
case of 32 colliders on one block (`FuelBarrelBig`). A mod that needs the machine's
geometry in a shader can therefore send analytic primitives and never touch a
triangle — but it should size the list by collider rather than by block.

The gate is not the runtime, it is **authoring**. There is no runtime shader
compiler, so a `.compute` (and equally an SM3 `.shader`) has to be built into an
asset bundle by a Unity **5.4.0f3** editor.

**There is a native Linux editor for 5.4.0f3, and it is still served.** This is
easy to conclude wrongly, because the modern URL pattern
(`download_unity/<hash>/LinuxEditorInstaller/Unity.tar.xz`) answers 404 for that
hash — that layout postdates 2016. The experimental Linux editors of the 5.x era
live somewhere else entirely, under a flat `linux/` path with a build date in the
filename, and they answer 200 today:

```
download.unity3d.com/download_unity/linux/unity-editor-5.4.0f3+20160727_amd64.deb        (1.28 GB)
download.unity3d.com/download_unity/linux/unity-editor-installer-5.4.0f3+20160727.sh     (1.16 GB)
download.unity3d.com/download_unity/linux/unity-editor-installer-5.4.0p1+20160810.sh
download.unity3d.com/download_unity/linux/unity-editor-installer-5.3.5f1+20160525.sh
```

Guess the date suffix wrong and you get a 404 that looks like the build does not
exist: `5.4.0f3+20160720` is a 404 and `5.4.0f3+20160727` is the file. Probe, do
not conclude.

The Windows and Mac editors are also still served, under the modern hash layout,
along with Linux *build target* support:

```
download_unity/a6d8d714de6f/Windows64EditorInstaller/UnitySetup64-5.4.0f3.exe          (392 MB)
download_unity/a6d8d714de6f/MacEditorInstaller/Unity-5.4.0f3.pkg
download_unity/a6d8d714de6f/TargetSupportInstaller/UnitySetup-Linux-Support-for-Editor-5.4.0f3.exe
```

Prefer the native Linux editor on Linux: it removes Wine, and its bundles are
built for the graphics API the player actually runs. The `.deb` does not install on
Debian 13, though: it depends on `gconf-service`, `libgconf-2-4` and `libpng12-0`,
all gone, `lib32gcc1`, renamed, and `npm`. Unpack it with `dpkg-deb -x` and supply
the libraries, or use the Wine route.

**And a 5.4 editor will not build anything until it is activated.** Batch mode
stops at

```
BatchMode: Unity has not been activated with a valid License.
Failed to activate/update license. Missing or bad username and password.
```

so `-batchmode -quit -nographics -executeMethod` is not by itself enough, and
neither is `-createManualActivationFile`, which in 5.4 still tries the network
first and fails with the same message whether or not `-quit` and `-nographics` are
there. The editor's own activation window is no help under Wine: it is a Chromium
view and renders solid black, and the editor log shows its login web packages
(`unity-editor-home`, `unityeditor-cloud-hub`) missing from the install.

Command-line activation with a Unity account does reach the licence server — and
then dies somewhere Unity no longer runs:

```
LICENSE SYSTEM Received https://license.unity3d.com/update/poll?cmd=9&tx_id=...
    HTTP/1.1 200 OK
Could not resolve host: collab.cloud.unity3d.com while processing request
  "https://collab.cloud.unity3d.com/api/whitelist/collab/<org id>", HTTP error code 0
Canceling DisplayDialog: Updating license failed Failed to update license within 60 seconds.
```

`collab.cloud.unity3d.com` is **NXDOMAIN** — Unity Collab was retired and the host
is gone, while 5.4's activation still asks it whether the account's organisation is
whitelisted. The failing URL carries an organisation id, so an account with no
organisation may well skip the call; that is the first thing to try, ahead of
anything cleverer.

A licence cannot be carried to the build machine, either. A `.ulf` records the
machine it was issued for, and the editor checks and then **deletes** it:

```
LICENSE SYSTEM 12345-oem-0000001-54321 != 00330-50000-00000-AAOEM
LICENSE SYSTEM U2VyaWFsIG51bWJlcg== != MA==
BatchMode: Unity has not been activated with a valid License.
```

Key 1 is the Windows `ProductId`, key 4 the SMBIOS system serial, and a Wine prefix
reports Wine's defaults (`12345-oem-0000001-54321`, base64 `"Serial number"`) unless
something has changed them — which an installer running in that prefix will, because
Wine reapplies registry defaults when it updates a prefix. So a licence that worked
yesterday can stop working because an unrelated installer touched the prefix. The
file is renamed to `Unity_v5.x.ulf.archive` the first time and simply removed on
later runs, so the failure looks different each time.

The bindings are also the fastest way to tell where a licence came from: the `.ulf`
is plain XML, and `StartDate`, `SerialMasked` and the three `Binding` values are
readable with `head -c 400`. If key 1 is not the prefix's own `ProductId`, the
licence was minted elsewhere and no amount of retrying will help — activate on the
machine that will do the building, or do the building on the machine that holds the
licence.

Two things follow. **Budget for the licence, not just the download** — it is the
real cost of shipping any shader from a mod, and it is not mentioned anywhere near
the asset-bundle advice. And note that it blocks *both* GPU routes equally: the
SM3 fragment-shader fallback needs a compiled shader exactly as the compute path
does, so it is no way around an editor that will not start.

Hand-building a bundle to avoid the editor is not the shortcut it sounds like
either: the game ships **no** compute shader assets to copy the format from —
searching every `.assets` and `level*` file for `local_size_x` finds nothing — so
Besiege's own water runs the SM3 path and there is no template in the install.

[18-vendoring-unity-code.md](18-vendoring-unity-code.md) records that the Linux
player wants the **Mac** bundle, which works because both are OpenGL — true, and an
accident. It need not be one: a native Linux editor exists for this exact version,
and Linux *build target* support exists for the Windows and Mac editors too, so a
bundle can be built for `StandaloneLinux64` on purpose and carry GL variants by
intent. Prefer that, and keep the Windows (D3D11) bundle beside it.

## `BuoyancyManager` is the template for coupling a mod simulation to PhysX

`CodeAnimo.SurfaceWaves.BuoyancyManager` is what a two-way coupling looks like when
one side is a texture on the GPU and the other is a `Rigidbody`:

- a `Buoy` component carries a radius and a `SphereCollider` set as a trigger, and
  registers itself with the manager on `OnTriggerEnter` / unregisters on exit;
- the manager's `FixedUpdate` gathers `getPositionData` and `getVelocityData` into
  `Vector4[]`, hands them to a `ComputeKernel1D`, and reads results back;
- `computeForces` then `applyBuoyForces` applies one force per body.

Shape to copy: **sample points, not geometry, cross the boundary.** Upload a small
array of positions, read back a small array of forces, apply them with
`AddForceAtPosition`. The per-step `GetData` readback is a pipeline stall and it is
what the game itself already pays; keep the buffer that crosses back proportional to
the number of *bodies*, never the number of particles.

### Ground you deform, under a collider PhysX cooks

A mod simulation that machines stand on (sand, snow, soft terrain as a height field) usually gets a
`MeshCollider` cooked from its heights, and then **the body rests on the collider, not on the data**.
Cooking costs, so it lags the data — recooked a few chunks a step, and only past a tolerance, because a
recooked collider drops the contacts PhysX was holding (static friction among them: a parked machine
slides as if on ice). So anything the mod does to the heights under a body is invisible to the body for
a step or several. Two consequences that cost something to find:

- **Take thin layers, not columns.** A spinning wheel that dug its whole column 14 cm down at once then
  hung over the hole, out of the mod's "touching" distance, until the collider caught up: one bite, a
  pause, another bite, and no stream of sand. Removing a layer a few centimetres thick each step keeps
  the body in touch while the collider follows.
- **Test with the lag in.** A headless test that put the wheel straight back on the data every step
  showed a fine roost; with the wheel on the highest point under its footprint and the heights it
  stood on three steps old, what it threw dropped by three quarters. Model the collider, not the data.
- **Count "under the body" from the contacts, not the heights.** What the collider reported a load on in
  the last few physics steps is what the body stands on, wherever the data now puts the surface; a body
  within a hand's breadth over such a cell is touching it. That one rule turned a wheel that stopped
  digging the moment the sand went down into one that dug and threw continuously.
- **Slippery ground is a `PhysicMaterial` with `frictionCombine = Minimum`.** Unity picks the combine
  mode of the pair by priority, Average < Minimum < Multiply < Maximum, so a ground material on Average is
  averaged with the block's own friction (a mud collider at 0.2 under a grippy tyre came out at most of
  tarmac's), and one on Minimum gives its own low value — unless the block's material is Multiply or
  Maximum, which outranks it. Log what the touching blocks use (`Collision.collider.sharedMaterial`) rather
  than assume.

The force PhysX pushes back with (`Collision.impulse` over `fixedDeltaTime`, normal component only —
the full impulse includes a powered wheel's drive) is what to sink the ground under, and the sink rate
must be fast: at 0.6 m/s a wheel crossing a 12 cm cell in a few hundredths of a second left a rut of a
few centimetres whatever it weighed.

## Threads are allowed, and that is where CPU headroom is

`System.Threading` is not on the blacklist — no prefix matches it — and
`System.Threading.dll` ships in `Managed`. The audio note
([07-audio.md](07-audio.md)) is the precedent: heavy arithmetic on a worker, results
handed over by a single reference assignment. Nothing that touches a Unity object may
run there, so a worker-thread simulation must own plain arrays and let the game
thread do every `transform`, every `Rigidbody`, every mesh upload.

What it is not: there is no Job System, no Burst, no `Unity.Mathematics`, no SIMD you
can rely on. The arithmetic runs on Besiege's old Mono. Budget accordingly, and
measure with `System.Diagnostics.Stopwatch`, which is one of the blacklist's exempted
type names.

Old Mono is slower than a modern runtime but not by the order of magnitude people
assume. Measured on one machine (6-core desktop, 2026): a dependent multiply-add
integration step over `float[]` arrays runs **200000 particles in 1.96 ms on one
thread**, about 9.8 ns per particle for roughly ten operations — near one operation
per nanosecond per core. Integration is therefore free and the contact solve is the
whole cost, which is the same shape as on any runtime. Take the measurement on the
target machine before sizing anything; the number above is calibration, not a
promise.

### What a thread pool does in the mod, measured

`ThreadPool.QueueUserWorkItem`, `Interlocked` and `ManualResetEvent` work in a mod (no blacklist hit),
so a loop over independent pieces — a chunk's mesh, a chunk's columns — can be shared between the
main thread and `ProcessorCount - 1` helpers while the main thread waits. Measured on a 6-core
desktop: a sand chunk's mesh at 3.1 ms for 36 chunks on one thread, 0.7 ms on six; a brush's columns added to at 0.12 µs a column on one thread and 0.05 µs on six.
Five things that cost something to learn:

- **A cache that threads share is a bug.** A "last chunk looked up" cache (chunk, x, z as three
  fields) was added to a lookup the solver's worker threads call, and one height in six came back
  from the wrong chunk: the three fields were written by different threads and read torn. Nothing
  threw; sand stopped being thrown up and the game stuttered. Per-thread (`[ThreadStatic]`, keyed
  by the owner and a generation) is correct. Test any shared lookup by reading from six threads and
  comparing with one.
- **A `[ThreadStatic]` read is dear on this Mono — read one, not five.** The per-thread cache above
  was five thread-static fields (chunk, owner, x, z, generation), each read on every lookup, and that
  cost more than the dictionary lookup it was saving: a loop of 60,000 lookups a frame spent 720 ms
  over a four-second test going through it and 110 ms without. Put the fields in one small class and
  keep a single `[ThreadStatic]` reference to it (created on first use per thread); in a hot loop on
  one thread, look the chunk up once per row segment yourself and do not go through the cache at all.
- **Even one `[ThreadStatic]` read is too dear in the main thread's hottest loops — so skip it when no other
  thread is running.** If all your threading is fork-join from the main thread (dispatch, help, wait for the
  last item), then outside those sections only the main thread touches the data, and a plain instance field
  serves as its cache. Count the sections (`Interlocked.Increment` before dispatching, `Decrement` after the
  wait, in a `finally`) and pick the cache by that count: `Running > 0 ? perThread() : mainCache`. A sand
  model's slump check (about forty chunk lookups a column) dropped from 53 to 32 ms a second of driving. Any
  thread of your own that reads the data outside such a section must count itself too, or it shares the
  main thread's cache and reads torn entries.
- **Wait for the items, on an event — not for the helpers, and not on a monitor.** Two stalls of a
  tenth of a second, both from the obvious pattern (queue N helpers, run items on the caller too,
  `lock` + `Monitor.Wait` until a counter of finished helpers reaches zero, the last helper
  `lock` + `PulseAll`):
  the caller waited for every helper to *start*, though it had often done every item alone before
  the pool woke one; and, with that fixed, the helper finishing the last item now and then sat
  100 ms (to the millisecond, every time) taking the lock to pulse while the caller was in `Wait`.
  Two or three 100 ms frames in four seconds of a 60 fps loop. What works: per-call state in a small
  object the queued delegate captures (a helper that starts late finds the items gone and leaves,
  never touching the next call); an `Interlocked` counter of finished *items*; the thread that
  finishes the last one — the caller included — `Set`s a static `ManualResetEvent` that the caller
  `Reset` before queueing and always `WaitOne`s on, so a `Set` can never belong to an earlier call.
- **Split the work so no two threads write the same bytes**, and read across the split only what a
  stale value cannot hurt. A chunk's columns are added to on one thread each; the heights read from
  the neighbouring chunk may be a step old, which a stability check with a tolerance absorbs.
- **Mono's own teardown crashes under a parked pool thread.** An offline host that calls
  `mono_jit_cleanup` after the program has finished segfaulted when the program had used the pool.
  Skip the cleanup in the host (`_exit` after flushing); the game never calls it.

## No native code, so no physics library

Restating [01-loader-and-blacklist.md](01-loader-and-blacklist.md) where it bites
hardest: `[DllImport]` is refused by its own check in `AssemblyScanner`, and
`System.Diagnostics` being blacklisted removes `Process.Start` as well. FleX, Bullet,
PhysX extensions, anything with a `.so` or a `.dll` behind it — not reachable by any
route. A solver a mod wants is a solver a mod writes, in C# 4 or in a shader.

## A wheel's dust cloud is reachable

Besiege's wheels carry `WheelSmoke` (on the block's own GameObject), whose private
`ParticleSystem` field is a child of the block from the prefab. `FixedUpdate` moves it
to the wheel's ground contact and emits from it by hand — `Emit(EmitParams, n)`, with
`n` from `emission.rate.constant × fixedDeltaTime`, and `EmitParams` setting position
and velocity only, so colour, size and lifetime come from the system.

So the cloud is a `ParticleSystem` somewhere under the block — not necessarily on the
`WheelSmoke`'s own object, and not the only one (a wheel carries others, its fire
among them). Find it as the one the wheel has moved away from the block's middle, down
to the ground. Its transform is where the wheel last touched, and `startColor`,
`startSize`, `startLifetime` and `emission.rate` (Unity 5.4: assign the
`EmissionModule` to a local, set `rate`) change the next puffs.

On the desert island level (4) its `Awake` tints the renderer's material `_TintColor`
brown, so a light `startColor` comes out dark; the neutral-grey tint in
[20](20-rendering-and-cameras.md) ("Recolouring a game particle system") is the fix.
It also picks its rolling sound from `PhysicMaterialGroup.Convert(collider.material)`
of what it touches — a mod ground's material decides whether it sounds like sand or
grass.

## Emitting into Unity's own particle system, and leaving the game's alone

On this Unity (5.4) a `ParticleSystem` made from code is configured on the system itself — no `main` module
yet: `simulationSpace`, `maxParticles`, `startSpeed`/`startSize`/`startLifetime`, `gravityModifier`,
`playOnAwake`, `loop`, then `emission.enabled = false` and `shape.enabled = false` for a system you only feed
by hand. Each particle then comes with its own place, speed, size, life and colour through
`Emit(ParticleSystem.EmitParams, 1)`; everything that changes it over its life is a module
(`limitVelocityOverLifetime` with `limit` and `dampen` for air, `sizeOverLifetime`, `colorOverLifetime` with a
`Gradient` for a fade). `GeometryUtility.CalculateFrustumPlanes` has only the allocating overload. The
renderer's `maxParticleSize` (a fraction of the screen, 0.5 by default) shrinks a big puff as the camera comes
near: raise it. **`Emit(EmitParams, n)` does not keep to `maxParticles`** here: a system
capped at 6,000 held over 10,000. Keep the cap yourself (read `particleCount` once a frame
and count what you emit). A few thousand soft puffs this way cost the CPU next to nothing,
where building them into a mesh in managed code every frame cost milliseconds.

**To dress a game effect in your own look without recolouring what is already in the air**, keep the game's
system emitting but make what it emits invisible and brief (`startColor` alpha 0, a short `startLifetime`) —
start values only touch particles made from then on — and read `particleCount` to know when and where it is
emitting (it lives at the effect's transform); emit your own particles there into a system of your own. A
wheel's `WheelSmoke` decides for itself when to emit (grounded, over its speed cut-off); its public
`smokeActive` is only its on/off setting.

## A dense spatial grid over every particle's bounds

A counting-sort grid (cell start indices, one int per cell) is cheap while the particles are bunched and
ruinous when a few are far away: the grid covers the bounds of all of them, and clearing, summing and
copying its cells every substep is work in the volume, not in the count. Four grains 80 m from the rest made
a sand solver's grid millions of cells and its step twenty times slower. Fall back to a sparse layout past a
few dozen cells a particle: sort the particles by cell index (`Array.Sort(keys, items)`), note where each row of
cells begins, and find a row by binary search. The same neighbour order survives, so slab-parallel solving
keeps working.

## Checked

Besiege 5.4.0f3, Linux, September 2026. The API presence and absence lists are
measured against the shipped `UnityEngine.dll`; the Surface Waves and GPGPU class
shapes are read out of `Assembly-CSharp` with `peek.sh`. The 100 Hz fixed step, the
gravity and solver settings, `supportsComputeShaders`, the `ComputeBuffer`
round-trip, the random-write `RenderTexture` and the Mono throughput number are all
measured by a probe mod reading them out into `Player.log`; the editor and target
installer URLs, including the native Linux ones, were checked with an HTTP request; the editor was installed under
Wine and its licence refusal is its own message, not a guess. The collider census
and the absence of Unity `Terrain` are measured in levels 30 and 45.

**Not yet measured:** whether a mod-supplied `ComputeShader` inside a mod asset
bundle loads and dispatches on this build — the runtime supports compute, but
nothing has yet carried a mod's own kernel across; the true cost of a
`ComputeBuffer.GetData` that follows a dispatch (an idle buffer reads back in
unmeasurably little time, which proves nothing); and whether
`Graphics.DrawProcedural` reaches the window on the Linux GL player — note 20's
`WaitForEndOfFrame` failure is reason to expect trouble from any immediate-mode
draw here, and a `MeshRenderer` whose vertex shader reads a `StructuredBuffer` is
the safer first thing to try.
