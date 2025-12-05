"""Unit tests for Git connector."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from git import Repo

from src.ingestion.connectors.git_connector import GitConnector


@pytest.fixture
def connector():
    """Create a connector instance."""
    return GitConnector()


@pytest.fixture
def connector_all_files():
    """Create connector that tracks all infrastructure files."""
    return GitConnector(track_terraform_only=False, track_additional_infra=True)


@pytest.fixture
def mock_commit():
    """Create a mock Git commit."""
    commit = Mock()
    commit.hexsha = "abc123def456"
    commit.author.name = "Jane Doe"
    commit.author.email = "jane@example.com"
    commit.committed_date = 1704067200  # 2024-01-01 00:00:00 UTC
    commit.message = "Update Terraform configuration\n\nAdded new resource group"
    commit.parents = []
    return commit


@pytest.fixture
def mock_commit_with_parent():
    """Create a mock commit with parent."""
    commit = Mock()
    commit.hexsha = "def456ghi789"
    commit.author.name = "John Smith"
    commit.author.email = "john@example.com"
    commit.committed_date = 1704153600  # 2024-01-02 00:00:00 UTC
    commit.message = "Fix storage account configuration"

    # Mock parent
    parent = Mock()
    parent.hexsha = "abc123def456"
    commit.parents = [parent]

    return commit, parent


class TestGitConnector:
    """Test suite for GitConnector."""

    def test_init_default(self):
        """Test default initialization."""
        connector = GitConnector()
        assert connector.track_terraform_only is True
        assert connector.track_additional_infra is False
        assert len(connector.patterns) == 4  # Only Terraform patterns

    def test_init_with_additional_patterns(self):
        """Test initialization with additional patterns."""
        connector = GitConnector(
            track_terraform_only=False, track_additional_infra=True
        )
        assert connector.track_terraform_only is False
        assert connector.track_additional_infra is True
        assert len(connector.patterns) == 8  # Terraform + additional patterns

    def test_should_track_file_terraform(self, connector):
        """Test tracking Terraform files."""
        assert connector._should_track_file("main.tf") is True
        assert connector._should_track_file("terraform/variables.tf") is True
        assert connector._should_track_file("prod.tfvars") is True
        assert connector._should_track_file("terraform.tfstate") is True
        assert connector._should_track_file("terraform.tfstate.backup") is True

    def test_should_track_file_non_terraform(self, connector):
        """Test not tracking non-Terraform files."""
        assert connector._should_track_file("README.md") is False
        assert connector._should_track_file("script.py") is False
        assert connector._should_track_file("config.yaml") is False
        assert connector._should_track_file("template.bicep") is False

    def test_should_track_file_additional_patterns(self, connector_all_files):
        """Test tracking additional infrastructure files."""
        # Terraform files still tracked
        assert connector_all_files._should_track_file("main.tf") is True

        # Additional patterns now tracked
        assert connector_all_files._should_track_file("template.bicep") is True
        assert connector_all_files._should_track_file("config.yaml") is True
        assert connector_all_files._should_track_file("config.yml") is True
        assert connector_all_files._should_track_file("template.json") is True

        # Still not tracked
        assert connector_all_files._should_track_file("README.md") is False

    def test_inject_auth_token(self, connector):
        """Test injecting auth token into URL."""
        url = "https://github.com/user/repo.git"
        token = "ghp_1234567890abcdef"

        result = connector._inject_auth_token(url, token)

        assert result == "https://ghp_1234567890abcdef@github.com/user/repo.git"

    def test_inject_auth_token_ssh(self, connector):
        """Test that SSH URLs are not modified."""
        url = "git@github.com:user/repo.git"
        token = "ghp_1234567890abcdef"

        result = connector._inject_auth_token(url, token)

        assert result == url  # Unchanged

    @patch("src.ingestion.connectors.git_connector.Repo")
    def test_clone_repository_simple(self, mock_repo_class, connector, tmp_path):
        """Test cloning a repository."""
        repo_url = "https://github.com/user/repo.git"
        target_dir = tmp_path / "clone"

        # Mock the clone_from method
        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        # Clone
        result = connector.clone_repository(repo_url, target_dir)

        # Verify
        mock_repo_class.clone_from.assert_called_once_with(repo_url, target_dir)
        assert result == mock_repo

    @patch("src.ingestion.connectors.git_connector.Repo")
    def test_clone_repository_with_branch(self, mock_repo_class, connector, tmp_path):
        """Test cloning a specific branch."""
        repo_url = "https://github.com/user/repo.git"
        target_dir = tmp_path / "clone"
        branch = "develop"

        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        # Clone with branch
        result = connector.clone_repository(repo_url, target_dir, branch=branch)

        # Verify branch was specified
        mock_repo_class.clone_from.assert_called_once_with(
            repo_url, target_dir, branch=branch
        )

    @patch("src.ingestion.connectors.git_connector.Repo")
    def test_clone_repository_with_auth(self, mock_repo_class, connector, tmp_path):
        """Test cloning with authentication token."""
        repo_url = "https://github.com/user/repo.git"
        target_dir = tmp_path / "clone"
        token = "ghp_token123"

        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        # Clone with token
        connector.clone_repository(repo_url, target_dir, auth_token=token)

        # Verify token was injected
        called_url = mock_repo_class.clone_from.call_args[0][0]
        assert token in called_url

    @patch("src.ingestion.connectors.git_connector.tempfile.mkdtemp")
    @patch("src.ingestion.connectors.git_connector.Repo")
    def test_clone_repository_temp_dir(
        self, mock_repo_class, mock_mkdtemp, connector
    ):
        """Test cloning to a temporary directory."""
        repo_url = "https://github.com/user/repo.git"
        temp_path = "/tmp/git_clone_xyz123"
        mock_mkdtemp.return_value = temp_path

        mock_repo = Mock()
        mock_repo_class.clone_from.return_value = mock_repo

        # Clone without target_dir
        connector.clone_repository(repo_url)

        # Verify temp dir was used
        mock_mkdtemp.assert_called_once()
        mock_repo_class.clone_from.assert_called_once()
        called_path = mock_repo_class.clone_from.call_args[0][1]
        assert str(called_path) == temp_path

    def test_extract_file_changes_initial_commit(self, connector, mock_commit):
        """Test extracting file changes from initial commit (no parents)."""
        # Mock tree traverse
        mock_file = Mock()
        mock_file.type = "blob"
        mock_file.path = "main.tf"

        mock_dir = Mock()
        mock_dir.type = "tree"
        mock_dir.path = "terraform"

        mock_commit.tree.traverse.return_value = [mock_file, mock_dir]

        # Mock repo (not really used for initial commit)
        mock_repo = Mock()

        # Extract changes
        changes = connector._extract_file_changes(mock_commit, mock_repo)

        # Verify
        assert len(changes) == 1
        assert changes[0]["path"] == "main.tf"
        assert changes[0]["change_type"] == "add"

    def test_extract_file_changes_with_parent(
        self, connector, mock_commit_with_parent
    ):
        """Test extracting file changes with parent commit."""
        commit, parent = mock_commit_with_parent

        # Mock diff
        mock_diff = Mock()
        mock_diff.renamed_file = False
        mock_diff.deleted_file = False
        mock_diff.new_file = False
        mock_diff.a_path = "variables.tf"
        mock_diff.b_path = "variables.tf"
        mock_diff.diff = b"+variable \"location\" {\n+  default = \"canadaeast\"\n+}\n"

        parent.diff.return_value = [mock_diff]

        # Mock repo
        mock_repo = Mock()

        # Extract changes
        changes = connector._extract_file_changes(commit, mock_repo)

        # Verify
        assert len(changes) == 1
        assert changes[0]["path"] == "variables.tf"
        assert changes[0]["change_type"] == "modify"
        assert changes[0]["additions"] == 3
        assert changes[0]["deletions"] == 0

    def test_extract_file_changes_new_file(self, connector, mock_commit_with_parent):
        """Test extracting a new file addition."""
        commit, parent = mock_commit_with_parent

        # Mock diff for new file
        mock_diff = Mock()
        mock_diff.renamed_file = False
        mock_diff.deleted_file = False
        mock_diff.new_file = True
        mock_diff.a_path = None
        mock_diff.b_path = "storage.tf"
        mock_diff.diff = b"+resource \"azurerm_storage\" { }\n"

        parent.diff.return_value = [mock_diff]
        mock_repo = Mock()

        changes = connector._extract_file_changes(commit, mock_repo)

        assert len(changes) == 1
        assert changes[0]["path"] == "storage.tf"
        assert changes[0]["change_type"] == "add"

    def test_extract_file_changes_deleted_file(
        self, connector, mock_commit_with_parent
    ):
        """Test extracting a file deletion."""
        commit, parent = mock_commit_with_parent

        # Mock diff for deleted file
        mock_diff = Mock()
        mock_diff.renamed_file = False
        mock_diff.deleted_file = True
        mock_diff.new_file = False
        mock_diff.a_path = "old_resource.tf"
        mock_diff.b_path = None
        mock_diff.diff = b"-resource \"old\" { }\n"

        parent.diff.return_value = [mock_diff]
        mock_repo = Mock()

        changes = connector._extract_file_changes(commit, mock_repo)

        assert len(changes) == 1
        assert changes[0]["path"] == "old_resource.tf"
        assert changes[0]["change_type"] == "delete"

    def test_extract_file_changes_renamed_file(
        self, connector, mock_commit_with_parent
    ):
        """Test extracting a file rename."""
        commit, parent = mock_commit_with_parent

        # Mock diff for renamed file
        mock_diff = Mock()
        mock_diff.renamed_file = True
        mock_diff.deleted_file = False
        mock_diff.new_file = False
        mock_diff.a_path = "old_name.tf"
        mock_diff.b_path = "new_name.tf"
        mock_diff.rename_to = "new_name.tf"
        mock_diff.rename_from = "old_name.tf"
        mock_diff.diff = b""

        parent.diff.return_value = [mock_diff]
        mock_repo = Mock()

        changes = connector._extract_file_changes(commit, mock_repo)

        assert len(changes) == 1
        assert changes[0]["path"] == "new_name.tf"
        assert changes[0]["change_type"] == "rename"
        assert changes[0]["old_path"] == "old_name.tf"

    def test_extract_file_changes_filters_non_terraform(
        self, connector, mock_commit_with_parent
    ):
        """Test that non-Terraform files are filtered out."""
        commit, parent = mock_commit_with_parent

        # Mock diff with both Terraform and non-Terraform files
        mock_diff_tf = Mock()
        mock_diff_tf.renamed_file = False
        mock_diff_tf.deleted_file = False
        mock_diff_tf.new_file = False
        mock_diff_tf.b_path = "main.tf"
        mock_diff_tf.diff = b"+resource { }\n"

        mock_diff_md = Mock()
        mock_diff_md.renamed_file = False
        mock_diff_md.deleted_file = False
        mock_diff_md.new_file = False
        mock_diff_md.b_path = "README.md"
        mock_diff_md.diff = b"+# Documentation\n"

        parent.diff.return_value = [mock_diff_tf, mock_diff_md]
        mock_repo = Mock()

        changes = connector._extract_file_changes(commit, mock_repo)

        # Only Terraform file should be included
        assert len(changes) == 1
        assert changes[0]["path"] == "main.tf"

    @pytest.mark.asyncio
    async def test_extract_commits(self, connector):
        """Test extracting commits from a repository."""
        # Create mock repo
        mock_repo = Mock()
        mock_repo.active_branch.name = "main"

        # Create mock commits
        commit1 = Mock()
        commit1.hexsha = "abc123"
        commit1.author.name = "User 1"
        commit1.author.email = "user1@example.com"
        commit1.authored_date = 1704067200
        commit1.committer.name = "User 1"
        commit1.committer.email = "user1@example.com"
        commit1.committed_date = 1704067200
        commit1.message = "Commit 1"
        commit1.parents = []

        # Mock iter_commits
        mock_repo.iter_commits.return_value = [commit1]

        # Mock _extract_file_changes
        with patch.object(
            connector,
            "_extract_file_changes",
            return_value=[
                {
                    "path": "main.tf",
                    "change_type": "add",
                    "old_path": None,
                    "additions": 10,
                    "deletions": 0,
                }
            ],
        ):
            # Extract
            commits = []
            async for commit_dict in connector.extract_commits(mock_repo):
                commits.append(commit_dict)

            # Verify
            assert len(commits) == 1
            assert commits[0]["sha"] == "abc123"
            assert commits[0]["author_name"] == "User 1"
            assert len(commits[0]["file_changes"]) == 1

    @pytest.mark.asyncio
    async def test_extract_commits_filters_empty(self, connector):
        """Test that commits with no relevant changes are filtered out."""
        mock_repo = Mock()
        mock_repo.active_branch.name = "main"

        commit1 = Mock()
        commit1.hexsha = "abc123"
        commit1.author.name = "User"
        commit1.author.email = "user@example.com"
        commit1.committed_date = 1704067200
        commit1.message = "No Terraform changes"
        commit1.parents = []

        mock_repo.iter_commits.return_value = [commit1]

        # No file changes returned
        with patch.object(connector, "_extract_file_changes", return_value=[]):
            commits = []
            async for commit_dict in connector.extract_commits(mock_repo):
                commits.append(commit_dict)

            # Should be filtered out
            assert len(commits) == 0

    @pytest.mark.asyncio
    async def test_extract_commits_with_filters(self, connector):
        """Test extracting commits with date and author filters."""
        mock_repo = Mock()
        mock_repo.active_branch.name = "main"

        # Extract with filters
        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        until = datetime(2024, 12, 31, tzinfo=timezone.utc)
        author = "jane@example.com"

        mock_repo.iter_commits.return_value = []

        # Call with filters
        commits = []
        async for commit_dict in connector.extract_commits(
            mock_repo, since=since, until=until, author=author
        ):
            commits.append(commit_dict)

        # Verify iter_commits was called with filters
        mock_repo.iter_commits.assert_called_once_with(
            since=since, until=until, author=author
        )

    @pytest.mark.asyncio
    async def test_convert_to_document(self, connector):
        """Test converting commit dict to document."""
        commit_dict = {
            "sha": "abc123def456",
            "short_sha": "abc123d",
            "author_name": "Jane Doe",
            "author_email": "jane@example.com",
            "author_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "committer_name": "Jane Doe",
            "committer_email": "jane@example.com",
            "commit_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "message": "Update infrastructure\n\nAdded new storage account",
            "message_subject": "Update infrastructure",
            "message_body": "Added new storage account",
            "file_changes": [
                {
                    "path": "main.tf",
                    "change_type": "modify",
                    "old_path": None,
                    "additions": 5,
                    "deletions": 2,
                }
            ],
        }

        doc = await connector.convert_to_document(
            commit_dict=commit_dict,
            repo_url="https://github.com/user/repo.git",
            branch="main",
        )

        # Verify document
        assert doc.id == "abc123def456"
        assert doc.sha == "abc123def456"
        assert doc.short_sha == "abc123d"
        assert doc.repo_url == "https://github.com/user/repo.git"
        assert doc.branch == "main"
        assert doc.author_name == "Jane Doe"
        assert doc.author_email == "jane@example.com"
        assert doc.committer_name == "Jane Doe"
        assert doc.committer_email == "jane@example.com"
        assert len(doc.files_changed) == 1
        assert doc.files_changed[0].path == "main.tf"
        assert doc.total_additions == 5
        assert doc.total_deletions == 2
        assert doc.has_terraform_changes is True
        assert "main.tf" in doc.terraform_files_changed

    @pytest.mark.asyncio
    @patch("src.ingestion.connectors.git_connector.Repo")
    async def test_fetch_all_commits(self, mock_repo_class, connector):
        """Test the convenience method fetch_all_commits."""
        # Mock clone_repository
        mock_repo = Mock()
        mock_repo.active_branch.name = "main"
        mock_repo.working_dir = "/tmp/test_repo"
        mock_repo_class.clone_from.return_value = mock_repo

        # Mock extract_commits
        async def mock_extract():
            yield {
                "sha": "abc123",
                "short_sha": "abc123",
                "author_name": "User",
                "author_email": "user@example.com",
                "author_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "committer_name": "User",
                "committer_email": "user@example.com",
                "commit_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "message": "Test commit",
                "message_subject": "Test commit",
                "message_body": "",
                "file_changes": [
                    {
                        "path": "main.tf",
                        "change_type": "add",
                        "old_path": None,
                        "additions": 1,
                        "deletions": 0,
                    }
                ],
            }

        with patch.object(connector, "extract_commits", side_effect=lambda **kw: mock_extract()):
            documents = []
            async for doc in connector.fetch_all_commits(
                repo_url="https://github.com/user/repo.git",
                branch="main",
            ):
                documents.append(doc)

            # Verify we got documents
            assert len(documents) == 1
            assert documents[0].sha == "abc123"
