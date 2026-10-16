#!/usr/bin/env python3
"""Source-bound independent verification entry. No installation or RTL modification."""
import argparse
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oracle import known_answers
from scenarios import generate

ROOT = Path(__file__).resolve().parent.parent
SELECTORS = ("rtl/*.sv", "design/SPEC.md", "design/ARCHITECTURE.md", "tests/*")


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sources(root):
    selected = set()
    for selector in SELECTORS:
        matches = {p for p in root.glob(selector) if p.is_file()}
        if not matches:
            raise FileNotFoundError(
                f"declared source selector matches no files: {selector} under {root}")
        selected.update(matches)
    return sorted(selected)


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sources(root)}


class Run:
    def __init__(self, output, args):
        self.output = output.resolve()
        try:
            self.output.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise FileExistsError(
                f"verification output already exists: {self.output}; prior evidence "
                "was not modified. Use a fresh independently admitted output path; "
                "do not replay this command, nest a retry here, or reuse its receipt. "
                "Rejected invocation: "+json.dumps({
                    "suite": args.suite, "output": str(self.output),
                    "executable": sys.executable, "script_argv": sys.argv,
                    "cwd": str(Path.cwd()),
                }, sort_keys=True)
            ) from exc
        self.receipt = {
            "kind": "independent-verification", "acceptance_evidence": False,
            "argv": [sys.executable, *sys.argv], "cwd": str(Path.cwd()),
            "start_utc": utc(), "source_sha256": hashes(ROOT),
            "suite": args.suite, "repair_of": args.repair_of,
            "commands": [], "runs": [], "versions": {},
            "ledger": {},
        }
        capacities=[int(x) for x in getattr(args,"capacities","1,3,16").split(",")]
        seeds=[int(x) for x in getattr(args,"seeds","17,89,203").split(",")]
        planned=[]
        if args.suite=="behavior":
            planned=[f"behavior-capacity-{cap}-seed-{seed}" for cap in capacities for seed in seeds]
        elif args.suite=="boundaries":
            planned=["boundary-units","illegal-capacity-0","illegal-capacity-257"]+[
                f"boundaries-capacity-{cap}-seed-203" for cap in (1,3,16,256)]
        elif args.suite in ("focused","smoke"):
            kind="smoke" if args.suite=="smoke" else "behavior"
            planned=[f"{kind}-capacity-{capacities[0]}-seed-{seeds[0]}"]
        elif args.suite=="units":
            planned=["boundary-units"]
        elif args.suite=="synthesis":
            planned=["generic-synthesis","synthesis-artifact-capture"]
        elif args.suite=="checker-sensitivity":
            planned=["mutation"]
        elif args.suite=="reproduce":
            planned=["clean-reproduction"]
        for name in ["environment",*planned]:
            self.receipt["ledger"][name]={"outcome":"not_run"}
        for source in sources(ROOT):
            target=self.output/"source_snapshot"/source.relative_to(ROOT)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
        self.save()

    def save(self):
        (self.output/"receipt.json").write_text(json.dumps(self.receipt,indent=2)+"\n")

    def ledger(self,name,outcome,**fields):
        entry=self.receipt["ledger"].setdefault(name,{})
        entry.update(outcome=outcome,**fields)
        self.save()

    def command(self, argv, name, cwd=ROOT, timeout=3600, allow_failure=False):
        out,err=self.output/f"{name}.stdout",self.output/f"{name}.stderr"
        record={"argv":list(map(str,argv)), "cwd":str(cwd), "start_utc":utc(),
                "timeout_s":timeout,"stdout":str(out),"stderr":str(err)}
        self.receipt["commands"].append(record);self.save()
        with out.open("wb") as stdout,err.open("wb") as stderr:
            try:
                process=subprocess.run(record["argv"],cwd=cwd,stdout=stdout,stderr=stderr,
                                       timeout=timeout,check=False)
                record["exit_code"]=process.returncode
                record["timed_out"]=False
            except subprocess.TimeoutExpired:
                record["exit_code"]=None;record["timed_out"]=True
        record["end_utc"]=utc();self.save()
        if record["timed_out"] or (record["exit_code"] and not allow_failure):
            raise AssertionError(f"tool failed: {name}: {record}; see retained raw logs")
        return record,out.read_text(errors="replace"),err.read_text(errors="replace")

    def environment(self):
        self.ledger("environment","running")
        self.command([sys.executable, "-B", ROOT/"tests/test_runner.py",
                      "--output", self.output/"runner-regression"],
                     "runner-regression")
        regression_path = self.output/"runner-regression/result.json"
        regression = json.loads(regression_path.read_text())
        required_checks = {
            "occupied_output_preserved", "fresh_output_not_certified",
            "gzip_roundtrip", "independent_zlib_roundtrip",
            "artifact_hashes_and_sizes", "artifact_overwrite_rejected",
            "occupied_cli_output_preserved",
            "empty_output_rejected", "file_output_preserved",
            "capture_size_self_accounted", "oversized_capture_rejected",
            "corrupt_hash_retention_rejected", "corrupt_size_retention_rejected",
            "missing_source_selectors_rejected",
        }
        assert set(regression["checks"]) == required_checks
        assert all(value is True for value in regression["checks"].values()), (
            "runner regression did not establish every required preservation check")
        assert regression["collision_command"]["exit_code"] != 0
        self.receipt["runner_regression"] = {
            "result": str(regression_path), "checks": regression["checks"],
            "result_sha256": hashlib.sha256(regression_path.read_bytes()).hexdigest(),
        }
        for tool,arg in (("python3","--version"),("iverilog","-V"),("vvp","-V"),("yosys","-V")):
            executable=shutil.which(tool)
            if executable is None:
                raise FileNotFoundError(f"required tool unavailable: {tool}; no installation attempted")
            _,stdout,stderr=self.command([executable,arg],f"version-{tool}")
            self.receipt["versions"][tool]=(stdout+stderr).strip()
        self.receipt["oracle_known_answers"]=known_answers()
        self.ledger("environment","passed",
                    known_answer_comparisons=sum(self.receipt["oracle_known_answers"].values()))

    def simulate(self,capacity,seed,kind="behavior",root=ROOT,name=None,expected_failure=False):
        name=name or f"{kind}-capacity-{capacity}-seed-{seed}"
        self.ledger(name,"running",capacity_blocks=capacity,seed=seed)
        work=self.output/name;work.mkdir()
        cases=generate(capacity,seed,kind)
        (work/"scenarios.svh").write_text(cases.text())
        rtl=[root/"rtl/rivet_a3_pkg.sv"]+sorted(
            p for p in (root/"rtl").glob("*.sv") if p.name!="rivet_a3_pkg.sv")
        self.command(["iverilog","-g2012","-Wall","-s","bridge",
                      f"-Pbridge.CAPACITY={capacity}","-I",work,
                      "-o",work/"sim.vvp",*rtl,root/"tests/bridge.sv"],name+"-compile")
        record,stdout,stderr=self.command(["vvp","-i",work/"sim.vvp"],name+"-simulate",
                                         timeout=3600,allow_failure=expected_failure)
        if expected_failure:
            assert record["exit_code"]!=0 and re.search(
                r"(OUTPUT|COMPLETION|legacy tag) mismatch",stdout), (
                    "mutation must compile and fail a behavioral comparison, not merely a tool error")
            row={"name":name,"capacity":capacity,"seed":seed,"outcome":"behaviorally_rejected",
                 "raw_receipt_command":name+"-simulate"}
        else:
            assert record["exit_code"]==0,stdout[-3000:]+stderr[-1000:]
            match=re.search(r"^RESULT (.+)$",stdout,re.M)
            assert match, "missing comparison-backed result"
            metrics={k:int(v) for k,v in re.findall(r"(\w+)=(\d+)",match[1])}
            observed=re.findall(r"^CASE (\S+)$",stdout,re.M)
            assert observed==cases.case_names,"missing/duplicated scenario comparisons"
            assert metrics["comparisons"]>0 and metrics["outputs"]>0
            maximum=kind=="boundaries" and capacity==256
            required=("key_stalls","csr_stalls","reset_checks","output_stalls",
                      "completion_stalls")
            if not maximum:
                required+=("tag_stalls",)
            if kind!="smoke":
                required+=("request_stalls","reads","writes")
                if not maximum:
                    required+=("simultaneous","canceled_outputs","canceled_requests")
                    assert metrics["faults"]==12, "not every required memory-fault stage exercised"
                    assert metrics["auth_rejections"]>=131
                    assert metrics["reset_epochs"]>=4
            for field in required:
                assert metrics[field]>0,f"unexercised {field}"
            row={"name":name,"capacity":capacity,"seed":seed,"outcome":"passed",
                 "metrics":metrics,"compared_cases":observed,
                 "required_cases":cases.case_names,"raw_receipt_command":name+"-simulate"}
            row["thresholds"]={"exact_case_list":True,"nonzero_metrics":list(required),
                               "memory_fault_events":0 if maximum else 12 if kind!="smoke" else 0,
                               "minimum_auth_rejections":131 if kind!="smoke" and not maximum else 0}
            row["units"]={"cycles":"rising clock edges","comparisons":"asserted comparison events",
                          "output_bytes":"accepted public payload bytes",
                          "write_lanes":"compared enabled memory-write lanes, including errors"}
        self.ledger(name,row["outcome"],record=row)
        self.receipt["runs"].append(row);self.save()
        return row

    def units(self):
        self.ledger("boundary-units","running")
        work=self.output/"boundary-units";work.mkdir()
        text=(ROOT/"rtl/rivet_a3_top.sv").read_text()
        begin=text.index("    wire [63:0] saved_aad")
        end=text.index("    wire status_range_safe",begin)
        excerpt=text[begin:end]
        (work/"arithmetic.svh").write_text(excerpt)
        self.receipt["boundary_arithmetic"]={
            "origin":"rtl/rivet_a3_top.sv","start_line":text[:begin].count("\n")+1,
            "sha256":hashlib.sha256(excerpt.encode()).hexdigest(),
            "scope":"exact combinational excerpt with public context-store initialization; no top forcing"}
        self.command(["iverilog","-g2012","-Wall","-s","boundary_units","-I",work,
                      "-o",work/"sim.vvp",ROOT/"tests/boundary_units.sv",
                      ROOT/"rtl/rivet_a3_context_store.sv",
                      ROOT/"rtl/rivet_a3_key_table.sv"],"boundary-units-compile")
        _,stdout,_=self.command(["vvp","-i",work/"sim.vvp"],"boundary-units-simulate")
        match=re.search(r"UNIT_RESULT comparisons=(\d+) arithmetic_cases=80 context_banks=4",stdout)
        assert match and int(match[1])>=100
        self.receipt["runs"].append({"name":"boundary-units","outcome":"passed",
                                    "comparisons":int(match[1]),"arithmetic_cases":80})
        self.ledger("boundary-units","passed",comparisons=int(match[1]),
                    arithmetic_cases=80,minimum_comparisons=100)

    def illegal_parameters(self):
        for capacity in (0,257):
            name=f"illegal-capacity-{capacity}"
            self.ledger(name,"running",capacity_blocks=capacity)
            rtl=[ROOT/"rtl/rivet_a3_pkg.sv"]+sorted(
                p for p in (ROOT/"rtl").glob("*.sv") if p.name!="rivet_a3_pkg.sv")
            binary=self.output/f"{name}.vvp"
            self.command(["iverilog","-g2012","-Wall","-s","rivet_a3_top",
                          f"-Privet_a3_top.MAX_PAYLOAD_BLOCKS={capacity}",
                          "-o",binary,*rtl],name+"-compile")
            record,stdout,_=self.command(["vvp",binary],name+"-simulate",allow_failure=True)
            assert record["exit_code"]!=0 and "PARAMETER ERROR" in stdout
            self.receipt["runs"].append({"name":name,"outcome":"explicitly_rejected"})
            self.ledger(name,"explicitly_rejected",compile_exit=0,simulation_exit=record["exit_code"],
                        required_diagnostic="PARAMETER ERROR")
        self.save()

    def synthesis_inputs(self):
        # Yosys 0.33 parses package declarations but not wildcard package imports.
        # Insert the exact package body at each import site, without modifying RTL.
        output=self.output/"yosys-input";output.mkdir()
        package=(ROOT/"rtl/rivet_a3_pkg.sv").read_text()
        body=package.split("package rivet_a3_pkg;",1)[1].rsplit("endpackage",1)[0]
        generated=[]
        for path in sorted((ROOT/"rtl").glob("*.sv")):
            if path.name=="rivet_a3_pkg.sv":
                continue
            text=path.read_text()
            text=text.replace("import rivet_a3_pkg::*;",body)
            assert "import " not in text and "rivet_a3_pkg::" not in text
            target=output/path.name;target.write_text(text);generated.append(target)
        self.receipt["synthesis_frontend"]={
            "method":"verbatim package-body insertion at wildcard imports",
            "package_body_sha256":hashlib.sha256(body.encode()).hexdigest(),
            "generated_sha256":{str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in generated},
            "unmodified_functional_sources":True}
        self.save()
        return generated

    def synthesis(self,capacity=16):
        self.ledger("generic-synthesis","running",capacity_blocks=capacity)
        rtl=self.synthesis_inputs()
        script=self.output/"synthesis.ys"
        script.write_text("read_verilog -sv "+" ".join(map(str,rtl))+"\n"
            f"chparam -set MAX_PAYLOAD_BLOCKS {capacity} rivet_a3_top\n"
            "hierarchy -check -top rivet_a3_top\n"
            "proc\ncheck -assert\n"
            f"write_json {self.output/'hierarchy.json'}\n"
            "synth -top rivet_a3_top -noabc\ncheck -assert\nstat\n"
            f"write_json {self.output/'netlist.json'}\n")
        self.command(["yosys","-s",script],"yosys",timeout=86400)
        for name in ("hierarchy.json","netlist.json"):
            path=self.output/name
            self.retain_synthesis_json(path)
            path.unlink()
        self.inspect_synthesis(self.output,capacity)

    def retain_synthesis_json(self,source):
        target=self.output/(source.name+".gz")
        digest=hashlib.sha256()
        size=0
        with source.open("rb") as original,target.open("xb") as raw:
            with gzip.GzipFile(filename="",mode="wb",fileobj=raw,mtime=0) as compressed:
                while chunk:=original.read(1024*1024):
                    digest.update(chunk)
                    size+=len(chunk)
                    compressed.write(chunk)
        restored=hashlib.sha256()
        restored_size=0
        with gzip.open(target,"rb") as compressed:
            while chunk:=compressed.read(1024*1024):
                restored.update(chunk)
                restored_size+=len(chunk)
        assert restored_size==size and restored.digest()==digest.digest(), (
            f"lossless netlist retention failed: {source}")
        compressed_digest=hashlib.sha256()
        with target.open("rb") as compressed:
            while chunk:=compressed.read(1024*1024):
                compressed_digest.update(chunk)
        self.receipt.setdefault("synthesis_artifacts",{})[source.name]={
            "path":str(target),"encoding":"gzip","uncompressed_bytes":size,
            "uncompressed_sha256":digest.hexdigest(),"compressed_bytes":target.stat().st_size,
            "compressed_sha256":compressed_digest.hexdigest(),
            "roundtrip_verified":True}
        self.save()

    def check_synthesis_capture(self):
        limit = 1073741824
        capture = {"limit_bytes": limit, "total_bytes": 0,
                   "scope": "all files under the declared suite output"}
        self.receipt["artifact_capture"] = capture
        entry = self.receipt["ledger"].setdefault("synthesis-artifact-capture", {})
        entry.clear()
        entry["outcome"] = "running"
        # Include the receipt itself, whose serialized byte count changes here.
        for _ in range(10):
            self.save()
            total = sum(path.stat().st_size for path in self.output.rglob("*")
                        if path.is_file())
            if total == capture["total_bytes"]:
                if total > limit:
                    entry["outcome"] = "failed"
                    entry["error"] = (
                        f"synthesis artifact bundle is {total} bytes, exceeding the "
                        f"{limit}-byte capture limit; retain this failure and use a "
                        "fresh independently admitted output after repair")
                    self.save()
                    raise AssertionError(entry["error"])
                if entry["outcome"] != "passed":
                    entry["outcome"] = "passed"
                    continue
                return
            capture["total_bytes"] = total
        entry["outcome"] = "failed"
        entry["error"] = "synthesis artifact size accounting did not converge"
        self.save()
        raise AssertionError("synthesis artifact size accounting did not converge")

    def inspect_synthesis(self,folder,capacity):
        with gzip.open(folder/"hierarchy.json.gz","rt") as stream:
            hierarchy=json.load(stream)["modules"]
        top=hierarchy["rivet_a3_top"]
        expected={"u_key_table":"rivet_a3_key_table","u_context_store":"rivet_a3_context_store",
                  "u_scheduler_dma":"rivet_a3_scheduler_dma","u_aes_core":"rivet_a3_aes_core",
                  "u_ghash":"rivet_a3_ghash"}
        consumed={bit for cell in top["cells"].values()
                  for port,bits in cell["connections"].items()
                  if cell["port_directions"][port]=="input" for bit in bits
                  if isinstance(bit,int)}
        consumed.update(bit for port in top["ports"].values()
                        if port["direction"]=="output" for bit in port["bits"]
                        if isinstance(bit,int))
        essential={
            "u_key_table":("read_key","read_key_len","valid_mask","lock_mask","result_valid"),
            "u_context_store":("read_data",),
            "u_scheduler_dma":("dispatch_valid","dispatch_descriptor","result_ready",
                               "mem_req_valid","mem_req_wdata","completion_valid"),
            "u_aes_core":("out_block","out_valid","key_ready","key_loaded","in_ready"),
            "u_ghash":("result","done","busy"),
        }
        for instance,module in expected.items():
            cell=top["cells"][instance]
            target=hierarchy[cell["type"]]
            assert cell["type"]==module or target.get("attributes",{}).get(
                "hdlname","").split()[0].lstrip("\\")==module
            assert len(cell["connections"])>4 and target["cells"]
            for port,bits in cell["connections"].items():
                if cell["port_directions"][port]=="output":
                    assert any(isinstance(bit,int) for bit in bits)
            for port in essential[instance]:
                assert set(cell["connections"][port]) & consumed, (
                    f"named instance does not drive its functional consumer: {instance}.{port}")
        for module in ("rivet_a3_key_schedule","rivet_a3_datapath","rivet_a3_sbox",
                       "rivet_a3_mixcolumns","rivet_a3_shiftrows"):
            assert any(cell["type"]==module for parent in hierarchy.values()
                       for cell in parent["cells"].values()),f"missing adapted primitive {module}"
        with gzip.open(folder/"netlist.json.gz","rt") as stream:
            net=json.load(stream)["modules"]
        cells=[c for m in net.values() for c in m["cells"].values()]
        assert not any("latch" in c["type"].lower() for c in cells)
        assert sum("dff" in c["type"].lower() for c in cells)>100
        assert len(cells)>1000
        reset_storage={}
        for module_name,prefixes in {
            "rivet_a3_top":("payload_store[","destination_store["),
            "rivet_a3_context_store":("records[",),
            "rivet_a3_key_table":("keys[",),
        }.items():
            module=net[module_name]
            bits={bit for name,entry in module["netnames"].items()
                  if name.startswith(prefixes) for bit in entry["bits"]
                  if isinstance(bit,int)}
            assert bits,f"no substantive storage for {module_name}"
            assert len(bits)=={
                "rivet_a3_top":4*16*capacity*40,
                "rivet_a3_context_store":4*1280,
                "rivet_a3_key_table":4*256,
            }[module_name],f"incorrect physical state-bit capacity for {module_name}"
            resettable={bit for cell in module["cells"].values()
                        if re.fullmatch(r"\$_DFFE?_PN0P?_",cell["type"])
                        and cell["connections"].get("R")==module["ports"]["rst_n"]["bits"]
                        for bit in cell["connections"]["Q"]}
            assert bits<=resettable,f"storage lacks real asynchronous zero reset: {module_name}"
            reset_storage[module_name]=len(bits)
        self.receipt["synthesis"]={"cells":len(cells),"named_instances":expected,
                                  "latches":0,"resettable_storage_bits":reset_storage,
                                  "physical_signoff":False}
        self.ledger("generic-synthesis","passed",record=self.receipt["synthesis"])

    def sensitivity(self):
        private=self.output/"mutant"
        for p in sources(ROOT):
            target=private/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(p,target)
        path=private/"rtl/rivet_a3_top.sv"
        text=path.read_text()
        original="current_byte^keystream[127:120]"
        assert text.count(original)==1
        path.write_text(text.replace(original,"current_byte^keystream[127:120]^8'h01"))
        self.receipt["mutation"]={"file":str(path),"from":original,
                                  "to":"current_byte^keystream[127:120]^8'h01",
                                  "source_sha256":hashes(private)}
        self.simulate(1,17,"smoke",root=private,name="mutation",expected_failure=True)

    def reproduce(self):
        self.ledger("clean-reproduction","running")
        fresh=self.output/"delivery"
        for path in sources(ROOT):
            target=fresh/path.relative_to(ROOT)
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
        assert hashes(fresh)==hashes(ROOT)
        assert not (fresh/"rivet_a2_reference").exists()
        self.receipt["reproduction_sources"]=hashes(fresh)
        # Invoke the delivered entry from the clean root, not this process's private imports.
        self.command([sys.executable,"tests/verify.py","--suite","focused",
                      "--output","results"],"clean-entry",cwd=fresh,timeout=86400)
        child=json.loads((fresh/"results/receipt.json").read_text())
        assert child["outcome"]=="passed" and child["runs"]
        self.receipt["reproduction_receipt"]=str(fresh/"results/receipt.json")
        self.ledger("clean-reproduction","passed",child_receipt=self.receipt["reproduction_receipt"])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--suite",required=True,choices=[
        "environment","behavior","boundaries","synthesis","checker-sensitivity",
        "reproduce","smoke","focused","units"])
    parser.add_argument("--seeds",default="17,89,203")
    parser.add_argument("--capacities",default="1,3,16")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--repair-of")
    args=parser.parse_args()
    run=Run(args.output,args)
    failed=False
    try:
        run.environment()
        if args.suite in ("smoke","focused"):
            run.simulate(int(args.capacities.split(",")[0]),int(args.seeds.split(",")[0]),
                         "smoke" if args.suite=="smoke" else "behavior")
        elif args.suite=="units":
            run.units()
        elif args.suite=="behavior":
            for capacity in map(int,args.capacities.split(",")):
                for seed in map(int,args.seeds.split(",")):
                    run.simulate(capacity,seed)
        elif args.suite=="boundaries":
            run.units()
            run.illegal_parameters()
            for capacity in (1,3,16,256):
                run.simulate(capacity,203,"boundaries")
        elif args.suite=="synthesis":
            run.synthesis()
        elif args.suite=="checker-sensitivity":
            run.sensitivity()
        elif args.suite=="reproduce":
            run.reproduce()
        assert hashes(ROOT)==run.receipt["source_sha256"],"accepted sources changed during check"
        run.receipt["outcome"]="passed"
        run.receipt["end_utc"]=utc()
        run.receipt["exit_code"]=0
        if args.suite=="synthesis":
            run.check_synthesis_capture()
    except Exception as exc:
        failed=True
        run.receipt["outcome"]="failed"
        run.receipt["error"]=f"{type(exc).__name__}: {exc}"
        for entry in run.receipt["ledger"].values():
            if entry["outcome"]=="running":
                entry["outcome"]="failed"
                entry["error"]=run.receipt["error"]
        (run.output/"failure.txt").write_text(traceback.format_exc())
    finally:
        if failed or "end_utc" not in run.receipt:
            run.receipt["end_utc"]=utc()
        run.receipt["exit_code"]=int(failed)
        run.save()
    print(json.dumps({"suite":args.suite,"outcome":run.receipt["outcome"],
                      "receipt":str(run.output/"receipt.json")}))
    return int(failed)


if __name__=="__main__":
    sys.exit(main())
