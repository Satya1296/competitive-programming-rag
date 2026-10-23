import re
import httpx
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.collectors.base import BaseCollector

ALLOWED_EXTENSIONS = {".cpp", ".cc", ".cxx", ".c", ".java", ".py", ".js", ".ts"}
IGNORED_DIR_PATTERNS = {
    ".git/", ".github/", "node_modules/", "venv/", ".venv/",
    "env/", "build/", "dist/", "__pycache__/", ".idea/", ".vscode/"
}
MAX_FILE_SIZE_BYTES = 500 * 1024  # 500 KB limit per file


def parse_github_repo_url(url_or_handle: str) -> Tuple[str, str]:
    """
    Parses a GitHub repo URL or handle into (owner, repo).
    Supports:
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - http://github.com/owner/repo
      - github.com/owner/repo
      - owner/repo
    """
    if not url_or_handle or not str(url_or_handle).strip():
        raise ValueError("GitHub repository URL or handle cannot be empty.")

    clean = str(url_or_handle).strip()
    clean = re.sub(r"\.git$", "", clean)
    clean = clean.rstrip("/")

    # Match https://github.com/owner/repo or github.com/owner/repo
    match = re.search(r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+)$", clean)
    if match:
        owner, repo = match.group(1).strip(), match.group(2).strip()
    else:
        parts = [p.strip() for p in clean.split("/") if p.strip()]
        if len(parts) == 2:
            owner, repo = parts[0], parts[1]
        else:
            raise ValueError(
                f"Invalid GitHub repository URL '{url_or_handle}'. "
                "Expected format: 'https://github.com/owner/repo' or 'owner/repo'."
            )

    # Validate characters
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", owner) or not re.match(r"^[a-zA-Z0-9_\-\.]+$", repo):
        raise ValueError(f"Invalid characters in repository identifier '{owner}/{repo}'.")

    return owner, repo


def detect_language_from_filename(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    mapping = {
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".c": "c",
        ".java": "java",
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
    }
    return mapping.get(ext, "unknown")


def extract_problem_info_from_path(file_path: str) -> Tuple[str, str, str]:
    """
    Extracts (platform, problem_id, problem_title) from a solution file path.
    """
    norm_path = file_path.replace("\\", "/").lower()
    if "leetcode" in norm_path:
        platform = "leetcode"
    elif "codeforces" in norm_path:
        platform = "codeforces"
    elif "codechef" in norm_path:
        platform = "codechef"
    else:
        platform = "github"

    base_name = Path(file_path).stem

    match = re.match(r"^(\d+[a-zA-Z\d]*)[_\-\s]+(.*)$", base_name)
    if match:
        problem_id = match.group(1).upper() if platform == "codeforces" else match.group(1).lstrip("0") or match.group(1)
        raw_title = match.group(2)
    else:
        problem_id = base_name
        raw_title = base_name

    clean_title = re.sub(r"[_\-\.]+", " ", raw_title).strip()
    clean_title = re.sub(r"([a-z])([A-Z])", r"\1 \2", clean_title)
    clean_title = clean_title.title() if clean_title else problem_id

    return platform, problem_id, clean_title


class GitHubAPIError(Exception):
    """Base exception for GitHub API errors."""
    pass


class GitHubRepoNotFoundError(GitHubAPIError):
    """Exception raised when a GitHub repository is not found or is private without authentication."""
    pass


class GitHubRateLimitError(GitHubAPIError):
    """Exception raised when GitHub API rate limit is exceeded."""
    pass


class GitHubAuthError(GitHubAPIError):
    """Exception raised when GitHub API authentication fails."""
    pass


import time
import json
import logging

logger = logging.getLogger(__name__)

# In-memory repository cache: cache_key -> {"timestamp": float, "branch": str, "paths": list, "folders": list}
_REPO_TREE_CACHE: Dict[str, Dict[str, Any]] = {}
# In-memory solution content cache: cache_key -> (timestamp, code_content)
_SOLUTION_CONTENT_CACHE: Dict[str, Tuple[float, str]] = {}


def _extract_numeric_id(val: Any) -> Optional[int]:
    if not val:
        return None
    s = str(val).strip()
    if s.isdigit():
        return int(s)
    m = re.match(r"^0*(\d+)[\-_\.\s]", s)
    if m:
        return int(m.group(1))
    return None


def _is_reliable_match(
    name_or_path: str,
    clean_slug: str,
    norm_title_slug: str,
    alnum_title: str,
    num_id: Optional[int] = None,
) -> bool:
    base = name_or_path.split("/")[-1]
    stem = re.sub(r"\.[a-zA-Z0-9]+$", "", base).lower()
    stem_no_num = re.sub(r"^[0-9]+[\-_\.\s]+", "", stem).strip("-_. ")
    alnum_stem = re.sub(r"[^a-z0-9]", "", stem_no_num)

    m_num = re.match(r"^0*([0-9]+)[\-_\.\s]+", stem)
    file_num_id = int(m_num.group(1)) if m_num else None

    # If both have explicit numeric problem IDs, they MUST match
    if num_id is not None and file_num_id is not None:
        if num_id != file_num_id:
            return False

    # Exact slug/title matches
    if clean_slug and (stem_no_num == clean_slug or stem == clean_slug):
        return True
    if norm_title_slug and (stem_no_num == norm_title_slug or stem == norm_title_slug):
        return True
    if alnum_title and alnum_stem == alnum_title:
        return True

    return False



class GitHubCollector(BaseCollector):
    """Collector for validating, connecting, and syncing competitive programming solutions from GitHub repositories."""

    def __init__(self, access_token: Optional[str] = None, timeout: float = 15.0):
        self.access_token = access_token
        self.timeout = timeout
        self.base_api_url = "https://api.github.com"
        self.default_branch = "main"

    def _get_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        active_token = token or self.access_token
        headers = {
            "User-Agent": "CP-Knowledge-Retrieval-System",
            "Accept": "application/vnd.github.v3+json",
        }
        if active_token and str(active_token).strip():
            headers["Authorization"] = f"Bearer {str(active_token).strip()}"
        return headers

    def validate_repository(self, repo_url_or_handle: str, token: Optional[str] = None) -> Dict[str, Any]:
        """
        Validates repository format and verifies that the repository is accessible via GitHub API.
        Falls back to public web verification if API rate limit is encountered without token.
        Returns repository metadata dictionary if valid.
        """
        owner, repo = parse_github_repo_url(repo_url_or_handle)
        url = f"{self.base_api_url}/repos/{owner}/{repo}"
        headers = self._get_headers(token)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    self.default_branch = data.get("default_branch", "main")
                    return {
                        "owner": owner,
                        "repo": repo,
                        "full_name": data.get("full_name", f"{owner}/{repo}"),
                        "default_branch": self.default_branch,
                        "description": data.get("description"),
                        "html_url": data.get("html_url", f"https://github.com/{owner}/{repo}"),
                        "is_private": data.get("private", False),
                        "stars": data.get("stargazers_count", 0),
                    }
                elif resp.status_code == 404:
                    raise GitHubRepoNotFoundError(
                        f"GitHub repository '{owner}/{repo}' not found or is private without a valid access token."
                    )
                elif resp.status_code == 401:
                    raise GitHubAuthError("GitHub authentication failed. Please check your Personal Access Token.")
                elif resp.status_code == 403:
                    msg = resp.json().get("message", "") if resp.headers.get("content-type", "").startswith("application/json") else ""
                    # If unauthenticated and public repository, check public web availability
                    if not token:
                        try:
                            web_resp = client.get(f"https://github.com/{owner}/{repo}", headers={"User-Agent": "Mozilla/5.0"})
                            if web_resp.status_code == 200:
                                return {
                                    "owner": owner,
                                    "repo": repo,
                                    "full_name": f"{owner}/{repo}",
                                    "default_branch": "main",
                                    "description": "Public repository",
                                    "html_url": f"https://github.com/{owner}/{repo}",
                                    "is_private": False,
                                    "stars": 0,
                                }
                            elif web_resp.status_code == 404:
                                raise GitHubRepoNotFoundError(
                                    f"GitHub repository '{owner}/{repo}' not found or is private without a valid access token."
                                )
                        except GitHubRepoNotFoundError:
                            raise
                        except Exception:
                            pass

                    if "rate limit" in msg.lower():
                        raise GitHubRateLimitError(
                            "GitHub API rate limit exceeded. Provide a Personal Access Token to increase limits."
                        )
                    raise GitHubAPIError(f"GitHub access forbidden (HTTP 403): {msg or 'Access denied'}")
                else:
                    raise GitHubAPIError(f"GitHub API returned HTTP {resp.status_code}: {resp.text[:200]}")
        except (GitHubRepoNotFoundError, GitHubAuthError, GitHubRateLimitError, GitHubAPIError):
            raise
        except Exception as e:
            raise GitHubAPIError(f"Failed to connect to GitHub: {str(e)}") from e

    def lookup_solution(
        self,
        repo_handle: str,
        token: Optional[str] = None,
        problem_title: str = "",
        problem_slug: str = "",
        problem_id: Optional[str] = None,
        preferred_language: Optional[str] = None,
        target_file_path: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Looks up matching solution file(s) in the connected GitHub repository for an existing submission.
        Uses problem title, slug, problem ID, and repository structure.
        Reliably matches exact problem, rejects false positives, supports multiple languages,
        prioritizes preferred submission language, and caches contents.
        Returns dict with (code, language, filename, url, path, available_solutions) or None.
        """
        try:
            owner, repo = parse_github_repo_url(repo_handle)
        except Exception:
            return None

        clean_slug = (problem_slug or "").strip().lower()
        clean_slug = re.sub(r"^lc_", "", clean_slug)
        clean_slug = re.sub(r"_\d+$", "", clean_slug).replace("_", "-").strip("-")

        clean_title = (problem_title or "").strip()
        norm_title_slug = re.sub(r"[^a-z0-9]+", "-", clean_title.lower()).strip("-")
        alnum_title = re.sub(r"[^a-z0-9]", "", clean_title.lower())

        if not clean_slug and not norm_title_slug:
            return None

        num_id = _extract_numeric_id(problem_id)

        cache_key = f"{owner.lower()}/{repo.lower()}"
        cached_data = _REPO_TREE_CACHE.get(cache_key)
        now = time.time()

        branch = "main"
        paths: List[str] = []
        folders: List[str] = []

        if cached_data and (now - cached_data["timestamp"] < 900):
            branch = cached_data["branch"]
            paths = cached_data.get("paths", [])
            folders = cached_data.get("folders", [])
        else:
            headers = self._get_headers(token)
            with httpx.Client(timeout=self.timeout) as client:
                try:
                    meta_resp = client.get(f"{self.base_api_url}/repos/{owner}/{repo}", headers=headers)
                    if meta_resp.status_code == 200:
                        branch = meta_resp.json().get("default_branch", "main")
                except Exception:
                    pass

                try:
                    tree_url = f"{self.base_api_url}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
                    tree_resp = client.get(tree_url, headers=headers)
                    if tree_resp.status_code == 200:
                        tree_items = tree_resp.json().get("tree", [])
                        paths = [it["path"] for it in tree_items if it.get("type") == "blob"]
                except Exception:
                    pass

                if not paths:
                    try:
                        web_url = f"https://github.com/{owner}/{repo}"
                        web_resp = client.get(web_url, headers={"User-Agent": "Mozilla/5.0"})
                        if web_resp.status_code == 200:
                            match = re.search(r'data-target="react-app\.embeddedData">({.*?})</script>', web_resp.text)
                            if match:
                                data = json.loads(match.group(1))
                                repo_route = data.get("payload", {}).get("codeViewRepoRoute", {})
                                branch = repo_route.get("refInfo", {}).get("name", branch)
                                items = repo_route.get("tree", {}).get("items", [])
                                folders = [it.get("name") for it in items if it.get("contentType") == "directory"]
                                paths = [it.get("path") for it in items if it.get("contentType") == "file"]
                    except Exception as e:
                        logger.warning(f"Failed web fallback for GitHub repo {owner}/{repo}: {e}")

            _REPO_TREE_CACHE[cache_key] = {
                "timestamp": now,
                "branch": branch,
                "paths": paths,
                "folders": folders,
            }

        candidate_matches: List[Dict[str, Any]] = []

        if paths:
            for p in paths:
                ext = Path(p).suffix.lower()
                if ext in ALLOWED_EXTENSIONS:
                    parts = p.split("/")
                    filename = parts[-1]
                    parent = parts[-2] if len(parts) > 1 else ""
                    if (parent and _is_reliable_match(parent, clean_slug, norm_title_slug, alnum_title, num_id)) or \
                       _is_reliable_match(filename, clean_slug, norm_title_slug, alnum_title, num_id):
                        lang = detect_language_from_filename(filename)
                        candidate_matches.append({
                            "path": p,
                            "filename": filename,
                            "language": lang,
                            "url": f"https://github.com/{owner}/{repo}/blob/{branch}/{p}",
                        })

        if not candidate_matches and folders:
            matched_folder = None
            for f in folders:
                if _is_reliable_match(f, clean_slug, norm_title_slug, alnum_title, num_id):
                    matched_folder = f
                    break

            if matched_folder:
                with httpx.Client(timeout=self.timeout) as client:
                    for ext in [".cpp", ".py", ".java", ".js", ".ts", ".c", ".cc", ".cxx"]:
                        candidate = f"{matched_folder}/{matched_folder}{ext}"
                        raw_test_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{candidate}"
                        try:
                            r_test = client.get(raw_test_url)
                            if r_test.status_code == 200:
                                lang = detect_language_from_filename(candidate)
                                candidate_matches.append({
                                    "path": candidate,
                                    "filename": Path(candidate).name,
                                    "language": lang,
                                    "url": f"https://github.com/{owner}/{repo}/blob/{branch}/{candidate}",
                                })
                                break
                        except Exception:
                            continue

                    if not candidate_matches:
                        for ext in [".cpp", ".py", ".java", ".js", ".ts", ".c"]:
                            for sol_name in ["solution", "Solution"]:
                                candidate = f"{matched_folder}/{sol_name}{ext}"
                                raw_test_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{candidate}"
                                try:
                                    r_test = client.get(raw_test_url)
                                    if r_test.status_code == 200:
                                        lang = detect_language_from_filename(candidate)
                                        candidate_matches.append({
                                            "path": candidate,
                                            "filename": Path(candidate).name,
                                            "language": lang,
                                            "url": f"https://github.com/{owner}/{repo}/blob/{branch}/{candidate}",
                                        })
                                        break
                                except Exception:
                                    continue
                            if candidate_matches:
                                break

        if not candidate_matches:
            return None

        # Select active match
        active_match = None
        if target_file_path:
            for c in candidate_matches:
                if c["path"] == target_file_path:
                    active_match = c
                    break
            if not active_match and target_file_path in paths:
                fn = Path(target_file_path).name
                active_match = {
                    "path": target_file_path,
                    "filename": fn,
                    "language": detect_language_from_filename(fn),
                    "url": f"https://github.com/{owner}/{repo}/blob/{branch}/{target_file_path}",
                }

        if not active_match and preferred_language:
            pref = preferred_language.lower().strip()
            ext_map = {
                "cpp": [".cpp", ".cc", ".cxx"],
                "c++": [".cpp", ".cc", ".cxx"],
                "python": [".py"],
                "python3": [".py"],
                "java": [".java"],
                "c": [".c"],
                "javascript": [".js"],
                "typescript": [".ts"],
            }
            target_exts = ext_map.get(pref, [f".{pref}"])
            for c in candidate_matches:
                p_ext = Path(c["path"]).suffix.lower()
                if p_ext in target_exts or c["language"].lower() == pref:
                    active_match = c
                    break

        if not active_match:
            active_match = candidate_matches[0]

        # Check solution content cache
        content_cache_key = f"{owner.lower()}/{repo.lower()}:{branch}:{active_match['path']}"
        cached_content = _SOLUTION_CONTENT_CACHE.get(content_cache_key)
        if cached_content and (now - cached_content[0] < 3600):
            content = cached_content[1]
        else:
            raw_headers = {"User-Agent": "CP-Knowledge-Retrieval-System"}
            if token and str(token).strip():
                raw_headers["Authorization"] = f"Bearer {str(token).strip()}"

            download_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{active_match['path']}"
            content = None
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(download_url, headers=raw_headers)
                    if resp.status_code != 200:
                        api_content_url = f"{self.base_api_url}/repos/{owner}/{repo}/contents/{active_match['path']}"
                        api_headers = self._get_headers(token)
                        api_headers["Accept"] = "application/vnd.github.v3.raw"
                        resp = client.get(api_content_url, headers=api_headers)

                    if resp.status_code == 200 and resp.text.strip():
                        content = resp.text
                        _SOLUTION_CONTENT_CACHE[content_cache_key] = (now, content)
            except Exception as e:
                logger.warning(f"Failed to fetch content for matched solution '{active_match['path']}': {e}")

            if not content:
                return None

        return {
            "code": content,
            "language": active_match["language"],
            "filename": active_match["filename"],
            "url": active_match["url"],
            "path": active_match["path"],
            "available_solutions": candidate_matches,
        }

    def fetch_submissions(self, handle: str, count: int = 100, **kwargs) -> Dict[str, Any]:
        """BaseCollector compliance method."""
        return {"status": "OK", "handle": handle, "submissions": []}


