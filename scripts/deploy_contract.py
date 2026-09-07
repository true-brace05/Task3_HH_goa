#!/usr/bin/env python3
"""Deploy EvidenceRegistry to configured local chain.

- Loads config/settings.py (CHAIN_RPC_URL, CHAIN_ID, PRIVATE_KEY)
- Compiles contract if artifact missing (via compile_contract)
- Deploys via Web3, waits for receipt
- Prints safe output: contract address, tx hash, block number (never private key)
- Optionally writes contracts/artifacts/deployment.json (gitignored) with address

Usage:
  CHAIN_RPC_URL=http://127.0.0.1:8545 CHAIN_ID=1337 PRIVATE_KEY=0x... python scripts/deploy_contract.py
  # Or configure .env

Requires: pip install py-solc-x web3 eth-account
Local chain: anvil (foundry) or ganache. Example:
  anvil --port 8545   # foundry
  ganache --port 8545
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import get_settings


def load_artifact() -> dict:
    artifact_path = Path("contracts/artifacts/EvidenceRegistry.json")
    if not artifact_path.exists():
        print("[deploy] Artifact not found, compiling ...")
        from scripts.compile_contract import compile_contract  # type: ignore

        artifact = compile_contract()
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with open(artifact_path, "w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2)
        return artifact
    return json.loads(artifact_path.read_text(encoding="utf-8"))


def main():
    settings = get_settings()
    if not settings.chain_rpc_url:
        print("ERROR: CHAIN_RPC_URL not set. Example: CHAIN_RPC_URL=http://127.0.0.1:8545", file=sys.stderr)
        sys.exit(1)
    if not settings.private_key:
        print("ERROR: PRIVATE_KEY not set. Use anvil/ganache test key (never commit).", file=sys.stderr)
        sys.exit(1)

    artifact = load_artifact()
    abi = artifact["abi"]
    bytecode = artifact["bytecode"]

    try:
        from web3 import Web3
        from eth_account import Account
    except ImportError:
        print("ERROR: web3/eth_account not installed. Run: pip install web3 eth-account", file=sys.stderr)
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(settings.chain_rpc_url))
    if not w3.is_connected():
        print(f"ERROR: cannot connect to RPC: {settings.chain_rpc_url}", file=sys.stderr)
        sys.exit(1)

    account = Account.from_key(settings.private_key)
    print(f"[deploy] Deployer: {account.address}  chainId={settings.chain_id}  rpc={settings.chain_rpc_url}")

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx = contract.constructor().build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "chainId": settings.chain_id,
            "gas": 2_000_000,
            "gasPrice": w3.eth.gas_price,
        }
    )
    signed = account.sign_transaction(tx)
    raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction", None)
    tx_hash = w3.eth.send_raw_transaction(raw_tx)
    print(f"[deploy] Sent tx: {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    contract_address = receipt.contractAddress
    print(f"[deploy] Contract deployed: {contract_address}")
    print(f"[deploy] Block: {receipt.blockNumber}  Tx: {tx_hash.hex()}")

    # Write deployment artifact (gitignored)
    out_path = Path("contracts/artifacts/deployment.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    deployment = {
        "contractAddress": contract_address,
        "transactionHash": tx_hash.hex(),
        "blockNumber": receipt.blockNumber,
        "chainId": settings.chain_id,
        "rpcUrl": settings.chain_rpc_url,
        "deployer": account.address,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(deployment, f, indent=2)
    # Safe: never write private key
    print(f"[deploy] Deployment artifact: {out_path}")
    print("Next: set CONTRACT_ADDRESS in .env to:", contract_address)


if __name__ == "__main__":
    main()
