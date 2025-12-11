"""Tests to verify fixes for issues previously identified.

These tests specifically validate:
1. HybridSearchEngine is initialized with correct object types
2. ResourceService has all required methods for tool endpoints
3. Graph population uses correct method signatures
4. GitService uses async Cosmos SDK correctly
5. Terraform plan parsing counts replacements correctly
"""

from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call

import pytest

from src.api.services.resource_service import ResourceService
from src.api.services.git_service import GitService
from src.api.services.terraform_service import TerraformService
from src.indexing.orchestrator import IndexingOrchestrator
from src.ingestion.connectors.terraform_plan import TerraformPlanConnector


class TestIssue1SearchEngineWiring:
    """Test that HybridSearchEngine is initialized with correct types.

    Issue: dependencies.py was passing endpoint strings instead of
    SearchClient, GraphBuilder, and EmbeddingPipeline instances.
    """

    @pytest.mark.asyncio
    async def test_init_services_passes_correct_types_to_search_engine(self):
        """Verify HybridSearchEngine receives object instances, not strings."""
        from src.api.dependencies import init_services, _services, get_settings

        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
                "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
                "COSMOS_DB_ENDPOINT": "https://test.documents.azure.com",
                "COSMOS_DB_GREMLIN_ENDPOINT": "https://test.documents.azure.com:443/",
                "COSMOS_DB_GREMLIN_KEY": "test-gremlin-key",
            },
        ):
            get_settings.cache_clear()
            settings = get_settings()

            # Mock all dependencies
            with patch("src.api.dependencies.DefaultAzureCredential"), \
                 patch("src.api.dependencies.CosmosClient"), \
                 patch("src.api.dependencies.AzureResourceGraphConnector"), \
                 patch("src.api.dependencies.SearchClient") as mock_search_client, \
                 patch("src.api.dependencies.EmbeddingPipeline") as mock_embedding, \
                 patch("src.api.dependencies.GraphBuilder") as mock_graph, \
                 patch("src.api.dependencies.HybridSearchEngine") as mock_hybrid, \
                 patch("src.api.dependencies.ResourceService"), \
                 patch("src.api.dependencies.TerraformService"), \
                 patch("src.api.dependencies.GitService"), \
                 patch("src.api.dependencies.OrchestrationEngine"), \
                 patch("src.api.dependencies.MemoryStore") as mock_memory, \
                 patch("src.api.dependencies.ConversationManager"):

                # Setup mocks
                mock_embedding_instance = AsyncMock()
                mock_embedding.return_value = mock_embedding_instance
                mock_memory_instance = AsyncMock()
                mock_memory.return_value = mock_memory_instance

                try:
                    await init_services(settings)

                    # Verify HybridSearchEngine was called with object instances
                    mock_hybrid.assert_called_once()
                    call_kwargs = mock_hybrid.call_args.kwargs

                    # These should be object instances, not strings
                    assert "search_client" in call_kwargs
                    assert "graph_builder" in call_kwargs
                    assert "embedding_pipeline" in call_kwargs

                    # Verify they're the mocked instances
                    assert call_kwargs["search_client"] == mock_search_client.return_value
                    assert call_kwargs["graph_builder"] == mock_graph.return_value
                    assert call_kwargs["embedding_pipeline"] == mock_embedding_instance

                finally:
                    _services.clear()


class TestIssue2ResourceServiceMethods:
    """Test that ResourceService has all methods required by tools.py.

    Issue: tools.py calls methods that didn't exist on ResourceService:
    - get_terraform_for_resource
    - get_dependencies
    - list_subscriptions
    - get_resource_types_summary
    """

    @pytest.fixture
    def resource_service(self):
        """Create ResourceService with mocked dependencies."""
        mock_cosmos = AsyncMock()
        mock_arg = MagicMock()
        mock_graph = MagicMock()

        return ResourceService(
            cosmos_client=mock_cosmos,
            database_name="test-db",
            container_name="test-container",
            arg_connector=mock_arg,
            graph_builder=mock_graph,
        )

    def test_has_get_terraform_for_resource_method(self, resource_service):
        """Verify get_terraform_for_resource method exists and is callable."""
        assert hasattr(resource_service, "get_terraform_for_resource")
        assert callable(resource_service.get_terraform_for_resource)

    def test_has_get_dependencies_method(self, resource_service):
        """Verify get_dependencies method exists and is callable."""
        assert hasattr(resource_service, "get_dependencies")
        assert callable(resource_service.get_dependencies)

    def test_has_list_subscriptions_method(self, resource_service):
        """Verify list_subscriptions method exists and is callable."""
        assert hasattr(resource_service, "list_subscriptions")
        assert callable(resource_service.list_subscriptions)

    def test_has_get_resource_types_summary_method(self, resource_service):
        """Verify get_resource_types_summary method exists and is callable."""
        assert hasattr(resource_service, "get_resource_types_summary")
        assert callable(resource_service.get_resource_types_summary)

    @pytest.mark.asyncio
    async def test_get_terraform_for_resource_uses_graph_builder(self, resource_service):
        """Verify get_terraform_for_resource uses graph builder when available."""
        resource_service.graph_builder.find_terraform_for_resource.return_value = [
            {"address": "azurerm_vm.test", "file_path": "main.tf", "repo_url": "https://github.com/test/repo"}
        ]

        result = await resource_service.get_terraform_for_resource("/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1")

        resource_service.graph_builder.find_terraform_for_resource.assert_called_once()
        assert len(result) == 1
        assert result[0].address == "azurerm_vm.test"

    @pytest.mark.asyncio
    async def test_get_dependencies_uses_graph_builder(self, resource_service):
        """Verify get_dependencies uses graph builder."""
        resource_service.graph_builder.find_dependencies.return_value = [
            {"id": "/subscriptions/sub-1/...", "name": "test", "type": "Microsoft.Storage/storageAccounts"}
        ]

        result = await resource_service.get_dependencies("/subscriptions/sub-1/.../vm1", direction="both", depth=2)

        resource_service.graph_builder.find_dependencies.assert_called_once_with(
            resource_id="/subscriptions/sub-1/.../vm1",
            direction="both",
            depth=2,
        )

    @pytest.mark.asyncio
    async def test_list_subscriptions_uses_arg_connector(self, resource_service):
        """Verify list_subscriptions uses ARG connector enumerate_subscriptions."""
        resource_service.arg_connector.__aenter__ = AsyncMock(return_value=resource_service.arg_connector)
        resource_service.arg_connector.__aexit__ = AsyncMock(return_value=None)
        resource_service.arg_connector.enumerate_subscriptions = AsyncMock(
            return_value=[{"id": "sub-1", "name": "Test Sub", "state": "Enabled"}]
        )

        result = await resource_service.list_subscriptions()

        resource_service.arg_connector.enumerate_subscriptions.assert_called_once()
        assert len(result) == 1
        assert result[0]["id"] == "sub-1"

    @pytest.mark.asyncio
    async def test_get_resource_types_summary_uses_arg_connector(self, resource_service):
        """Verify get_resource_types_summary uses ARG connector fetch_resource_types."""
        resource_service.arg_connector.__aenter__ = AsyncMock(return_value=resource_service.arg_connector)
        resource_service.arg_connector.__aexit__ = AsyncMock(return_value=None)
        resource_service.arg_connector.fetch_resource_types = AsyncMock(
            return_value=[{"type": "Microsoft.Compute/virtualMachines", "count_": 10}]
        )

        result = await resource_service.get_resource_types_summary()

        resource_service.arg_connector.fetch_resource_types.assert_called_once()
        assert len(result) == 1


class TestIssue3GraphPopulationSignatures:
    """Test that graph population uses correct method signatures.

    Issue: orchestrator._populate_graph was calling:
    - add_terraform_resource with keyword args instead of dict
    - link_terraform_to_azure with azure_resource_id instead of azure_id
    """

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        mock_cosmos = Mock()
        mock_cosmos.get_database_client.return_value.get_container_client.return_value = AsyncMock()

        mock_search_indexer = Mock()
        mock_search_indexer.index_chunks.return_value = {"total": 1, "succeeded": 1, "failed": 0, "errors": []}

        mock_embedding = AsyncMock()
        async def mock_embed(chunks):
            for c in chunks:
                c.embedding = [0.1] * 1536
                yield c
        mock_embedding.embed_chunks = mock_embed

        mock_graph = Mock()

        return IndexingOrchestrator(
            cosmos_client=mock_cosmos,
            cosmos_database="test-db",
            cosmos_container="test-container",
            search_indexer=mock_search_indexer,
            embedding_pipeline=mock_embedding,
            graph_builder=mock_graph,
            batch_size=10,
        )

    @pytest.mark.asyncio
    async def test_add_terraform_resource_called_with_dict(self, orchestrator):
        """Verify add_terraform_resource is called with a dict, not keyword args."""
        document = {
            "id": "tf-doc-1",
            "doc_type": "terraform_resource",
            "address": "azurerm_resource_group.main",
            "type": "azurerm_resource_group",
            "file_path": "main.tf",
            "repo_url": "https://github.com/test/repo",
            "branch": "main",
        }

        await orchestrator._populate_graph(document, "terraform_resource")

        # Should be called with a dict as first positional arg
        orchestrator.graph_builder.add_terraform_resource.assert_called_once()
        call_args = orchestrator.graph_builder.add_terraform_resource.call_args

        # First positional argument should be a dict
        assert len(call_args.args) == 1
        tf_dict = call_args.args[0]
        assert isinstance(tf_dict, dict)
        assert tf_dict["address"] == "azurerm_resource_group.main"
        assert tf_dict["type"] == "azurerm_resource_group"
        assert tf_dict["file_path"] == "main.tf"

    @pytest.mark.asyncio
    async def test_link_terraform_to_azure_uses_azure_id_param(self, orchestrator):
        """Verify link_terraform_to_azure is called with azure_id, not azure_resource_id."""
        document = {
            "id": "tf-doc-1",
            "doc_type": "terraform_resource",
            "address": "azurerm_virtual_machine.main",
            "type": "azurerm_virtual_machine",
            "file_path": "main.tf",
            "repo_url": "https://github.com/test/repo",
            "branch": "main",
            "azure_resource_id": "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        }

        await orchestrator._populate_graph(document, "terraform_resource")

        # Should use azure_id parameter, not azure_resource_id
        orchestrator.graph_builder.link_terraform_to_azure.assert_called_once()
        call_kwargs = orchestrator.graph_builder.link_terraform_to_azure.call_args.kwargs

        assert "azure_id" in call_kwargs
        assert "azure_resource_id" not in call_kwargs
        assert call_kwargs["azure_id"] == "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"


class TestIssue4GitServiceAsyncCosmos:
    """Test that GitService uses async Cosmos SDK correctly.

    Issue: GitService imported sync CosmosClient but used it in async methods,
    and called list(container.query_items(...)) which blocks the event loop.
    """

    def test_git_service_imports_async_cosmos_client(self):
        """Verify GitService imports the async CosmosClient."""
        import src.api.services.git_service as git_module
        import inspect

        # Check the import statement
        source = inspect.getsource(git_module)
        assert "azure.cosmos.aio" in source, "GitService should import from azure.cosmos.aio"
        assert "from azure.cosmos import CosmosClient" not in source.replace("azure.cosmos.aio", ""), \
            "GitService should not import sync CosmosClient"

    def test_list_commits_is_async_method(self):
        """Verify list_commits is an async method (uses async iteration internally)."""
        import inspect
        assert inspect.iscoroutinefunction(GitService.list_commits), \
            "list_commits should be an async method"

    def test_get_commit_is_async_method(self):
        """Verify get_commit is an async method."""
        import inspect
        assert inspect.iscoroutinefunction(GitService.get_commit), \
            "get_commit should be an async method"

    def test_get_diff_is_async_method(self):
        """Verify get_diff is an async method."""
        import inspect
        assert inspect.iscoroutinefunction(GitService.get_diff), \
            "get_diff should be an async method"

    def test_list_commits_uses_async_for_not_list(self):
        """Verify list_commits uses 'async for' not 'list()'."""
        import inspect
        source = inspect.getsource(GitService.list_commits)

        # Should use async for iteration
        assert "async for" in source, "list_commits should use 'async for' iteration"
        # Should NOT wrap in list() which blocks
        assert "list(container.query_items" not in source, \
            "list_commits should not use list(container.query_items(...))"

    def test_get_commit_uses_async_for_not_list(self):
        """Verify get_commit uses 'async for' not 'list()'."""
        import inspect
        source = inspect.getsource(GitService.get_commit)

        assert "async for" in source, "get_commit should use 'async for' iteration"
        assert "list(container.query_items" not in source, \
            "get_commit should not use list(container.query_items(...))"

    def test_get_diff_uses_async_for_not_list(self):
        """Verify get_diff uses 'async for' not 'list()'."""
        import inspect
        source = inspect.getsource(GitService.get_diff)

        assert "async for" in source, "get_diff should use 'async for' iteration"
        assert "list(container.query_items" not in source, \
            "get_diff should not use list(container.query_items(...))"


class TestIssue5TerraformPlanReplacementCounting:
    """Test that Terraform plan parsing correctly counts replacements.

    Issue: Replacement actions were counted as creates only, not as both
    creates AND destroys, under-reporting destructive changes.
    """

    @pytest.fixture
    def connector(self):
        return TerraformPlanConnector()

    @pytest.fixture
    def terraform_service(self):
        mock_cosmos = AsyncMock()
        return TerraformService(
            cosmos_client=mock_cosmos,
            database_name="test-db",
            container_name="test-container",
        )

    def test_connector_counts_replace_as_add_and_destroy(self, connector):
        """Verify TerraformPlanConnector counts replace as both add and destroy."""
        plan = {
            "terraform_version": "1.5.0",
            "resource_changes": [
                {
                    "address": "azurerm_public_ip.main",
                    "type": "azurerm_public_ip",
                    "provider_name": "azurerm",
                    "change": {
                        "actions": ["delete", "create"],  # This is a replace
                        "before": {"sku": "Basic"},
                        "after": {"sku": "Standard"},
                    },
                }
            ],
        }

        result = connector._process_plan(plan)

        # Replace should count as BOTH add and destroy
        assert result["total_add"] == 1
        assert result["total_destroy"] == 1
        assert result["total_change"] == 0

    def test_connector_counts_multiple_action_types(self, connector):
        """Verify correct counting with mix of creates, updates, deletes, replaces."""
        plan = {
            "terraform_version": "1.5.0",
            "resource_changes": [
                # Create
                {"address": "res1", "type": "type1", "change": {"actions": ["create"], "before": None, "after": {}}},
                # Update
                {"address": "res2", "type": "type2", "change": {"actions": ["update"], "before": {}, "after": {}}},
                # Delete
                {"address": "res3", "type": "type3", "change": {"actions": ["delete"], "before": {}, "after": None}},
                # Replace
                {"address": "res4", "type": "type4", "change": {"actions": ["delete", "create"], "before": {}, "after": {}}},
            ],
        }

        result = connector._process_plan(plan)

        # 1 create + 1 replace = 2 adds
        assert result["total_add"] == 2
        # 1 update
        assert result["total_change"] == 1
        # 1 delete + 1 replace = 2 destroys
        assert result["total_destroy"] == 2

    def test_service_parse_plan_counts_replace_as_add_and_destroy(self, terraform_service):
        """Verify TerraformService.parse_plan counts replace as both add and destroy."""
        plan_json = {
            "resource_changes": [
                {
                    "address": "azurerm_vm.main",
                    "type": "azurerm_virtual_machine",
                    "change": {
                        "actions": ["delete", "create"],  # Replace
                        "before": {"size": "Standard_B1s"},
                        "after": {"size": "Standard_B2s"},
                    },
                },
                {
                    "address": "azurerm_rg.main",
                    "type": "azurerm_resource_group",
                    "change": {
                        "actions": ["delete"],  # Pure delete
                        "before": {},
                        "after": None,
                    },
                },
            ],
        }

        result = terraform_service.parse_plan(plan_json)

        # 1 replace = 1 add
        assert result.add == 1
        # 1 delete + 1 replace = 2 destroys
        assert result.destroy == 2
        assert result.change == 0

    def test_replace_action_identified_before_individual_checks(self, connector):
        """Verify replace is detected even when 'create' comes before 'delete' in actions."""
        plan = {
            "terraform_version": "1.5.0",
            "resource_changes": [
                {
                    "address": "test",
                    "type": "test",
                    "change": {
                        "actions": ["create", "delete"],  # Order reversed
                        "before": {},
                        "after": {},
                    },
                }
            ],
        }

        result = connector._process_plan(plan)

        # Should still be counted as replace (both add and destroy)
        assert result["total_add"] == 1
        assert result["total_destroy"] == 1
