#!/usr/bin/env python3
"""Compile EvidenceRegistry.sol and emit artifact (ABI+bytecode).

Artifact: contracts/artifacts/EvidenceRegistry.json
Contains abi, bytecode, compilerVersion, sourceHash for reproducible verification.
Generated artifact is gitignored (local) — reproduce via this script.
Can be committed intentionally if team prefers committed artifacts.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

CONTRACT_SRC = Path("contracts/EvidenceRegistry.sol")
ARTIFACT_PATH = Path("contracts/artifacts/EvidenceRegistry.json")


def compile_contract() -> dict:
    try:
        import solcx  # type: ignore
    except ImportError:
        raise RuntimeError("py-solc-x not installed. Run: pip install py-solc-x")

    source = CONTRACT_SRC.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()

    # Ensure compiler
    if "0.8.20" not in [str(v) for v in solcx.get_installed_solc_versions()]:
        print("[compile] Installing solc 0.8.20 ...")
        solcx.install_solc("0.8.20")
    solcx.set_solc_version("0.8.20")

    compiled = solcx.compile_source(source, output_values=["abi", "bin"])
    # key is <stdin>:EvidenceRegistry
    key = [k for k in compiled.keys() if k.endswith(":EvidenceRegistry")][0]
    abi = compiled[key]["abi"]
    bytecode = compiled[key]["bin"]

    artifact = {
        "contractName": "EvidenceRegistry",
        "sourceHash": source_hash,
        "compilerVersion": "0.8.20",
        "abi": abi,
        "bytecode": bytecode,
    }
    return artifact


def main():
    if not CONTRACT_SRC.exists():
        raise FileNotFoundError(f"Contract source not found: {CONTRACT_SRC}")
    artifact = compile_contract()
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACT_PATH, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)
    print(f"[compile] Artifact written: {ARTIFACT_PATH}")
    print(f"[compile] sourceHash: {artifact['sourceHash'][:16]}... abi entries: {len(artifact['abi'])} bytecode: {len(artifact['bytecode'])} hex")


if __name__ == "__main__":
    main()
