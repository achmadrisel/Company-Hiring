import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from functools import lru_cache
import os

load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    database_url: str

    # JWT
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int

    # Application
    environment: str
    debug: bool

    # AI / External APIs
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY")
    UNSTRUCTURED_API_KEY: str = os.getenv("UNSTRUCTURED_API_KEY")
    UNSTRUCTURED_API_URL: str = os.getenv("UNSTRUCTURED_API_URL", "https://api.unstructured.io")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
    RERANK_MODEL: str = os.getenv("RERANK_MODEL", "cohere/rerank-4-pro")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nvidia/llama-nemotron-embed-vl-1b-v2:free")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", 1024))

    # RAG Evaluation (DeepEval) — judge model
    EVAL_LLM_MODEL: str | None = os.getenv("EVAL_LLM_MODEL")
    # Generate -> judge -> retry loop for screening feedback
    EVAL_RETRY_ENABLED: bool = os.getenv("EVAL_RETRY_ENABLED", "1") == "1"
    EVAL_RETRY_MAX: int = int(os.getenv("EVAL_RETRY_MAX", "3"))
    EVAL_RETRY_THRESHOLD: float = float(os.getenv("EVAL_RETRY_THRESHOLD", "8.0"))

    # MLflow GenAI Tracking
    MLFLOW_TRACKING_ENABLED: bool = os.getenv("MLFLOW_TRACKING_ENABLED", "0") == "1"
    MLFLOW_TRACKING_URI: str = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    MLFLOW_EXPERIMENT_NAME: str = os.getenv("MLFLOW_EXPERIMENT_NAME", "ai-screening")

    # S3 / Filebase
    S3_ACCESS_KEY_ID: str = os.getenv("S3_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY: str = os.getenv("S3_SECRET_ACCESS_KEY")
    S3_REGION: str = os.getenv("S3_REGION")
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL")
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()

settings = get_settings()
