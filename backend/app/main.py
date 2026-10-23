import re
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.config import USERS_DATA_DIR
from app.db import get_db, init_db
from app.models.user import User
from app.models.profile import PlatformProfile
from app.models.submission import SubmissionRecord
from app.models.source_code import SubmissionSourceCode
from app.auth.jwt import hash_password, verify_password, create_access_token
from app.auth.dependencies import get_current_user
from app.collectors.codeforces import (
    CodeforcesCollector,
    CodeforcesAPIError,
    CodeforcesUserNotFoundError,
)
from app.collectors.leetcode import (
    LeetCodeCollector,
    LeetCodeAPIError,
    LeetCodeUserNotFoundError,
)
from app.collectors.codechef import (
    CodeChefCollector,
    CodeChefAPIError,
    CodeChefUserNotFoundError,
    CodeChefRateLimitError,
)
from app.collectors.github import (
    GitHubCollector,
    GitHubAPIError,
    GitHubRepoNotFoundError,
    GitHubRateLimitError,
    GitHubAuthError,
    parse_github_repo_url,
)
from app.preprocessing.normalizer import (
    normalize_codeforces_submissions,
    save_normalized_codeforces,
    normalize_leetcode_submissions,
    normalize_codechef_submissions,
)
from app.schema.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    TokenResponse,
)
from app.schema.profile import (
    ConnectProfileRequest,
    ConnectGitHubRequest,
    ProfileStatusResponse,
    SyncResponse,
    SubmissionResponse,
    PublicProfileSearchRequest,
    PublicProfileSearchResponse,
)

from app.schema.source_code import (
    AddSourceCodeRequest,
    SourceCodeResponse,
)
from app.schema.vector import (
    SearchQueryRequest,
    SearchQueryResponse,
    IndexingResponse,
    BulkIndexingResponse,
)
from app.schema.rag import (
    RAGQueryRequest,
    RAGQueryResponse,
)
from app.rag.service import execute_rag_pipeline
from app.services.llm import LLMServiceError
from app.vectorstore import (
    index_submission_for_user,
    index_all_user_submissions,
    get_indexing_progress,
    search_user_knowledge,
    get_chroma_store,
)


ALLOWED_EXTENSIONS = {".cpp", ".cc", ".cxx", ".c", ".java", ".py", ".js", ".ts"}
MAX_SOURCE_CODE_SIZE_BYTES = 500 * 1024  # 500 KB


def detect_language_from_filename(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    mapping = {
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".c": "cpp",
        ".java": "java",
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
    }
    return mapping.get(ext, "unknown")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize relational database tables on startup (lightweight, <10ms, <1MB RAM)
    init_db()
    # Note: EmbeddingService and ChromaDB are lazily loaded on first query to preserve memory
    # and guarantee that Render health checks pass immediately on boot.
    yield


app = FastAPI(
    title="Competitive Programming Knowledge Retrieval System API",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for local React development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "1.0.0"}


# -----------------------------------------------------------------------------
# AUTHENTICATION ENDPOINTS
# -----------------------------------------------------------------------------

@app.post(
    "/api/auth/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(req: UserRegisterRequest, db: Session = Depends(get_db)):
    """Register a new user account."""
    existing_email = db.query(User).filter(User.email == req.email.lower()).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists.",
        )

    existing_username = (
        db.query(User).filter(User.username == req.username.lower()).first()
    )
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is already taken.",
        )

    hashed_pw = hash_password(req.password)
    user = User(
        email=req.email.lower(),
        username=req.username.lower(),
        hashed_password=hashed_pw,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    access_token = create_access_token(subject=user.id)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@app.post("/api/auth/login", response_model=TokenResponse)
def login_user(req: UserLoginRequest, db: Session = Depends(get_db)):
    """Authenticate existing user and return JWT access token."""
    login_val = req.email_or_username.lower().strip()
    user = (
        db.query(User)
        .filter((User.email == login_val) | (User.username == login_val))
        .first()
    )

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email/username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=user.id)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@app.get("/api/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Return currently authenticated user profile."""
    return UserResponse.model_validate(current_user)


# -----------------------------------------------------------------------------
# CODEFORCES PLATFORM ENDPOINTS (USER-SCOPED)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# MULTI-PLATFORM ENDPOINTS (CODEFORCES, LEETCODE, CODECHEF - USER-SCOPED)
# -----------------------------------------------------------------------------

@app.post("/api/platforms/codeforces/connect", response_model=ProfileStatusResponse)
def connect_codeforces_profile(
    req: ConnectProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Associate a Codeforces handle (and optional API Key / Secret for source code retrieval)
    with the authenticated user account.
    """
    clean_handle = req.handle.strip()

    # Validate handle against Codeforces API
    collector = CodeforcesCollector()
    try:
        collector.fetch_submissions(
            clean_handle,
            count=1,
            user_id=current_user.id,
            api_key=req.api_key,
            api_secret=req.api_secret,
        )
    except CodeforcesUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Codeforces handle: {exc}",
        )
    except CodeforcesAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Codeforces API error: {exc}",
        )

    profile = (
        db.query(PlatformProfile)
        .filter(
            PlatformProfile.user_id == current_user.id,
            PlatformProfile.platform == "codeforces",
        )
        .first()
    )

    if profile:
        if profile.handle.lower() != clean_handle.lower():
            old_handle = profile.handle
            old_subs = (
                db.query(SubmissionRecord)
                .filter(
                    SubmissionRecord.user_id == current_user.id,
                    SubmissionRecord.platform == "codeforces",
                )
                .all()
            )
            old_sub_ids = [s.id for s in old_subs]

            if old_sub_ids:
                db.query(SubmissionSourceCode).filter(
                    SubmissionSourceCode.user_id == current_user.id,
                    SubmissionSourceCode.submission_id.in_(old_sub_ids),
                ).delete(synchronize_session=False)

                db.query(SubmissionRecord).filter(
                    SubmissionRecord.user_id == current_user.id,
                    SubmissionRecord.platform == "codeforces",
                ).delete(synchronize_session=False)

                try:
                    get_chroma_store().delete_user_platform_vectors(current_user.id, "codeforces")
                except Exception:
                    pass

            old_raw_path = USERS_DATA_DIR / current_user.id / "raw" / f"codeforces_{old_handle.lower()}.json"
            old_proc_path = USERS_DATA_DIR / current_user.id / "processed" / f"codeforces_{old_handle.lower()}.json"
            if old_raw_path.exists():
                try: old_raw_path.unlink()
                except Exception: pass
            if old_proc_path.exists():
                try: old_proc_path.unlink()
                except Exception: pass

            profile.handle = clean_handle

        profile.api_key = req.api_key.strip() if req.api_key else None
        profile.api_secret = req.api_secret.strip() if req.api_secret else None
    else:
        profile = PlatformProfile(
            user_id=current_user.id,
            platform="codeforces",
            handle=clean_handle,
            api_key=req.api_key.strip() if req.api_key else None,
            api_secret=req.api_secret.strip() if req.api_secret else None,
        )
        db.add(profile)

    db.commit()
    db.refresh(profile)

    total_subs = (
        db.query(SubmissionRecord)
        .filter(
            SubmissionRecord.user_id == current_user.id,
            SubmissionRecord.platform == "codeforces",
        )
        .count()
    )

    return ProfileStatusResponse(
        platform="codeforces",
        handle=profile.handle,
        connected_at=profile.created_at,
        total_submissions_synced=total_subs,
        has_api_credentials=bool(profile.api_key and profile.api_secret),
    )


@app.get("/api/platforms/codeforces/status", response_model=ProfileStatusResponse)
def get_codeforces_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(PlatformProfile)
        .filter(
            PlatformProfile.user_id == current_user.id,
            PlatformProfile.platform == "codeforces",
        )
        .first()
    )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Codeforces profile connected for this user.",
        )

    total_subs = (
        db.query(SubmissionRecord)
        .filter(
            SubmissionRecord.user_id == current_user.id,
            SubmissionRecord.platform == "codeforces",
        )
        .count()
    )

    return ProfileStatusResponse(
        platform="codeforces",
        handle=profile.handle,
        connected_at=profile.created_at,
        total_submissions_synced=total_subs,
        has_api_credentials=bool(profile.api_key and profile.api_secret),
    )


@app.post("/api/platforms/codeforces/sync", response_model=SyncResponse)
def sync_codeforces_submissions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch and normalize latest Codeforces submissions for authenticated user's active handle."""
    profile = (
        db.query(PlatformProfile)
        .filter(
            PlatformProfile.user_id == current_user.id,
            PlatformProfile.platform == "codeforces",
        )
        .first()
    )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please connect a Codeforces profile first before syncing.",
        )

    collector = CodeforcesCollector()
    try:
        raw_data = collector.fetch_submissions(
            profile.handle,
            user_id=current_user.id,
            api_key=profile.api_key,
            api_secret=profile.api_secret,
        )
    except CodeforcesUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Codeforces handle '{profile.handle}' no longer exists: {exc}",
        )
    except CodeforcesAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch submissions from Codeforces: {exc}",
        )

    normalized_list = normalize_codeforces_submissions(raw_data, user_id=current_user.id)

    existing_ids = set(
        row[0]
        for row in db.query(SubmissionRecord.id)
        .filter(
            SubmissionRecord.user_id == current_user.id,
            SubmissionRecord.platform == "codeforces",
        )
        .all()
    )

    new_records = []
    for sub in normalized_list:
        db_sub_id = f"{current_user.id}_{sub.id}"
        if db_sub_id not in existing_ids:
            record = SubmissionRecord(
                id=db_sub_id,
                user_id=current_user.id,
                platform="codeforces",
                problem_id=sub.problem_id,
                problem_title=sub.problem_title,
                problem_url=sub.problem_url,
                submission_id=sub.submission_id,
                submission_url=sub.submission_url,
                language=sub.language,
                verdict=sub.verdict,
                time_complexity=sub.time_complexity,
                space_complexity=sub.space_complexity,
                difficulty=sub.difficulty,
                tags=sub.tags,
                execution_time_ms=sub.execution_time_ms,
                memory_bytes=sub.memory_bytes,
                submitted_at=sub.submitted_at,
                code=sub.code,
                code_source=sub.code_source,
                notes=sub.notes,
            )
            db.add(record)
            existing_ids.add(db_sub_id)
            new_records.append(record)

            # Auto-store & index authenticated API source code if returned by API
            if sub.code_source == "api_authenticated" and sub.code and not sub.code.startswith("// Source code not provided"):
                src_rec = SubmissionSourceCode(
                    user_id=current_user.id,
                    submission_id=sub.submission_id,
                    language=sub.language,
                    source_code=sub.code,
                )
                db.add(src_rec)

    db.commit()

    # Index authenticated source code into ChromaDB
    for rec in new_records:
        if rec.code_source == "api_authenticated" and rec.has_source_code:
            try:
                index_submission_for_user(user_id=current_user.id, submission_id=rec.submission_id, db=db)
            except Exception:
                pass

    save_normalized_codeforces(current_user.id, profile.handle, normalized_list)

    return SyncResponse(
        platform="codeforces",
        handle=profile.handle,
        fetched_count=len(normalized_list),
        new_synced_count=len(new_records),
        message=f"Successfully synced {len(new_records)} new submissions for Codeforces handle '{profile.handle}'.",
    )


# -----------------------------------------------------------------------------
# LEETCODE PLATFORM ENDPOINTS (USER-SCOPED)
# -----------------------------------------------------------------------------

@app.post("/api/platforms/leetcode/connect", response_model=ProfileStatusResponse)
def connect_leetcode_profile(
    req: ConnectProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    clean_handle = req.handle.strip()
    collector = LeetCodeCollector()
    try:
        collector.fetch_submissions(clean_handle, count=1, user_id=current_user.id)
    except LeetCodeUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid LeetCode username: {exc}",
        )
    except LeetCodeAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LeetCode API error: {exc}",
        )

    profile = (
        db.query(PlatformProfile)
        .filter(
            PlatformProfile.user_id == current_user.id,
            PlatformProfile.platform == "leetcode",
        )
        .first()
    )

    if profile:
        if profile.handle.lower() != clean_handle.lower():
            old_handle = profile.handle
            old_subs = (
                db.query(SubmissionRecord)
                .filter(
                    SubmissionRecord.user_id == current_user.id,
                    SubmissionRecord.platform == "leetcode",
                )
                .all()
            )
            old_sub_ids = [s.id for s in old_subs]

            if old_sub_ids:
                db.query(SubmissionSourceCode).filter(
                    SubmissionSourceCode.user_id == current_user.id,
                    SubmissionSourceCode.submission_id.in_(old_sub_ids),
                ).delete(synchronize_session=False)

                db.query(SubmissionRecord).filter(
                    SubmissionRecord.user_id == current_user.id,
                    SubmissionRecord.platform == "leetcode",
                ).delete(synchronize_session=False)

                try:
                    get_chroma_store().delete_user_platform_vectors(current_user.id, "leetcode")
                except Exception:
                    pass

            old_raw_path = USERS_DATA_DIR / current_user.id / "raw" / f"leetcode_{old_handle.lower()}.json"
            old_proc_path = USERS_DATA_DIR / current_user.id / "processed" / f"leetcode_{old_handle.lower()}.json"
            if old_raw_path.exists():
                try: old_raw_path.unlink()
                except Exception: pass
            if old_proc_path.exists():
                try: old_proc_path.unlink()
                except Exception: pass

            profile.handle = clean_handle
    else:
        profile = PlatformProfile(
            user_id=current_user.id,
            platform="leetcode",
            handle=clean_handle,
        )
        db.add(profile)

    db.commit()
    db.refresh(profile)

    total_subs = (
        db.query(SubmissionRecord)
        .filter(
            SubmissionRecord.user_id == current_user.id,
            SubmissionRecord.platform == "leetcode",
        )
        .count()
    )

    return ProfileStatusResponse(
        platform="leetcode",
        handle=profile.handle,
        connected_at=profile.created_at,
        total_submissions_synced=total_subs,
        has_api_credentials=False,
    )


@app.post("/api/platforms/leetcode/sync", response_model=SyncResponse)
def sync_leetcode_submissions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(PlatformProfile)
        .filter(
            PlatformProfile.user_id == current_user.id,
            PlatformProfile.platform == "leetcode",
        )
        .first()
    )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please connect a LeetCode username first before syncing.",
        )

    collector = LeetCodeCollector()
    try:
        raw_data = collector.fetch_submissions(profile.handle, user_id=current_user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch submissions from LeetCode: {exc}",
        )

    normalized_list = normalize_leetcode_submissions(raw_data, user_id=current_user.id)

    existing_ids = set(
        row[0]
        for row in db.query(SubmissionRecord.id)
        .filter(
            SubmissionRecord.user_id == current_user.id,
            SubmissionRecord.platform == "leetcode",
        )
        .all()
    )

    new_records = []
    for sub in normalized_list:
        db_sub_id = f"{current_user.id}_{sub.id}"
        if db_sub_id not in existing_ids:
            record = SubmissionRecord(
                id=db_sub_id,
                user_id=current_user.id,
                platform="leetcode",
                problem_id=sub.problem_id,
                problem_title=sub.problem_title,
                problem_url=sub.problem_url,
                submission_id=sub.submission_id,
                submission_url=sub.submission_url,
                language=sub.language,
                verdict=sub.verdict,
                submitted_at=sub.submitted_at,
                code=sub.code,
                code_source=sub.code_source,
            )
            db.add(record)
            existing_ids.add(db_sub_id)
            new_records.append(record)

    db.commit()

    return SyncResponse(
        platform="leetcode",
        handle=profile.handle,
        fetched_count=len(normalized_list),
        new_synced_count=len(new_records),
        message=f"Successfully synced {len(new_records)} new submissions for LeetCode user '{profile.handle}'.",
    )


# -----------------------------------------------------------------------------
# CODECHEF PLATFORM ENDPOINTS (USER-SCOPED)
# -----------------------------------------------------------------------------

@app.post("/api/platforms/codechef/connect", response_model=ProfileStatusResponse)
def connect_codechef_profile(
    req: ConnectProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    clean_handle = req.handle.strip()
    collector = CodeChefCollector()
    try:
        collector.validate_username(clean_handle)
    except CodeChefUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid CodeChef username: {exc}",
        )
    except CodeChefRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="CodeChef temporarily rate-limited this request. Please try again after a short wait.",
        )
    except CodeChefAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"CodeChef API error: {exc}",
        )

    profile = (
        db.query(PlatformProfile)
        .filter(
            PlatformProfile.user_id == current_user.id,
            PlatformProfile.platform == "codechef",
        )
        .first()
    )

    if profile:
        if profile.handle.lower() != clean_handle.lower():
            old_handle = profile.handle
            old_subs = (
                db.query(SubmissionRecord)
                .filter(
                    SubmissionRecord.user_id == current_user.id,
                    SubmissionRecord.platform == "codechef",
                )
                .all()
            )
            old_sub_ids = [s.id for s in old_subs]

            if old_sub_ids:
                db.query(SubmissionSourceCode).filter(
                    SubmissionSourceCode.user_id == current_user.id,
                    SubmissionSourceCode.submission_id.in_(old_sub_ids),
                ).delete(synchronize_session=False)

                db.query(SubmissionRecord).filter(
                    SubmissionRecord.user_id == current_user.id,
                    SubmissionRecord.platform == "codechef",
                ).delete(synchronize_session=False)

                try:
                    get_chroma_store().delete_user_platform_vectors(current_user.id, "codechef")
                except Exception:
                    pass

            old_raw_path = USERS_DATA_DIR / current_user.id / "raw" / f"codechef_{old_handle.lower()}.json"
            old_proc_path = USERS_DATA_DIR / current_user.id / "processed" / f"codechef_{old_handle.lower()}.json"
            if old_raw_path.exists():
                try: old_raw_path.unlink()
                except Exception: pass
            if old_proc_path.exists():
                try: old_proc_path.unlink()
                except Exception: pass

            profile.handle = clean_handle
    else:
        profile = PlatformProfile(
            user_id=current_user.id,
            platform="codechef",
            handle=clean_handle,
        )
        db.add(profile)

    db.commit()
    db.refresh(profile)

    total_subs = (
        db.query(SubmissionRecord)
        .filter(
            SubmissionRecord.user_id == current_user.id,
            SubmissionRecord.platform == "codechef",
        )
        .count()
    )

    return ProfileStatusResponse(
        platform="codechef",
        handle=profile.handle,
        connected_at=profile.created_at,
        total_submissions_synced=total_subs,
        has_api_credentials=False,
    )


@app.post("/api/platforms/codechef/sync", response_model=SyncResponse)
def sync_codechef_submissions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(PlatformProfile)
        .filter(
            PlatformProfile.user_id == current_user.id,
            PlatformProfile.platform == "codechef",
        )
        .first()
    )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please connect a CodeChef username first before syncing.",
        )

    existing_sub_ids = set(
        row[0]
        for row in db.query(SubmissionRecord.submission_id)
        .filter(
            SubmissionRecord.user_id == current_user.id,
            SubmissionRecord.platform == "codechef",
        )
        .all()
    )

    collector = CodeChefCollector()
    try:
        raw_data = collector.fetch_submissions(profile.handle, user_id=current_user.id, existing_sub_ids=existing_sub_ids)
    except CodeChefRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="CodeChef temporarily rate-limited this request. Please try again after a short wait.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch submissions from CodeChef: {exc}",
        )

    normalized_list = normalize_codechef_submissions(raw_data, user_id=current_user.id)

    existing_db_ids = set(
        row[0]
        for row in db.query(SubmissionRecord.id)
        .filter(
            SubmissionRecord.user_id == current_user.id,
            SubmissionRecord.platform == "codechef",
        )
        .all()
    )

    new_records = []
    for sub in normalized_list:
        db_sub_id = f"{current_user.id}_{sub.id}"
        if db_sub_id not in existing_db_ids:
            record = SubmissionRecord(
                id=db_sub_id,
                user_id=current_user.id,
                platform="codechef",
                problem_id=sub.problem_id,
                problem_title=sub.problem_title,
                problem_url=sub.problem_url,
                submission_id=sub.submission_id,
                submission_url=sub.submission_url,
                language=sub.language,
                verdict=sub.verdict,
                submitted_at=sub.submitted_at,
                code=sub.code,
                code_source=sub.code_source,
            )
            db.add(record)
            existing_db_ids.add(db_sub_id)
            new_records.append(record)

    db.commit()

    return SyncResponse(
        platform="codechef",
        handle=profile.handle,
        fetched_count=len(normalized_list),
        new_synced_count=len(new_records),
        message=f"Successfully synced {len(new_records)} new submissions for CodeChef user '{profile.handle}'.",
    )


# -----------------------------------------------------------------------------
# GITHUB REPOSITORY INTEGRATION ENDPOINTS (USER-SCOPED)
# -----------------------------------------------------------------------------

@app.post("/api/platforms/github/connect", response_model=ProfileStatusResponse)
def connect_github_repository(
    req: ConnectGitHubRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Connect a GitHub repository to the authenticated user's account.
    Validates URL format, accessibility via GitHub API, and handles private/public repos.
    """
    try:
        owner, repo = parse_github_repo_url(req.repo_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    full_repo = f"{owner}/{repo}"
    token = req.access_token.strip() if req.access_token else None

    collector = GitHubCollector(access_token=token)
    try:
        collector.validate_repository(full_repo, token=token)
    except GitHubRepoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except GitHubAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )
    except GitHubRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        )
    except GitHubAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to access GitHub repository '{full_repo}': {exc}",
        )

    profile = (
        db.query(PlatformProfile)
        .filter(
            PlatformProfile.user_id == current_user.id,
            PlatformProfile.platform == "github",
        )
        .first()
    )

    if profile:
        profile.handle = full_repo
        profile.api_key = token
    else:
        profile = PlatformProfile(
            user_id=current_user.id,
            platform="github",
            handle=full_repo,
            api_key=token,
        )
        db.add(profile)

    db.commit()
    db.refresh(profile)

    total_subs = (
        db.query(SubmissionRecord)
        .filter(
            SubmissionRecord.user_id == current_user.id,
            SubmissionRecord.code_source == "github_lookup",
        )
        .count()
    )

    return ProfileStatusResponse(
        platform="github",
        handle=profile.handle,
        connected_at=profile.created_at,
        total_submissions_synced=total_subs,
        has_api_credentials=bool(profile.api_key),
    )


@app.get("/api/platforms/github/status", response_model=ProfileStatusResponse)
def get_github_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve GitHub repository connection status for the authenticated user."""
    profile = (
        db.query(PlatformProfile)
        .filter(
            PlatformProfile.user_id == current_user.id,
            PlatformProfile.platform == "github",
        )
        .first()
    )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GitHub repository connected for this user.",
        )

    total_subs = (
        db.query(SubmissionRecord)
        .filter(
            SubmissionRecord.user_id == current_user.id,
            SubmissionRecord.code_source == "github_lookup",
        )
        .count()
    )

    return ProfileStatusResponse(
        platform="github",
        handle=profile.handle,
        connected_at=profile.created_at,
        total_submissions_synced=total_subs,
        has_api_credentials=bool(profile.api_key),
    )


@app.delete("/api/platforms/github/disconnect")
def disconnect_github_repository(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Disconnect GitHub repository for the authenticated user.
    Strictly scoped to current_user.
    """
    profile = (
        db.query(PlatformProfile)
        .filter(
            PlatformProfile.user_id == current_user.id,
            PlatformProfile.platform == "github",
        )
        .first()
    )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GitHub repository connected for this user.",
        )

    db.delete(profile)
    db.commit()

    return {"message": "GitHub repository disconnected successfully."}



@app.get("/api/platforms/status", response_model=List[ProfileStatusResponse])
def get_all_platform_statuses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profiles = (
        db.query(PlatformProfile)
        .filter(PlatformProfile.user_id == current_user.id)
        .all()
    )

    res = []
    for p in profiles:
        if p.platform == "github":
            total_subs = (
                db.query(SubmissionRecord)
                .filter(
                    SubmissionRecord.user_id == current_user.id,
                    SubmissionRecord.code_source == "github_lookup",
                )
                .count()
            )
        else:
            total_subs = (
                db.query(SubmissionRecord)
                .filter(
                    SubmissionRecord.user_id == current_user.id,
                    SubmissionRecord.platform == p.platform,
                )
                .count()
            )
        res.append(
            ProfileStatusResponse(
                platform=p.platform,
                handle=p.handle,
                connected_at=p.created_at,
                total_submissions_synced=total_subs,
                has_api_credentials=bool(p.api_key) if p.platform == "github" else bool(p.api_key and p.api_secret),
            )
        )

    return res



# -----------------------------------------------------------------------------
# PUBLIC / FRIEND PROFILE SEARCH ENDPOINT (TRANSIENT, NON-PERSISTED)
# -----------------------------------------------------------------------------

@app.post("/api/public-profiles/search", response_model=PublicProfileSearchResponse)
def search_public_profile(
    req: PublicProfileSearchRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Search and retrieve public profile information for a user/friend on Codeforces, LeetCode, or CodeChef.
    TRANSIENT ONLY: Results are returned for viewing and are NEVER saved to PlatformProfile,
    SubmissionRecord, SubmissionSourceCode, or ChromaDB. Does not affect personal dashboard stats or RAG context.
    """
    plat = req.platform.lower().strip()
    clean_username = req.username.strip()

    if not clean_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username cannot be empty.",
        )

    if plat == "codeforces":
        collector = CodeforcesCollector()
        try:
            raw = collector.fetch_submissions(clean_username, count=20, user_id=None)
            normalized = normalize_codeforces_submissions(raw)
            recent_act = [
                {
                    "problem_title": s.problem_title,
                    "problem_url": s.problem_url,
                    "verdict": s.verdict,
                    "language": s.language,
                    "submitted_at": s.submitted_at,
                }
                for s in normalized[:10]
            ]
            return PublicProfileSearchResponse(
                platform="codeforces",
                username=clean_username,
                is_valid=True,
                title_or_name=f"Codeforces handle '{clean_username}'",
                rank_or_rating=None,
                total_solved=len(normalized),
                recent_activity=recent_act,
                message=f"Public profile found for Codeforces handle '{clean_username}'.",
            )
        except CodeforcesUserNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Codeforces handle '{clean_username}' not found.",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Codeforces search error: {exc}",
            )

    elif plat == "leetcode":
        collector = LeetCodeCollector()
        try:
            raw = collector.fetch_submissions(clean_username, count=20, user_id=None)
            data_body = raw.get("data") or {}
            matched_user = data_body.get("matchedUser") or {}
            profile_info = matched_user.get("profile") or {}
            real_name = profile_info.get("realName") or matched_user.get("username") or clean_username
            ranking = profile_info.get("ranking")
            rank_str = f"Rank: {ranking}" if ranking else None

            normalized = normalize_leetcode_submissions(raw)
            recent_act = [
                {
                    "problem_title": s.problem_title,
                    "problem_url": s.problem_url,
                    "verdict": s.verdict,
                    "language": s.language,
                    "submitted_at": s.submitted_at,
                }
                for s in normalized[:10]
            ]
            return PublicProfileSearchResponse(
                platform="leetcode",
                username=clean_username,
                is_valid=True,
                title_or_name=real_name,
                rank_or_rating=rank_str,
                total_solved=len(normalized),
                recent_activity=recent_act,
                message=f"Public profile found for LeetCode user '{clean_username}'.",
            )
        except LeetCodeUserNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LeetCode username '{clean_username}' not found.",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LeetCode search error: {exc}",
            )

    elif plat == "codechef":
        collector = CodeChefCollector()
        try:
            pub_data = collector.fetch_public_profile(clean_username)
            return PublicProfileSearchResponse(
                platform="codechef",
                username=pub_data.get("username", clean_username),
                is_valid=True,
                title_or_name=pub_data.get("title_or_name"),
                rank_or_rating=pub_data.get("rank_or_rating"),
                total_solved=pub_data.get("total_solved", 0),
                recent_activity=pub_data.get("recent_activity", []),
                message=pub_data.get("message", f"Public profile found for CodeChef user '{clean_username}'."),
            )
        except CodeChefUserNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"CodeChef username '{clean_username}' not found.",
            )
        except CodeChefRateLimitError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="CodeChef temporarily rate-limited this request. Please try again after a short wait.",
            )
        except CodeChefAPIError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"CodeChef search error: {exc}",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"CodeChef search error: {exc}",
            )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported platform '{plat}'. Supported platforms: codeforces, leetcode, codechef.",
        )


# -----------------------------------------------------------------------------
# USER SUBMISSIONS QUERY ENDPOINTS (USER-SCOPED)
# -----------------------------------------------------------------------------

@app.get("/api/submissions", response_model=List[SubmissionResponse])
def get_user_submissions(
    platform: Optional[str] = Query(None, description="Filter by platform ('codeforces', 'leetcode', 'codechef', 'all')"),
    verdict: Optional[str] = Query(None, description="Filter by verdict ('ACCEPTED', 'WRONG_ANSWER')"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve submission history strictly belonging to the authenticated user.
    Never returns another user's submissions. Supports filtering by platform.
    """
    query = db.query(SubmissionRecord).filter(SubmissionRecord.user_id == current_user.id)

    if platform and platform.lower() != "all":
        query = query.filter(SubmissionRecord.platform == platform.lower())
    if verdict:
        query = query.filter(SubmissionRecord.verdict == verdict.upper())

    submissions = query.order_by(SubmissionRecord.submitted_at.desc()).offset(offset).limit(limit).all()
    return [SubmissionResponse.model_validate(sub) for sub in submissions]


@app.get("/api/stats")
def get_user_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return per-platform statistics and metrics for the authenticated user.
    """
    subs = db.query(SubmissionRecord).filter(SubmissionRecord.user_id == current_user.id).all()
    codeforces_count = sum(1 for s in subs if s.platform == "codeforces")
    leetcode_count = sum(1 for s in subs if s.platform == "leetcode")
    codechef_count = sum(1 for s in subs if s.platform == "codechef")

    with_code_count = sum(1 for s in subs if s.has_source_code)
    metadata_only_count = sum(1 for s in subs if not s.has_source_code)

    tag_counts = {}
    for s in subs:
        if s.tags:
            for t in s.tags:
                tag_counts[t] = tag_counts.get(t, 0) + 1
    top_topics = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "total_submissions": len(subs),
        "codeforces_count": codeforces_count,
        "leetcode_count": leetcode_count,
        "codechef_count": codechef_count,
        "with_source_code_count": with_code_count,
        "metadata_only_count": metadata_only_count,
        "top_topics": [{"tag": k, "count": v} for k, v in top_topics],
    }




# -----------------------------------------------------------------------------
# PHASE 3: SOURCE CODE IMPORT & STORAGE ENDPOINTS (USER-SCOPED)
# -----------------------------------------------------------------------------

def _validate_submission_ownership(
    submission_id: str, current_user_id: str, db: Session
) -> SubmissionRecord:
    """Helper to check submission existence and user ownership."""
    submission = db.query(SubmissionRecord).filter(SubmissionRecord.id == submission_id).first()
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission '{submission_id}' not found.",
        )
    if submission.user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access or modify this submission.",
        )
    return submission


@app.post(
    "/api/submissions/{submission_id}/source-code",
    response_model=SourceCodeResponse,
    status_code=status.HTTP_201_CREATED,
)

@app.put(
    "/api/submissions/{submission_id}/source-code",
    response_model=SourceCodeResponse,
)
def save_or_update_source_code_json(
    submission_id: str,
    req: AddSourceCodeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add or update source code text for an existing submission via JSON payload."""
    submission = _validate_submission_ownership(submission_id, current_user.id, db)

    raw_code = req.source_code.strip()
    if not raw_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source code text cannot be empty.",
        )

    code_bytes = len(raw_code.encode("utf-8"))
    if code_bytes > MAX_SOURCE_CODE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source code size ({code_bytes / 1024:.1f} KB) exceeds maximum allowed limit (500 KB).",
        )

    language = req.language or submission.language

    source_record = (
        db.query(SubmissionSourceCode)
        .filter(
            SubmissionSourceCode.submission_id == submission_id,
            SubmissionSourceCode.user_id == current_user.id,
        )
        .first()
    )

    if source_record:
        source_record.source_code = raw_code
        source_record.language = language
        if req.filename is not None:
            source_record.filename = req.filename
    else:
        source_record = SubmissionSourceCode(
            user_id=current_user.id,
            submission_id=submission_id,
            language=language,
            source_code=raw_code,
            filename=req.filename,
        )
        db.add(source_record)

    submission.code = raw_code
    submission.code_source = "user_upload"
    submission.language = language

    db.commit()
    db.refresh(source_record)
    db.refresh(submission)

    # Automatically re-index submission into ChromaDB with attached source code
    try:
        index_submission_for_user(user_id=current_user.id, submission_id=submission.submission_id, db=db)
    except Exception as e:
        logger.warning(f"Auto-indexing submission '{submission.submission_id}' failed: {e}")

    return SourceCodeResponse.model_validate(source_record)


@app.post(
    "/api/submissions/{submission_id}/upload-source-code",
    response_model=SourceCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_source_code_file(
    submission_id: str,
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a source code file (.cpp, .py, .java, .js, .ts, etc.) for a submission."""
    submission = _validate_submission_ownership(submission_id, current_user.id, db)

    filename = file.filename or "solution"
    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content_bytes = await file.read()
    if not content_bytes or not content_bytes.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if len(content_bytes) > MAX_SOURCE_CODE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded file size ({len(content_bytes) / 1024:.1f} KB) exceeds maximum allowed limit (500 KB).",
        )

    try:
        raw_code = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content could not be decoded as UTF-8 text.",
        )

    detected_lang = language or detect_language_from_filename(filename)
    if detected_lang == "unknown":
        detected_lang = submission.language

    source_record = (
        db.query(SubmissionSourceCode)
        .filter(
            SubmissionSourceCode.submission_id == submission_id,
            SubmissionSourceCode.user_id == current_user.id,
        )
        .first()
    )

    if source_record:
        source_record.source_code = raw_code
        source_record.language = detected_lang
        source_record.filename = filename
    else:
        source_record = SubmissionSourceCode(
            user_id=current_user.id,
            submission_id=submission_id,
            language=detected_lang,
            source_code=raw_code,
            filename=filename,
        )
        db.add(source_record)

    submission.code = raw_code
    submission.code_source = "user_upload"
    submission.language = detected_lang

    db.commit()
    db.refresh(source_record)
    db.refresh(submission)

    # Automatically re-index submission into ChromaDB with attached source code
    try:
        index_submission_for_user(user_id=current_user.id, submission_id=submission.submission_id, db=db)
    except Exception as e:
        logger.warning(f"Auto-indexing submission '{submission.submission_id}' failed: {e}")

    return SourceCodeResponse.model_validate(source_record)


@app.get(
    "/api/submissions/{submission_id}/source-code",
    response_model=SourceCodeResponse,
)
def get_submission_source_code(
    submission_id: str,
    file_path: Optional[str] = Query(None, description="Specific GitHub solution file path to view"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve saved source code record for a submission belonging to authenticated user.
    If source code is unavailable, dynamically look up the connected user's GitHub repository.
    If a reliable match is found, fetch, cache, and return the actual source code with GitHub link.
    If no reliable match is found, return 404 (Source Code Unavailable).
    """
    # 1. Attempt to locate submission in relational database
    submission = db.query(SubmissionRecord).filter(SubmissionRecord.id == submission_id).first()
    if submission:
        if submission.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access or modify this submission.",
            )
    else:
        # Check if this is an indexed standalone GitHub document belonging to the user
        chroma_store = get_chroma_store()
        res = None
        try:
            res = chroma_store._collection.get(
                where={"$and": [{"user_id": str(current_user.id)}, {"submission_id": str(submission_id)}]}
            )
        except Exception as e:
            logger.warning(f"ChromaDB lookup for standalone submission '{submission_id}' failed: {e}")

        if res and res.get("metadatas") and len(res["metadatas"]) > 0:
            meta = res["metadatas"][0]
            docs = res.get("documents", [])
            full_doc = "\n".join(docs) if docs else ""

            code_text = ""
            code_match = re.search(r"## Source Code\s*```[a-zA-Z0-9_\-]*\n([\s\S]*?)```", full_doc)
            if code_match:
                code_text = code_match.group(1).strip()
            elif docs:
                code_text = docs[0]

            gh_url = None
            notes_match = re.search(r"\*\*Notes\*\*:\s*Synced from GitHub repo ([^:\n]+):\s*([^\n]+)", full_doc)
            filename = None
            if notes_match:
                repo_name = notes_match.group(1).strip()
                file_subpath = notes_match.group(2).strip()
                gh_url = f"https://github.com/{repo_name}/blob/main/{file_subpath}"
                filename = Path(file_subpath).name

            if not code_text:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Source Code Unavailable",
                )

            now = datetime.now(timezone.utc)
            return SourceCodeResponse(
                id=f"src_{submission_id}",
                user_id=current_user.id,
                submission_id=submission_id,
                language=meta.get("language") or "cpp",
                source_code=code_text,
                filename=filename or f"{meta.get('problem_id', 'solution')}.{meta.get('language', 'cpp')}",
                created_at=now,
                updated_at=now,
                github_url=gh_url,
                available_solutions=[],
            )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission '{submission_id}' not found.",
        )

    source_record = (
        db.query(SubmissionSourceCode)
        .filter(
            SubmissionSourceCode.submission_id == submission_id,
            SubmissionSourceCode.user_id == current_user.id,
        )
        .first()
    )

    gh_profile = (
        db.query(PlatformProfile)
        .filter(
            PlatformProfile.user_id == current_user.id,
            PlatformProfile.platform == "github",
        )
        .first()
    )

    # 1. If user requested a specific file path from connected GitHub repository
    if file_path and gh_profile:
        collector = GitHubCollector(access_token=gh_profile.api_key)
        matched_solution = collector.lookup_solution(
            repo_handle=gh_profile.handle,
            token=gh_profile.api_key,
            problem_title=submission.problem_title,
            problem_slug=submission.problem_id,
            problem_id=submission.problem_id,
            preferred_language=submission.language,
            target_file_path=file_path,
        )
        if matched_solution:
            now = datetime.now(timezone.utc)
            return SourceCodeResponse(
                id=source_record.id if source_record else f"src_{submission.id}",
                user_id=current_user.id,
                submission_id=submission.id,
                language=matched_solution["language"],
                source_code=matched_solution["code"],
                filename=matched_solution["filename"],
                created_at=source_record.created_at if source_record else now,
                updated_at=source_record.updated_at if source_record else now,
                github_url=matched_solution["url"],
                available_solutions=matched_solution.get("available_solutions", []),
            )

    # 2. If genuine source code is already stored in SubmissionSourceCode, return it
    if source_record and source_record.source_code and not source_record.source_code.startswith("// Source code not provided"):
        gh_url = None
        if submission.notes and submission.notes.startswith("GitHub: "):
            gh_url = submission.notes[len("GitHub: "):].strip()
        resp = SourceCodeResponse.model_validate(source_record)
        resp.github_url = gh_url
        return resp

    # 2b. If genuine source code is already stored in submission.code, return it
    if submission.has_source_code:
        gh_url = None
        if submission.notes and submission.notes.startswith("GitHub: "):
            gh_url = submission.notes[len("GitHub: "):].strip()
        now = datetime.now(timezone.utc)
        return SourceCodeResponse(
            id=source_record.id if source_record else f"src_{submission.id}",
            user_id=current_user.id,
            submission_id=submission.id,
            language=submission.language,
            source_code=submission.code,
            filename=source_record.filename if source_record else None,
            created_at=source_record.created_at if source_record else now,
            updated_at=source_record.updated_at if source_record else now,
            github_url=gh_url,
        )

    # 3. If source code is unavailable, dynamically look up user's connected GitHub repository
    if gh_profile:
        collector = GitHubCollector(access_token=gh_profile.api_key)
        try:
            matched_solution = collector.lookup_solution(
                repo_handle=gh_profile.handle,
                token=gh_profile.api_key,
                problem_title=submission.problem_title,
                problem_slug=submission.problem_id,
                problem_id=submission.problem_id,
                preferred_language=submission.language,
            )
        except TypeError:
            matched_solution = collector.lookup_solution(
                repo_handle=gh_profile.handle,
                token=gh_profile.api_key,
                problem_title=submission.problem_title,
                problem_slug=submission.problem_id,
                problem_id=submission.problem_id,
            )

        if matched_solution:
            code_text = matched_solution["code"]
            lang = matched_solution["language"]
            filename = matched_solution["filename"]
            gh_url = matched_solution["url"]
            available_sols = matched_solution.get("available_solutions", [])

            if source_record:
                source_record.source_code = code_text
                source_record.language = lang
                source_record.filename = filename
            else:
                source_record = SubmissionSourceCode(
                    user_id=current_user.id,
                    submission_id=submission_id,
                    language=lang,
                    source_code=code_text,
                    filename=filename,
                )
                db.add(source_record)

            submission.code = code_text
            submission.code_source = "github_lookup"
            submission.language = lang
            submission.notes = f"GitHub: {gh_url}"

            db.commit()
            db.refresh(source_record)
            db.refresh(submission)

            # Automatically index new code into ChromaDB vector store
            try:
                index_submission_for_user(user_id=current_user.id, submission_id=submission.submission_id, db=db)
            except Exception as e:
                logger.warning(f"Auto-indexing submission '{submission.submission_id}' from GitHub lookup failed: {e}")

            resp = SourceCodeResponse.model_validate(source_record)
            resp.github_url = gh_url
            resp.available_solutions = available_sols
            return resp

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Source Code Unavailable",
    )



# -----------------------------------------------------------------------------
# PHASE 4: VECTOR INDEXING & SEMANTIC SEARCH ENDPOINTS (USER-SCOPED)
# -----------------------------------------------------------------------------

@app.post(
    "/api/vector/index/{submission_id}",
    response_model=IndexingResponse,
    status_code=status.HTTP_200_OK,
)
def index_submission(
    submission_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Index a single submission with source code into ChromaDB vector store for the current user.
    """
    res = index_submission_for_user(user_id=current_user.id, submission_id=submission_id, db=db)
    return IndexingResponse(**res)


@app.post(
    "/api/vector/index-all",
    response_model=BulkIndexingResponse,
    status_code=status.HTTP_200_OK,
)
def index_all_submissions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Index all submissions possession source code for the current user into ChromaDB.
    """
    res = index_all_user_submissions(user_id=current_user.id, db=db)
    return BulkIndexingResponse(**res)


@app.get("/api/vector/index-status")
def get_index_status(current_user: User = Depends(get_current_user)):
    """
    Return live indexing progress status for the authenticated user.
    """
    return get_indexing_progress(current_user.id)


@app.post(
    "/api/vector/search",
    response_model=SearchQueryResponse,
    status_code=status.HTTP_200_OK,
)
def search_knowledge(
    req: SearchQueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Perform natural language semantic vector search over the current user's indexed code knowledge.
    Only returns results that meet or exceed the relevance similarity threshold.
    """
    top_k = req.top_k or 20
    kwargs = {"user_id": current_user.id, "query": req.query, "top_k": top_k, "db": db}
    if req.min_similarity is not None:
        kwargs["min_similarity"] = req.min_similarity
    res = search_user_knowledge(**kwargs)
    return SearchQueryResponse(**res)


# -----------------------------------------------------------------------------
# PHASE 5: RAG ANSWER GENERATION ENDPOINT (USER-SCOPED)
# -----------------------------------------------------------------------------

@app.post(
    "/api/rag/query",
    response_model=RAGQueryResponse,
    status_code=status.HTTP_200_OK,
)
def rag_query(
    req: RAGQueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Execute grounded RAG answer generation over the authenticated user's retrieved submission context.
    Retrieved context is strictly isolated to current_user.id.
    """
    top_k = req.top_k or 10
    try:
        res = execute_rag_pipeline(user_id=current_user.id, query=req.query, top_k=top_k, db=db)
        return RAGQueryResponse(**res)
    except LLMServiceError as exc:
        logger.error(f"LLMServiceError in /api/rag/query for user '{current_user.id}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Knowledge Chat Error: {str(exc)}",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Unexpected error in /api/rag/query for user '{current_user.id}': {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Knowledge Chat failed due to an unexpected server error: {str(exc)}",
        )


