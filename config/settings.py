"""Minimal configuration for blockchain POC.

Extends .env pattern already hinted by .env.example in repo.
Loads CHAIN_RPC_URL, CHAIN_ID, CONTRACT_ADDRESS, PRIVATE_KEY.
Does NOT import any blockchain code to avoid circular deps.
PRIVATE_KEY is never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file(env_path: str = ".env") -> None:
    """Load .env file into os.environ if present, without overwriting existing vars."""
    p = Path(env_path)
    if not p.exists():
        return
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


_load_env_file()


@dataclass(frozen=True)
class Settings:
    chain_rpc_url: str = ""
    chain_id: int = 1337
    contract_address: str = ""
    private_key: str = ""
    evidence_version: str = "1.0"
    evidence_output_dir: str = "data/evidence"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        chain_rpc_url = os.environ.get("CHAIN_RPC_URL", "").strip()
        chain_id_raw = os.environ.get("CHAIN_ID", "1337").strip()
        try:
            chain_id = int(chain_id_raw)
        except ValueError:
            chain_id = 1337
        contract_address = os.environ.get("CONTRACT_ADDRESS", "").strip()
        private_key = os.environ.get("PRIVATE_KEY", "").strip()
        evidence_version = os.environ.get("EVIDENCE_VERSION", "1.0").strip()
        evidence_output_dir = os.environ.get("EVIDENCE_OUTPUT_DIR", "data/evidence").strip()
        log_level = os.environ.get("LOG_LEVEL", "INFO").strip()
        return cls(
            chain_rpc_url=chain_rpc_url,
            chain_id=chain_id,
            contract_address=contract_address,
            private_key=private_key,
            evidence_version=evidence_version,
            evidence_output_dir=evidence_output_dir,
            log_level=log_level,
        )

    def is_web3_configured(self) -> bool:
        return bool(self.chain_rpc_url and self.private_key)


def get_settings() -> Settings:
    return Settings.from_env()
