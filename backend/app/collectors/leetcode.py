import httpx
from typing import Any, Dict, Optional
from pathlib import Path

from app.config import RAW_DATA_DIR, USERS_DATA_DIR
from .base import BaseCollector

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"


class LeetCodeAPIError(Exception):
    """Exception raised when LeetCode GraphQL API returns an error or fails."""
    pass


class LeetCodeUserNotFoundError(LeetCodeAPIError):
    """Exception raised when LeetCode username is not found."""
    pass


class LeetCodeCollector(BaseCollector):
    """Collector for retrieving public submission history from LeetCode GraphQL API."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def fetch_submissions(
        self, username: str, count: int = 20, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch recent submission metadata for a LeetCode username via public GraphQL query.
        Validates username existence using matchedUser.
        """
        if not username or not username.strip():
            raise ValueError("LeetCode username cannot be empty.")

        clean_username = username.strip()
        query = """
        query userProfileAndRecent($username: String!, $limit: Int) {
          matchedUser(username: $username) {
            username
            profile {
              realName
              ranking
            }
          }
          recentSubmissionList(username: $username, limit: $limit) {
            title
            titleSlug
            timestamp
            statusDisplay
            lang
          }
          recentAcSubmissionList(username: $username, limit: $limit) {
            id
            title
            titleSlug
            timestamp
          }
        }
        """
        payload = {
            "query": query,
            "variables": {"username": clean_username, "limit": count},
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CompetitiveProgrammingRAG/1.0",
            "Referer": f"https://leetcode.com/u/{clean_username}/",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(LEETCODE_GRAPHQL_URL, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise LeetCodeAPIError(f"Network error contacting LeetCode API: {exc}") from exc
        except Exception as exc:
            raise LeetCodeAPIError(f"Failed to fetch data from LeetCode API: {exc}") from exc

        if "errors" in data and data["errors"]:
            for err in data["errors"]:
                msg = err.get("message", "")
                if "does not exist" in msg.lower() or "not found" in msg.lower():
                    raise LeetCodeUserNotFoundError(f"LeetCode username '{clean_username}' error: {msg}")

        data_body = data.get("data") or {}
        matched_user = data_body.get("matchedUser")
        if matched_user is None:
            raise LeetCodeUserNotFoundError(f"LeetCode username '{clean_username}' not found or does not exist.")

        # Save raw JSON locally
        if user_id:
            save_path = USERS_DATA_DIR / user_id / "raw" / f"leetcode_{clean_username.lower()}.json"
        else:
            save_path = RAW_DATA_DIR / "leetcode" / f"{clean_username.lower()}_submissions.json"

        self.save_raw_json(data, save_path)
        return data
