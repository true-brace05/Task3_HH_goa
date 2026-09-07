// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title EvidenceRegistry — minimal anchor for evidence root hash
/// @notice Stores ONE root evidence hash per submission. The envelope root hash
///         already commits to candidates + timeline, so candidate-level storage
///         is unnecessary.
contract EvidenceRegistry {
    struct Anchor {
        bytes32 evidenceHash;
        address submitter;
        uint64 timestamp;
        string manifestUri;
    }

    mapping(bytes32 => Anchor) private anchors;

    event EvidenceAnchored(bytes32 indexed evidenceHash, address indexed submitter, uint64 timestamp, string manifestUri);

    /// @notice Register a root evidence hash. Reverts on duplicate.
    function register(bytes32 evidenceHash, string calldata manifestUri) external {
        require(evidenceHash != bytes32(0), "empty hash");
        require(anchors[evidenceHash].timestamp == 0, "already registered");
        anchors[evidenceHash] = Anchor({
            evidenceHash: evidenceHash,
            submitter: msg.sender,
            timestamp: uint64(block.timestamp),
            manifestUri: manifestUri
        });
        emit EvidenceAnchored(evidenceHash, msg.sender, uint64(block.timestamp), manifestUri);
    }

    /// @notice Verify existence of an evidence hash.
    /// @return exists true if anchored
    /// @return anchor stored anchor (zero if not exists)
    function verify(bytes32 evidenceHash) external view returns (bool exists, Anchor memory anchor) {
        Anchor memory a = anchors[evidenceHash];
        if (a.timestamp == 0) {
            return (false, a);
        }
        return (true, a);
    }

    /// @notice Retrieve anchor directly (zero struct if not exists).
    function getAnchor(bytes32 evidenceHash) external view returns (Anchor memory) {
        return anchors[evidenceHash];
    }
}
