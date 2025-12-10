"""Unit tests for Git API router."""

import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from src.api.routers.git import router
from src.api.dependencies import get_git_service
from src.api.models.git import FileChange, GitCommit


@pytest.fixture
def mock_git_service():
    """Create mock GitService."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def app(mock_git_service):
    """Create a test FastAPI app with the git router."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    # Override the git service dependency
    test_app.dependency_overrides[get_git_service] = lambda: mock_git_service

    return test_app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def sample_commit():
    """Create sample GitCommit for testing."""
    return GitCommit(
        sha="abc123def456abc123def456abc123def456abc1",
        short_sha="abc123d",
        repo_url="https://github.com/example/infra",
        branch="main",
        message="Update network configuration",
        author_name="John Doe",
        author_email="john@example.com",
        commit_date=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        files_changed=[
            FileChange(
                path="network/main.tf",
                change_type="modify",
                additions=10,
                deletions=5,
            ),
            FileChange(
                path="network/variables.tf",
                change_type="modify",
                additions=2,
                deletions=1,
            ),
        ],
        terraform_files=["network/main.tf", "network/variables.tf"],
        has_terraform_changes=True,
    )


class TestListGitCommits:
    """Tests for GET /git/commits endpoint."""

    def test_list_commits_no_filters(self, client, mock_git_service, sample_commit):
        """Test listing commits without filters."""
        mock_git_service.list_commits.return_value = [sample_commit]

        response = client.get("/api/v1/git/commits")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["sha"] == "abc123def456abc123def456abc123def456abc1"
        assert data[0]["message"] == "Update network configuration"

        # Verify service was called with defaults
        mock_git_service.list_commits.assert_called_once()
        call_args = mock_git_service.list_commits.call_args
        assert call_args.kwargs["repo_url"] is None
        assert call_args.kwargs["limit"] == 20

    def test_list_commits_with_repo_filter(self, client, mock_git_service, sample_commit):
        """Test listing commits filtered by repository."""
        mock_git_service.list_commits.return_value = [sample_commit]

        response = client.get(
            "/api/v1/git/commits?repo_url=https://github.com/example/infra"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        # Verify filter was passed
        mock_git_service.list_commits.assert_called_once()
        call_args = mock_git_service.list_commits.call_args
        assert call_args.kwargs["repo_url"] == "https://github.com/example/infra"

    def test_list_commits_with_author_filter(self, client, mock_git_service, sample_commit):
        """Test listing commits filtered by author."""
        mock_git_service.list_commits.return_value = [sample_commit]

        response = client.get("/api/v1/git/commits?author=john@example.com")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["author_email"] == "john@example.com"

        # Verify filter was passed
        mock_git_service.list_commits.assert_called_once()
        call_args = mock_git_service.list_commits.call_args
        assert call_args.kwargs["author"] == "john@example.com"

    def test_list_commits_with_date_filters(self, client, mock_git_service, sample_commit):
        """Test listing commits with date range filters."""
        mock_git_service.list_commits.return_value = [sample_commit]

        since = "2024-01-01T00:00:00Z"
        until = "2024-01-31T23:59:59Z"

        response = client.get(f"/api/v1/git/commits?since={since}&until={until}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        # Verify filters were passed
        mock_git_service.list_commits.assert_called_once()
        call_args = mock_git_service.list_commits.call_args
        assert call_args.kwargs["since"] is not None
        assert call_args.kwargs["until"] is not None

    def test_list_commits_terraform_only(self, client, mock_git_service, sample_commit):
        """Test listing only commits with Terraform changes."""
        mock_git_service.list_commits.return_value = [sample_commit]

        response = client.get("/api/v1/git/commits?terraform_only=true")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["has_terraform_changes"] is True
        assert len(data[0]["terraform_files"]) == 2

        # Verify filter was passed
        mock_git_service.list_commits.assert_called_once()
        call_args = mock_git_service.list_commits.call_args
        assert call_args.kwargs["terraform_only"] is True

    def test_list_commits_with_limit(self, client, mock_git_service, sample_commit):
        """Test listing commits with custom limit."""
        mock_git_service.list_commits.return_value = [sample_commit] * 5

        response = client.get("/api/v1/git/commits?limit=5")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

        # Verify limit was passed
        mock_git_service.list_commits.assert_called_once()
        call_args = mock_git_service.list_commits.call_args
        assert call_args.kwargs["limit"] == 5

    def test_list_commits_limit_validation(self, client):
        """Test that limit is validated (1-100)."""
        # Test below minimum
        response = client.get("/api/v1/git/commits?limit=0")
        assert response.status_code == 422

        # Test above maximum
        response = client.get("/api/v1/git/commits?limit=101")
        assert response.status_code == 422

    def test_list_commits_empty_result(self, client, mock_git_service):
        """Test listing commits when no results found."""
        mock_git_service.list_commits.return_value = []

        response = client.get("/api/v1/git/commits")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_list_commits_service_error(self, client, mock_git_service):
        """Test handling of service errors."""
        mock_git_service.list_commits.side_effect = Exception("Database error")

        response = client.get("/api/v1/git/commits")

        assert response.status_code == 500
        assert "Failed to list Git commits" in response.json()["detail"]


class TestGetGitCommit:
    """Tests for GET /git/commits/{sha} endpoint."""

    def test_get_commit_by_full_sha(self, client, mock_git_service, sample_commit):
        """Test getting a commit by full SHA."""
        mock_git_service.get_commit.return_value = sample_commit

        sha = "abc123def456abc123def456abc123def456abc1"
        repo_url = "https://github.com/example/infra"

        response = client.get(f"/api/v1/git/commits/{sha}?repo_url={repo_url}")

        assert response.status_code == 200
        data = response.json()
        assert data["sha"] == sha
        assert data["message"] == "Update network configuration"

        # Verify service was called correctly
        mock_git_service.get_commit.assert_called_once_with(sha, repo_url)

    def test_get_commit_by_short_sha(self, client, mock_git_service, sample_commit):
        """Test getting a commit by short SHA."""
        mock_git_service.get_commit.return_value = sample_commit

        short_sha = "abc123d"
        repo_url = "https://github.com/example/infra"

        response = client.get(f"/api/v1/git/commits/{short_sha}?repo_url={repo_url}")

        assert response.status_code == 200
        data = response.json()
        assert data["short_sha"] == short_sha

        # Verify service was called with short SHA
        mock_git_service.get_commit.assert_called_once_with(short_sha, repo_url)

    def test_get_commit_not_found(self, client, mock_git_service):
        """Test getting a commit that doesn't exist."""
        mock_git_service.get_commit.return_value = None

        sha = "nonexistent"
        repo_url = "https://github.com/example/infra"

        response = client.get(f"/api/v1/git/commits/{sha}?repo_url={repo_url}")

        assert response.status_code == 404
        assert "Commit not found" in response.json()["detail"]

    def test_get_commit_missing_repo_url(self, client):
        """Test that repo_url is required."""
        response = client.get("/api/v1/git/commits/abc123")

        assert response.status_code == 422  # Validation error

    def test_get_commit_with_file_changes(self, client, mock_git_service, sample_commit):
        """Test that file changes are included in response."""
        mock_git_service.get_commit.return_value = sample_commit

        sha = "abc123d"
        repo_url = "https://github.com/example/infra"

        response = client.get(f"/api/v1/git/commits/{sha}?repo_url={repo_url}")

        assert response.status_code == 200
        data = response.json()
        assert len(data["files_changed"]) == 2
        assert data["files_changed"][0]["path"] == "network/main.tf"
        assert data["files_changed"][0]["additions"] == 10
        assert data["files_changed"][0]["deletions"] == 5

    def test_get_commit_service_error(self, client, mock_git_service):
        """Test handling of service errors."""
        mock_git_service.get_commit.side_effect = Exception("Database error")

        sha = "abc123"
        repo_url = "https://github.com/example/infra"

        response = client.get(f"/api/v1/git/commits/{sha}?repo_url={repo_url}")

        assert response.status_code == 500
        assert "Failed to fetch Git commit" in response.json()["detail"]


class TestGetCommitDiff:
    """Tests for GET /git/commits/{sha}/diff endpoint."""

    def test_get_commit_diff(self, client, mock_git_service):
        """Test getting a commit diff."""
        diff_text = """diff --git a/network/main.tf b/network/main.tf
index abc123..def456 100644
--- a/network/main.tf
+++ b/network/main.tf
@@ -10,3 +10,8 @@
+  subnet_id = azurerm_subnet.main.id
"""
        mock_git_service.get_diff.return_value = diff_text

        sha = "abc123"
        repo_url = "https://github.com/example/infra"

        response = client.get(f"/api/v1/git/commits/{sha}/diff?repo_url={repo_url}")

        assert response.status_code == 200
        data = response.json()
        assert data["sha"] == sha
        assert data["repo_url"] == repo_url
        assert "diff --git" in data["diff"]

        # Verify service was called
        mock_git_service.get_diff.assert_called_once_with(sha, repo_url, None)

    def test_get_commit_diff_with_file_filter(self, client, mock_git_service):
        """Test getting a commit diff filtered by file path."""
        diff_text = """diff --git a/network/main.tf b/network/main.tf
index abc123..def456 100644
--- a/network/main.tf
+++ b/network/main.tf
@@ -10,3 +10,8 @@
+  subnet_id = azurerm_subnet.main.id
"""
        mock_git_service.get_diff.return_value = diff_text

        sha = "abc123"
        repo_url = "https://github.com/example/infra"
        file_path = "network/main.tf"

        response = client.get(
            f"/api/v1/git/commits/{sha}/diff?repo_url={repo_url}&file_path={file_path}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "network/main.tf" in data["diff"]

        # Verify service was called with file_path
        mock_git_service.get_diff.assert_called_once_with(sha, repo_url, file_path)

    def test_get_commit_diff_not_found(self, client, mock_git_service):
        """Test getting diff for non-existent commit."""
        mock_git_service.get_diff.return_value = None

        sha = "nonexistent"
        repo_url = "https://github.com/example/infra"

        response = client.get(f"/api/v1/git/commits/{sha}/diff?repo_url={repo_url}")

        assert response.status_code == 404
        assert "Commit not found" in response.json()["detail"]

    def test_get_commit_diff_empty(self, client, mock_git_service):
        """Test getting diff when no diff is available."""
        mock_git_service.get_diff.return_value = ""

        sha = "abc123"
        repo_url = "https://github.com/example/infra"

        response = client.get(f"/api/v1/git/commits/{sha}/diff?repo_url={repo_url}")

        assert response.status_code == 200
        data = response.json()
        assert data["diff"] == ""

    def test_get_commit_diff_missing_repo_url(self, client):
        """Test that repo_url is required."""
        response = client.get("/api/v1/git/commits/abc123/diff")

        assert response.status_code == 422  # Validation error

    def test_get_commit_diff_service_error(self, client, mock_git_service):
        """Test handling of service errors."""
        mock_git_service.get_diff.side_effect = Exception("Database error")

        sha = "abc123"
        repo_url = "https://github.com/example/infra"

        response = client.get(f"/api/v1/git/commits/{sha}/diff?repo_url={repo_url}")

        assert response.status_code == 500
        assert "Failed to fetch commit diff" in response.json()["detail"]
