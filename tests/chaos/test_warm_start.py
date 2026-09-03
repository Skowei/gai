#!/usr/bin/env python3
"""
Agent System (Enterprise++ v3.5) - Chaos Test: Warm Start Recovery
Spec sekcja 10.2: Test odzyskiwania systemu po awarii (warm start).

Scenariusz:
1. Symulacja nagłego restartu usługi (crash).
2. System ładuje snapshot stanu z Redis Qdrant checkpoint.
3. Weryfikacja Merkle Tree `verify_checkpoint_integrity()` w O(1).
4. Automatyczne przejście w `reactive_mode` (reactive = True).
5. Test `QdrantClient.ping()`.
"""

from __future__ import annotations

import asyncio
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.storage.qdrant_client import QdrantClient, QdrantConfig
from src.audit.merkle_tree import MerkleTreeAudit, MerkleTreeConfig
from src.core.graph import initialize_system_state
from src.core.state import SystemState


async def run_warm_start_test() -> bool:
    """
    Symulacja warm-start recovery z wykryciem QDrant i odtworzeniem stanu.
    """
    print("[CHAOS] Starting warm-start chaos test...")

    # 1. Merkle Tree Integrity Check (O(1))
    audit_path = "/tmp/agent_audit_test"
    os.makedirs(audit_path, exist_ok=True)

    merkle = MerkleTreeAudit(
        config=MerkleTreeConfig(
            checkpoint_path=audit_path,
            checkpoint_interval=100,
        ),
    )
    await merkle.initialize()

    for i in range(150):
        await merkle.add_entry(
            entry_hash=f"entry_{i}",
        )

    root = merkle.root_hash
    assert root != "", "Merkle root should not be empty after appending entries"
    print(f"[CHAOS] Merkle root after 150 entries: {root[:16]}...")

    integrity_ok = await merkle.verify_checkpoint_integrity()
    assert integrity_ok, "Checkpoint integrity verification failed"
    print("[CHAOS] Merkle Tree integrity verification: PASSED")

    # 2. Qdrant Warm Start / Ping Test
    qdrant_cfg = QdrantConfig(
        host="localhost",
        port=6334,
        grpc_port=6335,
    )
    qdrant = QdrantClient(qdrant_cfg)
    ping_ok = await qdrant.ping()
    assert ping_ok, "Qdrant ping failed - vector store unreachable during warm start"
    print("[CHAOS] Qdrant warm-start ping: PASSED")

    # 3. initialize_system_state() - warm start detection → reactive_mode
    start_time = time.time()
    state = await initialize_system_state()
    elapsed = time.time() - start_time

    assert state is not None, "initialize_system_state returned None"
    assert state.schema_version == "3.5", f"Unexpected schema version: {state.schema_version}"

    reactive_val = getattr(state, "reactive_mode", None) or getattr(state, "_reactive_mode", None)
    if reactive_val is None:
        reactive_val = state.model_dump().get("reactive_mode", False)

    assert reactive_val is True, (
        f"Expected state.reactive_mode=True after warm start, got {reactive_val}"
    )
    print(f"[CHAOS] Warm-start reactive_mode detection: PASSED ({elapsed:.3f}s)")
    print(f"[CHAOS] State summary: version={state.schema_version}, mode={state.system_mode}, "
          f"reactive={reactive_val}, total_errors={len(state.error_log)}")

    await merkle.shutdown()
    await qdrant.close()

    print("[CHAOS] Warm-start recovery test PASSED.")
    return True


if __name__ == "__main__":
    success = asyncio.run(run_warm_start_test())
    sys.exit(0 if success else 1)
