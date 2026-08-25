# Recovering a mod whose source is gone

Several of these mods shipped to the Workshop in 2018 and the C# was lost; only
the built assembly survived. This is how one was rebuilt, and — more usefully —
how the result was *checked*, because a reconstruction nobody has verified is
worth very little.

Worked example: **Moon**, `MoonAssembly.dll`, 20,992 bytes, 7 types.

## You already have a decompiler's worth of tooling

`Besiege_Data/Managed/` ships **`Mono.Cecil.dll`**. Nothing needs installing: write
a dumper against Cecil, compile it with Besiege's own `mcs` and run it on Besiege's
own embedded Mono, exactly the way `tools/peek.sh` in this repository works.

What a dumper has to print to be useful for this, over and above
[06-reading-the-game.md](06-reading-the-game.md)'s signature dump:

- every method body as an instruction list;
- **branch operands resolved to the *ordinal* of the target instruction**, not a
  byte offset. This is the one thing that makes the output diffable: two builds of
  the same source have different byte offsets and identical ordinals.
- locals with their types, exception handlers, and custom attributes with their
  constructor arguments — `[XmlRoot("…")]` names the element a block module
  deserialises and is not recoverable any other way.

## What survives compilation, and what does not

Read directly, never guessed: types and base types, every field with its type and
`public`/`private`/`static` flags, every method signature and accessibility,
custom attribute arguments, auto-properties (backing field plus the
`MethodSemantics` rows pairing the accessors), and the compiler-generated iterator
behind a coroutine.

Gone for good: local variable names, parameter names of private methods where the
`Param` table was not emitted, comments, and the file layout. Name locals for
readability and say so.

## The original was probably not built by Besiege's compiler

This decides what "matching" can even mean. The 2018 Moon assembly is a **Debug**
build from Microsoft's C# compiler: it carries `[Debuggable]`, every method is
padded with `nop`, and the iterator state machine is named `<M>d__4`. A rebuild
with Besiege's `mcs` is a Release build and names the same class `<M>c__Iterator0`.

So byte-for-byte comparison is off the table. The systematic differences, all
harmless:

| original (csc, Debug) | rebuild (mcs, Release) |
| --- | --- |
| `nop` between every statement | absent |
| conditions spilled: `stloc.N` / `ldloc.N` / `brfalse` | `brfalse` straight off the stack |
| `!x` as `ldc.i4.0`/`ceq`; `x != k` as `ceq`/`ldc.i4.0`/`ceq` | fused `brtrue`, `bne.un`, `bge.un`, `ble.un` |
| every `return` through one shared exit | `ret` in place |
| object initialisers built with `dup` | built through a temp local |
| `call Int32::ToString()` | `constrained.` + `callvirt Object::ToString()` |
| `<M>d__N`, `<>1__state`, `<>2__current`, `<>4__this` | `<M>c__Iterator0`, `$PC`, `$current`, `$this` |

## The check that is worth doing

Dump both assemblies and compare **semantic content** per method: which members
are called, which fields are read and written, which constants and strings appear
— ignoring locals, branch encodings, stack shuffling and conversions, because
those are exactly what two compilers disagree about. Roughly a page of Python over
the dumper's output.

On Moon: **49 methods compared, every hand-written one matched.** The only four
that did not were inside the compiler-generated iterator, where `mcs` adds a
`$disposing` flag that `csc` encodes in the state number.

It earned its keep immediately: it caught the moon's `MeshCollider` physic
material transcribed as `bounceCombine = Maximum, frictionCombine = Multiply`
where the assembly said `Minimum` and `Maximum`. Nothing else was wrong, and
nothing else would have found it.

## Keep the harness for the cleanup afterwards

The same comparison is what makes it safe to *refactor* recovered code, which is
the second half of the job and the riskier one. Build once, keep that assembly,
refactor, build again, and compare the two:

- compare the **set of distinct string literals** and **distinct float constants**
  across the whole assembly. Every mapper key, resource name, shader property and
  tuning number is in there. On a refactor that extracted six helpers from Moon
  the numbers were "63 distinct strings before, 63 after, none lost or added; 31
  distinct floats before, 31 after" — which is the whole proof that no key was
  renamed and no constant fat-fingered.
- compare the **set of members called**. Every removal should map to code you
  deduplicated and every addition to a helper you introduced. Anything else is a
  bug you just wrote.

Counts of a literal are *expected* to drop when you deduplicate — `"_Color"` going
5 → 1 is the helper working. It is the **set** that must not change.

### When the refactor is big enough that IL comparison stops helping

Extracting a helper leaves most instructions where they were. Turning a
three-armed `switch` with six inlined blocks into four methods does not: every
instruction in that method moves, the diff is the whole method, and the comparison
reports noise rather than a finding.

The check that still works there is a **differential simulation**. Transcribe both
versions of the logic into a scripting language — one from the old IL, one from the
new C# — drive them with random input traces, and compare their state every step.
It is an hour's work and it is worth it on anything whose logic a player will feel.

On Return 2 Center's steering modes: 4,000 traces × 400 frames, random mode, random
key press and release edges, the toggle and the limits switched on and off
mid-trace, and a spread of speeds, frame times, limit ranges and mirror states —
comparing the demanded angle, the toggle latch, the captured input, and whether the
joint was written each frame. **1.6 million frames, no differences, bit-exact.**

Two things make it worth more than it sounds:

- *Bit-exact*, not "within tolerance", is a real result and worth checking for. The
  refactor had regrouped five multiplications (`a*b*c*d*e` into `a*(b*c*d)*e`),
  which is exactly the sort of change that is fine in principle and can move a
  result by an ULP. Comparing exactly says it did not, on any input tried.
- Random traces reach state combinations you would not write a case for. The
  interesting ones here were "latched, then the limit moved under it", which no
  hand-written test would have covered.

Where a refactor collapsed a cascade of `if`s into one boolean expression — two
independent flips of a limits range, which cancel — enumerate the four cases
exhaustively instead. That is not worth a simulation and it is worth doing.

## Two things this does not prove

- That the reconstruction matches the original says nothing about whether the
  original was **correct**. Moon's was not — five real defects, listed in that
  mod's `AGENTS.md`. Fix them *after* the comparison passes, so each fix shows up
  as a difference in exactly the method you meant to change.
- Floats print as decimal expansions (`0.05000000074505806`). That is `0.05f`;
  round before comparing.
