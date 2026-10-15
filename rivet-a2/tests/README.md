# Independent verification

Run from the project root, using installed tools (no dependencies are installed):

```
python3 tests/verify.py --check behavior
python3 tests/verify.py --check sensitivity
python3 tests/verify.py --check synthesis
```

`reference.py` uses standard-library Python only. Its AES S-box is calculated
from GF(256) inversion and the affine transform, rather than importing RTL
tables. Its GHASH uses polynomial convolution, reflected coefficients and
polynomial long division, rather than reproducing the RTL's shift recurrence.
FIPS 197 Appendix C.1/C.3 and the GCM submission Appendix B cases 1/2, 4,
13/14 and 16 anchor complete AES and GCM outputs, including empty, one-block
and multiblock/AAD/partial-message examples for both key lengths. Exact values,
document locations and URLs are retained in `reference_anchors.json` on every
behavior/sensitivity run. Anchors are checked before any RTL expectations are
generated. Encryption and ordinary inverse AES are both anchored.

## Executable requirement map

| Requirement | Executable checks and compared observation |
| --- | --- |
| Raw AES-128/256 and rekeying | Both directions, published vectors and zero/ones/ascending/seeded keys/data; exact complete block, ID, direction, 16-byte length and 10/14-edge latency. |
| Expansion contract | All 37 round keys across 128/256/128 rekeys; exact 40/52-edge expansion completion and key-input capture. |
| GHASH contract | 16 independent products, including zero, unit and reduction-sensitive patterns; exact 128-edge service, busy-start rejection, one-cycle done and clear priority/abort. |
| GCM formatting | Full ciphertext/plaintext/tag comparisons, AAD-only, payload-only, empty, partial, multiblock, long AAD and random input gaps; random nonzero padding checks ignored low bytes. |
| Capacity and byte boundaries | Capacities 1, 3, 16 simulate all final valid-byte counts 1..16 for both key sizes and directions, exact capacity, partial final capacity and capacity-plus-one rejection. Capacity 256 elaborates/simulates maximum 4096-byte encryption/decryption for both sizes. |
| Authentication | At capacity 16 corrupt every expected-tag bit for each key size with otherwise identical input timing; assert identical failure latency. Separately mutate AAD, IV and ciphertext. Compare complete calculated tag and failure status, not just a round trip. |
| Release isolation | Every public-pin sample checks no payload before successful tag transfer, no failed plaintext output, zero inactive data/metadata, stable stalled records and no new admission during computation/tag/drain. |
| Handshake timeline | Pre-edge acceptance, post-edge busy/ready transitions, command/data capture, tag presentation/consumption, first and last payload release, no same-edge replacement, exact transfer counts. |
| Arbitration and rejected traffic | Simultaneous key/command/raw valid checks key priority; simultaneous command/raw checks command priority; unloaded requests backpressure with zero error. Unaccepted changing stream/request inputs have no effect. |
| Reset and epochs | Time-zero active reset, first Active-region rising edge, falling-edge and post-edge samples, asynchronous mid-cycle abort, expansion, raw processing/stall, GCM AES/GHASH processing, successful/failed tag stalls, output stall, then independently checked fresh-message recovery. |
| Protocol errors | Accepted valid-bytes 0/17/31, short nonfinal beats, incorrect partial length/section, AAD after payload, oversize including `0xffffffff`; zero error tag and no payload followed by a valid decryption. |
| Differential exploration | Deterministic Python `random.Random(1701)` generation; capacity 16 adds 20 arbitrary message shapes per key size. This is a bounded matrix, not exhaustive or formal verification. |
| Functional sensitivity | Six independent disposable RTL copies: AES-256 extra SubWord, GHASH polynomial, partial mask, length block, one-bit tag omission and pre-authentication plaintext release. Identical real pin checker runs baseline and mutants; only the named functional assertion counts as a rejection. Compile/tool failures do not. |
| Generic synthesis | Actual Yosys hierarchy/check/generic synthesis at capacities 1/3/16; literal connected instance hierarchy, 60-word expanded key state, sequential payload storage, no latches/blackboxes/unresolved cells, conflicts or logic-loop diagnostics, and substantive post-synthesis state. No physical PPA/timing threshold. |

`bridge.sv` observes only top-level public ports. `units.py` directly instantiates
standalone module ports without hierarchical state access. Assertions use case
inequality and explicitly reject X/Z; stalls stay asserted throughout nested
observation helpers. Input requests are stable until the tested acceptance
edge, then deliberately changed to verify capture.

## Results and evidence index

Each invocation creates a fresh `evidence/checks/verifier-<check>-<UTC>-<id>/`
directory. Its `results.json` is the claim-to-evidence index: `source_sha256`,
`versions`, command receipts, configuration/seed rows, actual comparison counts,
expected counts and criterion, unit results, mutation observations or structural
statistics are linked to raw logs. `sources/` snapshots every declared design
and verification input. `cases.json` records planned stimulus/expected values;
it is **not** coverage evidence by itself. Only completed assertions and actual
comparison counts in a passing simulation establish the corresponding rows.
Missing comparisons, prerequisites, X/Z, mismatches, child errors or timeouts
produce a nonzero check exit and a retained failure record.

Subprocesses have a 3600-second execution guard, not a performance acceptance
threshold. RTL transaction-progress assertions are separate cycle-based safety
guards comfortably beyond the documented finite service latencies. Source
changes during a check are rejected. Outputs never depend on private workflow
metadata or previously compiled binaries.

The entrypoint disables Python bytecode writes before importing local modules:
`tests/*` is a verification input selector, so creating or refreshing
`tests/__pycache__` changes the admitted inputs even when all source files stay
unchanged. The first admitted behavior execution completed its functional
comparisons but was rejected by the shared runtime with
`validation_inputs_changed_during_execution`; its startup created three
`.pyc` files. That execution is not an accepted behavior result. The focused
`python3 tests/input_stability.py` preparation diagnostic checks unchanged
project inputs and two cache-free copied entrypoint launches without running
functional simulation or synthesis. It retains its own advisory receipts and
does not replace any admitted check.

Observed tools in initial bounded diagnostics: Python 3.12.3, Icarus Verilog
12.0 (stable), vvp 12.0 and Yosys 0.33 (git sha1 2584903a060). Every check
records the versions actually used. Yosys 0.33's native frontend requires
package-import expansion: `yosys-input/` contains the exact package declarations
textually inserted at the three imports, with unchanged declaration/function
bodies and module logic. `frontend-mapping.json` binds original and generated
hashes. Icarus compiles the unmodified package-form RTL, with the package first.
Pre-synthesis `hierarchy.json`, post-synthesis `netlist.json`/`netlist.v` and
`statistics.json` are retained separately. Literal hierarchy checks normalize
escaped `hdlname` identifiers without discarding instance or state assertions.

`--probe` runs only an advisory preparation diagnostic under a fresh
`evidence/preparation/` directory with an outer `receipt.json` and child
receipts. It cannot replace the three admitted commands above. `--repair-of`
links a repaired diagnostic to an immutable earlier preparation receipt.
Engineering acceptance and final reporting remain with the shared runtime and
independent review; no product report is a verification prerequisite.
