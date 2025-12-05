"""Git repository connector for extracting commit history and file changes."""

import logging
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import git
from git import Repo

from src.models.documents import GitCommitDocument, GitFileChange

logger = logging.getLogger(__name__)


class GitConnector:
    """Connector for cloning Git repositories and extracting commit history.

    Focuses on Terraform-related changes (*.tf, *.tfvars, *.tfstate, etc.)
    and extracts detailed file change information.
    """

    # File patterns to track for infrastructure changes
    TERRAFORM_PATTERNS = [
        r"\.tf$",
        r"\.tfvars$",
        r"\.tfstate$",
        r"\.tfstate\.backup$",
    ]

    # Additional infrastructure patterns
    INFRA_PATTERNS = [
        r"\.bicep$",
        r"\.json$",  # May include ARM templates
        r"\.yaml$",
        r"\.yml$",
    ]

    def __init__(
        self,
        track_terraform_only: bool = True,
        track_additional_infra: bool = False,
    ):
        """Initialize the Git connector.

        Args:
            track_terraform_only: If True, only track Terraform files
            track_additional_infra: If True, also track Bicep, ARM templates, etc.
        """
        self.track_terraform_only = track_terraform_only
        self.track_additional_infra = track_additional_infra

        # Compile regex patterns
        self.patterns = [re.compile(p) for p in self.TERRAFORM_PATTERNS]
        if track_additional_infra:
            self.patterns.extend([re.compile(p) for p in self.INFRA_PATTERNS])

    def clone_repository(
        self,
        repo_url: str,
        target_dir: Path | None = None,
        branch: str | None = None,
        auth_token: str | None = None,
    ) -> Repo:
        """Clone a Git repository to a local directory.

        Args:
            repo_url: URL of the Git repository
            target_dir: Directory to clone into (uses temp dir if None)
            branch: Specific branch to clone (uses default if None)
            auth_token: Personal access token for authentication

        Returns:
            GitPython Repo object

        Raises:
            git.GitCommandError: If clone fails
        """
        # Inject auth token into URL if provided
        if auth_token:
            repo_url = self._inject_auth_token(repo_url, auth_token)

        # Use temp directory if not specified
        if target_dir is None:
            target_dir = Path(tempfile.mkdtemp(prefix="git_clone_"))
        else:
            target_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Cloning repository {repo_url} to {target_dir}")

        # Clone with optional branch
        if branch:
            repo = Repo.clone_from(repo_url, target_dir, branch=branch)
        else:
            repo = Repo.clone_from(repo_url, target_dir)

        logger.info(f"Successfully cloned {repo_url}")
        return repo

    def _inject_auth_token(self, repo_url: str, token: str) -> str:
        """Inject authentication token into repository URL.

        Args:
            repo_url: Original repository URL
            token: Personal access token

        Returns:
            URL with embedded token
        """
        parsed = urlparse(repo_url)

        # For HTTPS URLs, inject token as username
        if parsed.scheme in ("https", "http"):
            netloc = f"{token}@{parsed.netloc}"
            return parsed._replace(netloc=netloc).geturl()

        # For other schemes, return as-is
        return repo_url

    async def extract_commits(
        self,
        repo: Repo,
        branch: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        author: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Extract commit history from a repository.

        Args:
            repo: GitPython Repo object
            branch: Branch to extract commits from (uses current if None)
            since: Only commits after this date
            until: Only commits before this date
            author: Filter by author name/email

        Yields:
            Commit dictionaries with metadata and file changes
        """
        # Switch to specified branch if needed
        if branch and repo.active_branch.name != branch:
            repo.git.checkout(branch)

        # Build filter kwargs
        kwargs: dict[str, Any] = {}
        if since:
            kwargs["since"] = since
        if until:
            kwargs["until"] = until
        if author:
            kwargs["author"] = author

        # Iterate commits
        for commit in repo.iter_commits(**kwargs):
            # Extract file changes
            file_changes = self._extract_file_changes(commit, repo)

            # Skip commits with no relevant file changes
            if self.track_terraform_only and not file_changes:
                continue

            # Split message into subject and body
            message_lines = commit.message.strip().split("\n", 1)
            message_subject = message_lines[0]
            message_body = message_lines[1].strip() if len(message_lines) > 1 else ""

            commit_dict = {
                "sha": commit.hexsha,
                "short_sha": commit.hexsha[:7],
                "author_name": commit.author.name,
                "author_email": commit.author.email,
                "author_date": datetime.fromtimestamp(commit.authored_date),
                "committer_name": commit.committer.name,
                "committer_email": commit.committer.email,
                "commit_date": datetime.fromtimestamp(commit.committed_date),
                "message": commit.message.strip(),
                "message_subject": message_subject,
                "message_body": message_body,
                "file_changes": file_changes,
            }

            yield commit_dict

    def _extract_file_changes(
        self, commit: git.Commit, repo: Repo
    ) -> list[dict[str, Any]]:
        """Extract file changes from a commit.

        Args:
            commit: Git commit object
            repo: Repository object

        Returns:
            List of file change dictionaries
        """
        changes = []

        # Handle initial commit (no parents)
        if not commit.parents:
            # All files are additions
            for item in commit.tree.traverse():
                if item.type == "blob":  # Files only, not trees
                    path = item.path
                    if self._should_track_file(path):
                        changes.append({
                            "path": path,
                            "change_type": "add",
                            "old_path": None,
                            "additions": 0,  # Can't compute without parent
                            "deletions": 0,
                        })
            return changes

        # Compare with first parent
        parent = commit.parents[0]
        diffs = parent.diff(commit, create_patch=True)

        for diff in diffs:
            # Get file path (handle renames)
            old_path = None
            if diff.renamed_file:
                path = diff.rename_to
                old_path = diff.rename_from
                change_type = "rename"
            elif diff.deleted_file:
                path = diff.a_path
                change_type = "delete"
            elif diff.new_file:
                path = diff.b_path
                change_type = "add"
            else:
                path = diff.b_path or diff.a_path
                change_type = "modify"

            # Filter by file patterns
            if not self._should_track_file(path):
                continue

            # Extract diff stats
            additions = 0
            deletions = 0

            try:
                # Get diff text and count additions/deletions
                if diff.diff:
                    diff_text = diff.diff.decode("utf-8", errors="replace")

                    # Count additions/deletions from diff
                    for line in diff_text.split("\n"):
                        if line.startswith("+") and not line.startswith("+++"):
                            additions += 1
                        elif line.startswith("-") and not line.startswith("---"):
                            deletions += 1
            except Exception as e:
                logger.warning(f"Failed to extract diff for {path}: {e}")

            changes.append({
                "path": path,
                "change_type": change_type,
                "old_path": old_path,
                "additions": additions,
                "deletions": deletions,
            })

        return changes

    def _should_track_file(self, file_path: str) -> bool:
        """Check if a file should be tracked based on patterns.

        Args:
            file_path: Path to the file

        Returns:
            True if file matches tracking patterns
        """
        return any(pattern.search(file_path) for pattern in self.patterns)

    async def convert_to_document(
        self,
        commit_dict: dict[str, Any],
        repo_url: str,
        branch: str,
    ) -> GitCommitDocument:
        """Convert commit dictionary to GitCommitDocument.

        Args:
            commit_dict: Commit data from extract_commits()
            repo_url: Repository URL
            branch: Branch name

        Returns:
            GitCommitDocument instance
        """
        # Convert file changes to GitFileChange objects
        file_changes = [
            GitFileChange(
                path=fc["path"],
                change_type=fc["change_type"],
                old_path=fc.get("old_path"),
                additions=fc["additions"],
                deletions=fc["deletions"],
            )
            for fc in commit_dict["file_changes"]
        ]

        # Calculate totals
        total_additions = sum(fc["additions"] for fc in commit_dict["file_changes"])
        total_deletions = sum(fc["deletions"] for fc in commit_dict["file_changes"])

        # Identify Terraform files
        terraform_files = [
            fc["path"]
            for fc in commit_dict["file_changes"]
            if self._should_track_file(fc["path"])
        ]

        # Create document
        doc = GitCommitDocument(
            id=commit_dict["sha"],
            sha=commit_dict["sha"],
            short_sha=commit_dict["short_sha"],
            repo_url=repo_url,
            branch=branch,
            message=commit_dict["message"],
            message_subject=commit_dict["message_subject"],
            message_body=commit_dict["message_body"],
            author_name=commit_dict["author_name"],
            author_email=commit_dict["author_email"],
            author_date=commit_dict["author_date"],
            committer_name=commit_dict["committer_name"],
            committer_email=commit_dict["committer_email"],
            commit_date=commit_dict["commit_date"],
            files_changed=file_changes,
            total_additions=total_additions,
            total_deletions=total_deletions,
            terraform_files_changed=terraform_files,
            has_terraform_changes=len(terraform_files) > 0,
        )

        return doc

    async def fetch_all_commits(
        self,
        repo_url: str,
        branch: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        author: str | None = None,
        auth_token: str | None = None,
        local_path: Path | None = None,
    ) -> AsyncIterator[GitCommitDocument]:
        """Fetch all commits from a repository.

        Convenience method that clones, extracts, and converts commits.

        Args:
            repo_url: Repository URL
            branch: Branch to extract from
            since: Only commits after this date
            until: Only commits before this date
            author: Filter by author
            auth_token: Authentication token
            local_path: Local clone path (uses temp if None)

        Yields:
            GitCommitDocument instances
        """
        # Clone repository
        repo = self.clone_repository(
            repo_url=repo_url,
            target_dir=local_path,
            branch=branch,
            auth_token=auth_token,
        )

        try:
            # Extract commits
            async for commit_dict in self.extract_commits(
                repo=repo,
                branch=branch,
                since=since,
                until=until,
                author=author,
            ):
                # Convert to document
                doc = await self.convert_to_document(
                    commit_dict=commit_dict,
                    repo_url=repo_url,
                    branch=branch or repo.active_branch.name,
                )
                yield doc
        finally:
            # Cleanup repo if using temp directory
            if local_path is None:
                import shutil
                shutil.rmtree(repo.working_dir, ignore_errors=True)
