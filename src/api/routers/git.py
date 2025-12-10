"""Git API router."""

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import get_git_service
from src.api.models.git import GitCommit
from src.api.services.git_service import GitService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/git", tags=["git"])


@router.get("/commits", response_model=list[GitCommit])
async def list_git_commits(
    repo_url: str | None = Query(default=None, description="Filter by repository URL"),
    author: str | None = Query(default=None, description="Filter by author name or email"),
    since: datetime | None = Query(default=None, description="Filter commits after this timestamp"),
    until: datetime | None = Query(default=None, description="Filter commits before this timestamp"),
    terraform_only: bool = Query(default=False, description="Only show commits with Terraform changes"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum number of results"),
    git_service: GitService = Depends(get_git_service),
):
    """
    List Git commits with optional filters.

    Returns a list of Git commits from your infrastructure repositories.

    **Filters:**
    - `repo_url`: Filter by repository
    - `author`: Filter by author name or email
    - `since/until`: Date range filter
    - `terraform_only`: Only show commits with Terraform changes

    **Use cases:**
    - "Show me recent infrastructure changes"
    - "Who modified the networking code last week?"
    - "What Terraform changes were made today?"
    """
    logger.info(
        f"Listing Git commits: repo_url={repo_url}, author={author}, "
        f"since={since}, until={until}, terraform_only={terraform_only}, limit={limit}"
    )

    try:
        commits = await git_service.list_commits(
            repo_url=repo_url,
            author=author,
            since=since,
            until=until,
            terraform_only=terraform_only,
            limit=limit,
        )

        logger.info(f"Found {len(commits)} Git commits")
        return commits

    except Exception as e:
        logger.error(f"Failed to list Git commits: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to list Git commits. Please try again later.",
        )


@router.get("/commits/{sha}", response_model=GitCommit)
async def get_git_commit(
    sha: str,
    repo_url: str = Query(..., description="Repository URL"),
    git_service: GitService = Depends(get_git_service),
):
    """
    Get full details for a Git commit.

    The SHA can be either the full commit SHA or the short SHA (first 7 characters).

    **Query parameters:**
    - `repo_url`: Required - Git repository URL to scope the search

    **Use cases:**
    - "Show me the details of commit abc1234"
    - "What files were changed in this commit?"
    - "Who made this commit and when?"
    """
    logger.info(f"Fetching Git commit: {sha} from {repo_url}")

    try:
        commit = await git_service.get_commit(sha, repo_url)

        if not commit:
            raise HTTPException(
                status_code=404,
                detail=f"Commit not found: {sha} in {repo_url}",
            )

        return commit

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch Git commit: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch Git commit. Please try again later.",
        )


@router.get("/commits/{sha}/diff")
async def get_commit_diff(
    sha: str,
    repo_url: str = Query(..., description="Repository URL"),
    file_path: str | None = Query(default=None, description="Optional file path to filter diff"),
    git_service: GitService = Depends(get_git_service),
):
    """
    Get the diff for a commit.

    Returns the unified diff output for the commit.
    Optionally filter to a specific file path.

    **Query parameters:**
    - `repo_url`: Required - Git repository URL
    - `file_path`: Optional - Filter diff to a specific file

    **Use cases:**
    - "Show me what changed in this commit"
    - "What did this commit change in main.tf?"
    - "Get the diff for commit xyz"
    """
    logger.info(f"Fetching diff for commit: {sha} from {repo_url}, file_path={file_path}")

    try:
        diff = await git_service.get_diff(sha, repo_url, file_path)

        if diff is None:
            raise HTTPException(
                status_code=404,
                detail=f"Commit not found: {sha} in {repo_url}",
            )

        return {"sha": sha, "repo_url": repo_url, "diff": diff}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch commit diff: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch commit diff. Please try again later.",
        )
