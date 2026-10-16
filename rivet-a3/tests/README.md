# Independent RIVET-A3 verification

`verify.py` owns all models, stimulus, scoreboards and tool scripts. It uses
Python 3 (including `random.Random.randbytes`, Python 3.9 or newer), Icarus
`iverilog`/`vvp`, and Yosys already present on PATH. It never installs tools.
Run the six commands in `design/SPEC.md` from the delivered root, using fresh
output directories. An existing output directory is an error, not an invitation
to overwrite evidence. Simulation subprocess deadlines are 3600 seconds;
generic synthesis and clean reproduction have 86400-second outer deadlines.
These are execution limits, not functional timing specifications.

## Requirement-to-check mapping

| Requirement | Executable checks and compared quantities |
| --- | --- |
| Independent cryptography | `oracle.py` computes its S-box by field inversion/affine transform, byte-matrix AES, byte CTR, and integer polynomial GHASH, without reading/importing DUT code. FIPS 197 AES-128/256 and published NIST GCM empty, full-block and AAD/partial vectors anchor encryption/decryption. `basic()` also drives the published zero-key GCM examples through the integrated top. |
| Legacy and enhanced access | Every behavioral run uses both AES key lengths, both directions, ECB/CTR/GCM, raw transaction IDs, legacy tags, enhanced cookies/context/status, exact output bytes/count/padding and no extra output. Legacy key lengths are explicitly reloaded into slot0. |
| Boundaries and retained ownership | Lengths 0, 1, 15, 16, 17 where legal, exact capacity and one-byte-over rejection; four simultaneous full-capacity sessions; empty first/final fragments; GCM AAD and ciphertext fragments inside blocks; all four slots/contexts and mixed key lengths. |
| Save/restore and isolation | Four-way interleaving in direct and DMA origins, independently computed whole-message tags, no intermediate payload, rejected slot/direction/IV/mode/phase/first/origin continuations followed by successful finalization. Retained DMA destinations include noncontiguous sub-block fragment mappings. |
| Authentication and zeroization | All 128 expected tag bits participate in the oracle; each tag-bit position is individually corrupted and must reject, alternating key lengths. Corrupted-tag direct/legacy/DMA cases require no released payload. The memory write scoreboard rejects every unplanned destination write, including authentication failures. CSR context release and subsequent same-context/key reuse check public nonleakage. Unit module ports check complete context-record clear/reset and readable key-bank reset/atomic rejection, without internal hierarchical accesses. Synthesis checks real asynchronous-zero reset connections for every retained payload/destination, context, and key storage bit. These bounded checks are not an unbounded noninterference proof. |
| Scheduler | Held raw output prevents preemption while both depth-two queues fill. Actual first descriptor fetches and completions must be high FIFO then normal FIFO, irrespective of enqueue order. A second case accepts an enqueue on the old-head selection edge. Competing key, queued DMA, direct, legacy command and raw requests remain asserted until their permitted acceptance. No throughput or starvation bound is assumed. |
| Handshakes and reset | Monitors compare all public outputs for X/Z on both clock edges; time-zero reset has no artificial `1 -> 0` prerequisite. The first rising-edge reset observation occurs in the Active region; release is checked before its first rising edge. All seven stimulus producers must hold valid/fields under backpressure. Complete output/completion/tag/request/key/CSR payloads must remain stable during stalls. Deterministic retained-completion/tag/output stalls complement seeded channel readiness and producer gaps. Reset cancels four saved contexts, accepted unanswered DMA, stalled output and active streaming; a fresh epoch proves no stale completion/data and invalidated keys/contexts. |
| DMA bus | Byte memory, aligned requests, zero read strobes/data, one outstanding request/response, held requests, finite independent request/response stalls, every enabled write byte/value/multiplicity, no writes outside declared ranges, and memory conservation including explicitly reset-canceled requests. Read permissions are cleared between finished cases. All byte offsets 0..15 include exact in-place operation. |
| Invalid inputs and faults | Invalid descriptor modes/reserved bytes, capacity, ECB count, unloaded/locked/bound keys, stream counts/section, abort conditions, CSR permissions/reserved bits/W1C, invalid/wrapping descriptor and section addresses, forbidden overlap, AAD/payload/output/status errors, each descriptor-fetch beat fault, and status delivery failure. Twelve actual bus-fault events per full run include nonfinal status failure aborting a consumed session, invalid-continuation status failure preserving an unconsumed session, and a restored-session read fault. Other saved contexts must still finalize against their original complete-message oracle. A newly arriving error coincides with W1C and must remain sticky. No fault is silently retried. |
| Rollover and module contract | `boundary_units.sv` drives the real context-store write/read/clear ports and checks pre-edge immutability, four-bank isolation, reset > clear > write, 128-bit key normalization, locked/bound nonmutation. An exact retained excerpt of top-level boundary arithmetic is independently checked on 80 cases around 64-bit length overflow, the last inc32 counter and saved unused keystream. This is not a claim that exabytes were streamed or top-level state was forced. |
| Actual synthesis | Yosys hierarchy checking, `proc`, `synth -noabc`, `check -assert`, statistics and JSON netlists. Named key/context/scheduler/AES/GHASH instances must exist, have real cells and connected output nets before generic synthesis. The final netlist must have no latches, no unresolved cells, substantive sequential/logic/storage and resettable storage. No physical PPA, timing, power or side-channel sign-off is inferred. |
| Checker sensitivity | A disposable declared-source copy changes one CTR/GCM transformed byte by XOR 1. It must compile, run and fail an actual payload/tag comparison. A compiler failure or merely nonzero tool exit does not count. The accepted RTL is never edited. |
| Clean reproduction | Only `rtl/*.sv`, `design/SPEC.md`, `design/ARCHITECTURE.md`, and `tests/*` files are copied to a new directory. A fresh Python process there invokes the delivered entry, recompiles RTL and executes the cross-feature singleton campaign without reference mount, binaries, runtime metadata or private imports. |

## Matrix and evidence interpretation

Behavior runs every seed 17, 89, 203 at every capacity 1, 3, 16. Boundaries
also elaborates/runs capacities 1, 3, 16, 256 and explicitly rejects 0/257.
Capacity256 runs a targeted maximum-capacity campaign rather than pretending
to repeat every seeded cross-product. It covers all four fully retained DMA
contexts, exact/over capacity, both key lengths and direct boundary lengths.
Other boundary configurations run the cross-feature scenarios as well.

`CASE` records are emitted only after all expected completions, payloads, tags,
fetch order, writes and memory conservation have been checked. The runner
requires the exact generated case list, a nonempty `RESULT`, real comparison
counts and nonzero required stall/fault/reset/queue-event counters. Cases are
not substitutes for code coverage or exhaustive formal proof. Published vector
anchors and boundary-unit comparisons are recorded separately.

Each fresh output contains `receipt.json`, declared-source snapshots/hashes,
exact tool argv/cwd/version, timestamps, timeout/exit, raw stdout/stderr,
generated stimulus, compiled simulation and comparison-backed per-run metrics.
Failed runs remain failures; `--repair-of` links a new advisory attempt to its
predecessor without modifying the predecessor. The shared runtime owns admitted
execution and final acceptance; a preparation receipt or this README does not
confer acceptance.

### Recovery after a retained execution

The shared runtime's retry of `environment` failed before any tool or oracle
ran: `evidence/environment` already contained the first execution, so the
exclusive directory creation raised `FileExistsError`. This is an output-path
collision, not a new environment or RTL failure. Keep the exclusive creation
guard and all prior evidence intact. Re-execution requires independently
admitted commands with fresh output paths, for example
`--output evidence/recovery-002/environment`, and corresponding fresh paths
for the other suites. Do not place a new run inside an old suite directory:
its output selector would also capture the old artifacts. In particular, the
original uncompressed synthesis output still exceeds the capture limit even
though the repaired runner compresses newly generated netlists. Neither
deleting old evidence nor reusing its success receipt qualifies a new run.
The shared runtime owns admission and execution of these recovery commands.
The six `recovery-002-*` checks have now been independently admitted in the
supplied work order; they are not proposals still awaiting admission. Execute
those fresh-path checks rather than the original colliding commands.

Recovery selection is a shared-runtime prerequisite, not a runner repair.
Changing verification inputs does not make `evidence/environment` fresh, and
must not be used as justification to replay its original command. A `ready`
handoff means the following already admitted checks can execute; it does not
mean the original occupied-output checks can execute or that either open
failure has passed:

| Admitted check ID | Fresh output passed to `--output` |
| --- | --- |
| `recovery-002-environment` | `evidence/recovery-002/environment` |
| `recovery-002-behavior` | `evidence/recovery-002/behavior` |
| `recovery-002-boundaries` | `evidence/recovery-002/boundaries` |
| `recovery-002-synthesis` | `evidence/recovery-002/synthesis` |
| `recovery-002-checker-sensitivity` | `evidence/recovery-002/checker-sensitivity` |
| `recovery-002-clean-reproduction` | `evidence/recovery-002/reproduce` |

Keep their admitted suites, seeds, capacities, input selectors and output
selectors unchanged. Their exact admitted commands, from the delivered root,
are:

```sh
python3 tests/verify.py --suite environment --output evidence/recovery-002/environment
python3 tests/verify.py --suite behavior --seeds 17,89,203 --capacities 1,3,16 --output evidence/recovery-002/behavior
python3 tests/verify.py --suite boundaries --output evidence/recovery-002/boundaries
python3 tests/verify.py --suite synthesis --output evidence/recovery-002/synthesis
python3 tests/verify.py --suite checker-sensitivity --output evidence/recovery-002/checker-sensitivity
python3 tests/verify.py --suite reproduce --output evidence/recovery-002/reproduce
```

These commands are for shared-runtime selection, not a second full campaign
inside a Verifier role call. A `continue` response cannot repair command
selection: the verification sources are ready for these admitted commands.
Admission alone does not establish that any command has executed, and a
source change does not renew the original output directories.

A successful Verifier process exit is not a successful check execution. For
recovery, the next shared-runtime check record must identify
`recovery-002-environment` and its exact fresh-output command above; another
Verifier invocation or an original-path environment retry does not establish
that selection. Each remaining recovery check still needs its own actual
source-bound result and retained artifacts before independent delivery review.
No runtime record is a deliverable source or a dependency of `verify.py`.

Read-only inspection of `attempt-0091/response.json` confirms its process
exited zero but returned `continue` for command selection, not a suite result.
The Verifier handoff must instead return `ready`: all six fresh-path commands
are already in the admitted executable contract, so no new command admission
or further source repair is needed to request their execution. This changes
the role decision, not runtime-owned selection or acceptance. The Verifier
must not execute the full campaign inside its role call to compensate for
selection. The retained outcomes and remaining obligations are:

| Retained observation | What still must be established |
| --- | --- |
| Original environment, behavior and boundaries checks passed on their recorded inputs. | Fresh results bound to the current complete source set; historical passes do not certify subsequent verification-source changes. |
| Original synthesis exited zero, but its 1,698,395,392-byte bundle exceeded the 1,073,741,824-byte capture limit. | Execute synthesis with the implemented lossless-retention repair and obtain successful shared-runtime artifact capture. |
| Subsequent original-path environment retries rejected an occupied output before checks ran. | Select the admitted fresh-path commands; preserve the collision guard and original evidence. |
| Recovery checker-sensitivity and clean reproduction have no supplied execution results. | Actual behavioral mutation rejection and actual fresh-directory cross-feature simulation, with their own receipts. |

The compression repair's advisory validation is retained at
`evidence/preparation/synthesis-artifact-retention-001/execution/validation/receipt.json`.
It does not close any of these current-source execution obligations.

If the runtime still selects the original occupied
paths, the collision remains unresolved: do not add unrelated regressions,
silently choose another directory, certify an old receipt, or modify retained
evidence to manufacture progress. The lossless synthesis-retention repair
addresses the original artifact-size failure only for newly executed synthesis;
current source-bound results and independent acceptance are still required.

`environment()` also executes `tests/test_runner.py` and retains its raw logs
and fixtures. This bounded runner regression checks rejection of occupied
outputs without mutation, fresh allocation without a success claim, complete
JSON gzip round-trip using both gzip and an independent zlib decoding path,
recorded hashes/sizes, and rejection of artifact overwrite. It does not run
simulation or synthesis and does not substitute for either suite. Output
collisions now explain the non-destructive recovery explicitly; they still
fail rather than silently redirecting outside the admitted output selector.
The collision exception includes a JSON `Rejected invocation` suffix with
the actual suite, resolved output, interpreter, script argv and cwd (Python
interpreter flags such as `-B` are not part of `sys.argv`). The fresh-process regression
compares those fields with its real rejected command and requires empty stdout,
so a scheduling collision cannot be mistaken for execution of a fresh-path check
or a successful suite. This diagnostic does not select a recovery command.
The regression also invokes the real CLI in a fresh Python process against an
occupied fixture, requires a nonzero exit and the recovery diagnostic, and
compares the original receipt and directory contents afterward. It writes
`runner-regression/result.json`; the environment suite requires all fourteen
explicit preservation/retention checks and binds that result's SHA-256 in its
receipt. A child exit of zero alone cannot certify this regression.
Existing empty directories are rejected without creating a receipt, and an
existing regular file at the requested output path is rejected byte-for-byte
unchanged. Neither condition authorizes reuse or automatic redirection. These
regressions strengthen evidence preservation; resolving the retained collision
still requires selection of the already admitted fresh-path recovery checks.

The installed Yosys 0.33 frontend does not accept wildcard package imports.
The synthesis runner inserts the **verbatim** package body at exactly those
import sites in a generated copy. It records every generated hash and keeps
all functions/constants unchanged. Functional simulation compiles the original
SystemVerilog package/import sources; deliverable RTL is never rewritten.
Generic synthesis omits ABC technology mapping deliberately, not synthesis.

Synthesis retains complete `hierarchy.json.gz` and `netlist.json.gz` files,
losslessly gzip-compressed to keep the artifact bundle within capture limits.
The runner verifies decompressed byte counts and SHA-256 against the original
Yosys JSON before removing its newly generated uncompressed copies. Both
compressed and uncompressed hashes/sizes are recorded in `synthesis_artifacts`
in the receipt. All structural assertions read the complete compressed JSON;
no cells, connections, attributes or storage checks are omitted. Read either
file with Python's `gzip.open(path, "rt")` and `json.load`, or `gzip -dc`.

Before synthesis reports success, the runner measures every file under its
declared output, including snapshots, logs, compressed netlists and the final
receipt itself. `artifact_capture` records that total and the known
1,073,741,824-byte capture limit. An oversized bundle fails explicitly rather
than returning success only to fail runtime artifact capture. This guard does
not certify capture by the shared runtime, change structural checks or make
occupied output paths reusable.
The synthesis ledger separates `generic-synthesis` from
`synthesis-artifact-capture`: a successful Yosys/structural result cannot
conceal a failed bundle-size guard. The latter remains `not_run` until
finalization, and records a failure independently if retention exceeds the
limit. Self-inclusive accounting includes its final passed ledger entry.
The runner regression additionally checks exact self-inclusive byte accounting
on real fixture files and explicit rejection of a synthetic over-limit file
size. The latter mocks size enumeration only; it is not a large-netlist run.
It also compares the saved capture-ledger outcomes for success and oversize
rejection, then checks fresh accounting after the negative fixture.
These two results are included in the fourteen required checks, along with
the two corruption-rejection checks below.

The same regression injects same-length byte corruption and truncated data at
the gzip writer, then uses the real decompressor and retention guard. Both
valid-gzip negative fixtures must fail lossless verification, preserve their
original JSON, and leave no verified artifact entry in memory or on disk.
All fourteen runner checks are required. This tests the artifact-retention
repair's failure path; it does not resolve runtime selection of occupied
outputs or replace the admitted synthesis and behavioral checks.

Source discovery rejects an empty match for each declared selector separately,
before hashes or reproduction comparisons can certify an incomplete bundle.
The runner regression removes each selector's sole fixture file in turn and
replaces it with a directory; both source enumeration and hashing must reject
it. Existing files matching other selectors cannot hide the missing input.
This source-binding guard does not change check selection or output allocation.
