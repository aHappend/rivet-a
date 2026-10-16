# RIVET-A3 integration specification

This document freezes the implementation ABI for the admitted RIVET-A3 work
order. Engineering acceptance is independent of this document. The reference
mount is provenance only; no A2 passing baseline is asserted.

## Clock, ownership and boundaries

One `clk`, asynchronous active-low `rst_n`. All public outputs are zero in
reset. An awake bit permits availability only after the first release edge.
Transfers sample valid and ready immediately before a rising edge; their
effects are visible afterward. Producers hold valid and fields while stalled.
Reset cancels without completion and clears keys, contexts, queues, retained
bytes and crypto state. The memory agent must discard responses from before
reset. Latency is variable.

| Boundary | Pre-edge event | Post-edge effect |
| --- | --- | --- |
| Reset | `rst_n=0` | All storage and outputs zero; no transfer |
| Release | First rising edge with reset released | Awake becomes one |
| Request | `valid && ready` | Exactly one owner acquires request |
| Stall | `valid && !ready` | Owner and fields unchanged |
| Retirement | Output `valid && ready` | Exactly one retirement; dependent release afterward |
| Memory | Final response transfers | Completion only on a subsequent observation |
| Queue | Enqueue and dequeue together | Old head executes; new item remains in FIFO order |
| Context | Clear and write together | Reset wins, then clear, then write |
| Sticky error | W1C and new error together | New error wins |
| Capacity | 1, 3, 16, 256 blocks | Exact byte capacity; no power-of-two wrap assumption |
| Illegal capacity | 0 or 257 | Explicit parameter diagnostic; not clamped |
| Single fragment | `first && last` | Full initialization and finalization, including empty data |

## Fixed public ABI

`rivet_a3_top`, parameter `MAX_PAYLOAD_BLOCKS=16` (legal 1..256), preserves
all ports of `rivet_a2_top`, and adds exactly the keyslot/result, direct
descriptor, DMA submission/completion, memory and CSR ports in the admitted
work order. Four slots and four contexts are fixed. No debug ports are added.
AES byte zero is bits127:120; memory lane i is bits8*i+:8.
AES-128 uses key bits255:128; unused key bits are zeroed. Raw ECB and legacy
GCM bind slot0. `key_loaded` means slot0 valid. Key loads reject locked or
live-bound slots atomically, with a retained result.

All scalar signals below are one bit unless a width is given. `valid/ready`
channels hold their payload until transfer; only one key result and one CSR
response may be outstanding. All signals are synchronous to `clk`.

| Channel | Inputs to top | Outputs from top |
| --- | --- | --- |
| Key | key_valid, key_in[255:0], key_len_sel, key_slot_id[1:0], key_lock, key_result_ready | key_ready, key_loaded, key_result_valid, key_result_code[3:0] |
| Raw ECB | in_valid, in_enc_dec, in_block[127:0], in_tag_id[7:0] | in_ready, err_unloaded_key |
| Legacy command | cmd_valid, cmd_decrypt, iv_in[95:0], aad_bytes[31:0], payload_bytes[31:0], expected_tag[127:0] | cmd_ready |
| Streaming input | data_valid, data_is_aad, data_in[127:0], valid_bytes[4:0] | data_ready |
| Shared output | out_ready | out_valid, out_block[127:0], out_tag_id[7:0], out_enc_dec, out_valid_bytes[4:0], out_is_gcm |
| Legacy tag | tag_ready | tag_valid, tag_out[127:0], tag_match, auth_fail, protocol_error |
| Direct descriptor | task_valid, task_descriptor[511:0] | task_ready |
| DMA queue | dma_submit_valid, dma_desc_addr[31:0], dma_priority, dma_cookie[7:0] | dma_submit_ready |
| Completion | completion_ready | completion_valid, completion_cookie[7:0], completion_ctx_id[1:0], completion_code[3:0], completion_final, completion_tag[127:0] |
| Memory request | mem_req_ready | mem_req_valid, mem_req_write, mem_req_addr[31:0], mem_req_wdata[127:0], mem_req_wstrb[15:0] |
| Memory response | mem_rsp_valid, mem_rsp_rdata[127:0], mem_rsp_error | mem_rsp_ready |
| CSR | csr_valid, csr_write, csr_addr[7:0], csr_wdata[31:0], csr_rsp_ready | csr_ready, csr_rsp_valid, csr_rdata[31:0], csr_error |
| Activity | - | busy |

`dma_priority=1` selects high priority. Enhanced direct and legacy data
channels cannot mix. Each accepted input beat has exactly min(16, remaining
section bytes) valid MSB bytes, first AAD then payload. Invalid section/count
aborts consumed work with code6, not truncated success. Enhanced output ID
is zero; raw output ID is preserved; direction is echoed. Only GCM output
sets `out_is_gcm`. Legacy tag/auth/protocol flags retain the most recent
legacy/shared engine result until another accepted crypto operation.

Codes: 0 OK; 1 INVALID_DESCRIPTOR_OR_REGISTER; 2 INVALID_KEY;
3 LOCKED_OR_BOUND; 4 INVALID_CONTEXT; 5 CAPACITY_OR_LENGTH;
6 STREAM_PROTOCOL; 7 AUTH_FAIL; 8 MEMORY_ERROR. Others reserved.

CSR map: 00 RO ID 52415633; 04 RO busy bit0; 08 RO valid bits3:0,
locked bits7:4; 0c RO live bits3:0; 10 sticky code bitmap, W1C;
14 WO idle-only context abort, index bits1:0. Reserved accesses/bits error.
Abort rejects any pending DMA, active engine or reserved response/output.
Suspended contexts alone do not make busy. Key data is never readable.

## Descriptor and status ABI

64-byte descriptor, little-endian words. Byte i is descriptor[8*i+:8].
Offsets: 0 control; 4 AAD address; 8 source; 12 destination; 16 status;
20 AAD byte count; 24 payload byte count; 28..39 chronological IV;
40..55 chronological expected tag; 56 cookie; 57..63 zero.
Control bits1:0 mode (ECB0 CTR1 GCM2); bit2 decrypt; bits4:3 context;
bits6:5 slot; bit7 first; bit8 last; all others zero.
Direct descriptors ignore addresses. DMA descriptor and status addresses are
16-byte aligned. Accessed ranges must not wrap 32-bit addresses. Exact
in-place payload is legal; other input/output overlap is rejected. Descriptor
and status storage cannot overlap active ranges. Software keeps inputs stable
and prevents writable overlap across outstanding jobs.

DMA status is 32 bytes: LE32 code, LE32 cumulative payload bytes, external
cookie at8, context at9, final bit at10, zero11..15, chronological tag16..31.
Tags are zero except successful final GCM. Fetch errors with unknown status
address return completion only. Write errors become MEMORY_ERROR, including
status-write failure. Prior acknowledged writes cannot be rolled back.
Authentication failure never writes payload.

## Context record: 1280 bits, frozen before RTL implementation

`rivet_a3_context_store` has the exact admitted write/read/clear interface.
Read is combinational and reset-gated; reset dominates clear dominates write.
Unused bits are zero. All active cryptographic continuation state is loaded
from this record and committed back before nonfinal completion.

| Bits | Field |
| --- | --- |
| 0 | Live |
| 2:1 | Mode |
| 3 | Decrypt |
| 4 | DMA origin |
| 6:5 | Keyslot |
| 7 | Payload phase begun |
| 103:8 | IV |
| 231:104 | GHASH accumulator |
| 359:232 | H |
| 487:360 | Tag mask |
| 615:488 | Next GCTR counter |
| 679:616 | AAD bits |
| 743:680 | Data bits |
| 871:744 | Pending GHASH bytes, MSB first, zero padded |
| 876:872 | Pending GHASH byte count (0..15) |
| 1004:877 | Remaining keystream, next byte at MSB |
| 1009:1005 | Remaining keystream byte count (0..16) |
| 1022:1010 | Retained payload byte count (0..4096) |
| 1023 | Counter exhausted |
| 1279:1024 | Reserved zero |

Four independent payload byte banks each retain `16*MAX_PAYLOAD_BLOCKS`
bytes, with one 32-bit destination address per byte. Per-byte mappings preserve
arbitrary fragment/destination boundaries. Storage remains reserved through
final completion and drain; consumed/scrubbed locations are cleared.

## Internal channels and required hierarchy

Top instances: `u_key_table`, `u_context_store`, `u_scheduler_dma`,
`u_aes_core`, `u_ghash`. AES contains separate adapted key schedule,
datapath, S-box, ShiftRows and MixColumns; GHASH performs polynomial multiply.
Adapted primitives originate from the supplied A2 RTL; module/package names
are changed to A3 and crypto reset is additionally used for engine scrubbing.

Scheduler owns depth2 high/normal address+cookie queues, descriptor fetch,
the sole memory transaction, status and completion. Dispatch is the admitted
512-bit descriptor, DMA flag and 8-bit cookie ready/valid channel. Direct
descriptors participate in the same dispatcher without entering DMA queues.
`enable` permits selection only when top can accept work and no key wins.
`queued` reports either queue nonempty; `active` includes fetch/status and
completion reservations. Strict high-before-normal FIFO selection is
nonpreemptive; normal traffic can starve indefinitely under high traffic.

Additional scheduler/top byte-memory channel:
`io_valid/io_ready`, `io_write`, `io_addr[31:0]`, `io_wbyte[7:0]`;
`io_rsp_valid/io_rsp_ready`, `io_rbyte[7:0]`, `io_error`.
Scheduler translates one byte operation into an aligned 128-bit request;
writes enable exactly its lane and reads use zero data/strobes. There is
exactly one outstanding read OR write, including descriptor/status traffic.
Top waits for each byte response before consuming input or advancing output.
This deliberately serial implementation claims no fixed throughput.

The result channel adds `result_bytes[31:0]` to the admitted
code/context/final/tag fields. `retire` pulses after public completion
retirement; top cannot emit direct payload before it. `event_code[3:0]`
reports scheduler errors to sticky CSR. `dispatch_desc_addr[31:0]`
lets top validate fetched descriptor overlap. Result tags are already
authentication-gated. Scheduler never reads context payload directly.
`fault_valid/fault_ready` is a scheduler-to-top status-write-fault handshake.
After a status fault, completion is withheld until top has scrubbed any
consumed session and acknowledges the fault. Rejected, unconsumed
continuations retain their pre-existing context even on status failure.
`result_status_allowed` suppresses status writes when descriptor validation
finds that status storage is misaligned, wraps, or overlaps input/
output storage; such descriptors still produce an error completion.

## Cryptographic/session semantics

ECB requires no AAD and whole blocks, first+last. CTR requires no AAD,
first+last, starts IV||1, uses AES encryption in both directions, inc32 only.
GCM uses J0=IV||1 and first counter IV||2, GHASH ciphertext and aggregate
64-bit big-endian lengths. All128 tag bits compare; bad tags release no
plaintext. Partial outputs are MSB-valid, zero elsewhere.

GCM arbitrary-byte fragments preserve pending hash bytes, unused keystream,
counter, phase, lengths and output mapping. AAD is padded only at the
session's transition to data/finalization, ciphertext only at finalization.
First requires an unused context. Continuation matches IV, mode, direction,
keyslot and origin; invalid continuations leave saved state intact. Once
data begins, later nonempty AAD is rejected. Nonfinal commits release the
engine but not the key binding. All enhanced output, in all modes and
directions, is retained until finalization. Capacity is cumulative per context.
Overflow/counter exhaustion is rejected before reuse. Software supplies
unique GCM IVs; hardware does not enforce nonce uniqueness.

Legacy GCM uses tag-before-payload, including failed-plaintext withholding.
Legacy unloaded attempts report `err_unloaded_key` without accepting work.
Enhanced outputs use tag ID0; raw ECB preserves its transaction ID.

## Verification ownership and reproduction

Designer owns RTL and this documentation, not tests. Independent Verifier
authors `tests/verify.py` and all functional/reference/synthesis helpers.
Required dependencies: Python3, Icarus (`iverilog`, `vvp`), Yosys. Versions
are established by the environment suite, not assumed by this specification.
No installation or executed functional result is claimed here.

Integrate all twelve `rtl/*.sv` source files with `rivet_a3_pkg.sv` read first
and top `rivet_a3_top`. Hold reset low, drive input valids low, then release
reset and wait for readiness after a rising edge. Load the desired keyslots
and consume their results before issuing dependent work. A suspended context
continues to bind its slot until final retirement or successful CSR abort.
Default retained capacity is 256 bytes per context. The source does not
import the reference mount or any private runtime state.

From the delivered root, run:

```
python3 tests/verify.py --suite environment --output evidence/environment
python3 tests/verify.py --suite behavior --seeds 17,89,203 --capacities 1,3,16 --output evidence/behavior
python3 tests/verify.py --suite boundaries --output evidence/boundaries
python3 tests/verify.py --suite synthesis --output evidence/synthesis
python3 tests/verify.py --suite checker-sensitivity --output evidence/checker-sensitivity
python3 tests/verify.py --suite reproduce --output evidence/reproduce
```

Deliverable inputs are `rtl/*.sv`, this file, `design/ARCHITECTURE.md`,
and Verifier-owned `tests/*`. Runtime metadata, reference mount and generated
evidence are not product dependencies. Compile the package before modules.
Generic synthesis is not fabrication, timing closure, power or side-channel
sign-off. The final product report is runtime-owned after acceptance.
