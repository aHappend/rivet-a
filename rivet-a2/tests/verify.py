#!/usr/bin/env python3
"""Independent executable acceptance checks for RIVET-A2.

Every run uses fresh compiled outputs and preserves commands, versions, source
snapshots, raw logs, comparison counts and failures. --probe is advisory only:
it is a bounded harness diagnostic, never a substitute for an admitted check.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid

# tests/* is an admitted input selector, including generated cache directories.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import anchors
from scenarios import Stimulus
from units import bench

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 3600


def now():
    return datetime.now(timezone.utc).isoformat()


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    return sorted(set(
        list((ROOT / "rtl").glob("*.sv"))
        + list((ROOT / "design").glob("*.md"))
        + [p for p in (ROOT / "tests").glob("*") if p.is_file()]
    ))


class Failure(RuntimeError):
    def __init__(self, kind, message, receipt=None):
        super().__init__(message)
        self.kind = kind
        self.receipt = receipt


class Run:
    def __init__(self, check, probe=False, repair_of=None):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        base = ROOT / "evidence" / ("preparation" if probe else "checks")
        self.path = base / f"verifier-{check}-{stamp}-{uuid.uuid4().hex[:8]}"
        self.path.mkdir(parents=True, exist_ok=False)
        self.records = []
        self.versions = {}
        self.hashes = {relative(p): sha(p) for p in sources()}
        for p in sources():
            dest = self.path / "sources" / relative(p)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
        self.result = dict(check=check, advisory=probe, status="running",
                           start_time=now(), source_sha256=self.hashes,
                           repair_of=repair_of, commands=self.records,
                           versions=self.versions, cases=[])
        self.save()

    def save(self):
        write_json(self.path / "results.json", self.result)

    def command(self, argv, folder, label, allow_failure=False, inputs=()):
        folder.mkdir(parents=True, exist_ok=True)
        stdout = folder / f"{label}.stdout.log"
        stderr = folder / f"{label}.stderr.log"
        receipt_path = folder / f"{label}.receipt.json"
        if receipt_path.exists():
            raise Failure("harness", f"Refusing to overwrite {relative(receipt_path)}")
        record = dict(argv=[str(a) for a in argv], cwd=str(ROOT),
                      start_time=now(), timeout_s=TIMEOUT, timed_out=False,
                      stdout=relative(stdout), stderr=relative(stderr),
                      source_sha256=self.hashes, tool_versions=dict(self.versions),
                      command_input_sha256={relative(p): sha(p) for p in inputs})
        start = time.monotonic()
        try:
            with stdout.open("wb") as out, stderr.open("wb") as err:
                child = subprocess.run(record["argv"], cwd=ROOT, stdout=out,
                                       stderr=err, timeout=TIMEOUT, check=False)
            record["exit_code"] = child.returncode
        except subprocess.TimeoutExpired:
            record.update(timed_out=True, exit_code=None)
        except OSError as exc:
            record.update(exit_code=None, launch_error=str(exc))
        record.update(end_time=now(), elapsed_s=time.monotonic() - start)
        write_json(receipt_path, record)
        self.records.append(relative(receipt_path))
        self.save()
        if record.get("launch_error"):
            raise Failure("prerequisite", record["launch_error"], relative(receipt_path))
        if record["timed_out"]:
            raise Failure("timeout", f"Tool timeout: {argv[0]}", relative(receipt_path))
        if record["exit_code"] != 0 and not allow_failure:
            raise Failure("tool", f"Child exit {record['exit_code']}: {argv[0]}",
                          relative(receipt_path))
        return record, stdout.read_text(errors="replace"), stderr.read_text(errors="replace")

    def prerequisites(self, check):
        tools = ["python3", "yosys"] if check == "synthesis" else ["python3", "iverilog", "vvp"]
        for tool in tools:
            if not shutil.which(tool):
                raise Failure("prerequisite", f"Missing required executable: {tool}")
            args = [tool, "--version"] if tool == "python3" else [tool, "-V"]
            record, out, err = self.command(args, self.path / "versions", tool)
            self.versions[tool] = dict(executable=shutil.which(tool),
                                       output=out + err, exit_code=record["exit_code"])
        self.save()

    def finish(self, status, **details):
        current = {relative(p): sha(p) for p in sources()}
        if current != self.hashes:
            raise Failure("source-change", "Production/verification inputs changed during check")
        self.result.update(status=status, end_time=now(), **details)
        self.save()
        if self.result["advisory"]:
            children = [json.loads((ROOT / p).read_text()) for p in self.records]
            for stream in ("stdout", "stderr"):
                (self.path / f"{stream}.log").write_text("".join(
                    f"\n--- {r[stream]} ---\n" + (ROOT / r[stream]).read_text(errors="replace")
                    for r in children))
            # Immutable outer receipt for the project-owned preparation invocation.
            write_json(self.path / "receipt.json", dict(
                argv=[sys.executable, *sys.argv], cwd=str(ROOT),
                source_sha256=self.hashes, tool_versions=self.versions,
                start_time=self.result["start_time"], end_time=now(),
                timeout_s=None, child_timeout_s=TIMEOUT,
                timed_out=any(r["timed_out"] for r in children),
                exit_code=0 if status == "passed" else 1,
                stdout=relative(self.path / "stdout.log"),
                stderr=relative(self.path / "stderr.log"),
                child_receipts=self.records,
                result=relative(self.path / "results.json"),
                repair_of=self.result["repair_of"]))


def rtl_files(rtl):
    package = rtl / "rivet_a2_pkg.sv"
    files = [package] + sorted(p for p in rtl.glob("*.sv") if p != package)
    if len(files) != 9 or not all(p.is_file() for p in files):
        raise Failure("inputs", "Expected the nine modular A2 RTL files")
    return files


def simulate(run, rtl, folder, capacity, anchor_rows, probe=False, mutant=False):
    folder.mkdir(parents=True, exist_ok=True)
    generator = Stimulus(capacity)
    stimulus = generator.build(anchor_rows, probe)
    (folder / "stimulus.svh").write_text(stimulus)
    write_json(folder / "cases.json", generator.cases)
    args = ["iverilog", "-g2012", "-Wall", "-I", folder, "-s", "tb",
            "-P", f"tb.CAPACITY={capacity}", "-o", folder / "simulation.vvp",
            *rtl_files(rtl), ROOT / "tests" / "bridge.sv"]
    try:
        run.command(args, folder, "compile",
                    inputs=[*rtl_files(rtl), ROOT / "tests" / "bridge.sv",
                            folder / "stimulus.svh"])
    except Failure as exc:
        raise Failure("compile", str(exc), exc.receipt) from exc
    record, out, err = run.command(["vvp", folder / "simulation.vvp"],
                                   folder, "simulation", allow_failure=True,
                                   inputs=[folder / "simulation.vvp", folder / "stimulus.svh",
                                           *rtl_files(rtl), ROOT / "tests" / "bridge.sv"])
    assertions = re.findall(r"ASSERT[^\n]*", out + err)
    if record["exit_code"] != 0:
        raise Failure("assertion" if assertions else "simulation",
                      assertions[0] if assertions else (out + err)[-2000:],
                      relative(folder / "simulation.receipt.json"))
    if assertions or "FATAL:" in out + err or "SIMULATION_COMPLETE" not in out:
        raise Failure("simulation", "Missing completion or unexpected diagnostic",
                      relative(folder / "simulation.receipt.json"))
    match = re.search(
        r"COUNTS cycles=(\d+) keys=(\d+) raw=(\d+) tags=(\d+) payload=(\d+) "
        r"beats=(\d+) resets=(\d+) errors=(\d+)", out)
    if not match:
        raise Failure("harness", "Missing actual comparison counts")
    counts = dict(zip(("cycles", "keys", "raw", "tags", "payload", "beats", "resets", "errors"),
                      map(int, match.groups())))
    for name, expected in generator.counts.items():
        if counts[name] != expected:
            raise Failure("harness", f"Coverage mismatch for {name}")
    if not all(counts[k] > 0 for k in ("cycles", "keys", "raw", "tags", "payload", "beats", "resets")):
        # Capacity 256 deliberately has no raw AES sweep (covered at 1/3/16).
        if capacity != 256 or not all(counts[k] > 0 for k in ("cycles", "keys", "tags", "payload", "beats", "resets")):
            raise Failure("harness", "Empty mandatory comparison bin")
    result = dict(capacity=capacity, seed=1701, probe=probe, mutant=mutant,
                  counts=counts, required_counts=generator.counts,
                  criterion="exact bytes/tags/lengths/status and exact expected comparison counts",
                  cases=relative(folder / "cases.json"),
                  receipt=relative(folder / "simulation.receipt.json"))
    run.result["cases"].append(result)
    run.save()
    return result


def unit_checks(run):
    folder = run.path / "units"
    folder.mkdir()
    tb = folder / "units.sv"
    tb.write_text(bench())
    run.command(["iverilog", "-g2012", "-Wall", "-s", "tb_units",
                 "-o", folder / "units.vvp", *rtl_files(ROOT / "rtl"), tb],
                folder, "compile", inputs=[*rtl_files(ROOT / "rtl"), tb])
    _, out, err = run.command(["vvp", folder / "units.vvp"], folder, "simulation",
                              inputs=[folder / "units.vvp", tb])
    if "SIMULATION_COMPLETE" not in out or "UNIT_COUNTS round_keys=37 hashes=16" not in out or "FATAL" in out + err:
        raise Failure("assertion", "Unit checks did not complete with required comparisons")
    run.result["units"] = dict(round_key_comparisons=37, ghash_comparisons=16,
                               receipt=relative(folder / "simulation.receipt.json"))
    run.save()


def behavior(run, probe):
    rows = anchors()
    write_json(run.path / "reference_anchors.json", rows)
    unit_checks(run)
    for capacity in ([3] if probe else [1, 3, 16, 256]):
        simulate(run, ROOT / "rtl", run.path / f"capacity-{capacity}",
                 capacity, rows, probe)
    if probe:
        # Compile every full generated harness without duplicating the admitted
        # functional suite. This diagnoses generator scoping and boundary widths.
        run.result["diagnostic_elaborations"] = []
        for capacity in (1, 3, 16, 256):
            folder = run.path / f"elaboration-only-{capacity}"
            folder.mkdir()
            generator = Stimulus(capacity)
            (folder / "stimulus.svh").write_text(generator.build(rows))
            run.command(
                ["iverilog", "-g2012", "-Wall", "-t", "null", "-I", folder,
                 "-s", "tb", "-P", f"tb.CAPACITY={capacity}",
                 *rtl_files(ROOT / "rtl"), ROOT / "tests" / "bridge.sv"],
                folder, "elaboration",
                inputs=[*rtl_files(ROOT / "rtl"), ROOT / "tests" / "bridge.sv",
                        folder / "stimulus.svh"])
            run.result["diagnostic_elaborations"].append(dict(
                capacity=capacity, simulated=False,
                receipt=relative(folder / "elaboration.receipt.json")))
            run.save()


MUTATIONS = [
    dict(name="aes256-extra-subword", file="rivet_a2_key_schedule.sv",
         old="else if (key256 && word_index[2:0] == 3'd4)",
         new="else if (1'b0 && key256 && word_index[2:0] == 3'd4)",
         assertion="AES_RESULT", description="Disable AES-256's extra SubWord at i mod 8 = 4."),
    dict(name="ghash-polynomial", file="rivet_a2_ghash.sv",
         old="128'he1000000000000000000000000000000",
         new="128'hc1000000000000000000000000000000",
         assertion="TAG_RESULT", description="Corrupt GHASH reduction polynomial."),
    dict(name="partial-mask", file="rivet_a2_top.sv",
         old="if (b < count)", new="if (b < 16)",
         assertion="TAG_RESULT", description="Include ignored low bytes in partial GHASH/payload data."),
    dict(name="length-block", file="rivet_a2_top.sv",
         old="payload_bits <= {32'd0, payload_bytes} << 3;",
         new="payload_bits <= {32'd0, payload_bytes} << 2;",
         assertion="TAG_RESULT", description="Encode payload length in four-bit units instead of bits."),
    dict(name="tag-comparison", file="rivet_a2_top.sv",
         old="computed_tag != expected_latched",
         new="computed_tag[127:1] != expected_latched[127:1]",
         assertion="TAG_RESULT", description="Ignore expected tag bit zero."),
    dict(name="preauth-plaintext", file="rivet_a2_top.sv",
         old="if (state == S_RAW && aes_out_valid) begin",
         new="""if (state == S_PAY_WAIT && decrypt_mode && aes_out_valid) begin
                out_valid = 1'b1;
                out_block = payload_result;
                out_valid_bytes = beat_bytes;
                out_is_gcm = 1'b1;
                out_enc_dec = 1'b1;
            end else if (state == S_RAW && aes_out_valid) begin""",
         assertion="PREAUTH_RELEASE", description="Expose tentative decrypted plaintext before authentication."),
]


def sensitivity(run, probe):
    rows = anchors()
    write_json(run.path / "reference_anchors.json", rows)
    # Identical public oracle/stimulus for baseline and all six independent defects.
    simulate(run, ROOT / "rtl", run.path / "baseline", 3, rows, probe=True)
    rejected = []
    for mutation in MUTATIONS:
        folder = run.path / mutation["name"]
        rtl = folder / "rtl"
        shutil.copytree(ROOT / "rtl", rtl)
        target = rtl / mutation["file"]
        text = target.read_text()
        if text.count(mutation["old"]) != 1:
            raise Failure("mutation", f"Ambiguous mutation target: {mutation['name']}")
        target.write_text(text.replace(mutation["old"], mutation["new"]))
        write_json(folder / "mutation.json", dict(
            **mutation, production_sha256=sha(ROOT / "rtl" / mutation["file"]),
            mutant_sha256=sha(target)))
        try:
            simulate(run, rtl, folder / "test", 3, rows, probe=True, mutant=True)
        except Failure as exc:
            if exc.kind != "assertion" or mutation["assertion"] not in str(exc):
                raise Failure("mutation", f"{mutation['name']} rejected for wrong reason: "
                              f"{exc.kind}: {exc}", exc.receipt) from exc
            rejected.append(dict(name=mutation["name"], status="functionally-rejected",
                                 observation=str(exc), receipt=exc.receipt))
        else:
            raise Failure("mutation", f"Checker accepted defect {mutation['name']}")
        run.result["mutations"] = rejected
        run.save()
    if len(rejected) != 6:
        raise Failure("mutation", "Six independent functional rejections required")


def yosys_sources(run, folder):
    """Mechanical package expansion for the installed Verilog frontend.

    Yosys 0.33's native frontend does not parse package wildcard imports.
    Substitute the exact package declarations at each import, without changing
    any declaration/function body or module logic. Keep both views in evidence.
    Icarus independently compiles the original package-form production sources.
    """
    rtl = ROOT / "rtl"
    package = (rtl / "rivet_a2_pkg.sv").read_text()
    if not package.startswith("package rivet_a2_pkg;") or not package.rstrip().endswith("endpackage"):
        raise Failure("frontend", "Unexpected package boundaries")
    declarations = package[len("package rivet_a2_pkg;"):package.rfind("endpackage")]
    generated = folder / "yosys-input"
    generated.mkdir(parents=True)
    mapping = []
    files = []
    for path in rtl_files(rtl)[1:]:
        text = path.read_text()
        count = text.count("import rivet_a2_pkg::*;")
        converted = text.replace("import rivet_a2_pkg::*;", declarations)
        if "import " in converted or "rivet_a2_pkg::" in converted:
            raise Failure("frontend", "Unconverted package dependency")
        dest = generated / path.name
        dest.write_text(converted)
        mapping.append(dict(source=relative(path), source_sha256=sha(path),
                            generated=relative(dest), generated_sha256=sha(dest),
                            exact_package_insertions=count))
        files.append(dest)
    if sum(row["exact_package_insertions"] for row in mapping) != 3:
        raise Failure("frontend", "Unexpected package import inventory")
    write_json(folder / "frontend-mapping.json", dict(
        method="exact textual package declaration expansion",
        package_sha256=sha(rtl / "rivet_a2_pkg.sv"), files=mapping))
    return files


def sequential_bits(module):
    bits = set()
    for cell in module["cells"].values():
        if re.search(r"(?:dff|adff|sdff|dffe)", cell["type"], re.I):
            bits.update(b for b in cell["connections"].get("Q", []) if isinstance(b, int))
    return bits


def structural_checks(folder, capacity):
    pre = json.loads((folder / "hierarchy.json").read_text())["modules"]
    post = json.loads((folder / "netlist.json").read_text())["modules"]
    top = pre["rivet_a2_top"]

    def instance(module, name, expected):
        if name not in module["cells"]:
            raise Failure("structure", f"Missing literal instance {name}")
        cell = module["cells"][name]
        if cell["type"] not in pre:
            raise Failure("structure", f"Unresolved module {cell['type']}")
        child = pre[cell["type"]]
        # Yosys may escape hdlname, especially for parameterized instances.
        hdlname = child.get("attributes", {}).get("hdlname", cell["type"]).split()[0].lstrip("\\")
        if hdlname != expected or not cell["connections"] or not child["cells"]:
            raise Failure("structure", f"Missing substantive {expected} at {name}")
        return child

    core = instance(top, "u_aes_core", "rivet_a2_aes_core")
    instance(top, "u_ghash", "rivet_a2_ghash")
    schedule = instance(core, "u_key_schedule", "rivet_a2_key_schedule")
    datapath = instance(core, "u_datapath", "rivet_a2_datapath")
    for name in ("sbox", "shiftrows", "mixcolumns"):
        instance(datapath, f"u_{name}", f"rivet_a2_{name}")
    for modules in (pre, post):
        for name, module in modules.items():
            if int(module.get("attributes", {}).get("blackbox", "0"), 2):
                raise Failure("structure", f"Blackbox {name}")
            for cell in module["cells"].values():
                if "latch" in cell["type"].lower():
                    raise Failure("structure", "Inferred latch")
                if not cell["type"].startswith("$") and cell["type"] not in modules:
                    raise Failure("structure", f"Unresolved {cell['type']}")
    storage = set()
    for name, net in top["netnames"].items():
        if name.startswith("payload_store[") or name.startswith("byte_store["):
            storage.update(b for b in net["bits"] if isinstance(b, int))
    state = sequential_bits(top)
    if len(storage) < capacity * 133 or not storage.issubset(state):
        raise Failure("structure", f"Payload storage not substantive sequential state: "
                      f"{len(storage)} bits, capacity={capacity}")
    if len(sequential_bits(schedule)) < 1920 or len(sequential_bits(datapath)) < 128:
        raise Failure("structure", "Missing expanded-key or iterative datapath state")
    post_bits = sum(len(sequential_bits(m)) for m in post.values())
    if post_bits < capacity * 128 + 128 or not post["rivet_a2_top"]["cells"]:
        raise Failure("structure", "Insufficient synthesized sequential logic")
    return dict(capacity=capacity, payload_storage_bits=len(storage),
                top_sequential_bits=len(state), post_sequential_bits=post_bits,
                literal_hierarchy="all seven required instances checked",
                latches=0, unresolved=0,
                hierarchy=relative(folder / "hierarchy.json"),
                netlist=relative(folder / "netlist.json"),
                statistics=relative(folder / "statistics.json"),
                receipt=relative(folder / "yosys.receipt.json"))


def synthesis(run, probe):
    results = []
    for capacity in ([1] if probe else [1, 3, 16]):
        folder = run.path / f"capacity-{capacity}"
        folder.mkdir()
        files = yosys_sources(run, folder)
        quote = lambda p: '"' + str(p).replace("\\", "\\\\").replace('"', '\\"') + '"'
        script = (
            "read_verilog -sv " + " ".join(map(quote, files)) + ";\n"
            f"hierarchy -check -top rivet_a2_top -chparam MAX_PAYLOAD_BLOCKS {capacity};\n"
            "proc; opt; check -assert;\n"
            f"write_json {quote(folder / 'hierarchy.json')};\n"
            "synth -top rivet_a2_top;\n"
            "check -assert;\n"
            f"tee -o {relative(folder / 'statistics.json')} stat -json;\n"
            f"write_json {quote(folder / 'netlist.json')};\n"
            f"write_verilog {quote(folder / 'netlist.v')};\n")
        script_path = folder / "synthesis.ys"
        script_path.write_text(script)
        _, out, err = run.command(["yosys", "-s", script_path], folder, "yosys",
                                  inputs=[script_path, *files])
        if re.search(r"logic loop|conflicting drivers|found and reported [1-9]\d* problems", out + err, re.I):
            raise Failure("structure", "Yosys structural diagnostics")
        results.append(structural_checks(folder, capacity))
        run.result["synthesis"] = results
        run.save()
    # Capacity 256 is elaborated with actual Icarus in behavior, as well as its
    # maximum-capacity functional sweep; no generic synthesis is claimed for it.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", required=True, choices=("behavior", "sensitivity", "synthesis"))
    parser.add_argument("--probe", action="store_true", help="bounded advisory harness diagnostic")
    parser.add_argument("--repair-of", help="project-relative earlier preparation receipt")
    args = parser.parse_args()
    if args.repair_of:
        p = (ROOT / args.repair_of).resolve()
        if not p.is_relative_to(ROOT / "evidence" / "preparation") or not p.is_file():
            parser.error("--repair-of must identify an existing project preparation receipt")
    run = Run(args.check, args.probe, args.repair_of)
    print(f"EVIDENCE {relative(run.path)}", flush=True)
    try:
        run.prerequisites(args.check)
        {"behavior": behavior, "sensitivity": sensitivity,
         "synthesis": synthesis}[args.check](run, args.probe)
        run.finish("passed")
    except Exception as exc:
        # Preserve an unexpected harness error as a failing record, never a pass.
        (run.path / "exception.log").write_text(traceback.format_exc())
        run.result["failure"] = dict(kind=getattr(exc, "kind", "reference"),
                                     message=str(exc), receipt=getattr(exc, "receipt", None))
        run.finish("failed")
        print(f"FAILED {getattr(exc, 'kind', 'reference')}: {exc}", file=sys.stderr)
        return 1
    print(f"{'ADVISORY' if args.probe else 'CHECK'} {args.check} passed; "
          f"results={relative(run.path / 'results.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
