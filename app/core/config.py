import os
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml
from pydantic import BaseModel, Field, validator

class ModelRoleConfig(BaseModel):
    provider: str
    name: str
    num_ctx: int = 8192
    temperature: float = 0.0
    top_p: float = 1.0
    num_predict: int = 1024
    roles: List[str]
    fallbacks: Optional[List[str]] = Field(default_factory=list)
    dimension: Optional[int] = None

class OllamaGlobalSettings(BaseModel):
    base_url: str
    timeout: int
    keep_alive: str
    num_threads: int = 4

class SystemConfig(BaseModel):
    ollama_global_settings: OllamaGlobalSettings
    models: Dict[str, ModelRoleConfig]
    default_role: str
    
    postgres_user: str = Field(default_factory=lambda: os.environ.get("POSTGRES_USER", "agent"))
    postgres_password: str = Field(default_factory=lambda: os.environ["POSTGRES_PASSWORD"])
    postgres_db: str = Field(default_factory=lambda: os.environ.get("POSTGRES_DB", "ai_memory"))
    database_url: str = ""
    redis_url: str = Field(default_factory=lambda: os.environ.get("REDIS_URL", "redis://redis:6379/0"))

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.database_url = f"postgresql://{self.postgres_user}:{self.postgres_password}@postgres:5432/{self.postgres_db}"

    @validator('postgres_password')
    def password_must_be_set(cls, v):
        if not v or v == "12345678":
            raise ValueError("POSTGRES_PASSWORD must be set to a secure value (not the default)")
        return v

class ConfigManager:
    _instance: Optional[SystemConfig] = None

    @classmethod
    def get_settings(cls) -> SystemConfig:
        if cls._instance is None:
            config_path = Path(__file__).resolve().parent.parent.parent / "config" / "models.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f)
            cls._instance = SystemConfig(**raw_data)
        return cls._instance

settings = ConfigManager.get_settings()
