# Audio: synthesising it, and placing it in the world

Everything here was found writing a block that generates every sample as the
machine runs. A block that only plays a clip needs none of it — set the
`AudioSource` up as 3D and stop reading.

## `OnAudioFilterRead` runs *after* the source's 3D stage

This is the one that costs a day. Unity's documentation says the callback is
inserted into the source's DSP chain; what it does not say is that the chain point
is **downstream of the panner and the distance rolloff**.

So a filter that *overwrites* the buffer — which is what generating audio means —
throws away everything the 3D stage did. The symptom is a block heard at one
volume, dead centre, from anywhere on the map, with `spatialBlend = 1` set and
looking correct.

Three ways out, and only one of them is good:

| Approach | Placed? | Latency |
| --- | --- | --- |
| `OnAudioFilterRead` overwriting the buffer | **no** | lowest |
| A streaming `AudioClip` with a PCM reader callback | yes | **bad** |
| `OnAudioFilterRead` + your own pan and distance gain | yes | lowest |

The middle row is the trap, because it looks like the clean fix and it works: feed
the samples in through the clip instead of a filter and they arrive *before* the
3D stage, so Unity pans them properly. But a streamed clip is read **well ahead**
of being heard. The gate opens into audio that was already generated with the gate
shut, and the note arrives late — plainly late, not subtly. **Do not go back to
it.**

So: leave the source **2D** (`spatialBlend = 0`, which also stops Unity distance-
culling it) and do the placement yourself. A distance gain and a stereo pan worked
out on the game thread, applied in the filter:

- compute the gain in `Update` from the block's position against the
  `AudioListener`'s, and hand it to the callback through `volatile` floats. A
  transform must never be read from the audio thread;
- **slide onto the new gain across the buffer** rather than applying it at the
  start. The value is a frame old and moves in steps; without the slide a turning
  camera is audible as a staircase;
- `min(1, 1 ∓ pan)` per ear keeps a block dead ahead exactly as loud as it was
  before any of this, and never exceeds 1, so nothing clips;
- **re-find the `AudioListener` whenever it is not `isActiveAndEnabled`.** Besiege
  swaps cameras between building and running and the listener goes with them, so a
  cached one goes stale rather than null.

## The source must be playing at all

Unity does not run the filter chain on a source that is not playing, so a
procedural block needs a clip and a `Play()` even though the clip is never heard.
One sample of silence, looped, is enough, and it can be one static shared by every
block.

## The audio thread

`OnAudioFilterRead` is not the game thread. Nothing in it may touch a mapper
value, a transform, or any other Unity object. Hand settings across in plain
`volatile` fields of primitive type and accept that a torn read costs one buffer
of slightly wrong timbre — which is cheaper than a lock on the audio callback.
The same in the other direction for anything the UI reads back, such as a scope
buffer: a torn read there costs one frame of a picture.

Build every lookup table on the game thread, before the first callback. An
allocation on the audio thread is a collection under a running note.

## Let the source outlive the gate

If the block has a release, stopping the `AudioSource` when the gate closes cuts
it: the callback is what plays the release out, and stopping the source stops the
callback. Keep the source up until the *voice* reports it has reached silence,
then stop it. A run does this by accident — it holds the source up for the whole
run — which is why a release can work in a simulation and be missing from a
build-mode preview, from the same code.

## DC is not always a bug

A synthesis port may be *meant* to sit far off zero — a narrow pulse spends most
of its cycle near the rail. On real hardware the output stage is capacitor-coupled
and none of it escapes; Unity has no such stage. Put a one-pole high-pass at the
very end rather than "fixing" the oscillator, and run it whether the gate is open
or not, since it is the offset it removes that would otherwise step the speaker as
the gate moves.

## Sample rate

Build anything rate-dependent for `AudioSettings.outputSampleRate` rather than
resampling from whatever rate the original ran at. It removes a whole stage, and
for a fixed-point port it removes the rounding that stage would add.
