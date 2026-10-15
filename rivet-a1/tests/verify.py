#!/usr/bin/env python3
"""Independent FIPS 197/public-pin checks; default execution includes every gate.

Requirement mapping:
  oracle_self_check: literal Appendix B/C.1, encrypt and decrypt.
  directed: reset/cancellation, unloaded gating, priority, capacity, exact K/B
            edges, cached keys, tag extremes and one/32/40-cycle output stalls.
  seed_1/17/89: each 64 blocks, eight keys, sixteen checked round trips,
                continuous offers, concurrent key/block offers and random stalls.
  mutations: five compiling functional changes, rejected by the same scoreboard.
  synthesis: complete source-faithful hierarchy, meaningful state, zero latches.

All protocol expectations use accepted public transactions and elapsed edges.
There are no hierarchical DUT observations or third-party oracle dependencies.
"""

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
RTL_NAMES = [
    "rivet_a1_pkg.sv", "rivet_a1_sbox.sv", "rivet_a1_shiftrows.sv",
    "rivet_a1_mixcolumns.sv", "rivet_a1_key_schedule.sv",
    "rivet_a1_datapath.sv", "rivet_a1_top.sv",
]
TOOL_TIMEOUT = 7200
OFFICIAL = [
    ("appendix_b", "2b7e151628aed2a6abf7158809cf4f3c",
     "3243f6a8885a308d313198a2e0370734", "3925841d02dc09fbdc118597196a0b32"),
    ("appendix_c1", "000102030405060708090a0b0c0d0e0f",
     "00112233445566778899aabbccddeeff", "69c4e0d86a7b0430d8cdb78070b4c55a"),
]


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def hashes(paths):
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths}


class CheckFailure(AssertionError):
    def __init__(self, assertion, **details):
        self.finding = {"assertion": assertion, **details}
        super().__init__(json.dumps(self.finding, sort_keys=True))


class ToolFailure(RuntimeError):
    pass


def require(condition, assertion, **details):
    if not condition:
        raise CheckFailure(assertion, **details)


def multiply(a, b):
    result = 0
    while b:
        if b & 1:
            result ^= a
        a <<= 1
        if a & 0x100:
            a ^= 0x11B
        b >>= 1
    return result


def reciprocal(value):
    if value == 0:
        return 0
    power, result, base = 254, 1, value
    while power:
        if power & 1:
            result = multiply(result, base)
        base = multiply(base, base)
        power >>= 1
    return result


def rotate(value, count):
    return ((value << count) | (value >> (8 - count))) & 255


def substitute(value):
    inv = reciprocal(value)
    return inv ^ rotate(inv, 1) ^ rotate(inv, 2) ^ rotate(inv, 3) ^ rotate(inv, 4) ^ 0x63


def inverse_substitute(value):
    return reciprocal(rotate(value, 1) ^ rotate(value, 3) ^ rotate(value, 6) ^ 0x05)


FORWARD = tuple(substitute(i) for i in range(256))
INVERSE = tuple(inverse_substitute(i) for i in range(256))


def expand_key(key):
    words = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    rcon = 1
    for i in range(4, 44):
        temp = words[-1][:]
        if i % 4 == 0:
            temp = [FORWARD[x] for x in temp[1:] + temp[:1]]
            temp[0] ^= rcon
            rcon = multiply(rcon, 2)
        words.append([a ^ b for a, b in zip(words[i - 4], temp)])
    return [sum(words[i:i + 4], []) for i in range(0, 44, 4)]


def shift(state, inverse):
    return [state[4 * ((col + (-row if inverse else row)) % 4) + row]
            for col in range(4) for row in range(4)]


def mix(state, inverse):
    matrix = ((14, 11, 13, 9), (9, 14, 11, 13),
              (13, 9, 14, 11), (11, 13, 9, 14)) if inverse else (
                  (2, 3, 1, 1), (1, 2, 3, 1), (1, 1, 2, 3), (3, 1, 1, 2))
    result = []
    for col in range(4):
        for row in matrix:
            value = 0
            for coefficient, byte in zip(row, state[4 * col:4 * col + 4]):
                value ^= multiply(byte, coefficient)
            result.append(value)
    return result


def crypt(key, block, inverse):
    keys = expand_key(key.to_bytes(16, "big"))
    state = list(block.to_bytes(16, "big"))
    order = list(range(10, -1, -1)) if inverse else list(range(11))
    state = [a ^ b for a, b in zip(state, keys[order[0]])]
    for step, index in enumerate(order[1:], 1):
        if inverse:
            state = [INVERSE[x] for x in shift(state, True)]
            state = [a ^ b for a, b in zip(state, keys[index])]
            if step != 10:
                state = mix(state, True)
        else:
            state = shift([FORWARD[x] for x in state], False)
            if step != 10:
                state = mix(state, False)
            state = [a ^ b for a, b in zip(state, keys[index])]
    return int.from_bytes(bytes(state), "big")


def oracle_self_check():
    require(all(INVERSE[FORWARD[x]] == x for x in range(256)),
            "oracle_substitution_bijection")
    results = []
    for name, key, plain, cipher in OFFICIAL:
        k, p, c = (int(x, 16) for x in (key, plain, cipher))
        for direction, source, expected in ((0, p, c), (1, c, p)):
            actual = crypt(k, source, direction)
            require(actual == expected, "oracle_official_vector",
                    vector=name, direction=direction,
                    expected=f"{expected:032x}", actual=f"{actual:032x}")
            results.append({"vector": name, "direction": direction,
                            "key": key, "input": f"{source:032x}",
                            "expected": f"{expected:032x}", "actual": f"{actual:032x}"})
    return results


@dataclass
class Stimulus:
    rst: int = 1
    kv: int = 0
    key: int = 0
    iv: int = 0
    mode: int = 0
    block: int = 0
    tag: int = 0
    ready: int = 1


@dataclass
class Pins:
    kr: int
    kl: int
    ir: int
    ov: int
    block: int
    tag: int
    mode: int
    busy: int
    error: int


class Contract:
    """Transaction obligations and absolute deadlines, not DUT FSM state."""

    def __init__(self):
        self.key = None
        self.loaded = False
        self.key_due = None
        self.work = None
        self.result = None
        self.cycle = 0
        self.counts = Counter()
        self.records = []
        self.key_records = []
        self.hold = 0
        self.max_hold = 0
        self.epoch = 0
        self.last_reset = False
        self.previous_stimulus = None
        self.previous_pins = None

    def begin(self, stimulus):
        if not stimulus.rst:
            if not self.last_reset:
                self.epoch += 1
                self.counts["reset_epochs"] += 1
                if self.key_due is not None:
                    self.counts["reset_expansion"] += 1
                if self.work:
                    self.counts["reset_processing"] += 1
                if self.result:
                    self.counts["reset_held_output"] += 1
            for item in (self.work, self.result):
                if item:
                    item["canceled_at"] = self.cycle
                    self.counts["canceled"] += 1
            self.key = None
            self.loaded = False
            self.key_due = None
            self.work = self.result = None
            self.hold = 0
        self.last_reset = not stimulus.rst

    def expected(self, stimulus):
        if not stimulus.rst:
            return Pins(0, 0, 0, 0, 0, 0, 0, 0, 0)
        busy = int(self.key_due is not None or self.work is not None or self.result is not None)
        result = self.result
        return Pins(1 - busy, int(self.loaded),
                    int(self.loaded and not busy and not stimulus.kv),
                    int(result is not None), result["expected"] if result else 0,
                    result["tag"] if result else 0, result["mode"] if result else 0,
                    busy, 0)

    def compare(self, stimulus, actual, phase):
        expected = self.expected(stimulus)
        for field in ("kr", "kl", "ir", "ov", "busy", "error"):
            require(getattr(actual, field) == getattr(expected, field),
                    "public_protocol_or_exact_timing", cycle=self.cycle, phase=phase,
                    field=field, expected=getattr(expected, field),
                    actual=getattr(actual, field), epoch=self.epoch)
        if actual.ov or not stimulus.rst:
            for field in ("block", "tag", "mode"):
                require(getattr(actual, field) == getattr(expected, field),
                        "oracle_result_or_metadata", cycle=self.cycle, phase=phase,
                        field=field, expected=f"{getattr(expected, field):x}",
                        actual=f"{getattr(actual, field):x}", epoch=self.epoch,
                        transaction=self.result)
        self.counts[f"pin_comparisons_{phase}"] += 1

    def edge(self, stimulus, pre, label):
        events = {"key": False, "block": False, "retire": False}
        if stimulus.rst:
            if self.previous_stimulus is not None and self.previous_stimulus.rst:
                old, pins = self.previous_stimulus, self.previous_pins
                if old.kv and not pins.kr:
                    require(stimulus.kv and stimulus.key == old.key,
                            "key_producer_retains_offer", cycle=self.cycle)
                if old.iv and not pins.ir:
                    require(stimulus.iv and
                            (stimulus.block, stimulus.mode, stimulus.tag) ==
                            (old.block, old.mode, old.tag),
                            "block_producer_retains_offer", cycle=self.cycle)
            if not self.loaded and stimulus.iv:
                self.counts["unloaded_block_gated"] += 1
            if pre.busy and stimulus.iv:
                self.counts["busy_block_offers"] += 1
                phase = ("expansion" if self.key_due is not None else
                         "processing" if self.work is not None else "held_output")
                self.counts[f"block_offer_during_{phase}"] += 1
            if pre.busy and stimulus.kv:
                self.counts["busy_key_offers"] += 1
            if pre.ov and not stimulus.ready:
                self.hold += 1
                self.max_hold = max(self.max_hold, self.hold)
                self.counts["held_edges"] += 1
            else:
                if self.hold:
                    self.counts[f"hold_length_{self.hold}"] += 1
                self.hold = 0
            if pre.ov and stimulus.ready:
                require(self.result is not None, "retirement_without_transaction")
                self.result["retired_at"] = self.cycle
                self.counts["retired"] += 1
                self.result = None
                events["retire"] = True
                require(not pre.kr and not pre.ir, "retirement_bubble", cycle=self.cycle)
                self.counts["retirement_bubble"] += 1
            if self.key_due == self.cycle:
                self.loaded = True
                self.key_due = None
                self.counts["key_expansions_exact_10_edges"] += 1
                self.key_records[-1]["loaded_at"] = self.cycle
            if self.work and self.work["due"] == self.cycle:
                require(self.result is None, "capacity_one_result_slot")
                self.result = self.work
                self.work = None
                self.result["completed_at"] = self.cycle
                self.counts["completed"] += 1
                self.counts["round_completions_exact_10_edges"] += 1
            if stimulus.kv and pre.kr:
                require(not pre.busy and not pre.ir, "key_priority", cycle=self.cycle)
                self.key = stimulus.key
                self.loaded = False
                self.key_due = self.cycle + 10
                self.key_records.append({"key": f"{self.key:032x}",
                                         "accepted_at": self.cycle,
                                         "due": self.key_due, "epoch": self.epoch})
                self.counts["accepted_keys"] += 1
                if stimulus.iv:
                    self.counts["concurrent_key_block_priority"] += 1
                events["key"] = True
            if stimulus.iv and pre.ir:
                require(self.loaded and self.key is not None and
                        not pre.busy and not stimulus.kv,
                        "accepted_block_has_complete_key", cycle=self.cycle)
                self.work = {
                    "accepted_at": self.cycle, "due": self.cycle + 10,
                    "key": f"{self.key:032x}", "input": f"{stimulus.block:032x}",
                    "expected": crypt(self.key, stimulus.block, stimulus.mode),
                    "tag": stimulus.tag, "mode": stimulus.mode, "label": label,
                    "epoch": self.epoch,
                }
                self.records.append(self.work)
                self.counts["accepted_blocks"] += 1
                self.counts[f"direction_{stimulus.mode}"] += 1
                events["block"] = True
            if self.result:
                self.counts["valid_result_observation_edges"] += 1
        self.previous_stimulus = stimulus
        self.previous_pins = pre
        return events

    def finish(self):
        outstanding = int(self.work is not None) + int(self.result is not None)
        require(self.counts["accepted_blocks"] ==
                self.counts["retired"] + self.counts["canceled"] + outstanding,
                "transaction_conservation", counts=dict(self.counts), outstanding=outstanding)
        require(outstanding == 0 and self.key_due is None, "drained_end_of_scenario")
        return {"counts": dict(self.counts), "max_held_edges": self.max_hold,
                "transactions": self.records, "key_transactions": self.key_records,
                "outstanding": outstanding}


class Scenario:
    def __init__(self, name):
        self.name = name
        self.model = Contract()
        self.current = Stimulus(rst=0)
        self.rows = []
        self.labels = []

    def set(self, **values):
        self.current = Stimulus(**{**asdict(self.current), **values})

    def tick(self, label="", **values):
        self.set(**values)
        stimulus = self.current
        self.model.begin(stimulus)
        pins = self.model.expected(stimulus)
        events = self.model.edge(stimulus, pins, label)
        self.rows.append(stimulus)
        self.labels.append(label)
        self.model.cycle += 1
        require(len(self.rows) < 100000, "scenario_generation_watchdog", name=self.name)
        return events

    def until(self, predicate, label=""):
        for _ in range(1000):
            if predicate():
                return
            self.tick(label)
        raise CheckFailure("scenario_generation_deadlock", name=self.name)

    def reset(self):
        self.tick(rst=0, kv=0, iv=0, ready=0)
        self.tick()
        self.tick(rst=1)

    def load(self, key, label=""):
        self.set(kv=1, key=key)
        while not self.tick(label)["key"]:
            pass
        self.set(kv=0)
        self.until(lambda: self.model.loaded, label)

    def block(self, block, mode, tag, label, hold=0):
        self.set(iv=1, block=block, mode=mode, tag=tag, ready=int(hold == 0))
        while not self.tick(label)["block"]:
            pass
        self.set(iv=0)
        self.until(lambda: self.model.result is not None, label)
        for _ in range(hold):
            self.tick(label)
        self.tick(label, ready=1)
        require(self.model.result is None, "scenario_block_retired")

    def idle_guard(self, length=14):
        self.set(kv=0, iv=0, ready=1)
        for _ in range(length):
            self.tick("no_stale_output_guard")


def directed():
    s = Scenario("directed")
    s.reset()
    _, key, plain, _ = OFFICIAL[0]
    k, p = int(key, 16), int(plain, 16)
    s.set(iv=1, block=p, mode=0, tag=0, ready=0)
    for _ in range(4):
        s.tick("unloaded_offer")
    require(s.tick("key_priority", kv=1, key=k)["key"], "directed_key_priority")
    s.set(kv=0)
    s.until(lambda: s.model.loaded)
    require(s.tick("appendix_b_enc")["block"], "first_block_after_key_ready")
    s.set(iv=0)
    s.until(lambda: s.model.result is not None)
    next_key = int(OFFICIAL[1][1], 16)
    next_block = int(OFFICIAL[1][2], 16)
    for _ in range(32):
        s.tick("stall_with_concurrent_pending_offers", kv=1, key=next_key,
               iv=1, block=next_block, tag=255, mode=0)
    events = s.tick("retirement_no_replacement", ready=1)
    require(events["retire"] and not events["key"] and not events["block"],
            "directed_retirement_bubble")
    require(s.tick("pending_key_wins")["key"], "pending_key_acceptance")
    s.set(kv=0)
    s.until(lambda: s.model.loaded)
    require(s.tick("appendix_c1_enc")["block"], "first_pending_block_acceptance")
    s.set(iv=0)
    s.until(lambda: s.model.result is not None)
    s.tick(ready=1)
    for name, key, plain, cipher in OFFICIAL:
        s.load(int(key, 16), name + "_key")
        s.block(int(plain, 16), 0, 255, name + "_enc_repeat", hold=1)
        s.block(int(cipher, 16), 1, 0, name + "_dec", hold=40)
    for key in (0, (1 << 128) - 1, int.from_bytes(bytes(range(16)), "big")):
        s.load(key, "boundary_key")
        for number, block in enumerate((0, (1 << 128) - 1,
                                        int.from_bytes(bytes(range(15, -1, -1)), "big"))):
            cipher = crypt(key, block, False)
            s.block(block, 0, (255 + number) & 255, "boundary_enc")
            s.block(cipher, 1, (255 + number) & 255, "boundary_dec")
    # Each cancellation is followed by more than a full old completion latency.
    s.set(kv=1, key=k)
    require(s.tick("cancel_key_load")["key"], "reset_expansion_setup")
    s.set(kv=0)
    for _ in range(3):
        s.tick()
    s.reset()
    s.idle_guard()
    s.load(k)
    require(s.tick("cancel_processing", iv=1, block=p, mode=1, tag=173)["block"],
            "reset_processing_setup")
    s.set(iv=0)
    for _ in range(5):
        s.tick()
    s.reset()
    s.idle_guard()
    s.load(k)
    require(s.tick("cancel_held", iv=1, block=p, mode=0, tag=173, ready=0)["block"],
            "reset_held_setup")
    s.set(iv=0)
    s.until(lambda: s.model.result is not None)
    for _ in range(3):
        s.tick()
    s.reset()
    s.idle_guard()
    s.load(k)
    s.block(p, 0, 173, "post_reset_recovery")
    s.idle_guard()
    s.model.finish()
    return s


def seeded(seed):
    rng = random.Random(seed)
    s = Scenario(f"seed_{seed}")
    s.reset()
    for group in range(8):
        key = rng.getrandbits(128)
        transactions = []
        for pair in range(2):
            plain = rng.getrandbits(128)
            cipher = crypt(key, plain, False)
            identity = f"seed{seed}_key{group}_pair{pair}"
            transactions.extend([
                (plain, 0, (group * 8 + pair * 2) & 255, identity + "_enc"),
                (cipher, 1, (group * 8 + pair * 2 + 1) & 255, identity + "_dec"),
            ])
        for extra in range(4):
            transactions.append((rng.getrandbits(128), rng.randrange(2),
                                 rng.choice((0, 255, 1, (group * 8 + extra) & 255)),
                                 f"seed{seed}_key{group}_independent{extra}"))
        index, offering = 0, True
        s.set(kv=1, key=key)
        key_accepted = False
        retired_start = s.model.counts["retired"]
        for _ in range(2000):
            if index < len(transactions):
                if not offering and rng.random() < 0.8:
                    offering = True
                block, mode, tag, label = transactions[index]
                s.set(iv=int(offering), block=block, mode=mode, tag=tag)
            else:
                s.set(iv=0)
                label = "drain"
            # Continuous offers occur between gaps; accepted payload alone advances.
            events = s.tick(label, ready=int(rng.random() < 0.65))
            if events["key"]:
                require(not key_accepted, "one_key_per_seed_group")
                key_accepted = True
                s.set(kv=0)
            if events["block"]:
                index += 1
                offering = rng.random() < 0.75
            if s.model.counts["retired"] - retired_start == len(transactions):
                break
        else:
            raise CheckFailure("seed_scenario_deadlock", seed=seed, group=group)
        require(key_accepted and index == 8, "seed_group_generated", seed=seed, group=group)
    s.idle_guard()
    s.model.finish()
    return s


BENCH = r"""
`timescale 1ns/1ps
module tb;
    reg clk = 0;
    reg rst_n;
    reg key_valid, in_valid, in_enc_dec, out_ready;
    reg [127:0] key_in, in_block;
    reg [7:0] in_tag_id;
    wire key_ready, key_loaded, in_ready, out_valid, out_enc_dec, busy, err_unloaded_key;
    wire [127:0] out_block;
    wire [7:0] out_tag_id;
    integer vectors, trace, fields, cycle, rst_arg, kv_arg, iv_arg, mode_arg, ready_arg;
    reg [127:0] key_arg, block_arg;
    reg [7:0] tag_arg;
    string vector_path, trace_path;
    rivet_a1_top dut(
        .clk(clk), .rst_n(rst_n), .key_valid(key_valid), .key_ready(key_ready),
        .key_in(key_in), .key_loaded(key_loaded), .in_valid(in_valid), .in_ready(in_ready),
        .in_enc_dec(in_enc_dec), .in_block(in_block), .in_tag_id(in_tag_id),
        .out_valid(out_valid), .out_ready(out_ready), .out_block(out_block),
        .out_tag_id(out_tag_id), .out_enc_dec(out_enc_dec), .busy(busy),
        .err_unloaded_key(err_unloaded_key)
    );
    always #5 clk = ~clk;
    task automatic observe(input string phase);
        begin
            if ((^{key_ready,key_loaded,in_ready,out_valid,out_block,out_tag_id,
                   out_enc_dec,busy,err_unloaded_key}) === 1'bx)
                $fatal(1, "ACTIVE_XZ cycle=%0d phase=%s time=%0t", cycle, phase, $time);
            if (!rst_n && {key_ready,key_loaded,in_ready,out_valid,out_block,out_tag_id,
                          out_enc_dec,busy,err_unloaded_key} !== 0)
                $fatal(1, "RESET_NOT_ZERO cycle=%0d phase=%s time=%0t", cycle, phase, $time);
            $fdisplay(trace, "%0d %s %h %h %h %h %032h %02h %h %h %h",
                      cycle, phase, key_ready, key_loaded, in_ready, out_valid,
                      out_block, out_tag_id, out_enc_dec, busy, err_unloaded_key);
        end
    endtask
    initial begin
        rst_n = 0;
        key_valid = 0; key_in = 0; in_valid = 0; in_block = 0;
        in_tag_id = 0; in_enc_dec = 0; out_ready = 0; cycle = 0;
        if (!$value$plusargs("VECTORS=%s", vector_path)) $fatal(1, "missing VECTORS");
        if (!$value$plusargs("TRACE=%s", trace_path)) $fatal(1, "missing TRACE");
        vectors = $fopen(vector_path, "r");
        trace = $fopen(trace_path, "w");
        if (!vectors || !trace) $fatal(1, "file open failure");
        while (!$feof(vectors)) begin
            fields = $fscanf(vectors, "%d %d %h %d %d %h %h %d\n",
                             rst_arg, kv_arg, key_arg, iv_arg, mode_arg,
                             block_arg, tag_arg, ready_arg);
            if (fields != 8) $fatal(1, "malformed stimulus %0d fields=%0d", cycle, fields);
            rst_n = rst_arg; key_valid = kv_arg; key_in = key_arg; in_valid = iv_arg;
            in_enc_dec = mode_arg; in_block = block_arg; in_tag_id = tag_arg;
            out_ready = ready_arg;
            // Settle time-zero asynchronous reset and off-edge combinational inputs.
            #0.001; observe("A");
            @(posedge clk); observe("E");
            #1; observe("P");
            @(negedge clk); observe("F");
            #1;
            cycle = cycle + 1;
            if (cycle > 100000) $fatal(1, "finite simulated-cycle watchdog");
        end
        $fclose(vectors); $fclose(trace);
        $display("TRACE_COMPLETE cycles=%0d", cycle);
        $finish;
    end
endmodule
"""


class Execution:
    def __init__(self, preparation, repair_of):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        parent = ROOT / "evidence" / ("preparation" if preparation else "results")
        self.directory = parent / f"verifier-{stamp}-{uuid.uuid4().hex[:8]}"
        self.directory.mkdir(parents=True, exist_ok=False)
        self.inputs = sorted([*(ROOT / "rtl").glob("*.sv"),
                              *(ROOT / "design").glob("*.md"),
                              *(ROOT / "tests").glob("*.py")])
        self.source_hashes = hashes(self.inputs)
        self.started = utc()
        self.commands = []
        self.versions = {}
        self.preparation = preparation
        self.repair_of = repair_of
        self.snapshot = self.directory / "sources"
        for source in self.inputs:
            destination = self.snapshot / source.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    def relative(self, path):
        return str(path.relative_to(ROOT))

    def run(self, name, argv, directory, source_paths=(), timeout=TOOL_TIMEOUT):
        receipt = directory / f"{name}.receipt.json"
        stdout = directory / f"{name}.stdout"
        stderr = directory / f"{name}.stderr"
        record = {"argv": [str(a) for a in argv], "cwd": str(ROOT),
                  "started_at": utc(), "timeout_s": timeout,
                  "stdout": self.relative(stdout), "stderr": self.relative(stderr),
                  "source_sha256": hashes(source_paths), "timed_out": False,
                  "exit_code": None}
        try:
            with stdout.open("xb") as out, stderr.open("xb") as err:
                result = subprocess.run(record["argv"], cwd=ROOT, stdout=out,
                                        stderr=err, timeout=timeout, check=False)
            record["exit_code"] = result.returncode
        except subprocess.TimeoutExpired:
            record["timed_out"] = True
            raise ToolFailure(f"Timeout: {self.relative(receipt)}") from None
        finally:
            record["ended_at"] = utc()
            write_json(receipt, record)
            self.commands.append(self.relative(receipt))
        if record["exit_code"] != 0:
            raise ToolFailure(f"Tool exit {record['exit_code']}: {self.relative(receipt)}")
        return stdout

    def tools(self):
        for name, argv in (("python", [sys.executable, "--version"]),
                           ("iverilog", ["iverilog", "-V"]),
                           ("vvp", ["vvp", "-V"]), ("yosys", ["yosys", "-V"])):
            require(shutil.which(argv[0]) is not None, "missing_prerequisite",
                    tool=argv[0], installation="not authorized")
            output = self.run("version_" + name, argv, self.directory, timeout=60)
            self.versions[name] = {
                "stdout": output.read_text(), "stderr":
                (self.directory / f"version_{name}.stderr").read_text()}

    def finish(self, status, results, failure=None):
        unchanged = hashes(self.inputs) == self.source_hashes
        receipt = {
            "kind": "verifier-preparation" if self.preparation else "verification-suite",
            "acceptance_evidence": False if self.preparation else
                "shared runtime admission and review required",
            "status": status, "started_at": self.started, "ended_at": utc(),
            "argv": [sys.executable, *sys.argv], "cwd": str(ROOT),
            "source_sha256": self.source_hashes, "source_snapshot": self.relative(self.snapshot),
            "accepted_sources_unchanged": unchanged,
            "tool_versions": self.versions, "commands": self.commands,
            "results": results, "failure": failure, "repair_of": self.repair_of,
            "limits": {"child_simulation_synthesis_timeout_s": TOOL_TIMEOUT,
                       "maximum_simulated_cycles_per_scenario": 100000},
        }
        write_json(self.directory / "receipt.json", receipt)
        require(unchanged, "accepted_source_changed_during_execution")


def trace_check(scenario, trace_path):
    model = Contract()
    phases = ("A", "E", "P", "F")
    with trace_path.open() as trace:
        for cycle, (stimulus, label) in enumerate(zip(scenario.rows, scenario.labels)):
            model.cycle = cycle
            model.begin(stimulus)
            pre = None
            for phase in phases:
                line = trace.readline()
                parts = line.split()
                require(len(parts) == 11, "trace_shape_or_missing_observation",
                        cycle=cycle, phase=phase, line=line)
                require(parts[:2] == [str(cycle), phase], "trace_order",
                        cycle=cycle, phase=phase, line=line)
                require(not re.search("[xz]", "".join(parts[2:]), re.IGNORECASE),
                        "active_xz", cycle=cycle, phase=phase, line=line)
                actual = Pins(*(int(value, 16) for value in parts[2:]))
                if phase == "E":
                    pre = actual
                    model.compare(stimulus, actual, phase)
                    model.edge(stimulus, actual, label)
                else:
                    model.compare(stimulus, actual, phase)
                if phase == "P" and pre.ov and not stimulus.ready:
                    require((actual.ov, actual.block, actual.tag, actual.mode) ==
                            (pre.ov, pre.block, pre.tag, pre.mode),
                            "elastic_output_stability", cycle=cycle)
            require(pre is not None, "missing_pre_edge")
        require(not trace.read().strip(), "unexpected_extra_trace")
    result = model.finish()
    result["cycles"] = len(scenario.rows)
    result["scenario"] = scenario.name
    result["thresholds"] = {"exact_key_expansion_edges": 10, "exact_round_edges": 10}
    counts = result["counts"]
    require(counts.get("completed", 0) > 0 and counts.get("retired", 0) > 0,
            "nonempty_functional_comparisons", scenario=scenario.name)
    if scenario.name == "directed":
        for item in ("reset_expansion", "reset_processing", "reset_held_output",
                     "unloaded_block_gated", "busy_block_offers", "busy_key_offers",
                     "concurrent_key_block_priority", "hold_length_1", "hold_length_32",
                     "hold_length_40", "retirement_bubble"):
            require(counts.get(item, 0) > 0, "directed_coverage_missing", bin=item)
        require(model.max_hold >= 32, "long_output_stall_threshold",
                expected_min=32, actual=model.max_hold)
        for name, key, plain, cipher in OFFICIAL:
            for mode, source, expected in ((0, plain, cipher), (1, cipher, plain)):
                matched = [t for t in result["transactions"]
                           if t["key"] == key and t["input"] == source and
                           t["mode"] == mode and t["expected"] == int(expected, 16)
                           and "retired_at" in t]
                require(bool(matched), "official_dut_vector_missing", vector=name, direction=mode)
        require(counts.get("canceled", 0) == 2, "directed_reset_cancellation_count",
                expected=2, actual=counts.get("canceled", 0))
    else:
        for item, minimum in (("retired", 64), ("accepted_blocks", 64),
                              ("accepted_keys", 8), ("direction_0", 1),
                              ("direction_1", 1), ("concurrent_key_block_priority", 8),
                              ("busy_block_offers", 1), ("held_edges", 1),
                              ("block_offer_during_expansion", 1),
                              ("block_offer_during_processing", 1),
                              ("block_offer_during_held_output", 1)):
            require(counts.get(item, 0) >= minimum, "seed_coverage_threshold",
                    scenario=scenario.name, bin=item, minimum=minimum,
                    actual=counts.get(item, 0))
        checked = {t["label"]: t for t in model.records if "retired_at" in t}
        pairs = []
        for label, enc in checked.items():
            if label.endswith("_enc"):
                dec = checked.get(label[:-4] + "_dec")
                require(dec is not None and enc["key"] == dec["key"] and
                        enc["expected"] == int(dec["input"], 16) and
                        dec["expected"] == int(enc["input"], 16) and
                        (enc["mode"], dec["mode"]) == (0, 1),
                        "independently_checked_round_trip", label=label)
                pairs.append(label[:-4])
        require(len(pairs) >= 16, "round_trip_threshold",
                scenario=scenario.name, expected_min=16, actual=len(pairs))
        result["round_trips"] = pairs
        result["seed"] = int(scenario.name.split("_")[1])
        blocks_per_key = Counter(t["key"] for t in checked.values())
        require(len(blocks_per_key) >= 8 and min(blocks_per_key.values()) >= 8,
                "cached_key_reuse_threshold", actual=dict(blocks_per_key))
        result["blocks_per_key"] = dict(blocks_per_key)
        result["thresholds"].update({"blocks": 64, "key_loads": 8, "round_trips": 16})
    return result


def compile_simulation(execution, directory, rtl_directory):
    directory.mkdir(parents=True, exist_ok=False)
    bench = directory / "tb.sv"
    bench.write_text(BENCH)
    rtl = [rtl_directory / name for name in RTL_NAMES]
    image = directory / "sim.vvp"
    execution.run("compile", ["iverilog", "-g2012", "-Wall", "-s", "tb",
                             "-o", image, *rtl, bench], directory, [*rtl, bench])
    return image


def run_scenario(execution, parent, image, scenario):
    directory = parent / scenario.name
    directory.mkdir()
    vectors = directory / "stimulus.txt"
    with vectors.open("x") as stream:
        for s in scenario.rows:
            stream.write(f"{s.rst} {s.kv} {s.key:032x} {s.iv} {s.mode} "
                         f"{s.block:032x} {s.tag:02x} {s.ready}\n")
    write_json(directory / "scenario.json",
               {"name": scenario.name, "labels": scenario.labels,
                "cycles": len(scenario.rows)})
    trace = directory / "trace.txt"
    execution.run("simulate", ["vvp", image, f"+VECTORS={vectors}", f"+TRACE={trace}"],
                  directory, [image, vectors, directory / "scenario.json"])
    try:
        result = trace_check(scenario, trace)
    except CheckFailure as error:
        write_json(directory / "finding.json", error.finding)
        raise
    result["raw_trace"] = execution.relative(trace)
    write_json(directory / "result.json", result)
    return result


MUTATIONS = {
    "sbox": ("rivet_a1_sbox.sv",
             "aes_sub_byte(state_in[127-8*byte_index -: 8], enc_dec);",
             "aes_sub_byte(state_in[127-8*byte_index -: 8], enc_dec) ^ 8'h01;"),
    "shiftrows": ("rivet_a1_shiftrows.sv",
                  "4*((column+row)%4)+row", "4*((column+row+1)%4)+row"),
    "mixcolumns": ("rivet_a1_mixcolumns.sv",
                   "gf_mul(a, 8'h02)", "gf_mul(a, 8'h03)"),
    "key_schedule": ("rivet_a1_key_schedule.sv",
                     "next_round_key(previous_key, rcon);",
                     "next_round_key(previous_key, rcon) ^ 128'd1;"),
    "round_count": ("rivet_a1_datapath.sv",
                    "if (round_number == 4'd10) begin",
                    "if (round_number == 4'd9) begin"),
}


def mutation(execution, category, scenario):
    directory = execution.directory / ("mutation_" + category)
    directory.mkdir()
    rtl = directory / "rtl"
    shutil.copytree(execution.snapshot / "rtl", rtl)
    filename, old, new = MUTATIONS[category]
    path = rtl / filename
    before = path.read_text()
    require(before.count(old) == 1, "mutation_anchor_must_be_unique", category=category)
    after = before.replace(old, new, 1)
    path.write_text(after)
    patch = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                       fromfile=filename, tofile=filename + ".mutated"))
    (directory / "change.diff").write_text(patch)
    manifest = {"category": category, "file": filename, "old": old, "new": new,
                "pristine_sha256": hashlib.sha256(before.encode()).hexdigest(),
                "mutated_sha256": hashlib.sha256(after.encode()).hexdigest(),
                "all_mutated_source_sha256": hashes(sorted(rtl.glob("*.sv"))),
                "unchanged_oracle_sha256": execution.source_hashes["tests/verify.py"]}
    write_json(directory / "mutation.json", manifest)
    simulation = directory / "simulation"
    image = compile_simulation(execution, simulation, rtl)
    try:
        run_scenario(execution, simulation, image, scenario)
    except CheckFailure as error:
        require(error.finding["assertion"] in
                ("public_protocol_or_exact_timing", "oracle_result_or_metadata",
                 "elastic_output_stability"),
                "mutation_requires_functional_assertion_not_tool_or_log_failure",
                category=category, finding=error.finding)
        result = {"category": category, "status": "detected",
                  "compiled_successfully": True, "simulation_exit_code": 0,
                  "detecting_assertion": error.finding,
                  "finding": execution.relative(simulation / scenario.name / "finding.json"),
                  "manifest": execution.relative(directory / "mutation.json")}
        write_json(directory / "result.json", result)
        return result
    raise CheckFailure("mutation_survived_unchanged_functional_checks", category=category)


def synthesis(execution):
    directory = execution.directory / "synthesis"
    directory.mkdir()
    original = execution.snapshot / "rtl"
    compatibility = directory / "frontend"
    compatibility.mkdir()
    package = (original / RTL_NAMES[0]).read_text()
    require(package.startswith("package rivet_a1_pkg;") and
            package.rstrip().endswith("endpackage"), "package_frontend_shape")
    declarations = package[len("package rivet_a1_pkg;"):package.rfind("endpackage")]
    generated = []
    transformations = []
    # Yosys's native SV frontend lacks package import support. Lexical inlining
    # preserves every original declaration/expression and every module boundary.
    for name in RTL_NAMES[1:]:
        source = original / name
        text = source.read_text()
        require(text.count("import rivet_a1_pkg::*;") <= 1, "frontend_import_shape", file=name)
        transformed = text.replace("import rivet_a1_pkg::*;", declarations)
        target = compatibility / name
        target.write_text(transformed)
        generated.append(target)
        transformations.append({
            "source": execution.relative(source), "generated": execution.relative(target),
            "operation": "replace exact package import with unmodified package body",
            "diff": "".join(difflib.unified_diff(
                text.splitlines(True), transformed.splitlines(True),
                fromfile=name, tofile="frontend/" + name)),
        })
    write_json(directory / "frontend.json",
               {"package": execution.relative(original / RTL_NAMES[0]),
                "package_sha256": hashlib.sha256(package.encode()).hexdigest(),
                "transformations": transformations,
                "generated_sha256": hashes(generated)})
    script = directory / "synthesis.ys"
    json_path = directory / "netlist.json"
    verilog_path = directory / "netlist.v"
    script.write_text(
        "read_verilog -sv " + " ".join('"' + str(p) + '"' for p in generated) + "\n"
        "hierarchy -check -top rivet_a1_top\n"
        "proc\nopt\nmemory\nopt\ncheck -assert\n"
        "stat\n"
        f'write_json "{json_path}"\n'
        f'write_verilog -noattr "{verilog_path}"\n')
    execution.run("yosys", ["yosys", "-T", "-s", script], directory, [*generated, script])
    netlist = json.loads(json_path.read_text())
    modules = netlist["modules"]
    require("rivet_a1_top" in modules, "synthesis_top_present")
    visited = set()
    counts = Counter()
    sequential_bits = Counter()
    latches = []
    hierarchy = []

    def visit(name, instance):
        require(name in modules, "synthesis_missing_module", module=name)
        require(name not in visited, "synthesis_unexpected_shared_or_recursive_hierarchy", module=name)
        visited.add(name)
        module = modules[name]
        require(not int(str(module.get("attributes", {}).get("blackbox", "0")), 2),
                "synthesis_blackbox", module=name)
        for cellname, cell in module.get("cells", {}).items():
            kind = cell["type"]
            counts[kind] += 1
            if "latch" in kind.lower():
                latches.append({"module": name, "cell": cellname, "type": kind})
            if kind in modules:
                hierarchy.append({"parent": name, "cell": cellname, "module": kind})
                visit(kind, instance + "." + cellname)
            elif re.search(r"(?:dff|dffe|adff|sdff|ff)", kind, re.IGNORECASE):
                require("Q" in cell["connections"], "sequential_cell_q_port", type=kind)
                sequential_bits[name] += len(cell["connections"]["Q"])

    visit("rivet_a1_top", "rivet_a1_top")
    result = {"cell_counts": dict(counts), "latches": latches, "latch_count": len(latches),
              "sequential_bits_by_module": dict(sequential_bits),
              "total_sequential_bits": sum(sequential_bits.values()),
              "hierarchy": hierarchy,
              "thresholds": {"latch_count": 0, "total_sequential_bits_min": 1600,
                             "key_schedule_sequential_bits_min": 1408,
                             "datapath_sequential_bits_min": 256},
              "raw_log": execution.relative(directory / "yosys.stdout"),
              "netlist_json": execution.relative(json_path),
              "netlist_verilog": execution.relative(verilog_path),
              "script": execution.relative(script),
              "frontend": execution.relative(directory / "frontend.json")}
    write_json(directory / "counts.json", result)
    require(not latches, "zero_latch_hierarchy", latches=latches)
    required_modules = {"rivet_a1_top", "rivet_a1_key_schedule", "rivet_a1_datapath",
                        "rivet_a1_sbox", "rivet_a1_shiftrows", "rivet_a1_mixcolumns"}
    require(visited == required_modules, "complete_production_hierarchy",
            actual=sorted(visited), expected=sorted(required_modules))
    require(sum(sequential_bits.values()) >= 1600 and
            sequential_bits["rivet_a1_key_schedule"] >= 1408 and
            sequential_bits["rivet_a1_datapath"] >= 256,
            "substantive_sequential_aes_key_storage", actual=dict(sequential_bits))
    top = modules["rivet_a1_top"]
    for name, minimum in (("out_block", 128), ("out_tag_id", 8), ("out_enc_dec", 1),
                          ("out_valid", 1), ("key_loaded", 1)):
        bits = top["ports"][name]["bits"]
        require(sum(isinstance(bit, int) for bit in bits) >= minimum,
                "synthesis_nonconstant_output", port=name, bits=bits)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true",
                        help="advisory directed/sbox/synthesis probe, not the mandatory full suite")
    parser.add_argument("--repair-of", help="project-relative earlier preparation receipt")
    arguments = parser.parse_args()
    execution = Execution(arguments.prepare, arguments.repair_of)
    results = {}
    behavior_names = ["directed"] if arguments.prepare else [
        "directed", "seed_1", "seed_17", "seed_89"]
    mutation_names = ["sbox"] if arguments.prepare else list(MUTATIONS)
    ledger = [
        {"check": "behavior/" + name, "status": "not_run"} for name in behavior_names
    ] + [
        {"check": "mutation/" + name, "status": "not_run"} for name in mutation_names
    ] + [{"check": "synthesis", "status": "not_run"}]
    results["ledger"] = ledger
    status, failure = "incomplete", None
    active = None
    print(f"Evidence: {execution.relative(execution.directory)}", flush=True)
    try:
        results["oracle"] = oracle_self_check()
        execution.tools()
        scenario = directed()
        # Construct all seed schedules even in preparation, catching source-side
        # generation mistakes without duplicating the admitted full execution.
        seeds = [seeded(seed) for seed in (1, 17, 89)]
        baseline = execution.directory / "baseline"
        image = compile_simulation(execution, baseline, execution.snapshot / "rtl")
        results["behavior"] = []
        scenarios = [scenario] if arguments.prepare else [scenario, *seeds]
        for s in scenarios:
            active = next(row for row in ledger if row["check"] == "behavior/" + s.name)
            active["status"] = "running"
            results["behavior"].append(run_scenario(execution, baseline, image, s))
            active["status"] = "passed"
            active["result"] = execution.relative(baseline / s.name / "result.json")
        results["mutations"] = []
        for name in mutation_names:
            active = next(row for row in ledger if row["check"] == "mutation/" + name)
            active["status"] = "running"
            results["mutations"].append(mutation(execution, name, scenario))
            active["status"] = "passed"
            active["result"] = execution.relative(
                execution.directory / ("mutation_" + name) / "result.json")
        active = ledger[-1]
        active["status"] = "running"
        results["synthesis"] = synthesis(execution)
        active["status"] = "passed"
        active["result"] = execution.relative(execution.directory / "synthesis" / "counts.json")
        results["mandatory_full_suite"] = not arguments.prepare
        status = "passed"
        print(f"{'Preparation' if arguments.prepare else 'Full suite'} passed; "
              f"{len(results['behavior'])} scenarios, {len(results['mutations'])} mutations, "
              "zero inferred latches.", flush=True)
    except (CheckFailure, ToolFailure, OSError, ValueError) as error:
        status = "failed"
        failure = error.finding if isinstance(error, CheckFailure) else {
            "type": type(error).__name__, "message": str(error)}
        if active is not None and active["status"] == "running":
            active["status"] = "failed"
            active["failure"] = failure
        print(f"FAILED: {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        execution.finish(status, results, failure)
    return 0


if __name__ == "__main__":
    sys.exit(main())
