import os
from dataclasses import dataclass


@dataclass(frozen=True)
class FirmsConfig:
    map_keys: tuple[str, ...]
    source: str = "VIIRS_SNPP_NRT"
    region: str = "world"
    day_range: int = 1
    timeout_seconds: float = 60.0

    @classmethod
    def from_environment(cls) -> "FirmsConfig":
        raw_keys = os.getenv("FIRMS_MAP_KEYS", "")
        keys = tuple(key.strip() for key in raw_keys.split(",") if key.strip())
        if not keys:
            raise RuntimeError(
                "FIRMS_MAP_KEYS is required; provide comma-separated NASA FIRMS "
                "map keys through the environment."
            )
        return cls(map_keys=keys)
