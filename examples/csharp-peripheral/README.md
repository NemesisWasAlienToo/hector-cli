# Example: custom C# peripheral (compiled by Renode at load)

A minimal **native C# peripheral** wired into a machine and driven by a test —
the simplest way to model your own hardware in Renode.

The peripheral is a single `.cs` file ([HectorSample.cs](HectorSample.cs)). There
is **nothing to build and nothing to install**: Renode bundles a C# compiler
(Roslyn), so hector just points it at the source and Renode compiles it — against
its *own* assemblies, so it always matches the Renode version in use.

```
HectorSample (memory-mapped at 0x40000000, size 0x100)
  0x0  ID      read-only  → 0x42
  0x4  SCRATCH read/write → stores whatever you write
```

## Run

```bash
# from this directory
hector test
```

The test (a `robot` step) reads the ID register and asserts `0x42`, then writes
`0xDEADBEEF` to the scratch register and reads it back — all over the system bus
via Renode's monitor, no firmware required.

## How it's wired

[.hector.yaml](.hector.yaml):

```yaml
modules:
  hector_sample:
    kind: csharp
    type: Antmicro.Renode.Peripherals.Miscellaneous.HectorSample
    source: HectorSample.cs          # raw .cs → Renode compiles it on load

machines:
  board:
    peripherals:
      sample:
        type: hector_sample          # reference the module by name
        at: "sysbus <0x40000000, +0x100>"
```

hector emits a single `i @HectorSample.cs` before any `mach create`, then places
the peripheral on the bus from the machine's `peripherals:`.

## Why no `.dll` / no .NET SDK?

The Renode image already contains everything for C#: the reference assemblies, the
.NET runtime, and the C# compiler. A pre-built `.dll` (via `dotnet build`) is only
worth it to pre-compile larger projects — and it needs a build image that carries
**both** the .NET SDK and Renode's assemblies, plus a framework/version match. For
most peripherals, the raw `.cs` path here is simpler and version-proof. See the
CLI README's *Developing your own peripherals* section for the deeper references.
