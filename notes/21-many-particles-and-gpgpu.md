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

## Graphics API census: what 5.4 has, and the four things it does not

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
built for the graphics API the player actually runs.

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

## No native code, so no physics library

Restating [01-loader-and-blacklist.md](01-loader-and-blacklist.md) where it bites
hardest: `[DllImport]` is refused by its own check in `AssemblyScanner`, and
`System.Diagnostics` being blacklisted removes `Process.Start` as well. FleX, Bullet,
PhysX extensions, anything with a `.so` or a `.dll` behind it — not reachable by any
route. A solver a mod wants is a solver a mod writes, in C# 4 or in a shader.

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
