# Level editor objects

A mod can add an object to the level editor's palette as well as a block to the block
menu. `<Entity path="Thing.xml" />` under `<Entities>` in `Mod.xml`, an XML much like a
block's, and it appears under whatever `<Category>` it names — `Virtual` sits with Wind,
Triggers and the other invisible ones.

Almost none of the block machinery applies. No module, no `BlockModuleBehaviour`, no
mapper, none of the per-run callbacks. What there is instead is worth writing down,
because working it out from the block API costs a day.

## There is exactly one hook, and it fires on the prefab

`ModEntryPoint` offers `OnEntityPrefabCreation(int entityId, GameObject prefab)` and
nothing else. `entityId` is the `<ID>` in the entity's own XML.

No per-instance callback at all. Stock entities build themselves from a
`GenericEntity.Init` override, which a mod cannot supply. So the only way to reach a
placed object is to put your own `MonoBehaviour` on the prefab and let the editor's own
cloning carry it to every instance:

```csharp
public override void OnEntityPrefabCreation(int entityId, GameObject prefab)
{
    if (entityId != MyEntityId) return;
    Attach.Component<MyEntityBehaviour>(prefab);
}
```

### The hook reaches only the mod that owns the entity

`OnEntityPrefabCreation` is **not** broadcast. `EntityLoader.CreatePrefab` calls
`entity.Info.Mod.OnEntityPrefabCreation(localId, prefab)` — the owning `ModContainer` —
and `ModContainer.OnEntityPrefabCreation` runs it only on that mod's own
`ModEntryPoint`s. Entity ids are checked for duplicates **within one mod**
(`EntityLoader.LoadMod`: "Multiple entities with the same ID"), and `ModIds` numbers them
globally from `(mod guid, local id)`, like blocks. So two mods numbering an entity `1` do
not collide, and a bare integer filter such as `if (entityId != MyEntityId) return;` is
enough.

**This section used to say the opposite.** It claimed the hook fires on every loaded
mod's entry point and that a sand region with `<ID>1</ID>` picked up another mod's
spotlight beam and lens because of it, and advised never numbering entities from 1.
Wrong: nothing in the loader delivers one mod's entity to another. The claim was an
explanation fitted to a real symptom — another mod's settings turning up on the
mod's objects — whose actual cause was the stale `BlockPrefab.ID` described under
`<LoadInTitleScreen />` in [01-loader-and-blacklist.md](01-loader-and-blacklist.md). It
was not shown to apply to the entity case; if an entity of yours ever wears another
mod's components, do not assume id collision — log what is on the prefab first:

```csharp
Debug.Log("[Mod] entity prefab " + entityId + " '" + prefab.name + "'");
```

and note which `OnEntityPrefabCreation` callers exist in the mods involved. Changing an
entity id after a level has been saved with it still breaks that level, as for a block.

From there it's an ordinary Unity component: `Awake`, `Start`, `Update`, `OnDestroy`.
**None of the block lifecycle applies** — no `SafeAwake`, no `SimulateUpdateAlways`, no
`OnSimulateStart`, no simulation clone. The object you get in `Awake` is the object the
editor placed and the level saves. Compare
[08-block-lifecycle.md](08-block-lifecycle.md), which is about blocks and doesn't
transfer.

Anything needing the level's own scene tree — cloning a gizmo out of
`_PERSISTENT/OBJECTS/Prefabs/...`, for instance — must wait for `Start` or later. At
prefab-creation time none of it exists.

## The SETTINGS tab takes the same controls a block's mapper does

`LevelEntity.EntityBehaviour` is a `GenericEntity`, and `GenericEntity` derives from
`SaveableDataHolder` — the same base a block's `BlockBehaviour` uses. So the object's
SETTINGS panel accepts the whole mapper vocabulary:

```csharp
LevelEntity entity = GetComponent<LevelEntity>();
GenericEntity holder = entity.EntityBehaviour;

holder.AddMenu("TypeKey", 0, items, footerMenu);
holder.AddSlider("Brightness", "BrightnessKey", 4f, 0f, 10f);
holder.AddColourSlider("Color", "ColorKey", Color.white, false);
holder.AddToggle("Lens", "LensKey", true);
holder.AddValue("Range", "RangeKey", 10f);
```

Saved, loaded and displayed exactly as a block's are, including
`MapperType.DisplayInMapper` for showing one page at a time.

### Add them in `Awake`, not `Start`

`LevelXMLLoader.CreateEntity` instantiates the entity and calls `LoadEntityData` in the
same breath, while Unity doesn't run `Start` until end of frame. A control added in
`Start` isn't there for the saved value to land in, and every setting silently resets to
its default the moment a level is loaded. Looks like a save bug; it's a timing bug.

`entity.EntityBehaviour` can still be null in `Awake` on some paths, so the robust shape
is to try in both and guard with a flag:

```csharp
private void Awake() { AddControls(); }
private void Start() { AddControls(); }   // in case EntityBehaviour was not up yet

private void AddControls()
{
    if (built) return;
    LevelEntity entity = GetComponent<LevelEntity>();
    if (entity == null || entity.EntityBehaviour == null) return;
    holder = entity.EntityBehaviour;
    built = true;
    ...
}
```

### `DisplayInMapper` is free to set every frame

`MapperType.set_DisplayInMapper` opens with `if (_displayInMapper == value) return;`
before firing `InvokeDisplayStateChanged`. So an entity driving its panel from a
per-frame `Update` — natural when settings can also come from level variables — can just
assign visibility every frame and skip the change subscriptions a block needs.

## Level variables are the way a level drives one object

Besiege's own **Modify Variable** event has a *scope of change* picker naming a single
entity, so a trigger anywhere in the level can reach one placed object and leave the
rest alone. Better than a modded event, which cannot be aimed anywhere except its own
logic chain.

```csharp
float value;
if (holder.GetVariableValue("brightness", out value)) ...
```

Three things constrain the design, all worth knowing before choosing variable names:

- **Variables are floats.** `Dictionary<string, float>` all the way down. No string
  variables, which is why a colour has to be three of them.
- **Nothing can delete a variable once set.** `SetVariable(key, VarModifyType, float)`
  offers `Add`, `Subtract` and `Set`, no remove. So a level that takes a setting over can
  never hand it back — unless you reserve a value for "no opinion". Negative works well
  for anything whose real range is non-negative:

  ```csharp
  private bool Variable(string key, ref float value)
  {
      float set;
      if (!holder.GetVariableValue(key, out set) || set < 0f) return false;
      value = set;
      return true;
  }
  ```

  Then a variable overrides its slider while `>= 0` and gives it back the moment the
  level sets it negative. Document that, because nobody guesses it.
- **`Add` and `Subtract` mean a level can ramp one.** Repeated events make a fade with no
  per-frame support from the mod.

## A modded event gets a much poorer set of controls

If you were going to add your own `<Trigger>` instead: a modded event's properties are
limited to `Choice`, `Icon`, `NumberInput`, `Picker`, `Row`, `TeamButton`, `Text`,
`TextInput`, `Toggle`. **No slider and no colour picker**, so a brightness becomes a
typed number and a colour a typed hex string, in a game whose own events have sliders
throughout.

With the aiming problem above, a modded event is usually the wrong tool: put the settings
on the SETTINGS tab, where they get real sliders, and let **Modify Variable** drive them.

## Entity XML notes

- `<ID>` is per-mod and independent of block IDs. It's what `OnEntityPrefabCreation` is
  handed, and changing it breaks saved levels exactly as a block's does.
- `<Fallback>` names the stock object someone without the mod sees in your level.
- An entity must name a `<Mesh>`. If the object is drawn some other way — a billboard, a
  light with no body — point it at any mesh and scale it to `0.0001`, what the stock
  invisible objects do.
- `<CanPick>` and `<ShowPhysicsToggle>` are entity-only elements with no block
  equivalent.
- `<Colliders>` is what the editor click-tests against. An object with no visible body
  still needs one or it can't be selected.
- **`<Offset>` is used once, at placement** (`LevelEditor.LateUpdate`: the ghost goes to the
  hit point plus the offset times the ghost's scale). The scale tool works about the object's
  origin, so a mesh centred on its origin and lifted by `<Offset>` sinks half into the ground
  on the first resize, and a save keeps it there. Put the origin where the object should stand
  (raise the mesh and collider in the XML) instead.
- **The editor's pick ray hits triggers**: `RaycastAll(..., QueryTriggerInteraction.Collide)`.
  An entity's collider can be `trigger="true"` and still be clicked — useful for a marker
  object the level's own raycasts and physics should look through.

## An entity's `<Mesh><Rotation>` does not turn the way a block's does

The editor's frame for an entity's mesh is not the object's. A mesh authored in block convention (Z-up, the
business end at +Z) pointed right with no rotation, along the object's forward turned `x -90`, and sideways
turned `x -180` — which together say mesh Y lies along world Z, mesh Z along world X and mesh X along world Y.
So to stand that mesh up, turn it a quarter about **Y** (`<Rotation x="0" y="90" z="0">`), which takes +Z onto
the X that is world up. (If "right" was in fact the other side it is `y="-90"`; the first in-game look says
which.) Fix it in the XML: measuring the mesh's axis at runtime and turning a child works, but it is work done
in game for something a fixed number decides.

## The SETTINGS tab is Besiege's block mapper, so a docked panel serves it too

The level editor opens the same `BlockMapper` on a selected object (`LevelEditor.OpenBlockMapper` ->
`BlockMapper.Open(SaveableDataHolder)`). `BlockMapper.Current` is then the object's `GenericEntity`:
`.Block` (`Current as BlockBehaviour`) is null and `.Entity` (`Current as GenericEntity`) is not. A docked
panel ([05-docking-a-window.md](05-docking-a-window.md)) that gates on `mapper.Block != null` never shows for
an entity; gate on `mapper.Current` and let the panel's own test pick block or entity. The entity's mapper has
a header with a LOGIC page beside SETTINGS (`BlockMapper.IsLogic`, the static `logicToggle`, always false for a
block); turning to it neither closes nor reopens the mapper, so a panel must stand aside while `IsLogic` and
poll to come back — no event says SETTINGS is showing again. Edits go through
`BlockMapper.OnEditField(mapper.Current, control)` as for a block.

## Checked

Besiege 5.4.0f3, August 2026, with `./tools/peek.sh check`: `LevelEntity`,
`LevelEntity::EntityBehaviour`, `LevelEntity::IsSelected`, `GenericEntity`,
`GenericEntity::GetVariableValue`, `GenericEntity::SetVariable`,
`SaveableDataHolder::AddSlider` / `AddColourSlider` / `AddMenu` / `AddToggle` /
`AddValue`, `Modding.ModEntryPoint::OnEntityPrefabCreation`,
`MapperType::DisplayInMapper`.
