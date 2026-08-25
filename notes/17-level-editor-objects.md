# Level editor objects

A mod can add an object to the level editor's palette as well as a block to the
block menu. `<Entity path="Thing.xml" />` under `<Entities>` in `Mod.xml`, an XML
much like a block's, and it appears under whatever `<Category>` it names — `Virtual`
sits with Wind, Triggers and the other invisible ones.

Almost none of the block machinery applies. There is no module, no
`BlockModuleBehaviour`, no mapper, and none of the per-run callbacks. What there is
instead is worth writing down, because working it out from the block API costs a
day.

## There is exactly one hook, and it fires on the prefab

`ModEntryPoint` offers `OnEntityPrefabCreation(int entityId, GameObject prefab)`
and nothing else. `entityId` is the `<ID>` in the entity's own XML.

There is no per-instance callback at all. Stock entities build themselves from a
`GenericEntity.Init` override, which a mod cannot supply. So the only way to reach
a placed object is to put a `MonoBehaviour` of your own on the prefab and let the
editor's own cloning carry it to every instance:

```csharp
public override void OnEntityPrefabCreation(int entityId, GameObject prefab)
{
    if (entityId != MyEntityId) return;
    Attach.Component<MyEntityBehaviour>(prefab);
}
```

From there it is an ordinary Unity component: `Awake`, `Start`, `Update`,
`OnDestroy`. **None of the block lifecycle applies** — no `SafeAwake`, no
`SimulateUpdateAlways`, no `OnSimulateStart`, and no simulation clone. The object
you get in `Awake` is the object the editor placed and the level saves. Compare
[08-block-lifecycle.md](08-block-lifecycle.md), which is about blocks and does not
transfer.

Anything that needs the level's own scene tree — cloning a gizmo out of
`_PERSISTENT/OBJECTS/Prefabs/...`, for instance — must wait for `Start` or later.
At prefab-creation time none of it exists.

## The SETTINGS tab takes the same controls a block's mapper does

`LevelEntity.EntityBehaviour` is a `GenericEntity`, and `GenericEntity` derives
from `SaveableDataHolder` — the same base a block's `BlockBehaviour` uses. So the
object's SETTINGS panel accepts the whole mapper vocabulary:

```csharp
LevelEntity entity = GetComponent<LevelEntity>();
GenericEntity holder = entity.EntityBehaviour;

holder.AddMenu("TypeKey", 0, items, footerMenu);
holder.AddSlider("Brightness", "BrightnessKey", 4f, 0f, 10f);
holder.AddColourSlider("Color", "ColorKey", Color.white, false);
holder.AddToggle("Lens", "LensKey", true);
holder.AddValue("Range", "RangeKey", 10f);
```

They are saved, loaded and displayed exactly as a block's are, including
`MapperType.DisplayInMapper` for showing one page at a time.

### Add them in `Awake`, not `Start`

`LevelXMLLoader.CreateEntity` instantiates the entity and calls `LoadEntityData` in
the same breath, while Unity does not run `Start` until the end of the frame. A
control added in `Start` is not there for the saved value to land in, and every
setting silently resets to its default the moment a level is loaded. It looks like
a save bug and it is a timing bug.

`entity.EntityBehaviour` can still be null in `Awake` on some paths, so the robust
shape is to try in both and guard with a flag:

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
before it fires `InvokeDisplayStateChanged`. So an entity that drives its panel
from a per-frame `Update` — which is the natural shape when settings can also come
from level variables — can just assign visibility every frame and skip the change
subscriptions a block needs.

## Level variables are the way a level drives one object

Besiege's own **Modify Variable** event has a *scope of change* picker that names a
single entity, so a trigger anywhere in the level can reach one placed object and
leave the rest alone. That is a better answer than a modded event, which cannot be
aimed anywhere except its own logic chain.

```csharp
float value;
if (holder.GetVariableValue("brightness", out value)) ...
```

Three things constrain the design, and all three are worth knowing before you
choose variable names:

- **Variables are floats.** `Dictionary<string, float>` all the way down. There are
  no string variables, which is why a colour has to be three of them.
- **Nothing can delete a variable once set.** `SetVariable(key, VarModifyType, float)`
  offers `Add`, `Subtract` and `Set`, and no remove. So a level that takes a setting
  over can never hand it back — unless you reserve a value for "no opinion".
  Negative works well for anything whose real range is non-negative:

  ```csharp
  private bool Variable(string key, ref float value)
  {
      float set;
      if (!holder.GetVariableValue(key, out set) || set < 0f) return false;
      value = set;
      return true;
  }
  ```

  Then a variable overrides its slider while it is `>= 0` and gives it back the
  moment the level sets it negative. Document that, because nobody guesses it.
- **`Add` and `Subtract` mean a level can ramp one.** Repeated events make a fade
  without any per-frame support from the mod.

## A modded event gets a much poorer set of controls

If you were going to add a `<Trigger>` of your own instead: a modded event's
properties are limited to `Choice`, `Icon`, `NumberInput`, `Picker`, `Row`,
`TeamButton`, `Text`, `TextInput` and `Toggle`. **There is no slider and no colour
picker**, so a brightness becomes a typed number and a colour a typed hex string,
in a game whose own events have sliders throughout.

Combined with the aiming problem above, a modded event is usually the wrong tool:
put the settings on the SETTINGS tab, where they get real sliders, and let
**Modify Variable** drive them.

## Entity XML notes

- `<ID>` is per-mod and independent of block IDs. It is what
  `OnEntityPrefabCreation` is handed, and changing it breaks saved levels exactly
  as a block's does.
- `<Fallback>` names the stock object someone without the mod sees in your level.
- An entity must name a `<Mesh>`. If the object is drawn some other way — a
  billboard, a light with no body — point it at any mesh and scale it to
  `0.0001`, which is what the stock invisible objects do.
- `<CanPick>` and `<ShowPhysicsToggle>` are entity-only elements with no block
  equivalent.
- `<Colliders>` is what the editor click-tests against. An object with no visible
  body still needs one or it cannot be selected.

## Checked

Besiege 5.4.0f3, August 2026, with `./tools/peek.sh check`:
`LevelEntity`, `LevelEntity::EntityBehaviour`, `LevelEntity::IsSelected`,
`GenericEntity`, `GenericEntity::GetVariableValue`, `GenericEntity::SetVariable`,
`SaveableDataHolder::AddSlider` / `AddColourSlider` / `AddMenu` / `AddToggle` /
`AddValue`, `Modding.ModEntryPoint::OnEntityPrefabCreation`,
`MapperType::DisplayInMapper`.
