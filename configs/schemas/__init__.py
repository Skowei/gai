"""
Agent System (Enterprise++ v3.5) - Configuration Validation Schemas
Pydantic v2 schemas for all configuration files.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# Enums
# =============================================================================

class EnvironmentType(str, Enum):
    PRODUCTION_EDGE = "production_edge"
    STAGING = "staging"
    DEVELOPMENT = "development"
    TESTING = "testing"


class RedisMode(str, Enum):
    STANDALONE = "standalone"
    SENTINEL = "sentinel"
    CLUSTER = "cluster"


class ClockProtocol(str, Enum):
    PTP = "PTP"
    GPS = "GPS"
    NTP = "NTP"


class FailureAction(str, Enum):
    RTL = "RTL"
    LAND = "LAND"
    HOLD = "HOLD"


# =============================================================================
# etcd Configuration
# =============================================================================

class EtcdEndpoints(BaseModel):
    endpoints: list[str] = Field(default_factory=lambda: ["http://etcd1:2379", "http://etcd2:2379", "http://etcd3:2379"])
    connection_timeout_ms: int = Field(default=5000, ge=100, le=30000)
    request_timeout_ms: int = Field(default=3000, ge=100, le=15000)
    retry_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_backoff_ms: int = Field(default=100, ge=10, le=5000)
    lock_ttl_seconds: int = Field(default=30, ge=5, le=300)
    fencing_token_key_prefix: str = Field(default="/fencing/tokens/")
    session_key_prefix: str = Field(default="/sessions/")
    health_check_interval_ms: int = Field(default=1000, ge=100, le=10000)


# =============================================================================
# NATS Configuration
# =============================================================================

class NATSJetStream(BaseModel):
    enabled: bool = True
    stream_name: str = "telemetry"
    subjects: list[str] = Field(default_factory=lambda: ["telemetry.>", "commands.>", "events.>"])
    max_age_ms: int = Field(default=500, ge=100, le=5000)
    max_msgs: int = Field(default=100000, ge=1000, le=10000000)
    max_bytes: int = Field(default=1073741824, ge=1048576, le=107374182400)
    discard_policy: Literal["old", "new"] = "old"
    storage_type: Literal["file", "memory"] = "file"
    replicas: int = Field(default=2, ge=1, le=5)


class NATSConsumer(BaseModel):
    ack_wait_ms: int = Field(default=500, ge=100, le=30000)
    max_deliver: int = Field(default=3, ge=1, le=10)
    max_ack_pending: int = Field(default=1000, ge=100, le=10000)


class NATSCluster(BaseModel):
    name: str = "agent-cluster"
    enabled: bool = True


class NATSConfig(BaseModel):
    endpoints: list[str] = Field(default_factory=lambda: ["nats://nats1:4222", "nats://nats2:4222"])
    jetstream: NATSJetStream = Field(default_factory=NATSJetStream)
    consumer: NATSConsumer = Field(default_factory=NATSConsumer)
    cluster: NATSCluster = Field(default_factory=NATSCluster)


# =============================================================================
# Redis Configuration
# =============================================================================

class RedisEndpoint(BaseModel):
    host: str
    port: int = Field(default=6379, ge=1, le=65535)


class RedisSentinelNode(BaseModel):
    host: str
    port: int = Field(default=26379, ge=1, le=65535)


class RedisSentinel(BaseModel):
    master_name: str = "mymaster"
    nodes: list[RedisSentinelNode] = Field(default_factory=list)


class RedisConnection(BaseModel):
    max_connections: int = Field(default=50, ge=1, le=500)
    socket_timeout_ms: int = Field(default=2000, ge=100, le=30000)
    socket_connect_timeout_ms: int = Field(default=1000, ge=100, le=15000)
    retry_on_timeout: bool = True


class RedisCheckpoint(BaseModel):
    key_prefix: str = "checkpoint:"
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    encryption_enabled: bool = True


class RedisRedlock(BaseModel):
    retry_count: int = Field(default=3, ge=1, le=10)
    retry_delay_ms: int = Field(default=200, ge=10, le=5000)
    clock_drift_factor: float = Field(default=0.01, ge=0.001, le=0.1)


class RedisConfig(BaseModel):
    mode: RedisMode = RedisMode.CLUSTER
    endpoints: list[RedisEndpoint] = Field(default_factory=lambda: [RedisEndpoint(host="redis", port=6379)])
    sentinel: RedisSentinel = Field(default_factory=RedisSentinel)
    connection: RedisConnection = Field(default_factory=RedisConnection)
    checkpoint: RedisCheckpoint = Field(default_factory=RedisCheckpoint)
    redlock: RedisRedlock = Field(default_factory=RedisRedlock)


# =============================================================================
# Qdrant Configuration
# =============================================================================

class QdrantHNSM(BaseModel):
    m: int = Field(default=16, ge=4, le=64)
    ef_construct: int = Field(default=100, ge=50, le=500)
    full_scan_threshold: int = Field(default=10000, ge=1000, le=100000)


class QdrantCollection(BaseModel):
    name: str = "agent_memory"
    vector_size: int = Field(default=1536, ge=64, le=4096)
    distance: Literal["Cosine", "Euclid", "Dot"] = "Cosine"
    hnsm: QdrantHNSM = Field(default_factory=QdrantHNSM)


class QdrantSearch(BaseModel):
    ef: int = Field(default=128, ge=16, le=512)
    limit: int = Field(default=10, ge=1, le=100)
    score_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class QdrantPersistence(BaseModel):
    storage_path: str = "/mnt/encrypted_luks/qdrant_data"
    encryption: str = "LUKS2"
    snapshot_path: str = "/mnt/encrypted_luks/qdrant_snapshots"


class QdrantHealthcheck(BaseModel):
    timeout_ms: int = Field(default=5000, ge=1000, le=30000)
    retry_attempts: int = Field(default=5, ge=1, le=10)


class QdrantConfig(BaseModel):
    host: str = "qdrant"
    port: int = Field(default=6333, ge=1, le=65535)
    grpc_port: int = Field(default=6334, ge=1, le=65535)
    api_key: Optional[str] = None
    https: bool = False
    persistence: QdrantPersistence = Field(default_factory=QdrantPersistence)
    collection: QdrantCollection = Field(default_factory=QdrantCollection)
    search: QdrantSearch = Field(default_factory=QdrantSearch)
    healthcheck: QdrantHealthcheck = Field(default_factory=QdrantHealthcheck)


# =============================================================================
# GPU & MPS Configuration
# =============================================================================

class MPSAllocation(BaseModel):
    vllm_percent: int = Field(default=50, ge=10, le=80)
    roboflow_percent: int = Field(default=30, ge=10, le=60)
    tools_percent: int = Field(default=20, ge=5, le=40)

    @model_validator(mode="after")
    def validate_allocation_sum(self) -> "MPSAllocation":
        total = self.vllm_percent + self.roboflow_percent + self.tools_percent
        if total != 100:
            raise ValueError(f"MPS allocation must sum to 100%, got {total}%")
        return self


class MPSConfig(BaseModel):
    enabled: bool = True
    allocation: MPSAllocation = Field(default_factory=MPSAllocation)
    control_port: int = Field(default=5555, ge=1024, le=65535)
    memory_limit_mb: Optional[int] = Field(default=None, ge=1024, le=1000000)


class ThermalConfig(BaseModel):
    warning_threshold_celsius: int = Field(default=80, ge=60, le=95)
    critical_threshold_celsius: int = Field(default=85, ge=70, le=100)
    emergency_threshold_celsius: int = Field(default=90, ge=75, le=105)
    polling_interval_ms: int = Field(default=500, ge=100, le=5000)
    throttle_actions: list[str] = Field(default_factory=lambda: ["reduce_fps", "switch_to_fallback_model", "pause_non_critical_inference"])
    emergency_actions: list[str] = Field(default_factory=lambda: ["hard_stop_all_inference", "trigger_graceful_drainage"])

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "ThermalConfig":
        if not (self.warning_threshold_celsius < self.critical_threshold_celsius < self.emergency_threshold_celsius):
            raise ValueError("Thermal thresholds must be ordered: warning < critical < emergency")
        return self


class ModelConfig(BaseModel):
    name: str
    engine: Literal["vllm", "roboflow", "ollama"] = "vllm"
    max_model_len: int = Field(default=8192, ge=512, le=131072)
    gpu_memory_utilization: float = Field(default=0.5, ge=0.1, le=0.95)
    enable_prefix_caching: bool = True
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class GPUConfig(BaseModel):
    device_id: int = Field(default=0, ge=0, le=15)
    cuda_visible_devices: str = "0"
    mps: MPSConfig = Field(default_factory=MPSConfig)
    thermal: ThermalConfig = Field(default_factory=ThermalConfig)
    models: dict[str, ModelConfig] = Field(default_factory=lambda: {
        "primary": ModelConfig(name="llama-3.1-70b", engine="vllm", max_model_len=8192, gpu_memory_utilization=0.50),
        "fallback": ModelConfig(name="qwen-2.5-7b", engine="vllm", max_model_len=4096, gpu_memory_utilization=0.30),
        "vision": ModelConfig(name="yolo-world", engine="roboflow", gpu_memory_utilization=0.30, confidence_threshold=0.5)
    })


# =============================================================================
# Fencing Configuration
# =============================================================================

class FencingValidation(BaseModel):
    strict_monotonicity: bool = True
    reject_equal_tokens: bool = True
    reject_stale_threshold_ms: int = Field(default=1000, ge=100, le=10000)


class FencingStorage(BaseModel):
    etcd_key_prefix: str = "/fencing/accepted/"
    redis_key_prefix: str = "fencing:accepted:"
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class FencingConfig(BaseModel):
    initial_token_value: int = Field(default=1000, ge=0, le=999999999)
    token_increment: int = Field(default=1, ge=1, le=1000)
    max_token_value: int = Field(default=999999999, ge=1000, le=999999999999)
    validation: FencingValidation = Field(default_factory=FencingValidation)
    storage: FencingStorage = Field(default_factory=FencingStorage)


# =============================================================================
# Hardware Safety Configuration
# =============================================================================

class HeartbeatConfig(BaseModel):
    enabled: bool = True
    interval_ms: int = Field(default=200, ge=50, le=1000)
    uart_port: str = "/dev/ttyS0"
    uart_baudrate: int = Field(default=115200, ge=9600, le=921600)
    heartbeat_byte: str = "0xAA"
    failure_action: FailureAction = FailureAction.RTL
    failure_threshold_ms: int = Field(default=600, ge=100, le=5000)


class WatchdogConfig(BaseModel):
    enabled: bool = True
    device: str = "/dev/watchdog"
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    keepalive_interval_seconds: int = Field(default=5, ge=1, le=30)


class HardwareSafetyConfig(BaseModel):
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    watchdog: WatchdogConfig = Field(default_factory=WatchdogConfig)


# =============================================================================
# Master Clock Configuration
# =============================================================================

class PTPConfig(BaseModel):
    domain: int = Field(default=0, ge=0, le=127)
    transport: Literal["L2", "UDPv4", "UDPv6"] = "L2"
    delay_mechanism: Literal["E2E", "P2P"] = "E2E"
    network_interface: str = "eth0"


class GPSConfig(BaseModel):
    device: str = "/dev/ttyUSB0"
    baudrate: int = Field(default=9600, ge=4800, le=115200)
    fix_timeout_ms: int = Field(default=5000, ge=1000, le=30000)


class SyncConfig(BaseModel):
    max_offset_us: int = Field(default=1000, ge=1, le=100000)
    holdover_seconds: int = Field(default=300, ge=60, le=3600)


class MasterClockConfig(BaseModel):
    protocol: ClockProtocol = ClockProtocol.PTP
    ptp: PTPConfig = Field(default_factory=PTPConfig)
    gps: GPSConfig = Field(default_factory=GPSConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)


# =============================================================================
# Audit Configuration
# =============================================================================

class MerkleTreeConfig(BaseModel):
    hash_algorithm: str = "sha256"
    leaf_prefix: str = "0x00"
    internal_prefix: str = "0x01"
    hash_combine: Literal["concat_then_hash", "hash_of_hashes"] = "concat_then_hash"


class RingBufferConfig(BaseModel):
    capacity: int = Field(default=100, ge=10, le=10000)
    group_commit_size: int = Field(default=100, ge=1, le=1000)
    flush_interval_ms: int = Field(default=5000, ge=100, le=60000)
    storage_path: str = "/var/log/agent_audit/"
    max_file_size_mb: int = Field(default=100, ge=10, le=10000)
    rotation_count: int = Field(default=10, ge=1, le=100)


class IntegrityConfig(BaseModel):
    verify_on_startup: bool = True
    snapshot_verification: bool = True


class AuditConfig(BaseModel):
    merkle_tree: MerkleTreeConfig = Field(default_factory=MerkleTreeConfig)
    ring_buffer: RingBufferConfig = Field(default_factory=RingBufferConfig)
    integrity: IntegrityConfig = Field(default_factory=IntegrityConfig)


# =============================================================================
# MCP Configuration
# =============================================================================

class MCPSandboxConfig(BaseModel):
    read_only_fs: bool = True
    tmpfs_size_mb: int = Field(default=128, ge=16, le=1024)
    no_new_privileges: bool = True
    seccomp_profile: str = "/etc/agent/seccomp_profile.json"
    apparmor_profile: str = "agent-mcp"


class DocParserConfig(BaseModel):
    enabled: bool = True
    max_file_size_mb: int = Field(default=50, ge=1, le=500)
    supported_formats: list[str] = Field(default_factory=lambda: ["pdf", "docx", "xlsx", "pptx", "html", "md"])
    timeout_seconds: int = Field(default=30, ge=5, le=300)


class MavlinkCtrlConfig(BaseModel):
    enabled: bool = True
    connection_string: str = "/dev/ttyS1:57600"
    system_id: int = Field(default=1, ge=1, le=255)
    component_id: int = Field(default=1, ge=1, le=255)
    command_timeout_ms: int = Field(default=5000, ge=100, le=30000)
    fencing_check: bool = True


class MCPServersConfig(BaseModel):
    doc_parser: DocParserConfig = Field(default_factory=DocParserConfig)
    mavlink_ctrl: MavlinkCtrlConfig = Field(default_factory=MavlinkCtrlConfig)


class MCPConfig(BaseModel):
    sandbox: MCPSandboxConfig = Field(default_factory=MCPSandboxConfig)
    servers: MCPServersConfig = Field(default_factory=MCPServersConfig)


# =============================================================================
# LangGraph Configuration
# =============================================================================

class SemanticCacheConfig(BaseModel):
    enabled: bool = True
    similarity_threshold: float = Field(default=0.95, ge=0.5, le=1.0)
    max_entries: int = Field(default=10000, ge=100, le=1000000)
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class LangGraphConfig(BaseModel):
    max_retries: int = Field(default=3, ge=0, le=10)
    recursion_limit: int = Field(default=25, ge=5, le=100)
    checkpoint_interval: int = Field(default=1, ge=1, le=100)
    semantic_cache: SemanticCacheConfig = Field(default_factory=SemanticCacheConfig)


# =============================================================================
# Prompts Configuration
# =============================================================================

class PromptsConfig(BaseModel):
    config_dir: str = "configs/prompts"
    debounce_ms: int = Field(default=300, ge=50, le=2000)
    hot_reload: bool = True
    atomic_replace: bool = True
    fallback_on_validation_error: bool = True
    validation: dict[str, Any] = Field(default_factory=lambda: {"strict_schema": True, "max_prompt_length": 100000})


# =============================================================================
# Observability Configuration
# =============================================================================

class PrometheusConfig(BaseModel):
    enabled: bool = True
    port: int = Field(default=9090, ge=1024, le=65535)
    scrape_interval_ms: int = Field(default=1000, ge=100, le=60000)
    metrics_path: str = "/metrics"


class GrafanaConfig(BaseModel):
    enabled: bool = True
    port: int = Field(default=3000, ge=1024, le=65535)


class PhoenixConfig(BaseModel):
    enabled: bool = True
    port: int = Field(default=6006, ge=1024, le=65535)


class DCGMConfig(BaseModel):
    enabled: bool = True
    polling_interval_ms: int = Field(default=1000, ge=100, le=10000)
    field_ids: list[int] = Field(default_factory=lambda: [1001, 1003, 1004, 203])


class ObservabilityConfig(BaseModel):
    prometheus: PrometheusConfig = Field(default_factory=PrometheusConfig)
    grafana: GrafanaConfig = Field(default_factory=GrafanaConfig)
    phoenix: PhoenixConfig = Field(default_factory=PhoenixConfig)
    dcgm: DCGMConfig = Field(default_factory=DCGMConfig)


# =============================================================================
# Security Configuration
# =============================================================================

class LUKSConfig(BaseModel):
    enabled: bool = True
    device: str = "/dev/nvme0n1p3"
    mount_point: str = "/mnt/encrypted_luks"
    key_slot: int = Field(default=0, ge=0, le=7)


class TPMConfig(BaseModel):
    enabled: bool = True
    device: str = "/dev/tpm0"


class SecretsConfig(BaseModel):
    rotation_interval_hours: int = Field(default=24, ge=1, le=168)
    in_memory_only: bool = True
    lock_memory: bool = True


class SecurityConfig(BaseModel):
    luks: LUKSConfig = Field(default_factory=LUKSConfig)
    tpm: TPMConfig = Field(default_factory=TPMConfig)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)


# =============================================================================
# Top-Level System Configuration
# =============================================================================

class SystemConfig(BaseModel):
    """Top-level system configuration for Agent System (Enterprise++ v3.5)."""
    schema_version: float = Field(default=3.5, ge=3.0, le=4.0)
    environment: EnvironmentType = EnvironmentType.PRODUCTION_EDGE
    system_name: str = "agent_system_enterprise_v35"
    etcd: EtcdEndpoints = Field(default_factory=EtcdEndpoints)
    nats: NATSConfig = Field(default_factory=NATSConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    gpu: GPUConfig = Field(default_factory=GPUConfig)
    fencing: FencingConfig = Field(default_factory=FencingConfig)
    hardware_safety: HardwareSafetyConfig = Field(default_factory=HardwareSafetyConfig)
    master_clock: MasterClockConfig = Field(default_factory=MasterClockConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    langgraph: LangGraphConfig = Field(default_factory=LangGraphConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    model_config = {"validate_assignment": True, "extra": "forbid", "str_strip_whitespace": True}


# =============================================================================
# Prompt Configuration Schema
# =============================================================================

class PromptOutputSchema(BaseModel):
    required_fields: list[str] = Field(default_factory=list)
    action_types: list[str] = Field(default_factory=list)
    max_response_tokens: int = Field(default=4096, ge=256, le=32768)


class PromptContext(BaseModel):
    max_tokens: int = Field(default=8192, ge=512, le=131072)
    reserved_tokens: int = Field(default=1024, ge=64, le=8192)
    prefix_caching: bool = True
    compression_trigger_ratio: float = Field(default=0.85, ge=0.5, le=0.99)


class PromptConfig(BaseModel):
    """Prompt configuration schema for v3.5_core.yaml and v2_fallback.yaml."""
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)
    core_prompt: str = Field(..., min_length=10, max_length=100000)
    output_schema: PromptOutputSchema = Field(default_factory=PromptOutputSchema)
    context: PromptContext = Field(default_factory=PromptContext)

    model_config = {"validate_assignment": True, "extra": "forbid"}
