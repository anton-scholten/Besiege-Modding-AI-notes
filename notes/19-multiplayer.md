# Multiplayer: chat, other players, and their machines

All found writing a mod that reads multiplayer chat aloud from the speaking player's
machine. Multiplayer is otherwise not covered in these notes, and almost none of it is
reachable the way you'd first try.

## Reading chat: the only hook is a log line

`ChatController.HandleSayMessage(PlayerData, string)` is the single point every received
message passes through — the team path and the global path in `HandleSayCommand` both
converge on it, and the host's own messages echo through it too. The right hook, and it
cannot be called, patched or subscribed to:

- it's **private**;
- `Modding.Events` has no chat event (it has `OnPlayerJoin`, `OnPlayerLeave` and ~20
  others, nothing for chat);
- **`System.Reflection` is blacklisted**, so Harmony and every other patching library is
  unavailable — worth stating plainly, because "just use Harmony" is the reflex and it's
  not an option in this loader.

What it does do is open with an unconditional

```csharp
Debug.Log("[ChatController] HandleSayMessage source=" + source.name + " " + message);
```

and `Application.logMessageReceived` delivers that for free, no patching. Currently the
only way for a mod to observe chat.

Three things to get right:

**The separator is a single space, and player names contain spaces.** Splitting on the
first space is wrong for a great many Steam names. Match the names in
`Playerlist.Players` against the front of the string, longest first — exact, and also
hands back the `PlayerData` you'll need for anything else.

**The callback sees your own logging.** Anything your mod writes with `Debug.Log` comes
back through the same handler, so a parser too loose will read its own output.

**Unity may deliver it off the main thread.** Do no Unity work in the handler; queue the
parsed message and drain it in `Update`.

The obvious alternative is worse, but worth knowing so it can be rejected knowingly: the
display path is `ICanvasInputView.AddTextEntry(string)` on `CanvasInputView`, whose
message list (`FixedSizedQueue textEntries`) is private, so it would mean polling the
instantiated row `GameObject`s in the scroll view. That sees the *formatted* string, with
rich-text markup and no `PlayerData`.

Be honest about what the log hook is: a private diagnostic string, not an API. It can
change in any update. Give the mod a way to say whether it has ever parsed a message, so
the failure reads as "the format changed" rather than as silence.

## The chat window is uGUI, and a mod can dock to it

Unlike the block mapper (note 04), the chat window is ordinary uGUI, so a mod can hang
its own controls off it.

**Its parts are private serialised fields** — wired in the Unity editor, not looked up by
name at runtime — so with reflection blacklisted none can be read. The way in is the
hierarchy, whose names are in the multiplayer scene:

```sh
strings -t d -n 3 Besiege_Data/level14 | grep -i chat
```

```
ChatViewContainer
  Scroll View / Viewport / Content    (t_TextEntry is the message row template)
  InputBar / InputParent / InputField, ChatMode, InviteFriend, Close
```

`ChatView` sits on an always-active object — its `LateUpdate` has to run — so
`FindObjectOfType<ChatView>()` finds it, and `ChatViewContainer` is a
`GetComponentsInChildren<RectTransform>(true)` away. **Pass `true`:** the container is
inactive whenever the chat is closed, which is most of the time and certainly the moment
a mod first goes looking.

**Parenting to the container gets show-and-hide for free.** `CanvasInputView.IsVisible`
is literally `viewContainer.activeSelf`, so the container is the object Besiege toggles as
the chat opens. A child of it follows with no visibility code and nothing to keep in sync.

**The look can be sampled rather than reproduced.** Note 04 says Besiege's own interface
cannot be borrowed, and that's true of the *mapper* — mesh UI whose materials need
`InternalModding`. The chat window is uGUI and on screen, so
`GetComponentsInChildren<Text>(true)` yields a real `Font` and
`GetComponentsInChildren<Image>(true)` a real background colour. The font is the part
that matters: a `Text` with no font draws nothing at all, reading as a panel that failed
to paint rather than one that failed to find a typeface.

**Anything placed outside the container's rect can be clipped.** A button docked to the
*left* of the chat window is outside it, so a `Mask` or `RectMask2D` anywhere up the
parent chain crops it away with no error and no symptom. Nothing in the chat hierarchy is
expected to clip, but walk up to the `Canvas` and log the culprit if one appears — this is
the failure here that looks exactly like a mod that didn't load.

## Finding another player's machine, and its core block

`PlayerData.machine` is a `ServerMachine`, extending `Machine`. Everything needed is
public:

```csharp
List<BlockBehaviour> blocks = machine.isSimulating
    ? machine.SimulationBlocks       // the clone's blocks
    : machine.BuildingBlocks;
// the starting block is BlockID == 0
```

`(int)BlockType.StartingBlock == 0`, established by a probe compile rather than assumed
from its position in the enum.

`Machine.FirstBlock` is a reasonable fallback and handles the simulating/building switch
itself, but it's literally "element 0 of the current list" — the starting block for a
machine built the usual way, and not guaranteed to be. Scanning for the id is exact.

**Re-resolve it every frame.** A simulation runs on a clone rebuilt from scratch each run
(note 08), so a `Transform` cached while building is destroyed the instant that player
starts a simulation. This is the multiplayer instance of the trap note 08 describes for a
block's own behaviours, and it bites harder here: the object you cached belongs to someone
else, and they can start and stop a simulation whenever they like.

`GameObject.Find("StartingBlock")` — which `SmoothLookAtMachine` uses — is no use in
multiplayer: it finds one object globally, and there are as many starting blocks as there
are players.

## Players

`Playerlist.Players` is a `List<PlayerData>`, public and static.
`PlayerData.localPlayer` is you, and `isLocalPlayer` says so per entry. Fields worth
knowing: `name`, `networkId`, `team` (`MPTeam`), `machine`, `isSpectator`.

`Modding.Common.Player` is the sanctioned wrapper over the same thing — `Name`,
`NetworkId`, `SteamId`, `IsHost`, `Team`, `Machine` (a `Modding.Blocks.PlayerMachine`) and
`InternalObject` to get back to the `PlayerData`. `Modding.Events.OnPlayerJoin` and
`OnPlayerLeave` hand you one.

**Key per-player settings by name, not by `networkId`.** A network id is meaningful for
one session only, so anything a player is meant to keep — a mute, a colour, a preference
— is wrong the next time they join if keyed by id.

**Poll rather than relying on the join and leave events** if what you need is "who is here
now". Half a second of latency is imperceptible, and polling also covers the cases the two
events don't name: a player changing their name, and your own panel being opened when the
lobby already has people in it.

## `StatMaster` says which side you are on

`StatMaster.isMP`, `isHosting` and `isClient` are public statics, and are how most of the
game's own code branches. A mod that must behave differently as host and client reads them
rather than inferring from the player list.
