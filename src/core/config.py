"""Application settings (Pydantic)."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLUS_")

    database_url: str = Field(default="sqlite:///./elevenplus.db")
    assets_dir: Path = Field(default=Path("./data/assets"))
    sources_dir: Path = Field(default=Path("./data/sources"))
    fixtures_dir: Path = Field(default=Path("./data/fixtures"))
    pipeline_version: str = Field(default="0.1.0")

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Settings":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        app = data.get("app", {})
        db = data.get("database", {})
        storage = data.get("storage", {})
        pipeline = data.get("pipeline", {})
        return cls(
            database_url=db.get("url", "sqlite:///./elevenplus.db"),
            assets_dir=Path(storage.get("assets_dir", "./data/assets")),
            sources_dir=Path(storage.get("sources_dir", "./data/sources")),
            fixtures_dir=Path(storage.get("fixtures_dir", "./data/fixtures")),
            pipeline_version=str(pipeline.get("version", "0.1.0")),
        )


def load_taxonomy(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_exams(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
