import hashlib
import time
import secrets
from typing import Any, Dict, Optional
import httpx
from pathlib import Path

from app.config import RAW_DATA_DIR, USERS_DATA_DIR
from .base import BaseCollector

CODEFORCES_API_URL = "https://codeforces.com/api/user.status"


class CodeforcesAPIError(Exception):
    """Exception raised when Codeforces API returns an error or fails."""
    pass


class CodeforcesUserNotFoundError(CodeforcesAPIError):
    """Exception raised when Codeforces handle is not found."""
    pass


def generate_codeforces_api_sig(method_name: str, params: Dict[str, Any], secret: str) -> str:
    """
    Generate SHA-512 signature for official Codeforces API authentication.
    Formula: rand_prefix (6 chars) + sha512(rand_prefix + "/" + methodName + "?" + sorted_params + "#" + secret)
    """
    rand_prefix = secrets.token_hex(3)
    sorted_items = sorted(params.items(), key=lambda item: (str(item[0]), str(item[1])))
    param_str = "&".join(f"{k}={v}" for k, v in sorted_items)
    to_hash = f"{rand_prefix}/{method_name}?{param_str}#{secret}"
    hash_sig = hashlib.sha512(to_hash.encode("utf-8")).hexdigest()
    return f"{rand_prefix}{hash_sig}"


class CodeforcesCollector(BaseCollector):
    """Collector for retrieving submission history from official Codeforces API."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def fetch_submissions(
        self,
        handle: str,
        count: int = 10000,
        user_id: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch submission history for a given Codeforces handle.
        If api_key and api_secret are provided, requests includeSources=true via authenticated SHA-512 API call.
        """
        if not handle or not handle.strip():
            raise ValueError("Codeforces handle cannot be empty.")

        clean_handle = handle.strip()

        if api_key and api_secret:
            params: Dict[str, Any] = {
                "apiKey": api_key.strip(),
                "count": count,
                "from": 1,
                "handle": clean_handle,
                "includeSources": "true",
                "time": int(time.time()),
            }
            api_sig = generate_codeforces_api_sig("user.status", params, api_secret.strip())
            params["apiSig"] = api_sig
        else:
            params = {"handle": clean_handle, "from": 1, "count": count}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(CODEFORCES_API_URL, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                data = exc.response.json() if exc.response.content else {}
                comment = data.get("comment", "User not found")
                raise CodeforcesUserNotFoundError(f"Codeforces handle '{clean_handle}' not found: {comment}")
            raise CodeforcesAPIError(f"HTTP error from Codeforces API: {exc}") from exc
        except httpx.HTTPError as exc:
            raise CodeforcesAPIError(f"Network request to Codeforces API failed: {exc}") from exc
        except Exception as exc:
            raise CodeforcesAPIError(f"Failed to fetch data from Codeforces API: {exc}") from exc

        if data.get("status") != "OK":
            comment = data.get("comment", "Unknown API error")
            if "not found" in comment.lower() or "handle" in comment.lower():
                raise CodeforcesUserNotFoundError(f"Codeforces handle '{clean_handle}' not found: {comment}")
            raise CodeforcesAPIError(f"Codeforces API error for handle '{clean_handle}': {comment}")

        # Save raw JSON response locally (user-scoped if user_id present, else global raw dir)
        if user_id:
            save_path = USERS_DATA_DIR / user_id / "raw" / f"codeforces_{clean_handle.lower()}.json"
        else:
            save_path = RAW_DATA_DIR / "codeforces" / f"{clean_handle.lower()}_submissions.json"

        self.save_raw_json(data, save_path)
        return data
