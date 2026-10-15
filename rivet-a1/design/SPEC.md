# RIVET-A1 functional specification

## Scope and representation

RIVET-A1 is a fixed-width FIPS 197 AES-128 encryption/decryption engine:
128-bit keys, 128-bit blocks, and ten iterative rounds. `in_enc_dec=0`
encrypts; `in_enc_dec=1` decrypts. There are no product parameters.
Byte 0 occupies `[127:120]`, byte 15 occupies `[7:0]`, and FIPS state
`s[r,c]` is byte `4*c+r`. Hexadecimal blocks and keys therefore use the
ordinary big-endian FIPS printed order without byte reversal.

This is functional RTL IP, not a physical chip signoff, side-channel-resistant
implementation, authenticated cipher mode, or certified security-erasure design.
An external controller must supply any mode of operation, padding and
authentication. Each transaction operates on exactly one block.

## Cycle and degenerate-boundary table

All handshakes use signal values immediately **before** a rising edge.
Updates below are the values **after** that edge. Reset is asynchronous,
active low; reset overrides every transaction and update.

| Edge or boundary | Action and post-edge state |
| --- | --- |
| `rst_n=0` | All public outputs zero, including readiness, status, error, output payload and valid. Cached keys, active block and pending result are canceled. |
| First clock after reset release, no offers | Empty engine, `key_ready=1`, `in_ready=0`, `busy=0`, error zero. No canceled output can reappear. Readiness may already rise combinationally on reset release. |
| K0: `key_valid && key_ready` | Capture RK0, invalidate `key_loaded`, begin expansion; `busy=1`. |
| K1 through K9 | Generate RK1 through RK9, one key per edge; both input readiness signals remain low. |
| K10 | Generate RK10; `key_loaded=1`, expansion ends, `busy=0`. |
| K11 | Earliest block acceptance following K0. |
| B0: `in_valid && in_ready` | Capture tag/direction, initial AddRoundKey with RK0 for encryption or RK10 for decryption; `active=1`, output valid remains zero. |
| B1 through B9 | Execute rounds 1 through 9, one per edge. |
| B10 | Execute final round; `active=0`, `out_valid=1` with result, original tag and direction, irrespective of `out_ready`. |
| B11, if `out_ready=1` | Earliest retirement of the completed output. Readiness was low before this edge; no input transaction is accepted on it. |
| B11 onward, if stalled | Hold all four output fields until a rising edge with `out_valid && out_ready`. |
| Edge after retirement | Earliest new key or block handshake. |
| Simultaneous idle key and block offers | Key wins; block is not accepted. |
| Offers while expansion, computation or result holding is busy | No acceptance or hidden buffering, even on a result-retirement edge. |
| Capacity-one boundary | One active block and one reserved result slot, never overlapping active computation with a pending result or key expansion. |
| Tags 0, 255, repeated or wrapping | All legal opaque identifiers, with no uniqueness requirement. |
| Reset during any operation | Cancel expansion, computation or stalled output immediately; a fresh key is required. |

Fixed AES dimensions make DEPTH/MAX_WORDS and non-power-of-two configuration
cases inapplicable. The actual degenerate boundaries are unloaded keys,
capacity one, simultaneous offers and reset cancellation.

## Public port contract

Every port belongs to `rivet_a1_top`, in one `clk` domain.

| Port | Direction / width | Meaning |
| --- | --- | --- |
| `clk`, `rst_n` | input / 1 each | Rising-edge clock, active-low asynchronous reset. Integrator releases reset synchronously to `clk`. |
| `key_valid`, `key_in` | input / 1, 128 | Key offer and key payload. |
| `key_ready` | output / 1 | Key acceptance permitted. |
| `key_loaded` | output / 1 | Complete RK0..RK10 cache available; remains high across blocks until replacement or reset. |
| `in_valid`, `in_enc_dec` | input / 1 each | Block offer and direction. |
| `in_block`, `in_tag_id` | input / 128, 8 | Block payload and opaque identifier. |
| `in_ready` | output / 1 | Block acceptance permitted. |
| `out_valid` | output / 1 | Registered result available. |
| `out_ready` | input / 1 | Receiver can retire result. |
| `out_block`, `out_tag_id`, `out_enc_dec` | output / 128, 8, 1 | Result and original transaction metadata. |
| `busy` | output / 1 | Expansion, active computation or pending output. |
| `err_unloaded_key` | output / 1 | Always zero: the explicitly selected unloaded-key behavior is clean gating by `in_ready`. |

Outside reset, the exact readiness equations are:

```text
busy      = expanding || active || out_valid
key_ready = !busy
in_ready  = key_loaded && !busy && !key_valid
```

Reset gates readiness, `key_loaded` and `busy` low. Before a complete key
exists, block offers cannot be accepted. Producers hold valid and all payload
fields until their corresponding valid/ready edge; a valid presented while
ready is low is only an offer. Pending old-key output prevents cache replacement.
`out_ready` never stalls computational rounds. On `out_valid && !out_ready`,
`out_valid`, `out_block`, `out_tag_id` and `out_enc_dec` remain unchanged.
Retired payload registers may retain their values until reset or next completion.

## AES transformations and key cache

Encryption uses initial XOR with RK0, then nine rounds of SubBytes, ShiftRows,
MixColumns, AddRoundKey, then SubBytes, ShiftRows, AddRoundKey with RK10.
Decryption uses initial XOR with RK10, then nine rounds of InvShiftRows,
InvSubBytes, AddRoundKey, InvMixColumns using RK9..RK1, then InvShiftRows,
InvSubBytes, AddRoundKey with RK0. The implementation commutes inverse byte
substitution with inverse row permutation, but does not commute inverse column
mixing with key addition. Cached keys are never inverse-transformed.

Substitution tables are the exact forward/inverse FIPS byte substitutions.
Column arithmetic uses GF(2^8), polynomial `0x11b`; forward first-row
coefficients are `02,03,01,01`, inverse `0e,0b,0d,09`, with cyclic matrix rows.
The scheduler expands four 32-bit words with RotWord, SubWord and Rcon1..10.
All eleven untransformed 128-bit keys remain cached between blocks.

## Integration and verification entry

Compile from the delivered project root, package first:

```sh
iverilog -g2012 -t null -s rivet_a1_top \
  rtl/rivet_a1_pkg.sv rtl/rivet_a1_sbox.sv \
  rtl/rivet_a1_shiftrows.sv rtl/rivet_a1_mixcolumns.sv \
  rtl/rivet_a1_key_schedule.sv rtl/rivet_a1_datapath.sv \
  rtl/rivet_a1_top.sv
```

Assert reset, release it synchronously, handshake a key, wait for
`key_loaded`, then handshake a block and consume its result. Keep reset/clock
electrical timing and target implementation constraints external to this RTL.
The earliest cached-key block initiation interval is 12 clocks: B0 acceptance,
B10 completion, B11 retirement, next acceptance at B12.

Design inputs are `rtl/*.sv` and `design/*.md`; independent verification source
inputs are only `tests/*.py`. The independent Verifier owns `tests/verify.py`;
its acceptance entry is `python3 tests/verify.py`, requiring Python 3,
Icarus Verilog, vvp and Yosys. It must cover both official vectors, independent
oracle comparisons, seeded traffic, timing/reset/backpressure, five functional
mutations and substantive zero-latch synthesis. Tool versions and results are
execution evidence, not assumed here. No tool installation is part of delivery.
Generated benches/logs/netlists are outputs, not additional hidden source inputs.
No final product report is a prerequisite for verification.
