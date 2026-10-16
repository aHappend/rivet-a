#!/usr/bin/env python3
"""Small retained regression for immutable outputs and lossless artifact capture."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import patch
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify import Run, SELECTORS, hashes, sources


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)

    source_fixture = root/"source-selectors"
    fixture_paths = ("rtl/fixture.sv", "design/SPEC.md",
                     "design/ARCHITECTURE.md", "tests/fixture.py")
    for name in fixture_paths:
        path = source_fixture/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("source selector fixture\n")
    assert len(sources(source_fixture)) == len(SELECTORS)
    assert len(hashes(source_fixture)) == len(SELECTORS)
    for selector, name in zip(SELECTORS, fixture_paths):
        path = source_fixture/name
        path.unlink()
        path.mkdir()
        for collect in (sources, hashes):
            try:
                collect(source_fixture)
            except FileNotFoundError as exc:
                assert f"selector matches no files: {selector}" in str(exc)
            else:
                raise AssertionError(f"missing source selector must fail: {selector}")
        path.rmdir()
        path.write_text("source selector fixture\n")

    occupied = root/"occupied"
    occupied.mkdir()
    original = b"retained original evidence\n"
    (occupied/"receipt.json").write_bytes(original)
    options = SimpleNamespace(suite="environment", repair_of=None)
    try:
        Run(occupied, options)
    except FileExistsError as exc:
        assert "fresh independently admitted output path" in str(exc)
    else:
        raise AssertionError("an occupied output must not be reused")
    assert sorted(p.name for p in occupied.iterdir()) == ["receipt.json"]
    assert (occupied/"receipt.json").read_bytes() == original

    empty = root/"empty"
    empty.mkdir()
    existing_file = root/"existing-file"
    existing_file.write_bytes(original)
    for collision in (empty, existing_file):
        try:
            Run(collision, options)
        except FileExistsError as exc:
            assert "fresh independently admitted output path" in str(exc)
        else:
            raise AssertionError(f"existing output must not be reused: {collision}")
    assert list(empty.iterdir()) == [], "empty outputs must not acquire a new receipt"
    assert existing_file.read_bytes() == original

    fresh = Run(root/"fresh", options)
    assert fresh.receipt["commands"] == [] and fresh.receipt["runs"] == []
    assert "outcome" not in fresh.receipt, "allocation is not passing verification"
    payload = json.dumps({
        "modules": {"fixture": {"cells": {}, "netnames": {}}},
        "bytes": list(range(256)),
        "repeated": "retained netlist data\n"*100000,
    }, indent=2).encode()
    source = fresh.output/"fixture.json"
    source.write_bytes(payload)
    fresh.retain_synthesis_json(source)
    compressed = fresh.output/"fixture.json.gz"
    metadata = fresh.receipt["synthesis_artifacts"]["fixture.json"]
    assert source.read_bytes() == payload, "retention must not delete its source"
    assert gzip.decompress(compressed.read_bytes()) == payload
    assert zlib.decompress(compressed.read_bytes(), wbits=31) == payload
    assert json.loads(gzip.decompress(compressed.read_bytes())) == json.loads(payload)
    assert metadata["uncompressed_sha256"] == hashlib.sha256(payload).hexdigest()
    assert metadata["uncompressed_bytes"] == len(payload)
    assert metadata["compressed_sha256"] == hashlib.sha256(compressed.read_bytes()).hexdigest()
    assert metadata["compressed_bytes"] == compressed.stat().st_size
    assert metadata["roundtrip_verified"] is True
    before = compressed.read_bytes()
    try:
        fresh.retain_synthesis_json(source)
    except FileExistsError:
        pass
    else:
        raise AssertionError("retention must not overwrite an existing artifact")
    assert compressed.read_bytes() == before and source.read_bytes() == payload
    original_write = gzip.GzipFile.write
    for corruption in ("hash", "size"):
        damaged_source = fresh.output/f"corrupt-{corruption}.json"
        damaged_source.write_bytes(payload)

        def corrupt_write(stream, data):
            if corruption == "hash":
                data = bytes([data[0] ^ 1]) + data[1:]
            else:
                data = data[:-1]
            return original_write(stream, data)

        with patch.object(gzip.GzipFile, "write", corrupt_write):
            try:
                fresh.retain_synthesis_json(damaged_source)
            except AssertionError as exc:
                assert "lossless netlist retention failed" in str(exc)
            else:
                raise AssertionError(f"{corruption} corruption must fail retention")
        damaged = gzip.decompress(
            (fresh.output/(damaged_source.name+".gz")).read_bytes())
        assert damaged != payload, "the negative fixture must actually corrupt data"
        if corruption == "hash":
            assert len(damaged) == len(payload), "exercise hash, not size, rejection"
        else:
            assert len(damaged) != len(payload), "exercise size rejection"
        assert damaged_source.read_bytes() == payload
        assert damaged_source.name not in fresh.receipt["synthesis_artifacts"]
        retained = json.loads((fresh.output/"receipt.json").read_text())
        assert damaged_source.name not in retained["synthesis_artifacts"]
    argv = [sys.executable, "-B", str(Path(__file__).with_name("verify.py")),
            "--suite", "environment", "--output", str(occupied)]
    stdout_path, stderr_path = root/"collision.stdout", root/"collision.stderr"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.run(argv, cwd=Path.cwd(), stdout=stdout, stderr=stderr,
                                 timeout=3600, check=False)
    assert process.returncode != 0, "occupied CLI output must fail before verification"
    diagnostic = stderr_path.read_text()
    assert "fresh independently admitted output path" in diagnostic
    invocation_line = next(line for line in diagnostic.splitlines()
                           if line.startswith("FileExistsError: verification output"))
    rejected = json.loads(invocation_line.split("Rejected invocation: ", 1)[1])
    assert rejected == {
        "suite": "environment", "output": str(occupied),
        "executable": sys.executable, "script_argv": argv[2:],
        "cwd": str(Path.cwd()),
    }, "collision diagnostics must identify the actual rejected command"
    assert stdout_path.read_bytes() == b"", "a collision must not report suite success"
    assert sorted(p.name for p in occupied.iterdir()) == ["receipt.json"]
    assert (occupied/"receipt.json").read_bytes() == original
    fresh.check_synthesis_capture()
    measured = sum(path.stat().st_size for path in fresh.output.rglob("*")
                   if path.is_file())
    assert fresh.receipt["artifact_capture"]["total_bytes"] == measured
    assert measured <= fresh.receipt["artifact_capture"]["limit_bytes"]
    capture_name = "synthesis-artifact-capture"
    assert fresh.receipt["ledger"][capture_name]["outcome"] == "passed"
    assert json.loads((fresh.output/"receipt.json").read_text())[
        "ledger"][capture_name]["outcome"] == "passed"
    oversized = SimpleNamespace(is_file=lambda: True,
                                stat=lambda: SimpleNamespace(st_size=1073741825))
    with patch.object(Path, "rglob", return_value=[oversized]):
        try:
            fresh.check_synthesis_capture()
        except AssertionError as exc:
            assert "exceeding the 1073741824-byte capture limit" in str(exc)
        else:
            raise AssertionError("oversized synthesis capture must be rejected")
    failed_capture = json.loads((fresh.output/"receipt.json").read_text())
    assert failed_capture["ledger"][capture_name]["outcome"] == "failed"
    assert "exceeding" in failed_capture["ledger"][capture_name]["error"]
    fresh.check_synthesis_capture()
    assert fresh.receipt["ledger"][capture_name] == {"outcome": "passed"}
    assert fresh.receipt["artifact_capture"]["total_bytes"] == sum(
        path.stat().st_size for path in fresh.output.rglob("*") if path.is_file())
    result = {
        "checks": {
            "occupied_output_preserved": True,
            "fresh_output_not_certified": True,
            "gzip_roundtrip": True,
            "independent_zlib_roundtrip": True,
            "artifact_hashes_and_sizes": True,
            "artifact_overwrite_rejected": True,
            "occupied_cli_output_preserved": True,
            "empty_output_rejected": True,
            "file_output_preserved": True,
            "capture_size_self_accounted": True,
            "oversized_capture_rejected": True,
            "corrupt_hash_retention_rejected": True,
            "corrupt_size_retention_rejected": True,
            "missing_source_selectors_rejected": True,
        },
        "collision_command": {
            "argv": argv, "cwd": str(Path.cwd()), "exit_code": process.returncode,
            "timeout_s": 3600, "stdout": str(stdout_path), "stderr": str(stderr_path),
        },
    }
    (root/"result.json").write_text(json.dumps(result, indent=2)+"\n")
    print("RUNNER_RESULT immutable_output=1 fresh_output=1 lossless_retention=1 "
          "independent_gzip_decode=1 immutable_artifact=1 cli_collision=1")


if __name__ == "__main__":
    main()
