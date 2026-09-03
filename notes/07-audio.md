# Audio: synthesising it, and placing it in the world

All found writing a block that generates every sample as the machine runs. A block
that only plays a clip needs none of it — set the `AudioSource` up as 3D and stop
reading.

## `OnAudioFilterRead` runs *after* the source's 3D stage

The one that costs a day. Unity's docs say the callback is inserted into the source's
DSP chain; what they don't say is the chain point is **downstream of the panner and
the distance rolloff**.

So a filter that *overwrites* the buffer — which is what generating audio means —
throws away everything the 3D stage did. Symptom: a block heard at one volume, dead
centre, from anywhere on the map, with `spatialBlend = 1` set and looking correct.

Three ways out, one good:

| Approach | Placed? | Latency |
| --- | --- | --- |
| `OnAudioFilterRead` overwriting the buffer | **no** | lowest |
| A streaming `AudioClip` with a PCM reader callback | yes | **bad** |
| `OnAudioFilterRead` + your own pan and distance gain | yes | lowest |

Middle row is the trap, because it looks like the clean fix and it works: feed samples
in through the clip instead of a filter and they arrive *before* the 3D stage, so Unity
pans them properly. But a streamed clip is read **well ahead** of being heard. The gate
opens into audio already generated with the gate shut, and the note arrives late —
plainly late, not subtly. **Do not go back to it.**

### There is a fourth row when the audio is known in advance

The table is about a block synthesising as it plays, which can't know its next sample
until the frame arrives. When the whole sound is decided the moment it starts — a
spoken line, a fixed phrase, anything triggered rather than played — **render all of it
up front** and the latency question disappears:

- synthesise into a `float[]` on a worker thread. Nothing in the generator needs Unity,
  so it can be pure managed code, tested offline; a few tens of ms of work is a visible
  hitch on the game thread and nothing at all on another;
- hand the finished array to the audio thread with a single `volatile` reference
  assignment. Reference writes are atomic, so a one-slot handoff — game thread writes
  only when the slot is null, callback takes it and clears it — needs no lock on the
  callback;
- `OnAudioFilterRead` then only copies and scales, and still does its own pan and
  distance gain, because the 2D-source requirement below is unchanged.

None of the streaming route's latency, none of the live route's per-sample cost, and
the generator stops being audio-thread code at all.

So: leave the source **2D** (`spatialBlend = 0`, which also stops Unity
distance-culling it) and do the placement yourself. A distance gain and stereo pan
worked out on the game thread, applied in the filter:

- compute the gain in `Update` from the block's position against the `AudioListener`'s,
  and hand it to the callback through `volatile` floats. A transform must never be read
  from the audio thread;
- **slide onto the new gain across the buffer** rather than applying it at the start.
  The value is a frame old and moves in steps; without the slide a turning camera is
  audible as a staircase;
- `min(1, 1 ∓ pan)` per ear keeps a block dead ahead exactly as loud as before any of
  this, and never exceeds 1, so nothing clips;
- **re-find the `AudioListener` whenever it isn't `isActiveAndEnabled`.** Besiege swaps
  cameras between building and running and the listener goes with them, so a cached one
  goes stale rather than null.

## The source must be playing at all

Unity doesn't run the filter chain on a source that isn't playing, so a procedural
block needs a clip and a `Play()` even though the clip is never heard. One sample of
silence, looped, is enough, and can be one static shared by every block.

## The audio thread

`OnAudioFilterRead` is not the game thread. Nothing in it may touch a mapper value, a
transform, or any other Unity object. Hand settings across in plain `volatile` fields
of primitive type and accept that a torn read costs one buffer of slightly wrong timbre
— cheaper than a lock on the audio callback. Same in the other direction for anything
the UI reads back, such as a scope buffer: a torn read there costs one frame of a
picture.

Build every lookup table on the game thread, before the first callback. An allocation
on the audio thread is a collection under a running note.

## Let the source outlive the gate

If the block has a release, stopping the `AudioSource` when the gate closes cuts it:
the callback is what plays the release out, and stopping the source stops the callback.
Keep the source up until the *voice* reports it has reached silence, then stop it. A run
does this by accident — it holds the source up for the whole run — which is why a
release can work in a simulation and be missing from a build-mode preview, from the
same code.

## DC is not always a bug

A synthesis port may be *meant* to sit far off zero — a narrow pulse spends most of its
cycle near the rail. On real hardware the output stage is capacitor-coupled and none of
it escapes; Unity has no such stage. Put a one-pole high-pass at the very end rather
than "fixing" the oscillator, and run it whether the gate is open or not, since it's the
offset it removes that would otherwise step the speaker as the gate moves.

## The master volume slider does not reach a block's AudioSource

Besiege has two kinds of volume control, arriving by different routes:

* **Per-category** sliders — BLOCKS, SFX, MUSIC, UI, AMBIENT, PHYSICS — are exposed
  parameters on an `AudioMixer`, written every frame by `MusicController.LateUpdate` as
  `UpdateVolume("BlockVolume", …)`. A block's `AudioSource` is routed through a mixer
  group, so these do reach it.
* **Master** slider sets `AudioListener.volume` — `OptionsMaster.SetMasterVolume` on
  scene load, and the slider's own callback while dragged.

**Unity does not apply `AudioListener.volume` to audio coming out of an
`AudioMixer`.** So the one slider a player reaches for first does nothing to a modded
block making its own sound, while the category sliders work — reads as "your mod
ignores my volume setting" and is hard to guess at from inside.

Apply it yourself, and only where the game isn't already doing it:

```csharp
private float MasterVolume()            // on the game thread, not the audio one
{
    if (source == null || source.outputAudioMixerGroup == null)
        return 1f;                      // straight to the listener: it scales this already
    BesiegeConfig config = OptionsMaster.BesiegeConfig;      // public static
    return config == null ? 1f : Mathf.Clamp01(config.MasterVolume / 100f);
}
```

`MasterVolume` is a percentage, why `SetMasterVolume` divides by 100. The mixer-group
test is the part that matters: without it, a source that *is* scaled by the listener
gets the slider applied twice and half volume becomes a quarter.

## A limiter has to live where the sum is

A block can't see the mix it's part of. Sixty blocks each handing over a signal peaking
near one add up to a signal peaking near sixty, and every one believes it's behaving.
Sharing an estimate between them helps — each reports its peak, all apply one gain —
but an estimate must assume something about phase, and whatever it assumes will be wrong
for some music. The power sum, `sqrt(sum of squares)`, is right for unrelated notes and
optimistic by 15–20% for a chord played on one sample, which is exactly what a generated
song does.

The mix itself is visible in one place: `OnAudioFilterRead` on a `MonoBehaviour`
attached to the object carrying the `AudioListener` receives the finished signal. A
limiter there reads the peak of the samples it's about to pass on, so it can guarantee
its output — no estimate, no overshoot.

Two things to get right:

* Work out headroom from the buffer's own peak **regardless of the current gain**.
  Computing it only when the current gain would clip lets the release climb past what
  the buffer allows, and a rising signal then walks out over the ceiling one buffer at a
  time.
* Leave the buffer alone when there's nothing to do, rather than multiplying it by one.
  It's the whole game's audio going through, not just yours.

Cost of putting it there is that it *is* the whole game's audio: above the ceiling,
everything ducks together. Keep a coarse stage on your own sources so the master stage
rarely has to act.

## Sample rate

Build anything rate-dependent for `AudioSettings.outputSampleRate` rather than
resampling from whatever rate the original ran at. Removes a whole stage, and for a
fixed-point port removes the rounding that stage would add.
