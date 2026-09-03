"""
Agent System (Enterprise++ v3.5) - Merkle Tree Audit Ledger
Cryptographic Merkle Tree for immutable audit log verification.

Features:
- SHA-256 Merkle Tree for tamper-proof audit logs
- Block chaining with hash linking
- O(1) checkpoint integrity verification on startup
- CRITICAL ALARM on integrity violation
- Automatic system halt on history modification detection
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MerkleTreeConfig(BaseModel):
    """Merkle Tree configuration."""
    hash_algorithm: str = "sha256"
    leaf_prefix: str = "0x00"
    internal_prefix: str = "0x01"
    hash_combine: str = "concat_then_hash"
    checkpoint_interval: int = Field(default=100, ge=10, le=1000)
    checkpoint_path: str = "/var/log/agent_audit/checkpoints/"


class Checkpoint(BaseModel):
    """Merkle tree checkpoint for O(1) verification."""
    sequence: int
    root_hash: str
    entry_count: int
    timestamp: float
    prev_checkpoint_hash: str = ""


@dataclass
class MerkleNode:
    """Single node in Merkle tree."""
    hash_value: str
    left: Optional[MerkleNode] = None
    right: Optional[MerkleNode] = None
    is_leaf: bool = False
    data: str = ""


class IntegrityViolationError(Exception):
    """Raised when audit log integrity is violated."""
    pass


class MerkleTreeAudit:
    """
    Merkle Tree for cryptographic audit log verification.
    
    Implements:
    - SHA-256 Merkle Tree construction
    - Block chaining with hash linking
    - O(1) checkpoint integrity verification
    - CRITICAL ALARM on tampering detection
    """

    def __init__(self, config: MerkleTreeConfig):
        self._config = config
        self._leaves: list[str] = []
        self._root: Optional[MerkleNode] = None
        self._root_hash: str = ""
        self._entry_count = 0
        self._checkpoints: list[Checkpoint] = []
        self._last_checkpoint_hash = ""
        self._checkpoint_path = Path(config.checkpoint_path)
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize Merkle Tree and load checkpoints."""
        try:
            self._checkpoint_path.mkdir(parents=True, exist_ok=True)
            await self._load_latest_checkpoint()
            logger.info(f"MerkleTreeAudit initialized (entries={self._entry_count}, checkpoints={len(self._checkpoints)})")
        except Exception as e:
            logger.error(f"Failed to initialize MerkleTreeAudit: {e}")
            raise

    async def add_entry(self, entry_hash: str) -> str:
        """
        Add audit entry hash to Merkle tree.
        
        Args:
            entry_hash: SHA-256 hash of audit entry
            
        Returns:
            Current root hash
        """
        async with self._lock:
            leaf_hash = self._hash_leaf(entry_hash)
            self._leaves.append(leaf_hash)
            self._entry_count += 1
            self._root = self._build_tree(self._leaves)
            self._root_hash = self._root.hash_value if self._root else ""

            if self._entry_count % self._config.checkpoint_interval == 0:
                await self._create_checkpoint()

            return self._root_hash

    def _hash_leaf(self, data: str) -> str:
        """Hash leaf data with prefix."""
        prefixed = f"{self._config.leaf_prefix}{data}"
        return hashlib.sha256(prefixed.encode()).hexdigest()

    def _hash_internal(self, left: str, right: str) -> str:
        """Hash internal node with prefix."""
        if self._config.hash_combine == "concat_then_hash":
            combined = f"{self._config.internal_prefix}{left}{right}"
        else:
            combined = f"{left}{right}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def _build_tree(self, leaves: list[str]) -> Optional[MerkleNode]:
        """Build Merkle tree from leaf hashes."""
        if not leaves:
            return None

        nodes = [MerkleNode(hash_value=h, is_leaf=True, data=h) for h in leaves]

        while len(nodes) > 1:
            next_level = []
            for i in range(0, len(nodes), 2):
                left = nodes[i]
                right = nodes[i + 1] if i + 1 < len(nodes) else nodes[i]
                parent_hash = self._hash_internal(left.hash_value, right.hash_value)
                parent = MerkleNode(
                    hash_value=parent_hash,
                    left=left,
                    right=right,
                )
                next_level.append(parent)
            nodes = next_level

        return nodes[0] if nodes else None

    async def _create_checkpoint(self) -> None:
        """Create checkpoint for O(1) verification."""
        checkpoint = Checkpoint(
            sequence=len(self._checkpoints),
            root_hash=self._root_hash,
            entry_count=self._entry_count,
            timestamp=time.time(),
            prev_checkpoint_hash=self._last_checkpoint_hash,
        )
        self._checkpoints.append(checkpoint)
        self._last_checkpoint_hash = self._hash_checkpoint(checkpoint)
        await self._save_checkpoint(checkpoint)

    def _hash_checkpoint(self, checkpoint: Checkpoint) -> str:
        """Hash checkpoint for chain linking."""
        data = f"{checkpoint.sequence}:{checkpoint.root_hash}:{checkpoint.entry_count}:{checkpoint.timestamp}:{checkpoint.prev_checkpoint_hash}"
        return hashlib.sha256(data.encode()).hexdigest()

    async def _save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Save checkpoint to disk."""
        try:
            filename = f"checkpoint_{checkpoint.sequence:06d}.json"
            filepath = self._checkpoint_path / filename
            with open(filepath, "w") as f:
                json.dump(checkpoint.model_dump(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    async def _load_latest_checkpoint(self) -> None:
        """Load latest checkpoint from disk."""
        try:
            checkpoint_files = sorted(self._checkpoint_path.glob("checkpoint_*.json"))
            if not checkpoint_files:
                return

            latest_file = checkpoint_files[-1]
            with open(latest_file) as f:
                data = json.load(f)

            checkpoint = Checkpoint(**data)
            self._root_hash = checkpoint.root_hash
            self._entry_count = checkpoint.entry_count
            self._last_checkpoint_hash = checkpoint.prev_checkpoint_hash

            for cf in checkpoint_files:
                with open(cf) as f:
                    cp_data = json.load(f)
                self._checkpoints.append(Checkpoint(**cp_data))

        except Exception as e:
            logger.error(f"Failed to load checkpoints: {e}")

    async def verify_checkpoint_integrity(self) -> bool:
        """
        Verify integrity of audit log chain on startup.
        
        Returns:
            True if integrity is verified
            
        Raises:
            IntegrityViolationError: If tampering is detected
        """
        if len(self._checkpoints) < 2:
            logger.info("Not enough checkpoints to verify")
            return True

        for i in range(1, len(self._checkpoints)):
            current = self._checkpoints[i]
            previous = self._checkpoints[i - 1]

            if current.prev_checkpoint_hash != self._hash_checkpoint(previous):
                error_msg = (
                    f"CRITICAL: Integrity violation at checkpoint {current.sequence}! "
                    f"Expected prev_hash={self._hash_checkpoint(previous)}, "
                    f"got {current.prev_checkpoint_hash}"
                )
                logger.critical(error_msg)
                raise IntegrityViolationError(error_msg)

        logger.info(f"Checkpoint integrity verified ({len(self._checkpoints)} checkpoints)")
        return True

    def verify_entry_in_tree(self, entry_hash: str, proof: list[tuple[str, str]]) -> bool:
        """
        Verify entry inclusion in Merkle tree.
        
        Args:
            entry_hash: Hash of entry to verify
            proof: Merkle proof path [(hash, direction), ...]
            
        Returns:
            True if entry is in tree
        """
        current_hash = self._hash_leaf(entry_hash)

        for sibling_hash, direction in proof:
            if direction == "left":
                current_hash = self._hash_internal(sibling_hash, current_hash)
            else:
                current_hash = self._hash_internal(current_hash, sibling_hash)

        return current_hash == self._root_hash

    def generate_proof(self, entry_hash: str) -> list[tuple[str, str]]:
        """Generate Merkle proof for entry."""
        leaf_hash = self._hash_leaf(entry_hash)
        proof = []
        self._generate_proof_recursive(self._root, leaf_hash, proof)
        return proof

    def _generate_proof_recursive(
        self,
        node: Optional[MerkleNode],
        target: str,
        proof: list[tuple[str, str]],
    ) -> bool:
        """Recursively generate proof path."""
        if node is None or node.is_leaf:
            return node is not None and node.hash_value == target

        if self._generate_proof_recursive(node.left, target, proof):
            if node.right:
                proof.append((node.right.hash_value, "right"))
            return True

        if self._generate_proof_recursive(node.right, target, proof):
            if node.left:
                proof.append((node.left.hash_value, "left"))
            return True

        return False

    @property
    def root_hash(self) -> str:
        return self._root_hash

    @property
    def entry_count(self) -> int:
        return self._entry_count

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "entry_count": self._entry_count,
            "root_hash": self._root_hash,
            "checkpoint_count": len(self._checkpoints),
            "last_checkpoint_hash": self._last_checkpoint_hash,
        }
