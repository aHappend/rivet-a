# RIVET-A1 architecture

## Structure and ownership

The architecture is a single 128-bit iterative round engine, with one complete
eleven-key cache and one reserved elastic result register. There is no
expansion/computation/output overlap. This keeps accepted-key association
unambiguous, and permits ten uninterrupted rounds even if the output is stalled
before the block starts. Capacity is one block transaction, not two pipelined
transactions.

| Source / instance | Responsibility and dependency |
| --- | --- |
| `rtl/rivet_a1_pkg.sv` | Fixed AES constants, forward/inverse substitution tables, GF byte helpers, SubWord and next-round-key function. |
| `rtl/rivet_a1_sbox.sv` / datapath `u_sbox` | Sixteen parallel combinational byte substitutions, selected by latched direction. |
| `rtl/rivet_a1_shiftrows.sv` / datapath `u_shiftrows` | FIPS column-major forward/inverse byte permutation. |
| `rtl/rivet_a1_mixcolumns.sv` / datapath `u_mixcolumns` | Four combinational forward/inverse GF matrix products. |
| `rtl/rivet_a1_key_schedule.sv` / top `u_key_schedule` | RK0 capture, ten expansion edges, untransformed indexed cache read. Top guarantees no load during computation or held output. |
| `rtl/rivet_a1_datapath.sv` / top `u_datapath` | Initial XOR, round sequencing, direction/tag ownership and elastic output registers. Top guarantees start only with complete keys and an empty engine. |
| `rtl/rivet_a1_top.sv` | Public key/block arbitration, reset-gated readiness, cache interlock and direct output connection. |

Primitives have `state_in[127:0]`, `enc_dec`, `state_out[127:0]` ports.
The key scheduler has `clk`, `rst_n`, `load`, `key_in[127:0]`,
`round_index[3:0]`, `round_key[127:0]`, `expanding`, `loaded`.
It exposes RK[index] for 0..10 and zero for an out-of-range index.
The datapath has `clk`, `rst_n`, `start`, `enc_dec`, `block_in[127:0]`,
`tag_in[7:0]`, `round_key[127:0]`, `out_ready`, `round_index[3:0]`,
`active`, `out_valid`, `out_block[127:0]`, `out_tag_id[7:0]`,
`out_enc_dec`. Top connects its output registers directly to the public channel,
without a completion pipeline stage.

## Representation and arithmetic

Byte `i` is `[127-8*i -: 8]`; state `[r,c]` is byte `4*c+r`.
Byte 0 is `[127:120]` and byte 15 `[7:0]`. A key's four words, in printed
FIPS order, are `[127:96]`, `[95:64]`, `[63:32]`, `[31:0]`.
RotWord rotates the last word by one byte toward its most significant end.
SubWord substitutes its four bytes; the next first word XORs Rcon into its
most significant byte. Subsequent words XOR the newly generated prior word.
Rcon starts at `01` and advances by GF multiplication by `02`.

The forward/inverse byte tables are constants, not state. GF multiplication
reduces by `0x11b` using `xtime`; all arithmetic is unsigned and byte wide.
ShiftRows assigns output row r / column c from input column `(c+r)%4`;
inverse assigns from `(c+4-r)%4`. MixColumns treats each consecutive four
bytes as a column.

The combinational round path is:

```text
state -> selected SubBytes -> selected ShiftRows -> shifted
encryption: shifted -> MixColumns -> XOR round key
decryption: shifted -> XOR round key -> InvMixColumns
final round in either direction: shifted -> XOR round key
```

InvSubBytes commutes with InvShiftRows, so the shared substitution-then-shift
ordering implements ordinary inverse AES. AddRoundKey is before InvMixColumns,
not after it; no equivalent-inverse key transformation is used.

## Storage, timing and boundary contract

The key cache is 11 x 128 = 1408 bits with one combinational indexed read.
One 128-bit state register is reused across the ten rounds. Direction and an
8-bit tag are captured at acceptance; output has separate 128-bit data,
8-bit tag and 1-bit direction registers, plus valid. This storage model does
not imply a particular SRAM macro, technology mapping, frequency or area.

The round counter holds the next computational round, 1..10. When idle,
`round_index` requests RK0 or RK10 from the offered direction so initial
AddRoundKey occurs on the acceptance edge. While active, it requests
RK[round] for encryption or RK[10-round] for decryption, using the captured
direction. No key read bubble occurs.

Handshakes are **pre-edge** values; updates are **post-edge** values:

| Edge / condition | Effect |
| --- | --- |
| Active asynchronous reset | Zero all public outputs and key/state/output storage, cancel all transactions; reset has highest priority. |
| Reset released, first idle clock | `key_ready=1`, `in_ready=0`, no valid result; readiness is combinational and can rise on release. |
| K0 accepted key | Store RK0, deassert loaded, assert expanding/busy. |
| K1..K9 | Store one subsequent round key each clock. |
| K10 | Store RK10, assert loaded, clear expansion/busy. |
| K11 | First possible block acceptance after a key load. |
| B0 accepted block | Initial XOR, capture direction/tag, active high. |
| B1..B9 | Ordinary forward/inverse rounds 1..9. |
| B10 | Final round, output valid/data/tag/direction registered, active low. |
| B11 or later retirement | Clear output valid only on valid/ready; no simultaneous replacement acceptance. |
| Clock after retirement | First possible next key/block acceptance; cached-key minimum initiation interval is 12 clocks. |
| Both idle offers | Key has priority regardless of block direction/tag. |
| Busy offers | No capture, including offers coincident with output retirement. |
| Reset during expansion / processing / held output | Cancel with no later stale completion; require fresh key. |
| Capacity-one, tags 0/255/repeated/wrapped | Legal; no tag comparison or uniqueness filter. |

There are no configurable depths, single-beat packet markers or variable-width
configurations. Capacity one, unloaded input attempts, simultaneous offers,
stalls and reset are the actual degenerate boundaries.

Outside reset:

```text
busy      = expanding || active || out_valid
key_ready = !busy
in_ready  = key_loaded && !busy && !key_valid
```

Reset gates the three status/readiness expressions low. The full external port
contract is:

| Inputs | Outputs |
| --- | --- |
| `clk`, `rst_n` | `key_ready`, `key_loaded` |
| `key_valid`, `key_in[127:0]` | `in_ready` |
| `in_valid`, `in_enc_dec`, `in_block[127:0]`, `in_tag_id[7:0]` | `out_valid`, `out_block[127:0]`, `out_tag_id[7:0]`, `out_enc_dec` |
| `out_ready` | `busy`, `err_unloaded_key` |

Keys and blocks transfer only on their own valid/ready rising edges. Producers
retain valid/payload until acceptance. A complete cache is reusable across any
number of blocks; accepted replacement invalidates it until K10. Blocks cannot
be accepted before loaded. `err_unloaded_key` is permanently zero, selecting the
work order's explicitly permitted cleanly gated alternative. While output valid
and not ready, all four output fields remain unchanged, independent of changes
on input ports. Retired data/tag/direction remain registered until the next
completion or reset. Asynchronous reset invalidates and clears keys, but this
is a functional convention, not a certified zeroization guarantee.

## Integration and independent checks

From the delivered root, the static elaboration command is:

```sh
iverilog -g2012 -t null -s rivet_a1_top \
  rtl/rivet_a1_pkg.sv rtl/rivet_a1_sbox.sv \
  rtl/rivet_a1_shiftrows.sv rtl/rivet_a1_mixcolumns.sv \
  rtl/rivet_a1_key_schedule.sv rtl/rivet_a1_datapath.sv \
  rtl/rivet_a1_top.sv
```

No include paths, generated key tables, private runtime files or debug ports
are required. Integrators supply a clock, assert asynchronous reset, release it
synchronously, handshake a key, wait for loaded, then submit blocks and consume
results. The combinational round must meet the integrator's clock period;
no timing closure, PPA, physical signoff or side-channel protection is claimed.

Independent verification source selectors are `tests/*.py`, separate from design
selectors `rtl/*.sv` and `design/*.md`. Verifier authors and runs
`python3 tests/verify.py` using Python 3, Icarus/vvp and Yosys, retaining actual
versions/results. This includes both official vectors in both directions,
independently derived oracle outputs, seeds 1/17/89 with the admitted transaction
and round-trip counts, key changes, protocol/timing/reset assertions, long
backpressure, five compiling functional mutations and real zero-latch synthesis.
Generated benches, mutation copies, logs and netlists are outputs, not design
sources. Any source-faithful synthesis frontend compatibility handling must be
retained by Verifier; synthesis has not been inferred merely from RTL structure.
Advisory lesson `exp-b7f85aea8b668c87905c6e46` is relevant to preserving output
stalls through cycle-advancing observation helpers, not evidence of this design
passing. The final product report is authored by the shared runtime only after
engineering acceptance and is not an input to these checks.
