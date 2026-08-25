# Drawing over the machine

Marking blocks in the build area — highlighting, previewing, showing a diff. From
**Git View**, which draws a translucent shell over every block a save changed.

## Use the game's own placement ghosts

`PrefabMaster.GetPrefab(BlockType, out BlockPrefab)` gives a `BlockPrefab`, and
`BlockPrefab.ghost` is the translucent preview Besiege shows while you drag a block
out of the menu. Every block type has one, it is already exactly the right shape,
and it already looks like Besiege. Nothing you model will match it.

**It is not inert.** A ghost carries `GhostTrigger` — and on some blocks
`GhostPinTrigger` — the behaviours that turn the preview red inside something and
call `IntersectWarning.WarningFromWorldPos`, which is the game's INTERSECTION
banner. They work off trigger colliders, and every ghost drawn as an overlay sits
exactly on a block of the machine, so an overlay of a dozen blocks raises a dozen
intersection warnings the instant it appears.

Sterilising one:

1. `Instantiate`
2. `SetActive(false)` **before anything on it gets a frame**
3. strip every `MonoBehaviour`, `Collider` and `Rigidbody` in the hierarchy
4. `SetActive(true)`

**Disable each behaviour as well as destroying it.** `Destroy` takes effect at the
end of the frame, and one `Update` in between is one banner on screen.

The obvious alternative — tinting the real blocks' renderers — does not work:
Besiege's blocks share their materials, so tinting one girder tints every girder.

## Anything you build yourself has to be put on the machine's layer

A ghost arrives on whatever layer Besiege authored it for. A `new GameObject` or a
`GameObject.CreatePrimitive` starts on the default layer, **which the build area's
camera need not be drawing at all** — so a shape of your own can be present,
correctly placed, correctly coloured and invisible, with nothing in the log to say
why.

Take the layer off the first renderer under the machine's block root and set it on
everything you make.

## Where to parent it

Saved block coordinates are relative to whatever the machine's blocks are parented
to. The field holding that on `Machine` is not public, so take it off a block —
`machine.BuildingBlocks[0].transform.parent` — and fall back to `machine.transform`
for an empty machine.

Ghosts parented there are plain GameObjects with no `BlockBehaviour`, and saving
walks `BuildingBlocks`, so they cannot end up in a save. Note the other side of
that coin: **anything parented into the machine is destroyed with the machine**, so
whatever manages the overlay has to notice and rebuild.

## Blocks that are in two places

A dragged block's ghost is one end of it. The rest — the brace itself, the length
of hose, the rope — is strung between `start-position` and `end-position` in the
block's data (see [12-machines-and-saves.md](12-machines-and-saves.md)). They are in
the block's own local space, scale included:

```
OnSave    transform.InverseTransformPoint(startPoint.position)
OnLoad    transform.TransformPoint(data.ReadVector3("start-position"))
```

so putting one back is `Position + Rotation * Vector3.Scale(local, Scale)`.
`Machine.SpawnBlock` assigns `transform.localScale = blockInfo.Scale` directly,
which is what makes the file's `Scale` the right one to use. Checked against 1900
endpoints in six real machines: they land in tight clusters at 0.71 (a block's
corner), 0.00 (dead on a block's centre) and 1.00 from the nearest other block —
distances that would smear if the space or the scale were wrong.

Nothing in the prefab library is "the middle of a brace", so draw it with a
`GameObject.CreatePrimitive(PrimitiveType.Cylinder)`: two units tall and one across,
so the scale is `(width, length / 2, width)` and the rotation is
`Quaternion.FromToRotation(Vector3.up, end - start)`. It arrives with a collider,
which wants the same stripping a ghost does.

## `Shader.Find` only finds shaders that shipped in the player's build

Try several and have a fallback. `Particles/Alpha Blended` is known to be in
Besiege's build and is a reasonable first choice for a translucent overlay.

## Scale a shell about its own middle

An overlay shell wants to be slightly larger than the block so the block sits inside
its mark. A few per cent is enough; much past a tenth and it starts hiding the
block's neighbours. Scale about the shell's own pivot, not the block's, or a shell
grows off to one side.
