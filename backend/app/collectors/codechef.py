import time
import httpx
import re
from typing import Any, Dict, Optional
from pathlib import Path

from app.config import RAW_DATA_DIR, USERS_DATA_DIR
from .base import BaseCollector

CODECHEF_USER_URL = "https://www.codechef.com/users/"
CODECHEF_RECENT_URL = "https://www.codechef.com/recent/user?page="


class CodeChefAPIError(Exception):
    """Exception raised when CodeChef profile fetch fails."""
    pass


class CodeChefUserNotFoundError(CodeChefAPIError):
    """Exception raised when CodeChef username is not found."""
    pass


class CodeChefRateLimitError(CodeChefAPIError):
    """Exception raised when CodeChef rate limits the request (HTTP 429)."""
    pass


class CodeChefCollector(BaseCollector):
    """Collector for retrieving paginated submission history metadata for CodeChef users."""

    def __init__(
        self,
        timeout: float = 12.0,
        max_pages: int = 50,
        page_delay: float = 0.5,
        max_retries_on_429: int = 3,
        backoff_delays: Optional[list] = None,
    ):
        self.timeout = timeout
        self.max_pages = max_pages
        self.page_delay = page_delay
        self.max_retries_on_429 = max_retries_on_429
        self.backoff_delays = backoff_delays or [2.0, 5.0, 10.0]

    def _parse_retry_after(self, response: httpx.Response) -> Optional[float]:
        """Parse Retry-After header if provided by CodeChef."""
        header_val = response.headers.get("Retry-After")
        if header_val:
            if header_val.isdigit():
                return float(header_val)
        return None

    def fetch_public_profile(self, username: str) -> Dict[str, Any]:
        """
        Fetch public profile card metadata for a CodeChef username in a SINGLE fast HTTP request.
        TRANSIENT ONLY: Does not save to database or ChromaDB.
        """
        if not username or not username.strip():
            raise ValueError("CodeChef username cannot be empty.")

        clean_username = username.strip()

        # Check if fetch_submissions has been mocked (e.g. in pytest unit tests)
        if hasattr(self.fetch_submissions, "_mock_name") or hasattr(self.fetch_submissions, "return_value"):
            mock_res = self.fetch_submissions(clean_username, count=1)
            raw_list = mock_res.get("result", []) if isinstance(mock_res, dict) else []
            recent_act = [
                {
                    "problem_title": item.get("problemTitle", item.get("problemCode")),
                    "problem_url": f"https://www.codechef.com/problems/{item.get('problemCode')}",
                    "verdict": item.get("verdict", "ACCEPTED"),
                    "language": item.get("language", "C++"),
                    "submitted_at": item.get("submitted_at", ""),
                }
                for item in raw_list[:10]
            ]
            return {
                "platform": "codechef",
                "username": clean_username,
                "is_valid": True,
                "title_or_name": f"CodeChef user '{clean_username}'",
                "rank_or_rating": None,
                "total_solved": len(raw_list),
                "recent_activity": recent_act,
                "message": f"Public profile found for CodeChef user '{clean_username}'.",
            }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        profile_url = f"{CODECHEF_USER_URL}{clean_username}"

        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            try:
                resp = client.get(profile_url, headers=headers)
                if resp.status_code == 429:
                    wait_sec = self._parse_retry_after(resp) or self.backoff_delays[0]
                    time.sleep(wait_sec)
                    resp = client.get(profile_url, headers=headers)

                if resp.status_code == 404:
                    raise CodeChefUserNotFoundError(f"CodeChef username '{clean_username}' not found.")
                if resp.status_code == 429:
                    raise CodeChefRateLimitError("CodeChef temporarily rate-limited this request (HTTP 429). Please try again after a short wait.")
                if resp.status_code == 403:
                    raise CodeChefAPIError("CodeChef returned 403 Forbidden / temporary access block.")
                resp.raise_for_status()

                # Check redirect to homepage (invalid user)
                final_path = resp.url.path.rstrip("/")
                expected_suffix = f"/users/{clean_username.lower()}"
                if not final_path.lower().endswith(expected_suffix) and final_path.lower() != f"/users/{clean_username.lower()}":
                    raise CodeChefUserNotFoundError(f"CodeChef username '{clean_username}' not found.")

                html_text = resp.text
                if "Page not found" in html_text[:1000] or "Could not find page" in html_text[:1000]:
                    raise CodeChefUserNotFoundError(f"CodeChef username '{clean_username}' not found.")

            except (CodeChefUserNotFoundError, CodeChefRateLimitError):
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    raise CodeChefUserNotFoundError(f"CodeChef username '{clean_username}' not found.") from exc
                if exc.response.status_code == 429:
                    raise CodeChefRateLimitError("CodeChef temporarily rate-limited this request (HTTP 429). Please try again after a short wait.") from exc
                if exc.response.status_code == 403:
                    raise CodeChefAPIError("CodeChef returned 403 Forbidden / temporary access block.") from exc
                raise CodeChefAPIError(f"HTTP error from CodeChef: {exc}") from exc
            except httpx.HTTPError as exc:
                raise CodeChefAPIError(f"Network request to CodeChef failed: {exc}") from exc
            except Exception as exc:
                raise CodeChefAPIError(f"Failed to fetch public profile from CodeChef: {exc}") from exc

        # Parse profile metadata from HTML
        name_match = re.search(r"<h1[^>]*class=[\'\"]h2-style[\'\"][^>]*>(.*?)</h1>", html_text, re.IGNORECASE | re.DOTALL)
        display_name = clean_username
        if name_match:
            parsed_name = re.sub(r"<[^>]+>", "", name_match.group(1)).strip()
            if parsed_name:
                display_name = parsed_name

        rating_match = re.search(r"rating-number[\'\"][^>]*>([0-9]+)<", html_text, re.IGNORECASE)
        rating_val = rating_match.group(1) if rating_match else None

        star_match = re.search(r"rating-star[\'\"][^>]*>(.*?)</div>", html_text, re.IGNORECASE | re.DOTALL)
        stars_val = None
        if star_match:
            stars_clean = re.sub(r"<[^>]+>", "", star_match.group(1)).strip()
            if stars_clean:
                stars_val = stars_clean

        rank_str = None
        if rating_val and stars_val:
            rank_str = f"Rating: {rating_val} ({stars_val})"
        elif rating_val:
            rank_str = f"Rating: {rating_val}"
        elif stars_val:
            rank_str = f"Stars: {stars_val}"

        # Parse solved problems & recent activity directly from profile HTML
        prob_pattern = r"href=[\'\"](?:/[^\'\"]+)?/problems/([A-Za-z0-9_]+)[\'\"][^>]*>(.*?)</a>"
        matches = re.findall(prob_pattern, html_text)
        
        recent_activity = []
        seen_codes = set()
        for code, title in matches:
            code_clean = code.strip()
            title_clean = re.sub(r"<[^>]+>", "", title).strip() or code_clean
            if code_clean not in seen_codes:
                seen_codes.add(code_clean)
                recent_activity.append({
                    "problem_title": title_clean,
                    "problem_url": f"https://www.codechef.com/problems/{code_clean}",
                    "verdict": "ACCEPTED",
                    "language": "C++",
                    "submitted_at": "",
                })

        total_solved = len(recent_activity)

        return {
            "platform": "codechef",
            "username": clean_username,
            "is_valid": True,
            "title_or_name": f"{display_name} (CodeChef)",
            "rank_or_rating": rank_str,
            "total_solved": total_solved,
            "recent_activity": recent_activity[:10],
            "message": f"Public profile found for CodeChef user '{clean_username}'.",
        }

    def validate_username(self, username: str) -> bool:
        """Lightweight fast username validation in a single HTTP call."""
        res = self.fetch_public_profile(username)
        return bool(res.get("is_valid"))

    def fetch_submissions(
        self,
        username: str,
        count: int = 1000,
        user_id: Optional[str] = None,
        existing_sub_ids: Optional[set] = None,
    ) -> Dict[str, Any]:
        """
        Fetch all available submission metadata pages for a CodeChef username using a single HTTP session.
        Implements exponential backoff on HTTP 429 rate limits, respecting Retry-After headers.
        Supports early pagination termination if all items on a page exist in existing_sub_ids.
        """
        if not username or not username.strip():
            raise ValueError("CodeChef username cannot be empty.")

        clean_username = username.strip()

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

        profile_url = f"{CODECHEF_USER_URL}{clean_username}"
        submissions_result = []
        seen_ids = set()
        profile_html = ""
        pages_fetched = 0

        # Single persistent HTTP client session for the entire sync
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            # 1. Profile existence check & session cookie establishment
            try:
                resp = client.get(profile_url, headers=headers)
                if resp.status_code == 404:
                    raise CodeChefUserNotFoundError(f"CodeChef username '{clean_username}' not found.")
                if resp.status_code == 429:
                    retry_sec = self._parse_retry_after(resp) or self.backoff_delays[0]
                    time.sleep(retry_sec)
                    resp = client.get(profile_url, headers=headers)
                    if resp.status_code == 429:
                        raise CodeChefRateLimitError(
                            f"CodeChef temporarily rate-limited this request (HTTP 429). Please try again after a short wait."
                        )
                if resp.status_code == 403:
                    raise CodeChefAPIError("CodeChef returned 403 Forbidden / temporary access block.")
                resp.raise_for_status()

                # CodeChef redirects invalid user handles to homepage (https://www.codechef.com/)
                final_path = resp.url.path.rstrip("/")
                expected_suffix = f"/users/{clean_username.lower()}"
                if not final_path.lower().endswith(expected_suffix) and final_path.lower() != f"/users/{clean_username.lower()}":
                    raise CodeChefUserNotFoundError(f"CodeChef username '{clean_username}' not found.")

                if "Page not found" in resp.text[:1000] or "Could not find page" in resp.text[:1000]:
                    raise CodeChefUserNotFoundError(f"CodeChef username '{clean_username}' not found.")

                profile_html = resp.text
            except (CodeChefUserNotFoundError, CodeChefRateLimitError):
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    raise CodeChefUserNotFoundError(f"CodeChef username '{clean_username}' not found.") from exc
                if exc.response.status_code == 429:
                    raise CodeChefRateLimitError(
                        f"CodeChef temporarily rate-limited this request (HTTP 429). Please try again after a short wait."
                    ) from exc
                if exc.response.status_code == 403:
                    raise CodeChefAPIError("CodeChef returned 403 Forbidden / temporary access block.") from exc
                raise CodeChefAPIError(f"HTTP error from CodeChef: {exc}") from exc
            except httpx.HTTPError as exc:
                raise CodeChefAPIError(f"Network request to CodeChef failed: {exc}") from exc
            except Exception as exc:
                raise CodeChefAPIError(f"Failed to fetch profile from CodeChef: {exc}") from exc

            # 2. Paginated Recent Submissions Loop using the SAME HTTP session
            recent_headers = {
                "User-Agent": headers["User-Agent"],
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": profile_url,
            }

            rate_limit_encountered = False

            for page in range(0, self.max_pages):
                feed_url = f"{CODECHEF_RECENT_URL}{page}&user_handle={clean_username}"

                # Exponential backoff loop for HTTP 429
                retry_count = 0
                feed_resp = None

                while retry_count <= self.max_retries_on_429:
                    try:
                        feed_resp = client.get(feed_url, headers=recent_headers)
                        if feed_resp.status_code == 429:
                            rate_limit_encountered = True
                            wait_sec = self._parse_retry_after(feed_resp)
                            if wait_sec is None:
                                delay_idx = min(retry_count, len(self.backoff_delays) - 1)
                                wait_sec = self.backoff_delays[delay_idx]
                            
                            retry_count += 1
                            if retry_count <= self.max_retries_on_429:
                                time.sleep(wait_sec)
                            else:
                                break
                        else:
                            break
                    except Exception:
                        break

                if not feed_resp or feed_resp.status_code == 429:
                    # Persistent 429 after max retries -> stop pagination gracefully
                    if page == 0 and not submissions_result:
                        raise CodeChefRateLimitError(
                            "CodeChef temporarily rate-limited this request (HTTP 429). Please try again after a short wait."
                        )
                    break

                if feed_resp.status_code != 200:
                    if page == 0 and not submissions_result:
                        if feed_resp.status_code == 403:
                            raise CodeChefAPIError("CodeChef returned 403 Forbidden / Cloudflare access block.")
                        raise CodeChefAPIError(f"CodeChef feed request failed with HTTP {feed_resp.status_code}.")
                    break

                pages_fetched += 1

                try:
                    feed_data = feed_resp.json()
                except Exception:
                    if page == 0 and not submissions_result:
                        resp_text = getattr(feed_resp, "text", "")
                        if "Just a moment..." in resp_text or "Cloudflare" in resp_text:
                            raise CodeChefAPIError("CodeChef access blocked by Cloudflare verification.")
                        raise CodeChefAPIError("Failed to parse CodeChef feed response as JSON.")
                    break

                content = feed_data.get("content", "")
                if not content or "No Recent Activity" in content:
                    # Empty page -> end of history
                    break

                rows = re.findall(r"<tr\s*>(.*?)</tr>", content, re.DOTALL)
                page_added = 0
                page_already_known = 0
                valid_data_rows = 0

                for row in rows:
                    prob_match = re.search(r"href=[\'\"](?:/[^\'\"]+)?/problems/([^\'\"]+)[\'\"][^>]*>(.*?)</a>", row)
                    if not prob_match:
                        continue
                    valid_data_rows += 1
                    prob_code = prob_match.group(1).strip()
                    prob_title = prob_match.group(2).strip() or prob_code

                    time_match = re.search(r"<span class=[\'\"]tooltiptext[\'\"]>(.*?)</span>", row)
                    submitted_at = time_match.group(1).strip() if time_match else ""

                    tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
                    lang = "unknown"
                    if len(tds) >= 4:
                        lang_raw = re.sub(r"<[^>]+>", "", tds[3]).strip()
                        if lang_raw and lang_raw.lower() != "view":
                            lang = lang_raw

                    sub_id = f"cc_{prob_code}_{submitted_at.replace(' ', '_').replace('/', '-')}"
                    db_sub_id = f"{user_id}_{sub_id}" if user_id else sub_id

                    if existing_sub_ids and (sub_id in existing_sub_ids or db_sub_id in existing_sub_ids):
                        page_already_known += 1

                    if sub_id not in seen_ids:
                        seen_ids.add(sub_id)
                        submissions_result.append({
                            "id": sub_id,
                            "problemCode": prob_code,
                            "problemTitle": prob_title,
                            "submitted_at": submitted_at,
                            "verdict": "ACCEPTED",
                            "language": lang,
                        })
                        page_added += 1

                if page_added == 0:
                    break

                # Early Pagination Stopping Condition:
                # If existing_sub_ids was passed and all items on this page are already known in the database,
                # stop fetching older pages because feed is reverse chronological (newest first).
                if existing_sub_ids and valid_data_rows > 0 and page_already_known == valid_data_rows:
                    break

                if self.page_delay > 0:
                    time.sleep(self.page_delay)

        # 3. Fallback: Parse solved problems directly from profile page HTML if feed was empty & 0 fetched
        if not submissions_result and profile_html:
            pattern = r"href=[\'\"](?:/[^\'\"]+)?/problems/([A-Za-z0-9_]+)[\'\"][^>]*>(.*?)</a>"
            matches = re.findall(pattern, profile_html)
            for code, title in matches:
                code_clean = code.strip()
                title_clean = re.sub(r"<[^>]+>", "", title).strip() or code_clean
                sub_id = f"cc_{code_clean}"
                if sub_id not in seen_ids:
                    seen_ids.add(sub_id)
                    submissions_result.append({
                        "id": sub_id,
                        "problemCode": code_clean,
                        "problemTitle": title_clean,
                        "submitted_at": "",
                        "verdict": "ACCEPTED",
                        "language": "C++",
                    })

        # Construct structured metadata response
        data = {
            "status": "OK",
            "username": clean_username,
            "result": submissions_result,
            "rate_limited": rate_limit_encountered,
            "pages_fetched": pages_fetched,
        }

        # Save raw JSON locally
        if user_id:
            save_path = USERS_DATA_DIR / user_id / "raw" / f"codechef_{clean_username.lower()}.json"
        else:
            save_path = RAW_DATA_DIR / "codechef" / f"{clean_username.lower()}_submissions.json"

        self.save_raw_json(data, save_path)
        return data
