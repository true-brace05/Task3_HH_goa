# Blockchain Evidence — Member 3

**Ownership:** Member 3 — Evidence integrity, deterministic hashing, blockchain anchoring, verification. Model-agnostic: records upstream verification results, does not choose the face model. `stub-hash-v1` is a temporary placeholder, not facial recognition.

## Architecture
```
Query Image
↓ Discovery (search/acquisition/runner.run_pipeline)
↓ Normalization (search/normalizer)
↓ Acquisition (VisualSearchAcquisitionProvider → manifest)
↓ Face Verification (verification/adapter.verify_candidate)  — upstream, stub-hash-v1
↓ Enriched Manifest (verification per candidate)
↓ Evidence Builder (evidence/builder.build_evidence)
↓ Candidate SHA-256 (per candidate, verification included)
↓ Root SHA-256 (envelope without evidence_hash)
↓ Blockchain Anchor (contracts/EvidenceRegistry.sol → InMemory/Web3)
↓ Independent Verification (verifier/independent.verify_offline)
```

## Evidence Integrity Model
- **Canonical JSON:** `evidence/canonical.py:canonical_dumps` — sort keys, `(",",":")`, `ensure_ascii=False`, UTF-8, float rejected. One location for `format_score` → string `0.873421` (6 decimals) to avoid floats.
- **Candidate hash:** `hash_candidate(candidate_dict without evidence_hash)` → SHA256. Includes `verification{method,score,decision,timestamp,query_face_detected,candidate_face_detected,error}`, `content_sha256`, `image_url`, `search_rank`, etc. Failed `status=failed` has `evidence_hash=None` not hashed as critical.
- **Root hash:** `hash_envelope(envelope without evidence_hash)` → SHA256. Includes sorted `candidates` (by `search_rank`, `candidate_id`), `candidates[].evidence_hash`, `timeline` (pre-registration), excludes `transaction_hash`/`block_number`/`contract_address`, `blockchain_registered`, runtime metadata.
- **Ordering:** candidates sorted before hashing; timeline order preserved; same logical data → identical bytes → deterministic hash.
- **What changes invalidates:** candidate metadata, `content_sha256`, `verification` method/score/decision, candidate order, hashed timeline.

## Blockchain
- **Contract:** `contracts/EvidenceRegistry.sol` `^0.8.20` — `Anchor{bytes32 evidenceHash, address submitter, uint64 timestamp, string manifestUri}`, `mapping(bytes32=>Anchor)`, `register(bytes32,string)` reverts on duplicate/empty, `verify(bytes32) view→(bool,Anchor)`, `EvidenceAnchored` event.
- **Anchoring:** only **root** `bytes32` (SHA256 hex→`bytes.fromhex`) is stored; candidate hashes committed via root. Duplicate `register` reverts.
- **Anchor metadata separation:** `data/blockchain/anchor_<hash>.json` holds `{evidence_hash, transaction_hash, block_number, contract_address, timestamp, manifestUri}` — never re-hashed into evidence. Evidence file `data/evidence/evidence_<run_id>.json` + canonical `*.canonical.json` (preimage without `evidence_hash`) remain immutable.
- **Clients:** `blockchain/client.py` — `InMemoryBlockchainClient` (deterministic `tx=sha256(hash+counter)`, for CI) and `Web3BlockchainClient` (requires `web3`, `eth_account`, `CHAIN_RPC_URL`, `PRIVATE_KEY`, `CHAIN_ID`, artifact ABI). `hash_to_bytes32` validates 64-hex.

## Verification
- **Cryptographic integrity** (Member 3): “Has recorded evidence been modified?” — `verifier/independent.py:verify_offline(path, client)` recomputes candidate/root hashes, compares, optionally loads `anchor_<hash>.json` and `verify_evidence` on-chain. Returns `{valid, candidate_hashes_valid, root_hash_valid, stored_hash, recomputed_hash, mismatches[], on_chain, anchor}`. `valid` is `candidate_hashes_valid && root_hash_valid`; `on_chain` does not override.
- **Model verification** (Member 1): “Did face model produce this result?” — upstream `verification/adapter`; evidence records result, verifier does not rerun model (avoids env differences).

## Running Locally
1. Environment:
```bash
pip install -r requirements.txt          # Pillow, requests, beautifulsoup4
pip install py-solc-x web3 eth-account   # optional for compile/deploy
cp .env.example .env                     # edit CHAIN_RPC_URL etc.
```
2. Compile contract & artifact:
```bash
python scripts/compile_contract.py
# → contracts/artifacts/EvidenceRegistry.json (abi, bytecode, sourceHash)
```
Artifact is gitignored locally (reproducible); commit intentionally if preferred. `Web3BlockchainClient` auto-loads ABI from artifact.

3. Start local chain (no public testnet):
```bash
anvil --port 8545          # foundry, or
ganache --port 8545
```
4. Deploy:
```bash
CHAIN_RPC_URL=http://127.0.0.1:8545 PRIVATE_KEY=0x... python scripts/deploy_contract.py
# → contract address, tx hash, block number
# writes contracts/artifacts/deployment.json (gitignored)
```
Set `CONTRACT_ADDRESS=0x...` in `.env`.

5. Register & verify (pipeline or direct):
```bash
# Full pipeline (mockable discovery, stub verification before hash)
python -c "from pipeline import run_full_pipeline; from blockchain.client import InMemoryBlockchainClient; print(run_full_pipeline('data/input/query.jpg', blockchain_client=InMemoryBlockchainClient())['envelope'].evidence_hash)"

# Verify file
python scripts/verify_evidence.py data/evidence/evidence_<id>.json
python scripts/verify_evidence.py data/evidence/evidence_<id>.json --on-chain
```

6. E2E demo (no chain required):
```bash
python scripts/e2e_demo.py
# → build → hash → InMemory register → verify VALID+ON-CHAIN → tamper copy → INVALID (candidate mismatch)
python scripts/e2e_demo.py --real-chain   # uses CHAIN_RPC_URL/PRIVATE_KEY
```

## CLI
- `pipeline.py:run_full_pipeline(image_path, register_on_chain, blockchain_client)` — thin orchestrator, face verification **before** `build_evidence`.
- `pipeline.py:verify_pipeline(evidence_path, client)` → `verify_offline`.
- `scripts/deploy_contract.py` / `scripts/compile_contract.py` / `scripts/verify_evidence.py` / `scripts/e2e_demo.py` — thin, no business logic duplication, never log `PRIVATE_KEY`.

## Notes
- `stub-hash-v1` placeholder: replace `_compute_stub_score` with real embedding and set `METHOD` to actual model; evidence hashing unchanged.
- Private key never printed, never written to anchor/evidence.
