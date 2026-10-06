import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict


class BaseCollector(ABC):
    """Abstract base class for platform data collectors."""

    @abstractmethod
    def fetch_submissions(self, handle: str) -> Dict[str, Any]:
        """Fetch raw submission data for a given handle from the platform API."""
        pass

    def save_raw_json(self, data: Dict[str, Any], filepath: Path) -> Path:
        """Save raw API response dictionary to disk as formatted JSON."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return filepath
