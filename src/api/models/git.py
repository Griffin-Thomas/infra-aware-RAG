"""Git-related API models."""

from datetime import datetime
from pydantic import BaseModel, Field


class FileChange(BaseModel):
    """File change in a commit."""

    path: str = Field(..., description="File path")
    change_type: str = Field(..., description="Change type: add, modify, delete, rename")
    additions: int = Field(..., ge=0, description="Number of lines added")
    deletions: int = Field(..., ge=0, description="Number of lines deleted")


class GitCommit(BaseModel):
    """Git commit model."""

    sha: str = Field(..., description="Full commit SHA")
    short_sha: str = Field(..., description="Short commit SHA (first 7 chars)")
    repo_url: str = Field(..., description="Git repository URL")
    branch: str = Field(..., description="Branch name")
    message: str = Field(..., description="Commit message")
    author_name: str = Field(..., description="Author name")
    author_email: str = Field(..., description="Author email")
    commit_date: datetime = Field(..., description="Commit timestamp")
    files_changed: list[FileChange] = Field(
        default_factory=list, description="List of file changes"
    )
    terraform_files: list[str] = Field(
        default_factory=list, description="List of Terraform files changed (*.tf)"
    )
    has_terraform_changes: bool = Field(
        default=False, description="Whether commit contains Terraform changes"
    )


class CommitDiff(BaseModel):
    """Commit diff response."""

    sha: str = Field(..., description="Commit SHA")
    repo_url: str = Field(..., description="Repository URL")
    diff: str = Field(..., description="Unified diff output")
