import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass
class Settings:
    provider: str = "rules"  # "rules", "anthropic" or "openai_compatible" (Ollama with Qwen, LM Studio, vLLM)
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-5-5"  # check the current model name in Anthropic's docs
    simulated_mode: bool = True  # R-05: everything says it is simulated
    config_dir: Path = field(default_factory=lambda: BASE_DIR / "config")
    data_dir: Optional[Path] = None  # where suggestions and the audit log are saved; None = memory only
    llm_timeout_seconds: float = 20.0
    llm_base_url: str = "http://localhost:11434/v1"  # Ollama's OpenAI-compatible address
    llm_model: str = "qwen2.5:7b"
    llm_api_key: Optional[str] = None
    backend_url: Optional[str] = None  # the Jusr AI backend, for example http://localhost:8000
    ai_service_email: Optional[str] = None
    ai_service_password: Optional[str] = None

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = os.environ.get("DATA_DIR")
        return cls(
            provider=os.environ.get("AI_PROVIDER", "rules").lower(),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
            simulated_mode=os.environ.get("SIMULATED_MODE", "true").lower() != "false",
            config_dir=Path(os.environ.get("CONFIG_DIR", str(BASE_DIR / "config"))),
            data_dir=Path(data_dir) if data_dir else None,
            llm_timeout_seconds=float(os.environ.get("LLM_TIMEOUT_SECONDS", "20")),
            llm_base_url=os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"),
            llm_model=os.environ.get("LLM_MODEL", "qwen2.5:7b"),
            llm_api_key=os.environ.get("LLM_API_KEY"),
            backend_url=os.environ.get("BACKEND_URL"),
            ai_service_email=os.environ.get("AI_SERVICE_EMAIL"),
            ai_service_password=os.environ.get("AI_SERVICE_PASSWORD"),
        )


def load_json(config_dir: Path, name: str):
    """R-03: criteria, routing and approver roles live in config files, not in code."""
    path = Path(config_dir) / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
