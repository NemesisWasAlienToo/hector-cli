// A tiny native C# peripheral for Renode, compiled by Renode at load time.
//
// No .NET SDK and no pre-built .dll are needed: Renode bundles a C# compiler
// (Roslyn), so hector just points it at this .cs file (see .hector.yaml ->
// modules.hector_sample) and Renode compiles it against its own assemblies when
// the emulation loads — automatically matched to the running Renode version.
//
// Register map (memory-mapped, 0x100 bytes):
//   0x0  ID      : read-only, always 0x42
//   0x4  SCRATCH : read/write, stores whatever you write

using Antmicro.Renode.Peripherals.Bus;

namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    public class HectorSample : IDoubleWordPeripheral, IKnownSize
    {
        private uint scratch;

        public uint ReadDoubleWord(long offset)
        {
            switch(offset)
            {
                case 0x0: return 0x42u;    // ID register
                case 0x4: return scratch;  // scratch register
                default:  return 0u;
            }
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            if(offset == 0x4)
            {
                scratch = value;
            }
        }

        public void Reset()
        {
            scratch = 0u;
        }

        public long Size => 0x100;
    }
}
