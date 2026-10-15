# RIVET-A1

AES-128 encryption/decryption, iterative rounds and transaction interfaces.

**Status:** Engineering accepted.

## Reproduce

Requires Python 3, Icarus Verilog (`iverilog`, `vvp`) and Yosys.
Run from this generation's directory:

```bash
python3 tests/verify.py
```

The test driver creates fresh local evidence. A published status is not a new run on your machine.

[Specification](design/SPEC.md) · [Architecture](design/ARCHITECTURE.md) · [RTL](rtl/) · [Verification source](tests/) · [Recorded check statuses](STATUS.json)

[Reviewed product report](REPORT.pdf) · [LaTeX source](REPORT.tex)

Simulation and generic synthesis do not establish physical signoff or measured silicon performance.
