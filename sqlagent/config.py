from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    database_url: str = "postgresql://warehouse@localhost:5432/warehouse"
    llm_provider: str = "litellm"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "openbmb/minicpm5:fp16"
    opencode_go_base_url: str = "https://opencode.ai/zen/go/v1"
    opencode_go_api_key: str = ""
    opencode_go_model: str = "deepseek-v4-flash"
    litellm_base_url: str = "http://localhost:4000/v1"
    litellm_api_key: str = ""
    litellm_model: str = "hosted_vllm/gemma4-chat"
    workspace_path: Path = PROJECT_ROOT / "skills" / "warehouse_prod"
    seed_orders: int = 50_000
    tpcds_scale: int = 10
    tpcds_data_path: Path = PROJECT_ROOT / ".data" / "tpcds" / "sf10"
    tpcds_toolkit_path: Path = PROJECT_ROOT / ".cache" / "tpcds-kit"
    max_result_rows: int = 500
    statement_timeout_ms: int = 15_000
    explorer_rounds: int = 3
    explorer_probes_per_round: int = 3
    bootstrap_on_start: bool = True
    verify_interval_hours: float = 24.0

    @classmethod
    def from_env(cls) -> "Settings":
        workspace = Path(os.getenv("WORKSPACE_PATH", "skills/warehouse_prod"))
        if not workspace.is_absolute():
            workspace = PROJECT_ROOT / workspace
        return cls(
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            llm_provider=os.getenv("LLM_PROVIDER", cls.llm_provider).strip().lower(),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", cls.ollama_base_url).rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", cls.ollama_model),
            opencode_go_base_url=os.getenv("OPENCODE_GO_BASE_URL", cls.opencode_go_base_url).rstrip("/"),
            opencode_go_api_key=os.getenv("OPENCODE_GO_API_KEY", cls.opencode_go_api_key),
            opencode_go_model=os.getenv("OPENCODE_GO_MODEL", cls.opencode_go_model),
            litellm_base_url=os.getenv("LITELLM_BASE_URL", cls.litellm_base_url).rstrip("/"),
            litellm_api_key=os.getenv("LITELLM_API_KEY", cls.litellm_api_key),
            litellm_model=os.getenv("LITELLM_MODEL", cls.litellm_model),
            workspace_path=workspace,
            seed_orders=int(os.getenv("SEED_ORDERS", str(cls.seed_orders))),
            tpcds_scale=int(os.getenv("TPCDS_SCALE", str(cls.tpcds_scale))),
            tpcds_data_path=Path(os.getenv("TPCDS_DATA_PATH", str(cls.tpcds_data_path))),
            tpcds_toolkit_path=Path(os.getenv("TPCDS_TOOLKIT_PATH", str(cls.tpcds_toolkit_path))),
            max_result_rows=int(os.getenv("MAX_RESULT_ROWS", str(cls.max_result_rows))),
            statement_timeout_ms=int(os.getenv("STATEMENT_TIMEOUT_MS", str(cls.statement_timeout_ms))),
            explorer_rounds=int(os.getenv("EXPLORER_ROUNDS", str(cls.explorer_rounds))),
            explorer_probes_per_round=int(os.getenv("EXPLORER_PROBES_PER_ROUND", str(cls.explorer_probes_per_round))),
            bootstrap_on_start=os.getenv("BOOTSTRAP_ON_START", "1").strip() not in {"0", "false", "no"},
            verify_interval_hours=float(os.getenv("VERIFY_INTERVAL_HOURS", str(cls.verify_interval_hours))),
        )

    @property
    def active_llm_model(self) -> str:
        return {
            "litellm": self.litellm_model,
            "opencode_go": self.opencode_go_model,
        }.get(self.llm_provider, self.ollama_model)

    @property
    def active_llm_base_url(self) -> str:
        return {
            "litellm": self.litellm_base_url,
            "opencode_go": self.opencode_go_base_url,
        }.get(self.llm_provider, self.ollama_base_url)
