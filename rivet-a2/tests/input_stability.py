#!/usr/bin/env python3
"""Retained, harness-only preparation diagnostic for entrypoint input stability."""

import hashlib
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify import ROOT, Run, sources


def fingerprint():
    paths = list(sources())
    paths.extend((ROOT / "tests").rglob("*"))
    return {
        str(p.relative_to(ROOT)): (
            p.is_dir(), p.stat().st_mtime_ns, p.stat().st_size,
            None if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()
        )
        for p in sorted(set(paths))
    }


def main():
    run = Run("input-stability", probe=True)
    print(f"EVIDENCE {run.path.relative_to(ROOT)}", flush=True)
    try:
        run.prerequisites("behavior")
        before = fingerprint()
        run.command(["python3", ROOT / "tests" / "verify.py", "--help"],
                    run.path / "project", "help", inputs=sources())
        if fingerprint() != before:
            raise AssertionError("Project verification inputs changed during entrypoint launch")

        # Each copy begins without a bytecode cache, reproducing the failure's
        # startup condition without deleting or modifying any original artifact.
        for index in (0, 1, 2):
            folder = run.path / f"fresh-{index}"
            copied = folder / "tests"
            copied.mkdir(parents=True)
            for source in (ROOT / "tests").glob("*.py"):
                shutil.copyfile(source, copied / source.name)
            if index == 0:
                entry = copied / "verify.py"
                text = entry.read_text()
                guard = "sys.dont_write_bytecode = True\n"
                if text.count(guard) != 1:
                    raise AssertionError("Ambiguous bytecode-write repair")
                entry.write_text(text.replace(guard, ""))
            inputs = sorted(copied.glob("*.py"))
            _, stdout, _ = run.command(
                ["python3", copied / "verify.py", "--help"], folder, "help",
                inputs=inputs)
            if "--check" not in stdout:
                raise AssertionError("Copied entrypoint did not reach argument parsing")
            if index == 0:
                cache = copied / "__pycache__"
                if (not cache.is_dir()
                        or len(list(cache.glob("*.pyc"))) != 3
                        or sorted(copied.iterdir()) == inputs):
                    raise AssertionError("Negative control did not reproduce input cache creation")
                run.result["negative_control"] = dict(
                    observation="Removed bytecode guard creates three .pyc input files",
                    receipt=str((folder / "help.receipt.json").relative_to(ROOT)))
                run.save()
                continue
            if sorted(copied.iterdir()) != inputs:
                raise AssertionError("Copied entrypoint created a bytecode cache or other input")
        if fingerprint() != before:
            raise AssertionError("Original inputs changed during copied entrypoint launches")
        run.finish("passed", project_inputs_unchanged=True,
                   cache_free_launches=2,
                   scope="entrypoint imports only; no RTL simulation or synthesis")
    except Exception as exc:
        run.finish("failed", failure=dict(message=str(exc)))
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"ADVISORY input stability passed; results={run.path.relative_to(ROOT)}/results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
