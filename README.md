# Visual Evidence Verification

A reproducible **visual discovery → face verification → tamper-evident evidence → optional blockchain anchor** pipeline. Upload a query image, discover visually related candidates, verify identities with **InsightFace buffalo_l**, build a canonical **SHA-256** evidence envelope that commits to every verification result and timeline entry, and verify offline. Optionally anchor the **root hash only** on an Ethereum smart contract (`EvidenceRegistry`) for cryptographic timestamping.

---

## Why this project exists

Images found online can be copied, re-encoded, cropped, reordered, or have their verification results altered after collection. Screenshots and manual comparisons are not reproducible or cryptographically verifiable.

This project creates an automated, reproducible chain of custody that combines:

- visual candidate discovery (reverse-image-style search)
- real face detection and verification
- deterministic evidence serialization and hashing
- independent offline verification
- optional blockchain anchoring

**Blockchain anchors the 64-hex root evidence hash, not the images or full evidence JSON.** Images and evidence stay off-chain; only the hash is `register(bytes32)`-ed for tamper detection.

---

## How it works

```
Query Image
    │
    ▼
Visual Discovery        search/searcher.py, search/visual/yandex.py
    │                   Yandex Visual Search (primary), post image → parse HTML/JSON
    ▼
Candidate Normalization search/normalizer.py, search/visual/runner.py
    │
    ▼
Candidate Acquisition   search/acquisition/  downloads image_url → validates PIL → SHA-256 → data/candidates/
    │
    ▼
Face Verification       face/detector.py + embedder.py + matcher.py + ranking.py
    │                   verification/adapter.py  (adapter, query embedding reused)
    │                   insightface-buffalo_l, cosine similarity, max-selection
    ▼
Evidence Construction   evidence/builder.py + schema.py
    ├── Candidate Hashes (SHA-256 of canonical candidate, excludes evidence_hash)
    ├── Verification Results (deterministic 6-decimal string scores)
    └── Timeline (discovery → normalization → acquisition → verification → evidence_built)
    │
    ▼
Root Evidence Hash      evidence/hash.py  hash_envelope() canonical SHA-256 (preserves candidate hashes, excludes root evidence_hash)
    │
    ├──────────────────► Independent Offline Verification  verifier/independent.py
    │                     recomputes candidate hashes + root hash + order + timeline
    │
    ▼
Optional Blockchain Anchor  blockchain/registration.py + client.py  EvidenceRegistry.sol
                         InMemory (deterministic) or Web3 (Ganache/anvil) — register + verify + receipt status==1
                         evidence hash only — never images

Flask UI                  app.py  wraps pipeline.run_full_pipeline() + verifier.verify_offline()
                          vanilla JS + Tailwind CDN
```

Authoritative orchestration is `pipeline.py:run_full_pipeline()` (1-discovery, 2-face verification, 3-timeline, 4-`build_evidence`, 5-optional `register_evidence`). `pipeline.verify_pipeline()` / `verifier/independent.verify_offline()` is the verifier.

---

## Core Features

### Visual Candidate Discovery
`search/searcher.py` delegates to `YandexVisualSearchProvider` (primary) with `GoogleLensProvider` fallback (honestly reports CAPTCHA blocks). Posts local image to Yandex endpoint via `requests` + `BeautifulSoup`, extracts `source_url`/`image_url`/`title`, deduplicates via `search/normalizer.py`.

### Candidate Acquisition
`search/acquisition/runner.py` + `VisualSearchAcquisitionProvider` download `image_url`, enforce timeouts, limit response size, validate content-type and PIL image, compute `content_sha256` (64 hex), save deterministic `data/candidates/cand_*.jpg`, write `data/debug/candidate_manifest.json`. Handles `status: success|failed`, preserves failed entries.

### Face Verification
`face/detector.py` (`get_face_analyzer("buffalo_l")` CPU, `providers=["CPUExecutionProvider"]`, `det_size=(640,640)`), `embedder.py` L2-normalized embeddings, `matcher.py` cosine similarity (dot of unit vectors, clipped `[-1,1]`, `verify_candidate_embeddings` selects **maximum** across faces), `ranking.py` thresholds, `verification/adapter.py` thin adapter returning `VerificationData{method,score,decision,timestamp,query_face_detected,candidate_face_detected,error}`.

### Deterministic Verification Results
`verification/adapter.py:38` `METHOD="insightface-buffalo_l"`, `SCORE_PRECISION=6`, `format_score(f"{value:.6f}")` always string. Query embedding generated once via `get_reference_embedding()` and reused via `verify_candidate_with_embedding()` for all candidates.

### Tamper-Evident Evidence
`evidence/builder.py:build_evidence(manifest, timeline, write_files=True)` sorts candidates (`search_rank`, `candidate_id`), hashes each success with `hash_candidate()` (excludes `evidence_hash`), builds `EvidenceEnvelope{envelope_version="1.0", pipeline_run_id=uuid4, created_at, candidates, timeline}` and `hash_envelope()` (excludes top-level `evidence_hash` only). Writes `data/evidence/evidence_<run>.json` (pretty) + `.canonical.json` (exact hashing preimage). Timeline events `discovery_complete → normalization_complete → acquisition_complete → verification_complete → evidence_built`; `blockchain_registered` stays **outside** envelope in `EventBus` + `data/blockchain/anchor_<hash>.json`.

### Independent Verification
`verifier/independent.py:verify_offline(path, client=None, anchor_dir="data/blockchain")` recomputes candidate hashes (preserving order), recomputes root hash, compares, optionally checks anchor file and `blockchain/verification.verify_evidence` on-chain. Returns `{valid, candidate_hashes_valid, root_hash_valid, stored_hash, recomputed_hash, mismatches[], on_chain, anchor}`. `valid` is strictly `candidate_hashes_valid && root_hash_valid`; `on_chain` never rescues tampering.

### Optional Blockchain Anchoring
`contracts/EvidenceRegistry.sol` pragma `^0.8.20`: `mapping(bytes32=>Anchor)`, `register(bytes32 evidenceHash, string manifestUri)` reverts on `bytes32(0)` or duplicate `timestamp==0`, `verify(bytes32) view returns (bool,Anchor)`. `blockchain/client.py` `InMemoryBlockchainClient` (deterministic `tx_hash = sha256(hash+block)` ) and `Web3BlockchainClient` ( `web3.py` + `eth_account`, `gas 200000`, `wait_for_transaction_receipt` + explicit `receipt.status==1` else `RuntimeError: reverted (status=0)`). Anchoring stores only root hash + `submitter/timestamp/manifestUri/tx/block/contract`.

### Security-Aware UI
`app.py` Flask (`MAX_CONTENT_LENGTH 20MiB`) with `GET /`, `GET /api/status`, `GET /api/evidence/list` (excludes `.canonical.json`), `GET /image/<token>` opaque token (`uuid4` → `Path` map) + `GET /candidate_image` legacy allowlisted (`UPLOAD_DIR`, `data/candidates`, `data/input` via `resolve().is_relative_to()` → `403` otherwise), `POST /api/investigate` (multipart `image` + `anchor`?), `POST /api/verify`, `POST /api/tamper_demo`. Sanitizes error messages (strips `/tmp`, `/var`, `home`, `data` absolute), drops `trace` field, logs server-side. Frontend `templates/index.html` vanilla JS, Tailwind CDN, JetBrains Mono for hashes, forensic dark theme (charcoal `#0f1114`, surface `#1a1d23`), Evidence Pipeline `01–05` visual, candidate grid, face cards (`↔` query vs candidate), multi-face note, failure reasons, `Evidence Hash ≠ Transaction Hash` distinction, mobile hamburger drawer, `isInvestigating` disable + spinner, inline error banner.

---

## Face Verification

- **Model:** `insightface` `buffalo_l` — 5 ONNX: `det_10g.onnx` (detection), `w600k_r50.onnx` (recognition), `2d106det`, `1k3d68`, `genderage`. Singleton `get_face_analyzer()` cached.
- **Detection:** `face/detector.py:detect_faces` loads via `cv2.imdecode(np.fromfile)`, `app.get(img)` → `bbox, det_score, embedding, kps`. `detect_query_face` enforces **exactly 1** face → `ValueError: No face detected` / `Multiple faces (N) ...`.
- **Embedding:** `face/embedder.py:normalize_embedding` L2 `emb/norm`, `generate_embedding(face_or_image)` accepts dict/path/ndarray.
- **Matching:** `face/matcher.py:compute_similarity` normalizes both, `dot` clipped. `verify_candidate` handles `not found → status:error`, `0 faces → no_face`, `≥1 faces → generate_embedding each → verify_candidate_embeddings → max similarity` (not average). Returns `{faces_detected, best_face_index, best_similarity, face_similarities, status, quality_status, error}`.
- **Query reuse:** `pipeline._run_face_verification` calls `get_reference_embedding(query)` once; if `No face` → all candidates `inconclusive`, else `error`. Then `verify_candidate_with_embedding(ref, candidate)` per acquired `local_path`. One failed candidate never crashes pipeline.
- **Decision states (lowercase `evidence` vocab, mapped from `face/ranking` upper):**

| `best_similarity` | `face/ranking.make_decision` | `verification.adapter` `decision` |
|---|---|---|
| `>= 0.70` | `MATCH` | `match` |
| `<= 0.40` | `NO MATCH` | `no_match` |
| `0.40 < s < 0.70` or `None` | `INCONCLUSIVE` | `inconclusive` |
| file missing/corrupt | — | `error` (`query_face_detected`/`candidate_face_detected` `None`) |

Thresholds are `DEFAULT_HIGH_THRESHOLD = 0.70`, `DEFAULT_LOW_THRESHOLD = 0.40` (`verification/adapter.py:39-40`, `face/ranking.py:15-16`) — demo / POC, not production-calibrated, validated on buffalo_l cosine space.

- **Edge cases:** no query face → `inconclusive` + `query_face_detected=False`; multiple query faces → `error`; no candidate face → `inconclusive` + `candidate_face_detected=False` + `score None`; error → `decision error`, `candidate_face_detected None`.

---

## Evidence Model

`evidence/schema.py` dataclasses `VerificationData{method,score,decision,timestamp,query_face_detected,candidate_face_detected,error}`, `CandidateEvidence{..., discovery_provider, search_rank, status, evidence_hash, verification}`, `TimelineEvent{ts,event,detail,actor}`, `EvidenceEnvelope{envelope_version="1.0", query_image, manifest_timestamp, created_at, pipeline_run_id, candidate_count, acquired_count, evidence_hash, candidates[], timeline[]}`.

- **Included:** all candidates (preserving `search_rank` order), `content_sha256`, `source_url`, `image_url`, `verification` (method/score/decision…), `candidate evidence_hash` per success ( `hash_candidate` of canonical candidate without its `evidence_hash`), `timeline` (5 pre-registration events + `evidence_built` with `evidence_hash`), `root evidence_hash` (`hash_envelope` of canonical envelope without top-level `evidence_hash` only — candidate hashes preserved).
- **Score determinism:** `verification/adapter.format_score` `f"{float:.6f}"` → string. `evidence/canonical.py:canonical_dumps` `json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=False).encode('utf-8')` and `_reject_floats` raises `ValueError` on any `float` — hashes are on decimal strings, never binary floats.
- **Order matters:** `builder.py` sorts candidates (`search_rank`, `candidate_id`) before hashing; reordering changes `hash_envelope` → invalid.
- **Timeline protected:** `timeline` is inside envelope before `evidence_built` recompute; mutating `candidate_count` or any event invalidates root.
- **Hash represents complete envelope:** root `evidence_hash` commits to candidates + verification + timeline + metadata. Changing any body field changes root.
- **Blockchain metadata excluded:** `register_evidence` writes `data/blockchain/anchor_<hash>.json` (`evidence_hash, submitter, timestamp, manifestUri, transaction_hash, block_number, contract_address`) **outside** envelope; `EventBus` `blockchain_registered` is runtime only. Re-hashing envelope after anchoring does not include anchor.

---

## Tamper Detection

`verifier/independent.verify_offline` recomputes every hash from the file itself and compares to stored values. Any body mutation invalidates; old anchor never rescues.

| Tampered Field | Stored vs Recomputed | `valid` |
|---|---|---|
| Verification `score` (`"0.982642"` → `"0.000000"`) | `candidate_hash_mismatch` + `root_hash_mismatch` | `false` |
| Verification `decision` (`no_match` → `match`) | `candidate_hash_mismatch` + `root_hash_mismatch` | `false` |
| Candidate order (reverse list) | `root_hash_mismatch` | `false` |
| Timeline (`candidate_count 4 → 999`) | `root_hash_mismatch` | `false` |
| Root `evidence_hash` (`→ 0*64`) | `root_hash_mismatch` | `false` |

Also checks `missing_root_hash`, `failed_candidate_hash_not_none`, `missing_candidate_hash`, `anchor_hash_mismatch`. Valid evidence (`candidate_hashes_valid && root_hash_valid`) → `valid true`; tampered copy → `valid false` even if original anchor exists.

---

## Blockchain

**Does NOT store:** query images, candidate images, full evidence JSON. Only the root evidence hash.

Flow: `evidence JSON → canonical → SHA-256 evidence_hash (64 hex) → hash_to_bytes32 → EvidenceRegistry.register(bytes32, manifestUri) → transaction proof`.

**Modes:**
- `InMemoryBlockchainClient(contract_address="0x000…")` — deterministic `block_number` increment, `tx_hash=sha256(hash+block)[0:64]`, duplicate `ValueError`. Used when `CHAIN_RPC_URL/PRIVATE_KEY` absent (CI/demo default).
- `Web3BlockchainClient(rpc_url, contract_address, private_key, chain_id=1337, abi)` — `contracts/artifacts/EvidenceRegistry.json` ABI, `eth_account` signing, `send_raw_transaction`, `wait_for_transaction_receipt(timeout=120)` with **explicit `receipt.status==1` else `RuntimeError: blockchain transaction reverted (status=0)`** (fixes duplicate reporting). `verify(bytes32)` view call maps to `{found, submitter, timestamp, manifestUri}`.

**Config:** `.env` (gitignored) or env vars `CHAIN_RPC_URL`, `CHAIN_ID`, `CONTRACT_ADDRESS`, `PRIVATE_KEY` (`config/settings.py:Settings.from_env()`). Example `.env.example`: `CHAIN_RPC_URL=http://127.0.0.1:8545`, `CHAIN_ID=1337`. `contracts/artifacts/deployment.json` (gitignored) written by `scripts/deploy_contract.py`.

**Receipt handling:** `blockchain/client.py:Web3BlockchainClient.register` inspects `receipt.status` / `receipt.blockNumber` (dict or object), raises on `!=1`, sanitizes `private_key → "***"`.

---

## Architecture

| Component | Responsibility |
|---|---|
| `pipeline.py` | Authoritative orchestration `run_full_pipeline(image_path, register_on_chain, blockchain_client, evidence_output_dir, anchor_dir) → {manifest,enriched_manifest,verification_results,envelope,anchor,event_bus}` and `verify_pipeline(path, client, anchor_dir)` |
| `search/` | `searcher.py` → Yandex primary, Google Lens backup; `normalizer.py` deterministic IDs; `retriever.py` HTTP failures/empty; `acquisition/runner.py` + `visual` provider |
| `search_provider/` | Additional provider config/audit |
| `face/` | `detector.py` buffalo_l, `embedder.py` normalize, `matcher.py` cosine + max-selection, `ranking.py` `make_decision`/`rank_candidates` |
| `verification/` | `adapter.py` `METHOD="insightface-buffalo_l"`, `get_reference_embedding`, `verify_candidate_with_embedding`, `verify_candidate`, `verify_candidates` |
| `evidence/` | `schema.py` dataclasses, `builder.py` `build_evidence(manifest,timeline,…)`, `canonical.py` `canonical_dumps` (reject floats), `hash.py` `hash_candidate`/`hash_envelope`/`sha256_hex`, `timeline.py` |
| `verifier/` | `independent.py` `verify_offline(path, client, anchor_dir)` |
| `blockchain/` | `client.py` `InMemory`/`Web3` + `hash_to_bytes32`, `registration.py` `register_evidence(envelope, client, anchor_dir)`, `verification.py` `verify_evidence(hash, client)` |
| `contracts/` | `EvidenceRegistry.sol` + `artifacts/EvidenceRegistry.json` + `artifacts/deployment.json` (gitignored) |
| `config/` | `settings.py` `get_settings()` loads `.env` |
| `utils/` | `events.py` `EventBus` |
| `app.py` | Flask `app` (`template_folder="templates"`, `static_folder="static"`, `MAX_CONTENT_LENGTH 20MiB`), 8 routes: `/`, `/api/status`, `/api/evidence/list`, `/uploads/<f>`, `/image/<token>` (opaque), `/evidence_file/<f>`, `/candidate_image` (allowlisted legacy), `/api/investigate`, `/api/verify`, `/api/tamper_demo` |
| `templates/index.html` | Single-page forensic UI (vanilla JS + Tailwind CDN + JetBrains Mono), sidebar `Investigate/Evidence/Verification/Blockchain/System Status`, pipeline `01–05`, candidate grid, face cards, integrity panel, anchor panel, tamper demo, mobile drawer |
| `scripts/` | `compile_contract.py`, `deploy_contract.py` (loads `Settings`, signs, `send_raw_transaction` with `raw_transaction` fallback, writes `deployment.json`), `e2e_demo.py`, `verify_evidence.py` |

Directory: `data/input/` (query), `data/candidates/` (acquired), `data/debug/candidate_manifest.json`, `data/evidence/` (evidence_*.json + canonical), `data/blockchain/` (anchor_*.json), `~/.insightface/models/buffalo_l/` 336 MB (5 ONNX).

---

## Getting Started

```bash
git clone <repo>
cd Task3_HH_goa
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# requirements: Pillow, requests, beautifulsoup4, numpy, opencv-python, onnxruntime, insightface, Flask
```

**Quick UI demo (no blockchain):**
```bash
python3 app.py
# http://127.0.0.1:5001
# Upload JPG/PNG/WEBP (single face recommended) → 20 discovered → acquired → face verification → evidence hash
# Evidence → Inspect  data/evidence/evidence_*.json
# Verification → drop evidence JSON → VALID / TAMPER DETECTED
# Tamper buttons → score/decision/order/timeline → mismatches
```

**CLI pipeline (no UI):**
```python
from pipeline import run_full_pipeline, verify_pipeline
res = run_full_pipeline("data/input/query.jpg", register_on_chain=False)
print(res["envelope"].evidence_hash)
verify_pipeline("data/evidence/evidence_<id>.json")
```
```bash
python -m search.visual.runner   # Yandex visual search only
python scripts/e2e_demo.py        # InMemory evidence→hash→anchor→verify
python scripts/verify_evidence.py data/evidence/evidence_*.json
```

**Optional blockchain (Ganache):**
```bash
npx ganache --detach --port 8545 --chain.chainId 1337 --wallet.mnemonic "test test test test test test test test test test test junk"
cp .env.example .env
# edit .env: CHAIN_RPC_URL=http://127.0.0.1:8545, CHAIN_ID=1337, PRIVATE_KEY=0xac09…f2ff80 (ganache acct 0), CONTRACT_ADDRESS after deploy
python3 scripts/compile_contract.py
python3 scripts/deploy_contract.py  # writes contracts/artifacts/deployment.json
# then in UI: check “Anchor on blockchain” on Investigate, or
# python3 app.py → investigate will register if .env configured; Verification “check on-chain” uses Web3
```

**Tests:**
```bash
python3 -m unittest discover -s tests -v
# 165 tests including InMemory, Web3 receipt status, canonical float rejection, face thresholds, offline verifier, acquisition, UI security
python3 -m unittest tests.test_ui_security -v
python3 -m unittest tests.test_blockchain.TestWeb3ReceiptStatus -v
```

---

## Real Validation Already Performed

Confirmed from code/tests and existing `/tmp` artifacts (not mocked):

1. **Real buffalo_l** via `face/detector.get_face_analyzer()` — 5 ONNX cached `~/.insightface/models/buffalo_l` (336 MB), `skimage.data.astronaut` (1 face) + `insightface/data/images/t1.jpg` (6 faces).
2. **Same-identity augmentation** (astronaut brightness 1.1 + 2° rotate) → **0.982642** `match`; verified `verify_candidate_with_embedding` reuse.
3. **Different-face** cropped `t1` face0 → **0.038130** `no_match`, face2 → **0.034953**, multi full `t1` max **0.094492** among 6 sims.
4. **No-face** solid noise → `0 faces`, `inconclusive`, `score None`, `candidate_face_detected False`.
5. **Multi-face** `t1.jpg` 6 faces → `faces_detected 6`, `best_face_index` + `max` similarity (not average).
6. **Real evidence** `/tmp/real_evidence_test/evidence_real-validation-0001.json` root `729a1874a72403349e4505f5e1b8563469a9431adbffa3885cb0a8ad37b2cffc`, 4 candidates `04a33a…/c8848a…/9174f1…/6c8690…`.
7. **Hashes:** candidate `hash_candidate` reproducible, root `hash_envelope` reproducible, `canonical_dumps` `ValueError` on float, `verify_offline` `valid true`.
8. **Tamper:** copies `tampered_score/decision/order/timeline/root` → `candidate_hash_mismatch` + `root_hash_mismatch` → `valid false`, original stays `valid true`.
9. **Ganache** `deepfried_cinnamon_muffin` `127.0.0.1:8545` `chainId 1337`, contract `0x5FbDB2315678afecb367f032d93F642f64180aa3` deploy tx `f6d9ad…` block 1 `status 1`, register `729a…` tx `db3c02…` block 2 `status 1`, `verify true`, `unknown 0*64` → `None`.
10. **Duplicate rejected:** second `register(same hash)` → `receipt status 0` → `RuntimeError: reverted (status=0)` (client now checks `receipt.status`).
11. **Suite:** `Ran 165 tests OK` (unit + InMemory/Web3/face/evidence/verifier/UI security).

---

## Security Notes

- `GET /candidate_image` and `GET /image/<token>` strictly allowlist `UPLOAD_DIR`, `data/candidates`, `data/input` via `Path.resolve().is_relative_to()` → `403` otherwise (`/etc/passwd` tested). No absolute paths, no `trace` in API errors, sanitized messages. Uploads via `send_from_directory`, traversal blocked.
- `Evidence Hash ≠ Transaction Hash` — evidence stays local; tx hash is chain receipt.
- `Web3` duplicate `status 0` correctly raises; InMemory duplicate `ValueError`.
- `candidate order` is integrity-critical; reordering invalidates root.

## Limitations

- Thresholds `0.70/0.40` demo POC, not production-calibrated.
- Yandex public endpoint subject to rate-limit/availability; reports `[VISUAL SEARCH BLOCKED]` honestly.
- ganache ephemeral (`--detach`); `deployment.json` gitignored; re-deploy per fresh env.
- Model cache ~336 MB not in git; first run downloads buffalo_l.

## License

MIT — see [LICENSE](LICENSE).

## 🎥 Project Demo

A complete walkthrough of our end-to-end pipeline, demonstrating reverse image discovery, multi-candidate face verification, evidence generation, SHA-256 hashing, independent verification, and tamper detection.

▶️ [Watch the Demo Video on YouTube](https://youtu.be/cg4vpDRE6Fc?si=E8MHoikUKPNWJ8k5)



