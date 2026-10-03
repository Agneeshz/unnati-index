"""Settings come only from environment variables: GitHub Actions secrets in CI, and the
`.env.local` written by `neon link` in development (`uv run --env-file ../.env.local unnati ...`).

The pipeline prefers Neon's direct connection (`DATABASE_URL_UNPOOLED`): it runs long
transactions and schema-dependent work, which Neon recommends doing outside the pooler."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    data_gov_in_api_key: str | None
    revalidate_url: str | None
    revalidate_secret: str | None

    @classmethod
    def from_env(cls) -> Settings:
        def get(name: str) -> str | None:
            value = os.environ.get(name, "").strip()
            return value or None

        return cls(
            database_url=get("DATABASE_URL_UNPOOLED") or get("DATABASE_URL"),
            data_gov_in_api_key=get("DATA_GOV_IN_API_KEY"),
            revalidate_url=get("REVALIDATE_URL"),
            revalidate_secret=get("REVALIDATE_SECRET"),
        )


class MissingSettingError(RuntimeError):
    pass


def require(value: str | None, name: str) -> str:
    if not value:
        raise MissingSettingError(f"{name} is not set. Add it to your environment or .env file.")
    return value
