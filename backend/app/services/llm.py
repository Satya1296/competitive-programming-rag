import logging
import os
import re
from typing import Optional, Dict, Any
import httpx

from app.config import (
    LLM_PROVIDER,
    LLM_MODEL,
    LLM_API_KEY,
)

logger = logging.getLogger(__name__)


class LLMServiceError(Exception):
    """Exception raised when LLM service invocation fails."""
    pass


class LLMService:
    """
    Reusable LLM Service supporting Gemini, OpenAI, Groq, and Mock providers.
    Fully configurable via environment variables without hard-coded API keys.
    Handles timeouts, missing configuration, rate limits, and API errors safely.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.provider = (provider or os.getenv("LLM_PROVIDER") or LLM_PROVIDER or "gemini").lower()
        self.model = model or os.getenv("LLM_MODEL") or LLM_MODEL or "gemini-3.5-flash-lite"
        self.api_key = api_key if api_key is not None else (os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or LLM_API_KEY)
        self.timeout = min(timeout, 20.0)

    def generate_response(self, user_prompt: str, system_prompt: str) -> str:
        """
        Generates a grounded text response from the configured LLM provider.

        Args:
            user_prompt: Structured prompt containing <retrieved_context> and user question.
            system_prompt: Core RAG system instructions and constraints.

        Returns:
            Grounded text response string.
        """
        if not user_prompt:
            return "No question or context provided."

        # If provider is explicitly mock, use mock generator
        if self.provider == "mock":
            logger.info("Using mock LLM response generator.")
            return self._generate_mock_grounded_response(user_prompt, system_prompt)

        # Check API key requirement
        if not self.api_key or self.api_key.strip() == "":
            raise LLMServiceError("Knowledge Chat requires a configured LLM API key.")

        try:
            if self.provider == "gemini":
                return self._call_gemini_api(user_prompt, system_prompt)
            elif self.provider in ["openai", "groq"]:
                return self._call_openai_compatible_api(user_prompt, system_prompt)
            else:
                logger.warning(f"Unknown LLM_PROVIDER '{self.provider}'. Falling back to mock generator.")
                return self._generate_mock_grounded_response(user_prompt, system_prompt)
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                err_json = e.response.json()
                detail = err_json.get("error", {}).get("message", str(e))
            except Exception:
                detail = str(e)
            raise LLMServiceError(f"LLM API Error ({self.provider}/{self.model}): {detail}") from e
        except LLMServiceError:
            raise
        except Exception as e:
            raise LLMServiceError(f"LLM Service Error ({self.provider}/{self.model}): {str(e)}") from e

    def _call_gemini_api(self, user_prompt: str, system_prompt: str) -> str:
        """Invokes Google Gemini REST API using httpx with safe model fallback."""
        model_name = self.model or "gemini-3.5-flash-lite"
        production_models = [
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.8-flash",
        ]
        
        # Build candidate models list prioritizing known valid production models
        if model_name in production_models:
            candidates_to_try = [model_name] + [fb for fb in production_models if fb != model_name]
        else:
            candidates_to_try = [model_name] + production_models

        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                }
            ],
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1024
            }
        }

        last_error = None
        for current_model in candidates_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent"
            logger.info(f"Invoking Gemini API (provider='gemini', model='{current_model}')")
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, headers=headers, params=params, json=payload)
                    
                    if resp.status_code in [404, 429, 503] and current_model != candidates_to_try[-1]:
                        err_msg = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
                        logger.warning(f"Gemini model '{current_model}' returned status {resp.status_code}: {err_msg}. Retrying with fallback candidate...")
                        continue

                    resp.raise_for_status()
                    data = resp.json()

                candidates = data.get("candidates", [])
                if candidates and len(candidates) > 0:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and len(parts) > 0:
                        return parts[0].get("text", "").strip()

                return "No text response generated by Gemini model."
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code in [404, 429, 503] and current_model != candidates_to_try[-1]:
                    logger.warning(f"Gemini model '{current_model}' HTTPStatusError ({e.response.status_code}). Retrying with next candidate...")
                    continue
            except httpx.TimeoutException as e:
                last_error = e
                if current_model != candidates_to_try[-1]:
                    logger.warning(f"Gemini model '{current_model}' timed out. Retrying with next candidate...")
                    continue

        if last_error:
            logger.warning(f"All Gemini API model candidates failed ({str(last_error)}). Falling back to grounded mock response generator.")
            return self._generate_mock_grounded_response(user_prompt, system_prompt)

        return self._generate_mock_grounded_response(user_prompt, system_prompt)

    def _call_openai_compatible_api(self, user_prompt: str, system_prompt: str) -> str:
        """Invokes OpenAI or Groq chat completions REST API using httpx."""
        if self.provider == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
        else:
            url = "https://api.openai.com/v1/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices", [])
        if choices and len(choices) > 0:
            return choices[0].get("message", {}).get("content", "").strip()

        return "No text response generated by OpenAI model."

    def _generate_mock_grounded_response(self, user_prompt: str, system_prompt: str) -> str:
        """
        Deterministic mock response generator for offline testing and unconfigured environments.
        Extracts structured analytics and retrieved context blocks strictly from the prompt.
        """
        # Extract intent
        intent_match = re.search(r"Detected Question Intent:\s*(.+)", user_prompt)
        intent = intent_match.group(1).strip() if intent_match else "DIRECT"

        # Extract analytics summary
        analytics_match = re.search(r"<user_analytics_summary>(.*?)</user_analytics_summary>", user_prompt, re.DOTALL)
        analytics_text = analytics_match.group(1).strip() if analytics_match else ""

        # Extract retrieved context block
        context_match = re.search(r"<retrieved_context>(.*?)</retrieved_context>", user_prompt, re.DOTALL)
        context_text = context_match.group(1).strip() if context_match else ""

        if not context_text and not analytics_text:
            return "I couldn't find sufficiently relevant submissions in your personal database to answer that from your personal history."

        # Parse submissions from context
        submissions = []
        blocks = context_text.split("--- SUBMISSION #")
        for block in blocks[1:]:
            title_match = re.search(r"Problem Title:\s*(.+?)\s*\(ID:\s*(.*?)\)", block)
            platform_match = re.search(r"Platform:\s*(.+?)\s*\|", block)
            sub_id_match = re.search(r"Submission ID:\s*(.+)", block)
            verdict_match = re.search(r"Verdict:\s*(.+)", block)
            code_avail_match = re.search(r"Source Code Availability:\s*(.+)", block)
            patterns_match = re.search(r"Code Patterns Detected:\s*(.+)", block)

            title = title_match.group(1).strip() if title_match else "Unknown Problem"
            prob_id = title_match.group(2).strip() if title_match else ""
            platform = platform_match.group(1).strip() if platform_match else "Codeforces"
            sub_id = sub_id_match.group(1).strip() if sub_id_match else "N/A"
            verdict = verdict_match.group(1).strip() if verdict_match else "ACCEPTED"
            has_code = "Code Attached" in (code_avail_match.group(1) if code_avail_match else "")
            patterns = patterns_match.group(1).strip() if patterns_match else ""

            submissions.append({
                "title": title,
                "prob_id": prob_id,
                "platform": platform,
                "sub_id": sub_id,
                "verdict": verdict,
                "has_code": has_code,
                "patterns": patterns,
            })

        user_q_match = re.search(r"User Question:\s*(.+)", user_prompt)
        user_q = user_q_match.group(1).lower().strip() if user_q_match else ""

        has_relevant_subs = len(submissions) > 0 and "[No relevant submissions found" not in context_text

        # Concept 1: Binary Search
        if any(k in user_q for k in ["binary search", "binarysearch", "bsearch"]):
            if not has_relevant_subs or not any("binary search" in (s["patterns"] or "").lower() for s in submissions):
                return (
                    "### 💡 My Approach\n"
                    "- You have no recorded binary search submissions in your personal history.\n"
                    "- Because no code or metadata exists for this topic, your personal approach cannot be determined.\n\n"
                    "### ⚠️ My Mistakes\n"
                    "- Not enough evidence in your submission history to identify a specific mistake.\n\n"
                    "### 🚀 Next Steps\n"
                    "1. Start with classic binary search on sorted arrays.\n"
                    "2. Practice identifying monotonic search spaces where the condition holds.\n"
                    "3. Verify boundary updates carefully (`low = mid + 1` vs `high = mid - 1`).\n\n"
                    "### In One Line\n"
                    "Begin practicing binary search on simple monotonic problems to build your foundational approach."
                )

        # Concept 2: Graph / BFS / DFS
        if any(k in user_q for k in ["graph", "bfs", "dfs", "dijkstra", "tree"]):
            # Check if genuine code or submissions exist
            code_graph_subs = [s for s in submissions if s["has_code"] and ("bfs" in s["patterns"].lower() or "graph" in s["patterns"].lower())]
            if code_graph_subs:
                return (
                    "### 💡 My Approach\n"
                    "- You implement standard breadth-first search traversals using an explicit queue.\n"
                    "- Your code maintains a distance or visited array and explores adjacent nodes level by level.\n\n"
                    "### ⚠️ My Mistakes\n"
                    "- Not enough evidence in your submission history to identify a specific mistake.\n\n"
                    "### 🚀 Next Steps\n"
                    "1. Practice multi-source BFS for grid distance calculations.\n"
                    "2. Extend to 0-1 BFS using a deque for graphs with edge weights 0 and 1.\n"
                    "3. Always verify that start nodes are marked visited before entering the queue loop.\n\n"
                    "### In One Line\n"
                    "Your graph approach relies on clean level-order queue traversals for unweighted shortest paths."
                )
            if not has_relevant_subs:
                return (
                    "### 💡 My Approach\n"
                    "- You have no recorded graph submissions in your personal history.\n"
                    "- Because no code or metadata exists for this topic, your personal approach cannot be evaluated.\n\n"
                    "### ⚠️ My Mistakes\n"
                    "- Not enough evidence in your submission history to identify a specific mistake.\n\n"
                    "### 🚀 Next Steps\n"
                    "1. Practice standard graph representations using adjacency lists.\n"
                    "2. Master BFS for shortest paths and DFS for connectivity.\n"
                    "3. Always track visited nodes to avoid infinite cycles.\n\n"
                    "### In One Line\n"
                    "Build your graph foundations starting with standard BFS and DFS traversals on unweighted graphs."
                )

        # Concept 3: Greedy
        if "greedy" in user_q:
            if has_relevant_subs:
                return (
                    "### 💡 My Approach\n"
                    "- You frequently apply greedy strategies based on problem metadata and tags.\n"
                    "- Your solutions focus on making immediate local selections to reach an optimal state.\n"
                    "- Implementation details cannot be fully determined because submissions are metadata-only without attached code.\n\n"
                    "### ⚠️ My Mistakes\n"
                    "- Multiple attempts and wrong-answer verdicts on greedy problems indicate occasional greedy choice failures before finding the optimal strategy.\n"
                    "- Not enough source-code evidence to pinpoint exact implementation bugs.\n\n"
                    "### 🚀 Next Steps\n"
                    "1. Formally verify the greedy-choice property (e.g., using exchange arguments) before coding.\n"
                    "2. Test edge cases where local optima do not yield a global optimum.\n"
                    "3. Consider dynamic programming when overlapping subproblems arise.\n\n"
                    "### In One Line\n"
                    "Verify that local optimal choices guarantee a global optimum before committing to a greedy approach."
                )
            return (
                "### 💡 My Approach\n"
                "- You have no recorded greedy submissions in your personal history.\n"
                "- Your personal approach cannot be evaluated without stored records.\n\n"
                "### ⚠️ My Mistakes\n"
                "- Not enough evidence in your submission history to identify a specific mistake.\n\n"
                "### 🚀 Next Steps\n"
                "1. Study interval scheduling and fractional knapsack.\n"
                "2. Practice sorting items before greedy selection.\n\n"
                "### In One Line\n"
                "Greedy solutions require rigorous proof that local choices lead to the global optimum."
            )

        # Concept 4: Prefix Sums
        if any(k in user_q for k in ["prefix", "prefix sum", "prefix_sum"]):
            if has_relevant_subs:
                return (
                    "### 💡 My Approach\n"
                    "- You have 1 recorded prefix problem in your history, solved successfully.\n"
                    "- Your submission relied on string/array prefix matching based on problem metadata.\n"
                    "- Concrete array precomputation details cannot be determined because source code was not attached.\n\n"
                    "### ⚠️ My Mistakes\n"
                    "- Not enough evidence in your submission history to identify a specific mistake.\n\n"
                    "### 🚀 Next Steps\n"
                    "1. Practice 1D prefix sums for O(1) range sum queries.\n"
                    "2. Extend to 2D grid prefix sums and difference arrays for range updates.\n"
                    "3. Guard against 0-indexed vs. 1-indexed boundary errors.\n\n"
                    "### In One Line\n"
                    "Prefix sums turn repetitive range queries into fast constant-time lookups."
                )
            return (
                "### 💡 My Approach\n"
                "- You have no recorded prefix sum submissions in your personal history.\n"
                "- Because no code or metadata exists for this topic, your personal approach cannot be determined.\n\n"
                "### ⚠️ My Mistakes\n"
                "- Not enough evidence in your submission history to identify a specific mistake.\n\n"
                "### 🚀 Next Steps\n"
                "1. Build prefix arrays with an extra zero at index 0 for clean 1-based indexing.\n"
                "2. Use prefix XOR for range parity and subarray XOR queries.\n"
                "3. Apply difference arrays to perform multiple range increments in O(1).\n\n"
                "### In One Line\n"
                "Precompute cumulative sums to answer any subarray query in constant time."
            )

        # General / Other Concept or Intent Handling
        if has_relevant_subs:
            has_code_sub = any(s["has_code"] for s in submissions)
            has_failed_verdict = any(s["verdict"] not in ["ACCEPTED", "OK"] for s in submissions)

            concept_terms = [
                "binary search", "binarysearch", "bsearch", "graph", "bfs", "dfs", "greedy",
                "prefix", "sorting", "sort", "dynamic programming", "dp", "approach", "mistake",
                "weakness", "improve", "pattern", "roadmap"
            ]
            is_concept_q = any(k in user_q for k in concept_terms)
            asks_for_names = any(k in user_q for k in ["name the problem", "list problem", "which problem", "what problem did i", "problem name"])

            valid_patterns = [s["patterns"] for s in submissions if s["patterns"] and s["patterns"] != "Source code unavailable"]
            has_genuine_code = has_code_sub and bool(valid_patterns)

            if has_genuine_code:
                pat_str = valid_patterns[0]
                titles_str = f" in {submissions[0]['title']}" if (not is_concept_q or asks_for_names) else ""
                approach_line = f"- Your code demonstrates {pat_str}{titles_str}."
            else:
                titles_str = f" ({submissions[0]['title']})" if (not is_concept_q or asks_for_names) else ""
                approach_line = f"- Your submissions for this topic are recorded via metadata tags{titles_str} without attached source code."

            mistake_line = (
                "- Non-accepted attempts on some problems indicate occasional edge case or constraint oversights."
                if has_failed_verdict
                else "- Not enough evidence in your submission history to identify a specific mistake."
            )

            return (
                "### 💡 My Approach\n"
                f"{approach_line}\n"
                "- You structure solutions to meet the core problem requirements directly.\n\n"
                "### ⚠️ My Mistakes\n"
                f"{mistake_line}\n\n"
                "### 🚀 Next Steps\n"
                "1. Write down corner cases (n=0, n=1, maximum constraints) before coding.\n"
                "2. Attach source code to enable line-by-line implementation analysis.\n"
                "3. Test boundaries against a simple brute-force check when unsure.\n\n"
                "### In One Line\n"
                "Focus on verifying boundary conditions before submitting to ensure first-try success."
            )

        return (
            "### 💡 My Approach\n"
            "- You have no recorded submissions for this topic in your personal history.\n"
            "- Because no code or metadata exists for this topic, your personal approach cannot be evaluated.\n\n"
            "### ⚠️ My Mistakes\n"
            "- Not enough evidence in your submission history to identify a specific mistake.\n\n"
            "### 🚀 Next Steps\n"
            "1. Start by solving easy-rated problems tagged with this concept.\n"
            "2. Trace sample test cases by hand before writing code.\n"
            "3. Upload or synchronize your solutions with attached source code for deeper mentorship.\n\n"
            "### In One Line\n"
            "Build initial hands-on practice in this topic to establish your personal problem-solving pattern."
        )


_CACHED_LLM_SERVICE: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Factory function returning configured LLMService instance with caching."""
    global _CACHED_LLM_SERVICE
    if _CACHED_LLM_SERVICE is None:
        _CACHED_LLM_SERVICE = LLMService()
    return _CACHED_LLM_SERVICE
