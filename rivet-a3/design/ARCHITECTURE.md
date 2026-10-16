# RIVET-A3 architecture

One shared iterative AES datapath and one 128-cycle polynomial GHASH multiplier
serve four keyslots and four saved contexts. A byte-serial session controller
preserves arbitrary fragment boundaries without padding them independently.
Input beats are buffered then consumed a byte at a time. ECB collects full
blocks; CTR/GCM consume saved keystream and request a new counter block only
when needed. GCM accumulates bytes into one pending hash block.

Context storage is four 1280-bit records with a combinational read and
edge-committed write/clear. The exact layout is in SPEC. Working state is
restored at dispatch and committed before a suspension response. Invalid
continuations do not clear or overwrite the record. Per-context byte output
banks and per-byte destination maps outlive descriptors. Thus fragment
boundaries need not coincide with AES, GHASH or memory boundaries.

Storage capacity is 4*16*MAX_PAYLOAD_BLOCKS bytes of payload and four times
that many mapping bytes, plus 640 bytes of context and 128 key bytes.
This is capacity accounting, not a synthesized area measurement. Fully
resettable retained storage deliberately favors explicit zeroization over
technology-specific RAM inference.

Scheduler owns two depth2 FIFOs, descriptor fetch and completion/status.
It arbitrates only at descriptor boundaries. Priority is accepted key load,
high DMA, normal DMA, direct enhanced, legacy GCM, raw ECB. A pending or
backpressured completion owns the scheduler. Nonfinal work releases the
engine after saved-state commit and completion retirement. Suspended contexts
alone are not busy. Continuous high priority may starve normal priority.

| Owner | Guarantee to consumer | Required assumption |
| --- | --- | --- |
| Key table | Atomic immutable bound/locked keys | Top provides live binding mask |
| Context store | Reset/clear/write priority, fixed record | Top does not reuse live context |
| Session engine | No speculative plaintext, byte-accurate mapping | Scheduler acknowledges every memory operation |
| Scheduler | One outstanding request, stable stalls | Memory eventually responds or reset cancels |
| Host | Stable accepted descriptors/source; no cross-job write races | Completion returns ownership |
| Memory agent | No stale pre-reset responses | Reset domain integration |

Memory uses aligned 128-bit requests with byte lanes little-endian on the
bus. A conservative byte transaction adapter handles every unaligned offset
without speculative lane writes. Descriptor fetch uses four full read beats;
status uses two full write beats. Payload writes occur only after successful
authentication/finalization and are individually acknowledged. A late memory
fault cannot undo previous acknowledged writes; completion still reports the
fault even if its status write fails.

Reset and end-of-session scrubbing clear the shared crypto state, active
working record, retained payload and destination mappings. Key schedule
expansion is repeated on dispatch from the selected hardware keyslot; no
software key round-trip or reference mount is needed. Keyslot locking lasts
until reset.

Reproduction commands and dependencies are in SPEC. No functional,
synthesis, physical, throughput or side-channel result is inferred from
architecture or reference provenance. Independent acceptance suites remain
required.
