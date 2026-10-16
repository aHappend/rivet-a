# RIVET-A3

Multiple keys and contexts, scheduling and DMA.

**Status:** Engineering accepted.

## Reproduce

Requires Python 3, Icarus Verilog (`iverilog`, `vvp`) and Yosys.
Run the admitted checks from this generation's directory:

```bash
python3 tests/verify.py --suite environment --output evidence/mandatory-rerun-001/environment
python3 tests/verify.py --suite behavior --seeds 17,89,203 --capacities 1,3,16 --output evidence/mandatory-rerun-001/behavior
python3 tests/verify.py --suite boundaries --output evidence/mandatory-rerun-001/boundaries
python3 tests/verify.py --suite synthesis --output evidence/mandatory-rerun-001/synthesis
python3 tests/verify.py --suite checker-sensitivity --output evidence/mandatory-rerun-001/checker-sensitivity
python3 tests/verify.py --suite reproduce --output evidence/mandatory-rerun-001/reproduce
python3 tests/verify.py --suite environment --output evidence/recovery-002/environment
python3 tests/verify.py --suite behavior --seeds 17,89,203 --capacities 1,3,16 --output evidence/recovery-002/behavior
python3 tests/verify.py --suite boundaries --output evidence/recovery-002/boundaries
python3 tests/verify.py --suite synthesis --output evidence/recovery-002/synthesis
python3 tests/verify.py --suite checker-sensitivity --output evidence/recovery-002/checker-sensitivity
python3 tests/verify.py --suite reproduce --output evidence/recovery-002/reproduce
```

The test driver creates fresh local evidence. A published status is not a new run on your machine.

Use a clean checkout or fresh output directories when a driver refuses existing evidence.

[Specification](design/SPEC.md) · [Architecture](design/ARCHITECTURE.md) · [RTL](rtl/) · [Verification source](tests/) · [Recorded check statuses](STATUS.json)

The independently reviewed product report has not been published yet.

Simulation and generic synthesis do not establish physical signoff or measured silicon performance.
