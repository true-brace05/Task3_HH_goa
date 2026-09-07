"""Blockchain package."""

from blockchain.client import BlockchainClient, InMemoryBlockchainClient

try:
    from blockchain.client import Web3BlockchainClient
except Exception:  # web3 not installed in CI
    Web3BlockchainClient = None  # type: ignore

__all__ = ["BlockchainClient", "InMemoryBlockchainClient", "Web3BlockchainClient"]
