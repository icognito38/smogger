import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FirmsConfig:
    map_keys: tuple[str, ...]
    source: str = "VIIRS_SNPP_NRT"
    region: str = "world"
    day_range: int = 1
    timeout_seconds: float = 60.0

    @classmethod
    def from_environment(cls) -> "FirmsConfig":
        dotenv_values = _read_dotenv(
            Path(__file__).resolve().parent / ".env"
        )
        numbered_keys = [
            _configured_value(f"FIRMS_MAP_KEYS{number}", dotenv_values)
            for number in range(1, 6)
        ]
        keys = tuple(key for key in numbered_keys if key)
        if not keys:
            raw_keys = _configured_value("FIRMS_MAP_KEYS", dotenv_values) or ""
            keys = tuple(key.strip() for key in raw_keys.split(",") if key.strip())
        if not keys:
            raise RuntimeError(
                "FIRMS_MAP_KEYS1 through FIRMS_MAP_KEYS5 are required; provide "
                "NASA FIRMS map keys through the environment or ingestion .env file."
            )
        return cls(map_keys=keys)


def _configured_value(name: str, dotenv_values: dict[str, str]) -> str | None:
    value = os.getenv(name)
    if value is None:
        value = dotenv_values.get(name)
    if value is None:
        return None
    return value.strip().strip("'\"").strip() or None


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip()
        if name:
            values[name] = value.strip()
    return values
