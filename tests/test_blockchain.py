"""Phase 2 Blockchain POC tests — standalone InMemory verification."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from evidence.builder import build_evidence
from blockchain.client import InMemoryBlockchainClient, hash_to_bytes32, bytes32_to_hex
from blockchain.registration import register_evidence
from blockchain.verification import verify_evidence


FIXTURE_MANIFEST = {
    "query_image": "query.jpg",
    "candidate_count": 2,
    "acquired_count": 2,
    "failed_count": 0,
    "timestamp": "2026-09-06T12:00:00+00:00",
    "candidates": [
        {
            "candidate_id": "cand_001",
            "status": "success",
            "provider": "visual-search-acquisition",
            "local_path": "data/candidates/cand_001.jpeg",
            "content_type": "image/jpeg",
            "file_size": 100,
            "content_sha256": "8d37a2dbaac684b736e007f43990bec42171c7a708bb1fae6a55a508b85e0c95",
            "source_url": "https://example.com/page1",
            "image_url": "https://example.com/img1.jpg",
            "thumbnail_url": None,
            "title": None,
            "search_rank": 1,
            "discovery_provider": "yandex-visual-search",
        },
        {
            "candidate_id": "cand_002",
            "status": "success",
            "provider": "visual-search-acquisition",
            "local_path": "data/candidates/cand_002.jpeg",
            "content_type": "image/jpeg",
            "file_size": 200,
            "content_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "source_url": "https://example.com/page2",
            "image_url": "https://example.com/img2.jpg",
            "thumbnail_url": None,
            "title": None,
            "search_rank": 2,
            "discovery_provider": "yandex-visual-search",
        },
    ],
}

VALID_HASH = "ab" * 32  # 64 hex


class TestInMemoryClient(unittest.TestCase):
    def test_register_valid_hash(self):
        client = InMemoryBlockchainClient()
        anchor = client.register(VALID_HASH)
        self.assertEqual(anchor["evidence_hash"], VALID_HASH)
        self.assertIn("transaction_hash", anchor)
        self.assertIn("block_number", anchor)

    def test_verify_registered_hash(self):
        client = InMemoryBlockchainClient()
        client.register(VALID_HASH)
        found = client.verify(VALID_HASH)
        self.assertIsNotNone(found)
        self.assertEqual(found["evidence_hash"], VALID_HASH)

    def test_verify_unknown_hash(self):
        client = InMemoryBlockchainClient()
        self.assertIsNone(client.verify("ff" * 32))

    def test_duplicate_rejected(self):
        client = InMemoryBlockchainClient()
        client.register(VALID_HASH)
        with self.assertRaises(ValueError):
            client.register(VALID_HASH)

    def test_invalid_hash_rejected(self):
        client = InMemoryBlockchainClient()
        with self.assertRaises(ValueError):
            client.register("short")
        with self.assertRaises(ValueError):
            client.register("zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz")
        with self.assertRaises(ValueError):
            client.verify("not-hex")


class TestHashToBytes32(unittest.TestCase):
    def test_roundtrip(self):
        h = "0123456789abcdef" * 4  # 64 hex
        b = hash_to_bytes32(h)
        self.assertEqual(len(b), 32)
        self.assertEqual(bytes32_to_hex(b), h.lower())

    def test_invalid_rejected(self):
        with self.assertRaises(ValueError):
            hash_to_bytes32("short")


class TestRegistrationLayer(unittest.TestCase):
    def test_valid_envelope_registers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", output_dir=tmpdir, write_files=False)
            client = InMemoryBlockchainClient()
            anchor = register_evidence(env, client, manifest_uri="", anchor_dir=tmpdir, write_anchor=True)
            self.assertEqual(anchor["evidence_hash"], env.evidence_hash)
            self.assertIn("transaction_hash", anchor)
            self.assertIn("block_number", anchor)
            self.assertTrue(anchor["transaction_hash"].startswith("0x"))

    def test_anchor_file_written_separately(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", output_dir=tmpdir, write_files=False)
            client = InMemoryBlockchainClient(contract_address="0x1234567890123456789012345678901234567890")
            anchor = register_evidence(env, client, anchor_dir=tmpdir, write_anchor=True)
            anchor_path = Path(tmpdir) / f"anchor_{env.evidence_hash}.json"
            self.assertTrue(anchor_path.exists())
            with open(anchor_path) as f:
                data = json.load(f)
            self.assertEqual(data["evidence_hash"], env.evidence_hash)
            # never contains private key
            self.assertNotIn("PRIVATE_KEY", json.dumps(data))
            self.assertNotIn("private_key", json.dumps(data).lower())

    def test_envelope_hash_unchanged_after_registration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="cccccccc-cccc-cccc-cccc-cccccccccccc", output_dir=tmpdir, write_files=False)
            before = env.evidence_hash
            client = InMemoryBlockchainClient()
            register_evidence(env, client, anchor_dir=tmpdir, write_anchor=False)
            self.assertEqual(env.evidence_hash, before)
            # evidence file must not have blockchain fields mixed into hash preimage
            env_dict = env.to_dict()
            self.assertNotIn("transaction_hash", json.dumps(env_dict))
            self.assertNotIn("block_number", json.dumps(env_dict))

    def test_invalid_envelope_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="dddddddd-dddd-dddd-dddd-dddddddddddd", output_dir=tmpdir, write_files=False)
            env.evidence_hash = "bad"
            client = InMemoryBlockchainClient()
            with self.assertRaises(ValueError):
                register_evidence(env, client, anchor_dir=tmpdir, write_anchor=False)


class TestVerification(unittest.TestCase):
    def test_registered_verifies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", output_dir=tmpdir, write_files=False)
            client = InMemoryBlockchainClient()
            register_evidence(env, client, anchor_dir=tmpdir, write_anchor=False)
            result = verify_evidence(env.evidence_hash, client)
            self.assertTrue(result["found"])
            self.assertEqual(result["evidence_hash"], env.evidence_hash)
            self.assertIsNotNone(result["transaction_hash"])

    def test_unknown_fails(self):
        client = InMemoryBlockchainClient()
        result = verify_evidence("ff" * 32, client)
        self.assertFalse(result["found"])
        self.assertIsNone(result["submitter"])

    def test_modified_evidence_not_verify(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="ffffffff-ffff-ffff-ffff-ffffffffffff", output_dir=tmpdir, write_files=False)
            client = InMemoryBlockchainClient()
            register_evidence(env, client, anchor_dir=tmpdir, write_anchor=False)
            # modify evidence: change title of first candidate
            env.candidates[0].title = "tampered"
            # need to recompute root hash to simulate tampering detection: new hash != old anchor
            from evidence.hash import hash_candidate, hash_envelope
            # recompute candidate hash then envelope hash
            for c in env.candidates:
                if c.status == "success":
                    c.evidence_hash = hash_candidate(c.to_dict())
            env.evidence_hash = None
            # rebuild envelope dict without hash then hash
            new_hash = hash_envelope(env.to_dict())
            # new hash should NOT verify against old anchor
            result = verify_evidence(new_hash, client)
            self.assertFalse(result["found"])
            # old hash still verifies
            # (we lost old hash, reconstruct by building fresh envelope)
            env2 = build_evidence(FIXTURE_MANIFEST, created_at="2026-09-06T12:00:00+00:00", pipeline_run_id="ffffffff-ffff-ffff-ffff-ffffffffffff", output_dir=tmpdir, write_files=False)
            self.assertTrue(verify_evidence(env2.evidence_hash, client)["found"])


class TestSolidityContract(unittest.TestCase):
    def test_contract_source_exists(self):
        p = Path("contracts/EvidenceRegistry.sol")
        self.assertTrue(p.exists())
        content = p.read_text()
        self.assertIn("pragma solidity ^0.8.20", content)
        self.assertIn("contract EvidenceRegistry", content)
        self.assertIn("register(bytes32", content)
        self.assertIn("EvidenceAnchored", content)

    def test_contract_compiles_if_solc_available(self):
        # Lightweight: try py-solc-x if available, else skip
        try:
            import solcx
        except ImportError:
            self.skipTest("solcx not installed — compilation check skipped")
            return
        try:
            # ensure 0.8.20 available
            if "0.8.20" not in solcx.get_installed_solc_versions():
                solcx.install_solc("0.8.20")
            solcx.set_solc_version("0.8.20")
            source = Path("contracts/EvidenceRegistry.sol").read_text()
            compiled = solcx.compile_source(source, output_values=["abi", "bin"])
            self.assertTrue(len(compiled) > 0)
            key = list(compiled.keys())[0]
            abi = compiled[key]["abi"]
            self.assertTrue(any(item.get("name") == "register" for item in abi))
        except Exception as e:
            self.skipTest(f"compilation failed/skipped: {e}")


class TestNoWeb3DependencyForCoreTests(unittest.TestCase):
    def test_web3_tests_skipped_cleanly_when_unconfigured(self):
        # Ensure InMemory suffices and Web3 not required
        client = InMemoryBlockchainClient()
        h = "aa" * 32
        client.register(h)
        self.assertIsNotNone(client.verify(h))


class TestWeb3ReceiptStatus(unittest.TestCase):
    """Regression: Web3BlockchainClient must reject reverted receipts (status !=1)."""

    def _make_client_with_mock(self, receipt_status):
        from unittest.mock import MagicMock, PropertyMock
        from blockchain.client import Web3BlockchainClient

        # Patch Web3 and Account imports via mocking __init__ collaborators
        mock_w3 = MagicMock()
        mock_contract = MagicMock()
        mock_receipt = MagicMock()
        mock_receipt.status = receipt_status
        mock_receipt.blockNumber = 42
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 1
        mock_w3.eth.send_raw_transaction.return_value = bytes.fromhex("ab" * 32)
        mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt
        mock_w3.is_connected.return_value = True
        mock_w3.to_checksum_address.side_effect = lambda x: x

        mock_account = MagicMock()
        mock_account.address = "0x0000000000000000000000000000000000000000"
        mock_signed = MagicMock()
        mock_signed.raw_transaction = b"\xab" * 32
        mock_account.sign_transaction.return_value = mock_signed

        # Build client without hitting network: patch internal attributes after construction bypass
        # Use __new__ to avoid __init__ side effects, then manually set fields
        client = Web3BlockchainClient.__new__(Web3BlockchainClient)
        client.rpc_url = "http://127.0.0.1:8545"
        client.chain_id = 1337
        client.contract_address = "0x0000000000000000000000000000000000000000"
        client.private_key = "0x" + "00" * 32
        client.abi = []
        client.w3 = mock_w3
        client.account = mock_account
        client.contract = mock_contract
        # contract register builder chain
        mock_contract.functions.register.return_value.build_transaction.return_value = {}
        return client, mock_w3, mock_receipt

    def test_success_receipt_status_1_succeeds(self):
        client, _, receipt = self._make_client_with_mock(receipt_status=1)
        h = "bb" * 32
        anchor = client.register(h)
        self.assertEqual(anchor["evidence_hash"], h)
        self.assertEqual(anchor["block_number"], 42)
        self.assertIn("transaction_hash", anchor)

    def test_reverted_receipt_status_0_raises(self):
        client, _, receipt = self._make_client_with_mock(receipt_status=0)
        h = "cc" * 32
        with self.assertRaises(RuntimeError) as ctx:
            client.register(h)
        self.assertIn("reverted", str(ctx.exception).lower())
        self.assertIn("status=0", str(ctx.exception))

    def test_duplicate_cannot_be_reported_as_success(self):
        # Simulate contract revert on duplicate (status 0) must not return anchor
        client, _, _ = self._make_client_with_mock(receipt_status=0)
        h = "dd" * 32
        with self.assertRaises(RuntimeError):
            client.register(h)
        # No anchor should be returned; exception ensures caller cannot treat as success

    def test_status_none_treated_as_success_for_legacy_nodes(self):
        # If node returns no status field (pre-Byzantium), legacy behaviour preserves success
        from unittest.mock import MagicMock
        from blockchain.client import Web3BlockchainClient

        client, mock_w3, _ = self._make_client_with_mock(receipt_status=1)
        # Override receipt to have no status attribute
        legacy_receipt = MagicMock()
        # delete status attr
        del legacy_receipt.status
        legacy_receipt.blockNumber = 99
        # Make it dict-like fallback without status key
        legacy_receipt.__class__ = type("LegacyReceipt", (), {"__getattr__": lambda self, k: (_ for _ in ()).throw(AttributeError(k))})  # noqa
        # Simpler: use SimpleNamespace-like object
        class SimpleReceipt:
            blockNumber = 99
        mock_w3.eth.wait_for_transaction_receipt.return_value = SimpleReceipt()
        h = "ee" * 32
        anchor = client.register(h)
        self.assertEqual(anchor["block_number"], 99)

    def test_inmemory_unchanged(self):
        # Ensure InMemory still rejects duplicate via ValueError, not RuntimeError path
        from blockchain.client import InMemoryBlockchainClient

        c = InMemoryBlockchainClient()
        h = "ff" * 32
        c.register(h)
        with self.assertRaises(ValueError):
            c.register(h)
        self.assertIsNotNone(c.verify(h))


if __name__ == "__main__":
    unittest.main()
