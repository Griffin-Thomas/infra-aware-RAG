"""Command-line interface for Infra-Aware RAG.

This module provides a CLI tool for querying Azure infrastructure
and Terraform configurations using the Infra-Aware RAG system.

Usage:
    python -m src.cli chat                 # Interactive chat mode
    python -m src.cli chat "list all VMs"  # Single query mode
    python -m src.cli search "storage"     # Direct search
    python -m src.cli query "Resources | limit 10"  # KQL query
"""

from src.cli.main import app

__all__ = ["app"]
