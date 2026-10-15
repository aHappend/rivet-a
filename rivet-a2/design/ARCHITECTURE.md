# RIVET-A2 architecture

## Implementation target and ownership

This is portable synthesizable SystemVerilog RTL IP, not a physical chip
signoff. No process, board, clock target, area limit or physical PPA is claimed.
Designer owns `rtl/*.sv` and `design/*.md`; the independent Verifier owns
`tests/*`, including `tests/verify.py`. The mounted Gen-1 source is unchanged.
A2 retains its iterative AES round datapath, forward/inverse transforms and
stored expanded keys, with a shared engine for raw AES and GCM.

## Cycle & Degenerate-Boundary Table

All transfers use signals sampled **pre-edge**; state and registered results
are visible **post-edge**. A newly presented result cannot transfer at the
edge that creates it.

| Boundary | Contract |
| --- | --- |
| Active asynchronous reset | Every public output is zero; keys, state and payload storage clear. |
| First rising edge after reset release | Enables idle readiness post-edge; no transfer occurs at this edge. |
| Idle arbitration | Key load wins over command, which wins over raw input. Lower-priority ready is low. |
| Raw acceptance at E | Initial AddRoundKey at E; round 1 at E+1; result at E+10 or E+14. |
| Stalled result/tag | Entire record stable; no new operation or key load accepted. |
| Last result/tag consumption | No simultaneous new operation; idle readiness resumes post-edge. |
| Capacity 1 | One entry, first equals last; no zero-width pointer. |
| Capacity 3 | Explicit count comparisons, no power-of-two wrapping. |
| Capacity 256 | Counts include 256; capacity is 4096 bytes. |
| Buffer production versus drain | Mutually exclusive phases; no simultaneous read/write ownership. |
| Reset versus any event | Reset wins, aborting all accepted work and clearing all outputs. |
| Invalid accepted stream beat | Abort wins over AES/GHASH launch; scrub then one error tag record. |
| Tag transfer versus payload release | Tag transfers first; first payload is visible post-transfer edge, never earlier. |

## Resource architecture

`rivet_a2_top` instantiates `rivet_a2_aes_core u_aes_core` and
`rivet_a2_ghash u_ghash`. The core instantiates
`rivet_a2_key_schedule u_key_schedule` and `rivet_a2_datapath u_datapath`.
The datapath has `rivet_a2_sbox u_sbox`, `rivet_a2_shiftrows u_shiftrows`,
and `rivet_a2_mixcolumns u_mixcolumns`. These are actual connected transforms.

The AES key schedule stores 60 32-bit words, with 44 used for AES-128.
One new word is calculated per cycle. At a load edge E the first four/eight
words are captured. `loaded` becomes high at E+40 for AES-128 or E+52 for
AES-256. `expanding` is high post-E until that completion edge.
The round key is an asynchronous read of four consecutive words selected by
`round_index`. AES-256 uses the additional SubWord at index modulo 8 equal to 4.

The AES datapath accepts `start` only when neither `active` nor `out_valid`.
It performs initial AddRoundKey on the acceptance edge and one round per
subsequent edge. `rounds` is 10 or 14 and must remain stable for the operation.
`enc_dec=1` selects ordinary inverse AES, including untransformed-key addition
before inverse MixColumns. `out_valid` appears exactly Nr edges after start.
Its output remains stable until `out_ready`, then its data and metadata clear.
The working state clears at completion, and output storage clears at consumption.
The core's key and data readiness exclude each other on key requests.

GHASH is an iterative 128-cycle multiply. Its service inputs are `start`,
`x`, `h`, and synchronous `clear`; outputs are `busy`, one-cycle `done`, and
`result`. A start at E captures x and h, then one MSB-first bit is processed
per edge E+1 through E+128. The result and done appear post-E+128.
The shift is rightward with reduction constant
`128'he1000000000000000000000000000000`. Start is accepted only while idle;
clear has priority and erases operands, accumulator and result.
The top supplies `(previous_hash XOR padded_block)` as x.

## GCM lifecycle and dependency contracts

The controller serializes AES and GHASH service requests. It derives H, derives
E(J0), accepts AAD, then payload, and finally hashes the length block. GCM
always uses forward AES, even when decrypting. It does not cache H across
commands. Each payload counter begins at IV||2; only the low 32 bits increment.
Byte lengths are zero-extended to 64 bits before left shifting by three.

Payload storage contains `MAX_PAYLOAD_BLOCKS` entries of 128 data bits plus five
valid-byte bits. The default is 16 entries (256 payload bytes); supported
capacities are 1..256 (16..4096 bytes). Unsupported values are outside the
contract, not silently clamped. AAD has no resident-capacity limit beyond its
32-bit byte count and is processed one accepted block at a time.

| Resource | Producer / owner | Release and dependency |
| --- | --- | --- |
| Expanded keys | Accepted key load | Retained until rekey/reset; operation admission requires loaded. |
| Stream holding register | Accepted payload beat | Cleared when AES result is consumed; cannot accept another beat meanwhile. |
| Payload entries | Payload AES completion | Private until successful tag transfer; consumed entries scrub immediately. |
| GHASH state | Ordered AAD/ciphertext/length operations | Cleared after tag computation or error. |
| Tag record | Final authentication or scrub completion | Stable until tag_ready; no payload release before transfer. |

Both encryption and decryption buffer their complete payload. Failed tag
comparison is a full-width equality with no bit-position early exit. On failure
or malformed stream, every payload entry is synchronously scrubbed, one per
cycle, **before** tag_valid. Scrubbing does not depend on tag_ready or out_ready.
Transient block registers clear at finalization/abort. Successful entries are
scrubbed on consumption; reset clears the whole buffer asynchronously.
Inactive public payload data and metadata are always zero. These are logical
RTL erasure properties, not claims of remanence or physical side-channel safety.

## Public timeline

For a command transferred at C, post-C busy is high and command admission
closes. H and tag-mask derivations occur before data_ready. A valid stream beat
transferred at D is latched at D; data_ready drops while that beat is processed.
The next section/beat is admitted only after the hash update completes.
After the last payload (or AAD, or empty command), the length block is hashed.
The finalization edge T creates a successful tag record, or begins the
ready-independent scrub preceding a failure/error record.

If tag_valid is stalled, all tag/status fields remain stable. On tag transfer
at U, successful nonempty commands expose payload entry zero post-U.
The first payload can transfer no earlier than U+1. Each consumed entry clears
on its transfer edge and the next entry becomes visible post-edge. The last
entry transfer clears the record and returns idle post-edge. For empty success
or failure/error, the tag transfer itself returns idle post-edge.
All statuses clear at the next accepted key/raw/command operation.

## Reproduction and evidence boundary

Required tools are `python3`, `iverilog`, `vvp`, and `yosys`. From the delivered
root, the independent verification commands are:

```
python3 tests/verify.py --check behavior
python3 tests/verify.py --check sensitivity
python3 tests/verify.py --check synthesis
```

Verifier must record observed tool versions, reference-vector provenance,
fresh result paths, hierarchy evidence and claim-to-evidence links after
execution. No functional, mutation or synthesis acceptance is claimed in this
design handoff. The final product report is not an input to any check.

Designer ran only static syntax/elaboration with Icarus Verilog 12.0 (stable):

```
iverilog -g2012 -t null -s rivet_a2_top rtl/rivet_a2_pkg.sv rtl/rivet_a2_aes_core.sv rtl/rivet_a2_datapath.sv rtl/rivet_a2_ghash.sv rtl/rivet_a2_key_schedule.sv rtl/rivet_a2_mixcolumns.sv rtl/rivet_a2_sbox.sv rtl/rivet_a2_shiftrows.sv rtl/rivet_a2_top.sv
```

It exited zero with no diagnostics. Exact command, RTL hashes, tool-version
output, times and raw logs are retained in
`evidence/preparation/designer-static-20261015T163638676002Z/receipt.json`.
This is advisory static evidence only, not functional or synthesis acceptance.
Other required tool versions remain to be established by Verifier.
