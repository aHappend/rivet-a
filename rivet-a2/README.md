# RIVET-A2

AES-256 and GCM authenticated encryption/decryption.

**Status:** Engineering accepted.

## Reproduce

Requires Python 3, Icarus Verilog (`iverilog`, `vvp`) and Yosys.
Run the admitted checks from this generation's directory:

```bash
python3 tests/verify.py --check behavior
python3 tests/verify.py --check sensitivity
python3 tests/verify.py --check synthesis
```

The test driver creates fresh local evidence. A published status is not a new run on your machine.

Use a clean checkout or fresh output directories when a driver refuses existing evidence.

[Specification](design/SPEC.md) · [Architecture](design/ARCHITECTURE.md) · [RTL](rtl/) · [Verification source](tests/) · [Recorded check statuses](STATUS.json)

The independently reviewed product report has not been published yet.

Simulation and generic synthesis do not establish physical signoff or measured silicon performance.
