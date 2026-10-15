"""Requirement-to-stimulus mapping; all expected bytes come from reference.py.

Public tests cross both key sizes/directions with every partial byte count at
capacity 16; 1/3 add single-entry/non-power-of-two boundaries; 256 runs full
4096-byte encryption and decryption. These are directed/seeded tests, not formal
proof or a full parameter cross-product.
"""

import random
from reference import aes, blocks, gcm


def svhex(data, bits=None):
    bits = bits or len(data) * 8
    return f"{bits}'h{data.hex().zfill(bits // 4)}"


class Stimulus:
    def __init__(self, capacity, seed=1701):
        self.capacity = capacity
        self.rng = random.Random(seed)
        self.lines = []
        self.cases = []
        self.counts = dict(keys=0, raw=0, tags=0, payload=0, beats=0, errors=0)
        self.case = 0

    def emit(self, line):
        self.lines.append(line)

    def mark(self, label, **details):
        self.case += 1
        self.emit(f'case_id = {self.case}; $display("CASE {self.case} {label}");')
        self.cases.append(dict(id=self.case, label=label, **details))

    def random(self, n):
        return self.rng.randbytes(n)

    def load(self, key, priority=False):
        low = self.random(16) if len(key) == 16 else b""
        self.emit(f"load_key({svhex(key + low)}, {int(len(key) == 32)}, {int(priority)});")
        self.counts["keys"] += 1

    def raw(self, key, value, dec, ident):
        expected = aes(key, value, dec)
        self.mark("raw", key_bits=len(key) * 8, decrypt=dec,
                  input=value.hex(), expected=expected.hex())
        self.emit(f"raw_start({svhex(value)}, {int(dec)}, 8'd{ident});")
        self.emit(f"raw_result({svhex(expected)}, {int(dec)}, 8'd{ident}, "
                  f"{10 if len(key) == 16 else 14});")
        self.counts["raw"] += 1

    def begin(self, dec, iv, aad_len, payload_len, expected, success=True):
        self.emit(f"command({int(dec)}, {svhex(iv)}, 32'd{aad_len}, "
                  f"32'd{payload_len}, {svhex(expected)}, {int(success)});")

    def beat(self, aad, b, count=None):
        n = len(b) if count is None else count
        # Random nonzero unused bytes distinguish ignore/zero-pad from clean inputs.
        value = b + self.random(16 - len(b))
        self.emit(f"beat({int(aad)}, {svhex(value)}, 5'd{n}, {self.rng.randrange(4)});")
        self.counts["beats"] += 1

    def finish(self, tag, dec, payload, fail=False, error=False):
        n = len(blocks(payload))
        self.emit(f"tag_result({svhex(tag)}, {int(dec and not fail and not error)}, "
                  f"{int(fail)}, {int(error)}, {n}, {int(dec)});")
        self.counts["tags"] += 1
        self.counts["errors"] += int(error)
        for i, b in enumerate(blocks(payload)):
            self.emit(f"payload_result({svhex(b.ljust(16, bytes(1)))}, 5'd{len(b)}, "
                      f"{int(dec)}, {int(i == n - 1)}, {self.rng.randrange(5)});")
            self.counts["payload"] += 1
        self.emit("quiet(3); wait_idle();")

    def gcm(self, key, iv, aad, plain, dec, corruption=None, bit=None):
        ct, tag = gcm(key, iv, aad, plain)
        sent_aad, sent_iv, sent_ct, expected = aad, iv, ct, tag
        if corruption == "tag":
            expected = (int.from_bytes(tag, "big") ^ (1 << bit)).to_bytes(16, "big")
        elif corruption == "aad":
            sent_aad = bytes([aad[0] ^ 128]) + aad[1:]
        elif corruption == "iv":
            sent_iv = bytes([iv[0] ^ 1]) + iv[1:]
        elif corruption == "ciphertext":
            sent_ct = bytes([ct[0] ^ 1]) + ct[1:]
        fail = corruption is not None
        calculated_tag = tag
        if dec and fail and corruption != "tag":
            # GCTR is symmetric; recover the modified message independently,
            # then compute the tag on exactly the ciphertext supplied to pins.
            decoded, _ = gcm(key, sent_iv, b"", sent_ct)
            _, calculated_tag = gcm(key, sent_iv, sent_aad, decoded)
        self.mark("gcm-" + (corruption or "valid"), key_bits=len(key) * 8,
                  decrypt=dec, aad_bytes=len(aad), payload_bytes=len(plain),
                  tag_bit=bit, expected_tag=calculated_tag.hex())
        self.begin(dec, sent_iv, len(aad), len(plain), expected, not fail)
        for b in blocks(sent_aad):
            self.beat(True, b)
        for b in blocks(sent_ct if dec else plain):
            self.beat(False, b)
        self.finish(calculated_tag, dec, b"" if fail else (plain if dec else ct), fail)
        if corruption == "tag":
            self.emit("if (failure_latency < 0) failure_latency = last_tag_latency;")
            self.emit('else if (failure_latency != last_tag_latency) fail("TAG_POSITION_TIMING");')

    def errors(self, key):
        for n in (16 * self.capacity + 1, 0xFFFFFFFF):
            self.mark("oversize", payload_bytes=n)
            self.begin(False, bytes(12), 0, n, bytes(16), False)
            self.finish(bytes(16), False, b"", error=True)
        for count, section, an, pn in [
            (0, True, 16, 0), (17, True, 16, 0), (31, True, 16, 0),
            (15, True, 16, 0), (2, False, 0, 1),
            (16, False, 16, 0), (16, True, 0, 16),
        ]:
            self.mark("malformed", valid_bytes=count, section=section,
                      aad_bytes=an, payload_bytes=pn)
            self.begin(False, bytes(12), an, pn, bytes(16), False)
            self.beat(section, self.random(16), count)
            self.finish(bytes(16), False, b"", error=True)
        if self.capacity > 1:
            self.mark("aad-after-payload")
            self.begin(True, bytes(12), 0, 17, bytes(16), False)
            self.beat(False, self.random(16))
            self.beat(True, self.random(1))
            self.finish(bytes(16), True, b"", error=True)
        self.gcm(key, self.random(12), b"recovery", b"recovered", True)

    def resets(self, key):
        self.mark("reset-expansion")
        self.emit("wait_idle(); key_valid = 1; key_in = 0; key_len_sel = 1; tick();")
        self.emit("key_valid = 0; repeat(9) tick(); reset_dut();")
        self.load(key)
        self.mark("reset-raw-processing")
        self.emit(f"raw_start({svhex(self.random(16))}, 0, 8'd99);")
        self.emit("repeat(3) tick(); reset_dut();")
        self.load(key)
        self.mark("reset-raw-output-stall")
        value = self.random(16)
        self.emit(f"raw_start({svhex(value)}, 1, 8'd77);")
        self.emit(f"repeat({14 if len(key) == 32 else 10}) tick();")
        self.emit('if (!out_valid) fail("RESET_RAW_STALL_NOT_REACHED");')
        self.emit("repeat(3) tick(); reset_dut();")
        self.load(key)
        self.mark("reset-ghash-processing")
        self.begin(False, self.random(12), 32, 0, bytes(16))
        self.beat(True, self.random(16))
        self.emit("repeat(17) tick(); reset_dut();")
        self.load(key)
        for stage in ("processing", "tag-stall", "output-stall", "failed-tag-stall"):
            self.mark("reset-gcm-" + stage)
            plain, iv = self.random(16), self.random(12)
            ct, tag = gcm(key, iv, b"", plain)
            bad = stage == "failed-tag-stall"
            expected = bytes(16) if bad else tag
            self.begin(True, iv, 0, 16, expected, not bad)
            self.beat(False, ct)
            if stage == "processing":
                self.emit("repeat(4) tick();")
            elif stage in ("tag-stall", "failed-tag-stall"):
                self.emit(f"begin : reset_tag_wait_{self.case} integer n; n=0;")
                self.emit('while (!tag_valid) begin tick(); n=n+1; if(n>5000) fail("RESET_TAG_PROGRESS"); end')
                self.emit('if (out_valid) fail("RESET_PREAUTH"); repeat(3) tick(); end')
            else:
                self.emit(f"tag_result({svhex(tag)}, 1, 0, 0, 1, 1);")
                self.counts["tags"] += 1
                self.emit('if (!out_valid) fail("RESET_OUTPUT_STALL_NOT_REACHED");')
                self.emit("repeat(3) tick();")
            self.emit("reset_dut();")
            self.load(key)
            self.gcm(key, self.random(12), b"", b"fresh epoch", True)

    def build(self, anchors, probe=False):
        self.mark("unloaded-backpressure")
        self.emit("in_valid=1; cmd_valid=1; repeat(4) begin")
        self.emit('tick(); if(in_ready || cmd_ready || err_unloaded_key || busy) fail("UNLOADED_BACKPRESSURE"); end')
        self.emit("in_valid=0; cmd_valid=0;")
        if probe:
            key = bytes(range(32))
            self.load(key, True)
            self.raw(key, bytes(range(16)), False, 19)
            self.raw(key, bytes(range(16)), True, 23)
            self.gcm(key, bytes(12), b"aad partial", b"payload partial", False)
            self.gcm(key, bytes(12), b"aad partial", b"payload partial", True)
            self.gcm(key, bytes(12), b"aad partial", b"payload partial", True, "tag", 0)
            self.errors(key)
            self.resets(key)
        elif self.capacity == 256:
            for size in (16, 32):
                key = self.random(size)
                self.load(key)
                plain = self.random(4096)
                iv, aad = self.random(12), self.random(33)
                self.gcm(key, iv, aad, plain, False)
                self.gcm(key, iv, aad, plain, True)
                self.errors(key)
        else:
            # Published expectations are also compared directly against the RTL.
            for row in anchors:
                key = bytes.fromhex(row["key"])
                if row["kind"] == "AES":
                    self.load(key, True)
                    self.raw(key, bytes.fromhex(row["plaintext"]), False, 41)
                    self.raw(key, bytes.fromhex(row["ciphertext"]), True, 42)
                elif len(bytes.fromhex(row["plaintext"])) <= self.capacity * 16:
                    self.load(key)
                    for dec in (False, True):
                        self.gcm(key, bytes.fromhex(row["iv"]), bytes.fromhex(row["aad"]),
                                 bytes.fromhex(row["plaintext"]), dec)
            for size in (16, 32):
                for key in (bytes(size), b"\xff" * size, bytes(range(size)), self.random(size)):
                    self.load(key, True)
                    for b in (bytes(16), b"\xff" * 16, bytes(range(16)), self.random(16)):
                        for dec in (False, True):
                            self.raw(key, b, dec, self.rng.randrange(256))
                    iv = self.random(12)
                    for dec in (False, True):
                        self.gcm(key, iv, key[:16] * 2, key[:16], dec)
                key = self.random(size)
                self.load(key)
                # Both directions, both sizes and every legal final valid_bytes.
                for n in range(1, 17):
                    length = n if self.capacity == 1 else 16 + n
                    plain, aad, iv = self.random(length), self.random(32 + n), self.random(12)
                    for dec in (False, True):
                        self.gcm(key, iv, aad, plain, dec)
                # AAD can exceed resident payload capacity.
                for an, pn in [(0, 0), (65, 0), (0, 16), (0, 1),
                               (37, self.capacity * 16), (17, self.capacity * 16 - 1)]:
                    for dec in (False, True):
                        self.gcm(key, self.random(12), self.random(an), self.random(pn), dec)
                self.errors(key)
                if self.capacity == 16:
                    iv, aad, plain = self.random(12), self.random(19), self.random(31)
                    self.emit("failure_latency=-1;")
                    identical_stream = self.rng.getstate()
                    for bit in range(128):
                        self.rng.setstate(identical_stream)
                        self.gcm(key, iv, aad, plain, True, "tag", bit)
                    for fault in ("aad", "iv", "ciphertext"):
                        self.gcm(key, iv, aad, plain, True, fault)
                    for _ in range(20):
                        self.gcm(key, self.random(12), self.random(self.rng.randrange(90)),
                                 self.random(self.rng.randrange(257)), bool(self.rng.randrange(2)))
                self.resets(key)
        for name, count in self.counts.items():
            counter = {"keys": "key_checks", "tags": "tag_checks",
                       "beats": "beat_checks", "errors": "error_checks"}.get(
                           name, f"{name}_checks")
            self.emit(f'if ({counter} != {count}) fail("COVERAGE_{name.upper()}");')
        self.emit('if (reset_checks == 0 || cycles == 0) fail("EMPTY_COVERAGE");')
        return "\n".join(self.lines) + "\n"
