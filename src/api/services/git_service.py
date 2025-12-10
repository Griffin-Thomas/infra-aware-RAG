"""Git service for querying commit history."""

import logging
from datetime import datetime
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError

from src.api.models.git import FileChange, GitCommit

logger = logging.getLogger(__name__)


class GitService:
    """Service for Git commit operations."""

    def __init__(self, cosmos_client: CosmosClient, database_name: str, container_name: str):
        """Initialize Git service.

        Args:
            cosmos_client: Azure Cosmos DB client
            database_name: Database name
            container_name: Container name for documents
        """
        self.cosmos_client = cosmos_client
        self.database_name = database_name
        self.container_name = container_name
        self._container = None

    def _get_container(self):
        """Get Cosmos DB container (lazy initialization)."""
        if self._container is None:
            database = self.cosmos_client.get_database_client(self.database_name)
            self._container = database.get_container_client(self.container_name)
        return self._container

    async def list_commits(
        self,
        repo_url: str | None = None,
        author: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        terraform_only: bool = False,
        limit: int = 20,
    ) -> list[GitCommit]:
        """List Git commits with optional filters.

        Args:
            repo_url: Filter by repository URL
            author: Filter by author name or email
            since: Filter commits after this timestamp
            until: Filter commits before this timestamp
            terraform_only: Only include commits with Terraform changes
            limit: Maximum number of results

        Returns:
            List of Git commits
        """
        try:
            container = self._get_container()

            # Build query
            query = "SELECT * FROM c WHERE c.doc_type = 'git_commit'"
            params = []

            if repo_url:
                query += " AND c.repo_url = @repo_url"
                params.append({"name": "@repo_url", "value": repo_url})

            if author:
                query += " AND (c.author_name = @author OR c.author_email = @author)"
                params.append({"name": "@author", "value": author})

            if since:
                query += " AND c.commit_date >= @since"
                params.append({"name": "@since", "value": since.isoformat()})

            if until:
                query += " AND c.commit_date <= @until"
                params.append({"name": "@until", "value": until.isoformat()})

            if terraform_only:
                query += " AND c.has_terraform_changes = true"

            query += " ORDER BY c.commit_date DESC"

            # Execute query
            items = list(
                container.query_items(
                    query=query,
                    parameters=params,
                    max_item_count=limit,
                    enable_cross_partition_query=True,
                )
            )

            # Map to GitCommit models
            commits = []
            for item in items:
                commits.append(self._map_to_commit(item))

            return commits

        except CosmosHttpResponseError as e:
            logger.error(f"Failed to list commits: {e}")
            raise

    async def get_commit(self, sha: str, repo_url: str) -> GitCommit | None:
        """Get a specific Git commit.

        Args:
            sha: Commit SHA (full or short)
            repo_url: Repository URL

        Returns:
            Git commit or None if not found
        """
        try:
            container = self._get_container()

            # Query by SHA (support both full and short SHA)
            query = """
                SELECT * FROM c
                WHERE c.doc_type = 'git_commit'
                AND c.repo_url = @repo_url
                AND (c.sha = @sha OR c.short_sha = @sha)
            """

            params = [
                {"name": "@repo_url", "value": repo_url},
                {"name": "@sha", "value": sha},
            ]

            items = list(
                container.query_items(
                    query=query,
                    parameters=params,
                    enable_cross_partition_query=True,
                )
            )

            if not items:
                return None

            return self._map_to_commit(items[0])

        except CosmosHttpResponseError as e:
            logger.error(f"Failed to get commit: {e}")
            raise

    async def get_diff(
        self, sha: str, repo_url: str, file_path: str | None = None
    ) -> str | None:
        """Get the diff for a commit.

        Args:
            sha: Commit SHA
            repo_url: Repository URL
            file_path: Optional file path to filter diff

        Returns:
            Unified diff string or None if commit not found
        """
        commit = await self.get_commit(sha, repo_url)
        if not commit:
            return None

        try:
            container = self._get_container()

            # Get the full document which may have diff data
            query = """
                SELECT c.diff FROM c
                WHERE c.doc_type = 'git_commit'
                AND c.repo_url = @repo_url
                AND (c.sha = @sha OR c.short_sha = @sha)
            """

            params = [
                {"name": "@repo_url", "value": repo_url},
                {"name": "@sha", "value": sha},
            ]

            items = list(
                container.query_items(
                    query=query,
                    parameters=params,
                    enable_cross_partition_query=True,
                )
            )

            if not items or "diff" not in items[0]:
                # If no diff stored, return empty string
                return ""

            diff = items[0]["diff"]

            # Filter by file path if requested
            if file_path and diff:
                # Simple filter: look for the file in the diff
                lines = diff.split("\n")
                filtered_lines = []
                in_file = False

                for line in lines:
                    if line.startswith("diff --git"):
                        # Check if this is the file we want
                        in_file = file_path in line
                    if in_file:
                        filtered_lines.append(line)

                return "\n".join(filtered_lines) if filtered_lines else ""

            return diff

        except CosmosHttpResponseError as e:
            logger.error(f"Failed to get diff: {e}")
            raise

    def _map_to_commit(self, item: dict) -> GitCommit:
        """Map Cosmos DB item to GitCommit model.

        Args:
            item: Cosmos DB document

        Returns:
            GitCommit instance
        """
        # Extract file changes
        files_changed = []
        if "files_changed" in item:
            for fc in item["files_changed"]:
                files_changed.append(
                    FileChange(
                        path=fc["path"],
                        change_type=fc["change_type"],
                        additions=fc.get("additions", 0),
                        deletions=fc.get("deletions", 0),
                    )
                )

        return GitCommit(
            sha=item["sha"],
            short_sha=item.get("short_sha", item["sha"][:7]),
            repo_url=item["repo_url"],
            branch=item.get("branch", "main"),
            message=item.get("message", ""),
            author_name=item.get("author_name", "Unknown"),
            author_email=item.get("author_email", ""),
            commit_date=datetime.fromisoformat(item["commit_date"].replace("Z", "+00:00")),
            files_changed=files_changed,
            terraform_files=item.get("terraform_files", []),
            has_terraform_changes=item.get("has_terraform_changes", False),
        )
