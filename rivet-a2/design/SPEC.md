# RIVET-A2 integration specification

## Sources and scope

Top: `rtl/rivet_a2_top.sv`, module `rivet_a2_top`.
Compile `rtl/rivet_a2_pkg.sv` first, then all other `rtl/*.sv`.
This extends the Gen-1 iterative architecture with AES-256 and SP 800-38D GCM.
It preserves raw AES-128 encryption/decryption semantics, not pin compatibility:
the key port is now 256 bits.

Parameter `integer MAX_PAYLOAD_BLOCKS=16` supports positive values 1..256.
Payload limits apply equally to encrypt and decrypt. Unsupported parameters are
outside the supported product range, with no silent clamping.

## Ports

All ports not annotated below are one bit. Inputs and outputs are logic.

| Direction | Ports | Meaning |
| --- | --- | --- |
| input | clk, rst_n | Rising-edge clock, asynchronous active-low reset. |
| input | key_valid, key_in[255:0], key_len_sel | Key request; 0 selects upper 128 bits, 1 selects all 256 bits. |
| output | key_ready, key_loaded | Key acceptance readiness and completed expansion. |
| input | in_valid, in_enc_dec, in_block[127:0], in_tag_id[7:0] | Raw AES request; 0 encrypts, 1 decrypts. |
| output | in_ready | Raw acceptance readiness. |
| input | out_ready | Consumption of either kind of payload output. |
| output | out_valid, out_block[127:0], out_tag_id[7:0], out_enc_dec | Payload record. |
| output | out_valid_bytes[4:0], out_is_gcm | Exact payload byte count and GCM discriminator. |
| output | busy, err_unloaded_key | Busy includes expansion, processing, scrubbing, tag wait and payload drain; error is always zero. |
| input | cmd_valid, cmd_decrypt, iv_in[95:0] | GCM command and 96-bit IV. |
| input | aad_bytes[31:0], payload_bytes[31:0], expected_tag[127:0] | Exact section byte counts and full decryption tag. |
| output | cmd_ready | GCM command acceptance readiness. |
| input | data_valid, data_is_aad, data_in[127:0], valid_bytes[4:0] | Stream beat; section 1=AAD, 0=payload. |
| output | data_ready | Stream beat acceptance readiness. |
| input | tag_ready | Tag/status consumption. |
| output | tag_valid, tag_out[127:0], tag_match, auth_fail, protocol_error | One tag/status record per accepted command. |

## Ordering and handshakes

Only pre-edge valid AND ready accepts a request. Inputs are captured only on
that handshake. Requests while not ready do nothing. Idle arbitration is
key > command > raw, and ready signals prevent simultaneous acceptance.
Keys are accepted only with no pending output/tag. Raw/commands require a
fully expanded key; unloaded requests are backpressured, not error transactions.
Keys persist until reset or replacement. No same-edge output/input replacement.

All public outputs are zero while reset is asserted. On the first rising edge
after release, idle readiness may appear; there was no pre-edge readiness and
thus no transfer at that edge. Reset aborts expansion and all operations.
A result created post-edge cannot transfer until a subsequent edge.
Stalled tag/payload records are bitwise stable. Inactive payload data and
metadata are zero. Status fields persist until the next accepted operation;
tag_out clears when tag_valid clears.

Raw AES uses FIPS 197 initial AddRoundKey, 10/14 rounds and no final MixColumns.
A raw input at E produces out_valid post-E+10/14, with captured tag/direction.
Raw out_valid_bytes=16 and out_is_gcm=0. See ARCHITECTURE.md for internal
service latencies and the pre-edge/post-edge boundary table.

## GCM formatting and authentication

First byte is bits [127:120], with AES column-major state mapping.
J0 = IV||32'h00000001; H = E_K(0); first payload counter = IV||2.
Only the low 32 counter bits increment. GCM uses forward AES for both
directions. GHASH consumes padded AAD, padded ciphertext, then the 128-bit
block `[aad_bit_length]64 || [payload_bit_length]64`. Counts are widened before
multiplication by eight. Tag = E_K(J0) XOR final GHASH.

Transfer exactly aad_bytes of AAD followed by exactly payload_bytes of payload.
Zero-length sections consume no beats. Every beat has exactly
min(16, remaining section bytes) valid bytes, in 1..16. Unused low-order bytes
are ignored, zero-padded before GHASH, and zero in partial payload output.
Decryption authenticates input ciphertext; encryption authenticates its
generated ciphertext.

Incorrect accepted section indicators or valid_bytes abort. An oversized
command is accepted as an error transaction without stream consumption.
Both cases scrub storage, return exactly one tag record with tag_out=0,
protocol_error=1, tag_match=0, auth_fail=0, and never release payload.
Unaccepted extra traffic has no effect. Recovery is automatic after that tag
is consumed; a new command may then be accepted.

Every successful computation produces one stable full-width tag record,
including empty messages. Encryption has tag_match=0, auth_fail=0.
Correct decryption has tag_match=1, auth_fail=0. Incorrect decryption has
tag_match=0, auth_fail=1, and returns the calculated tag only after scrubbing
all tentative plaintext. All 128 expected-tag bits participate in comparison.
No GCM payload is publicly visible before successful tag transfer.

After successful tag consumption, payload drains in order, with out_is_gcm=1,
out_tag_id=0, out_enc_dec=cmd_decrypt and the exact out_valid_bytes.
Failures and empty messages return idle on tag consumption without payload.
New operations remain blocked throughout tag wait and payload drain.
The caller must ensure unique encryption IVs under each key; persistent nonce
reuse detection is not implemented. Only 96-bit IVs and 128-bit tags are supported.

## Claim-to-evidence index

| Claim | Design source | Independent evidence |
| --- | --- | --- |
| AES-128/256 and inverse rounds | key_schedule, datapath, transformation modules | Pending Verifier behavior results. |
| GCM/AAD/partial blocks and authentication | top, ghash | Pending Verifier behavior results. |
| Plaintext-release protection and recovery | top buffer/scrub/tag/drain FSM | Pending Verifier adversarial results. |
| Functional defect sensitivity | Production RTL remains unchanged by mutation runs | Pending Verifier sensitivity results. |
| Generic synthesizability and required hierarchy | rtl/*.sv | Pending Verifier synthesis results. |

These entries identify implementation intent, not passing acceptance.
Verifier owns the executable checks and their actual result index.
