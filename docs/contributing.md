# Contributing Guide

Thank you for your interest in contributing to Infra-Aware RAG! This guide will help you get started.

## Code of Conduct

Please be respectful and constructive in all interactions. We're building something together.

## Getting Started

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/Griffin-Thomas/infra-aware-RAG.git
cd infra-aware-RAG
```

### 2. Set Up Development Environment

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

### 3. Verify Setup

```bash
# Run tests
python -m pytest tests/ -v

# Run linting
ruff check src/
black --check src/

# Run type checking
mypy src/
```

## Project Structure

```
src/
├── api/           # FastAPI application
├── cli/           # Command-line interface
├── ingestion/     # Data connectors
├── indexing/      # Embedding & search indexing
├── orchestration/ # LLM chat orchestration
├── search/        # Hybrid search engine
└── models/        # Pydantic data models

tests/
├── unit/          # Unit tests
├── integration/   # Integration tests
└── fixtures/      # Test data

docs/              # Documentation
frontend/          # React + TypeScript UI
infrastructure/    # Deployment configs
```

## Development Workflow

### Finding Tasks

1. Check [TASKS.md](../TASKS.md) for the current task list
2. Look for unchecked items (`- [ ]`) that interest you

### Making Changes

1. **Create a branch:**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```

2. **Make your changes:**
   - Follow the code style guidelines below
   - Add tests for new functionality
   - Update documentation as needed

3. **Run tests:**
   ```bash
   python -m pytest tests/ -v
   ```

4. **Commit your changes:**
   ```bash
   git add .
   git commit -m "feat: add new feature description"
   ```

5. **Push and create PR:**
   ```bash
   git push origin feature/your-feature-name
   # Then create a Pull Request on GitHub
   ```

## Code Style Guidelines

### Python

We use these tools to maintain code quality:

- **Black**: Code formatting (line length: 100)
- **Ruff**: Linting and import sorting
- **mypy**: Static type checking

```bash
# Format code
black src/ tests/

# Check linting
ruff check src/ tests/

# Fix auto-fixable issues
ruff check --fix src/ tests/

# Type check
mypy src/
```

### Style Rules

1. **Type hints**: All functions must have type hints
   ```python
   def process_resource(resource_id: str, options: dict[str, Any] | None = None) -> Resource:
       ...
   ```

2. **Docstrings**: Public functions need docstrings
   ```python
   def search_resources(query: str, top: int = 10) -> list[Resource]:
       """Search for Azure resources.

       Args:
           query: Search query text
           top: Maximum number of results

       Returns:
           List of matching resources
       """
   ```

3. **Async/await**: Use async for I/O operations
   ```python
   async def fetch_resource(resource_id: str) -> Resource:
       async with httpx.AsyncClient() as client:
           response = await client.get(f"/resources/{resource_id}")
           return Resource(**response.json())
   ```

4. **Pydantic models**: Use for data validation
   ```python
   class ResourceRequest(BaseModel):
       resource_id: str
       include_dependencies: bool = False

       model_config = ConfigDict(extra="forbid")
   ```

### TypeScript (Frontend)

- Use TypeScript strict mode
- Define interfaces for all data structures
- Use React functional components with hooks

```typescript
interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
}

const MessageItem: React.FC<{ message: Message }> = ({ message }) => {
  return <div className={`message ${message.role}`}>{message.content}</div>;
};
```

## Testing

### Writing Tests

- Place unit tests in `tests/unit/`
- Place integration tests in `tests/integration/`
- Name test files `test_<module>.py`
- Name test functions `test_<behaviour>`

```python
# tests/unit/test_chunkers.py
import pytest
from src.indexing.chunkers import chunk_terraform

class TestTerraformChunker:
    def test_chunk_single_resource(self):
        """Should create one chunk per resource block."""
        tf_content = '''
        resource "azurerm_storage_account" "main" {
          name = "mystorageaccount"
        }
        '''
        chunks = chunk_terraform(tf_content)
        assert len(chunks) == 1
        assert "azurerm_storage_account" in chunks[0].content

    def test_chunk_empty_file(self):
        """Should return empty list for empty file."""
        chunks = chunk_terraform("")
        assert chunks == []
```

### Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Specific file
python -m pytest tests/unit/test_chunkers.py -v

# With coverage
python -m pytest tests/ -v --cov=src --cov-report=html

# Only unit tests
python -m pytest tests/unit/ -v

# Skip slow tests
python -m pytest tests/ -v -m "not slow"
```

### Test Markers

Use pytest markers for test categorization:

```python
import pytest

@pytest.mark.unit
def test_fast_operation():
    ...

@pytest.mark.integration
def test_azure_connection():
    ...

@pytest.mark.slow
def test_full_pipeline():
    ...
```

## Pull Request Guidelines

### PR Title Format

Use conventional commits format:

- `feat: add new feature`
- `fix: resolve issue with X`
- `docs: update README`
- `test: add tests for Y`
- `refactor: restructure Z module`
- `chore: update dependencies`

### PR Description Template

```markdown
## Description
Brief description of changes

## Related Issues
Fixes #123

## Changes Made
- Change 1
- Change 2

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Checklist
- [ ] Code follows style guidelines
- [ ] Tests pass locally
- [ ] Documentation updated
- [ ] TASKS.md updated (if applicable)
```

### Review Process

1. All PRs require at least one approval
2. CI checks must pass (tests, linting, type checking)
3. Code coverage should not decrease
4. Documentation must be updated for new features

## Documentation

### When to Update Docs

- New features: Add to relevant guide
- API changes: Update api-reference.md
- Configuration changes: Update deployment-guide.md
- Bug fixes: Consider adding to troubleshooting.md

### Documentation Style

- Use clear, concise language
- Include code examples
- Add screenshots for UI changes
- Keep the README.md updated

## Architecture Decisions

For significant changes, consider:

1. **Discuss first**: Open an issue to discuss approach
2. **Document decisions**: Update docs/PLAN.md for architecture decisions
3. **Consider backwards compatibility**: Avoid breaking changes when possible

## Common Tasks

### Adding a New API Endpoint

1. Create router in `src/api/routers/`
2. Add Pydantic models in `src/api/models/`
3. Register router in `src/api/main.py`
4. Add tests in `tests/unit/test_<router>.py`
5. Update `docs/api-reference.md`

### Adding a New Data Connector

1. Create connector in `src/ingestion/connectors/`
2. Add document model in `src/models/documents.py`
3. Add chunker in `src/indexing/chunkers.py`
4. Add tests
5. Update `docs/01-data-ingestion.md`

### Adding a New LLM Tool

1. Add tool definition in `src/api/tools/definitions.py`
2. Implement handler in appropriate service
3. Add to tool router
4. Add tests
5. Update `docs/03-api-and-tools.md`

## Release Process

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create release PR
4. After merge, tag the release
5. CI builds and publishes packages

## Getting Help

- **Questions**: Open a GitHub Discussion
- **Bugs**: Open a GitHub Issue
- **Security**: Email security@example.com (do not open public issue)

## Recognition

Contributors are recognized in:
- Git commit history
- CONTRIBUTORS.md file
- Release notes

Thank you for contributing!
