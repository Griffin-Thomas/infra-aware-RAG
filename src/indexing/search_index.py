"""Azure AI Search index schema and management."""

import logging

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    VectorSearch,
    VectorSearchProfile,
)

logger = logging.getLogger(__name__)


def create_infra_index(
    index_name: str = "infra-index",
    embedding_dimensions: int = 1536,
) -> SearchIndex:
    """Create the search index schema for infrastructure documents.

    Args:
        index_name: Name of the index
        embedding_dimensions: Dimensions of the embedding vectors

    Returns:
        SearchIndex configuration
    """
    fields = [
        # Core fields
        SearchField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,
            filterable=True,
        ),
        SearchField(
            name="content",
            type=SearchFieldDataType.String,
            searchable=True,
            analyzer_name="en.microsoft",
        ),
        SearchField(
            name="doc_type",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        # Vector field
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=embedding_dimensions,
            vector_search_profile_name="embedding-profile",
        ),
        # Azure resource fields
        SearchField(
            name="resource_id",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchField(
            name="resource_type",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SearchField(
            name="resource_name",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchField(
            name="resource_group",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SearchField(
            name="subscription_id",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SearchField(
            name="location",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        # Terraform fields
        SearchField(
            name="address",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchField(
            name="provider",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SearchField(
            name="file_path",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchField(
            name="repo_url",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchField(
            name="branch",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchField(
            name="azure_resource_id",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        # Git fields
        SearchField(
            name="sha",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchField(
            name="author_name",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SearchField(
            name="author_email",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchField(
            name="commit_date",
            type=SearchFieldDataType.DateTimeOffset,
            filterable=True,
            sortable=True,
        ),
        SearchField(
            name="has_terraform_changes",
            type=SearchFieldDataType.Boolean,
            filterable=True,
        ),
        # Plan fields
        SearchField(
            name="plan_id",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchField(
            name="action",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        # Tags (stored as JSON string for flexibility)
        SearchField(
            name="tags",
            type=SearchFieldDataType.String,
            searchable=True,
        ),
    ]

    # Vector search configuration using HNSW algorithm
    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw-algorithm",
                parameters=HnswParameters(
                    m=4,  # Number of bi-directional links
                    ef_construction=400,  # Size of dynamic candidate list for construction
                    ef_search=500,  # Size of dynamic candidate list for search
                    metric="cosine",  # Distance metric
                ),
            ),
        ],
        profiles=[
            VectorSearchProfile(
                name="embedding-profile",
                algorithm_configuration_name="hnsw-algorithm",
            ),
        ],
    )

    # Semantic configuration for re-ranking
    semantic_config = SemanticConfiguration(
        name="semantic-config",
        prioritized_fields=SemanticPrioritizedFields(
            content_fields=[SemanticField(field_name="content")],
        ),
    )

    return SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=SemanticSearch(configurations=[semantic_config]),
    )


class SearchIndexManager:
    """Manages the Azure AI Search index lifecycle."""

    def __init__(
        self,
        endpoint: str,
        api_key: str | None = None,
        index_name: str = "infra-index",
        embedding_dimensions: int = 1536,
    ):
        """Initialize search index manager.

        Args:
            endpoint: Azure AI Search endpoint URL
            api_key: API key (if None, uses DefaultAzureCredential)
            index_name: Name of the index to manage
            embedding_dimensions: Dimensions of the embedding vectors
        """
        self.endpoint = endpoint
        self.index_name = index_name
        self.embedding_dimensions = embedding_dimensions

        # Initialize client
        if api_key:
            self.index_client = SearchIndexClient(
                endpoint=endpoint,
                credential=AzureKeyCredential(api_key),
            )
        else:
            credential = DefaultAzureCredential()
            self.index_client = SearchIndexClient(
                endpoint=endpoint,
                credential=credential,
            )

    def create_or_update_index(self) -> SearchIndex:
        """Create or update the search index.

        Returns:
            The created/updated SearchIndex

        Raises:
            Exception: If index creation fails
        """
        try:
            index = create_infra_index(
                index_name=self.index_name,
                embedding_dimensions=self.embedding_dimensions,
            )
            result = self.index_client.create_or_update_index(index)
            logger.info(f"Successfully created/updated index: {self.index_name}")
            return result

        except Exception as e:
            logger.error(f"Failed to create/update index {self.index_name}: {e}")
            raise

    def delete_index(self):
        """Delete the search index.

        Raises:
            Exception: If index deletion fails
        """
        try:
            self.index_client.delete_index(self.index_name)
            logger.info(f"Successfully deleted index: {self.index_name}")

        except Exception as e:
            logger.error(f"Failed to delete index {self.index_name}: {e}")
            raise

    def index_exists(self) -> bool:
        """Check if the index exists.

        Returns:
            True if index exists, False otherwise
        """
        try:
            self.index_client.get_index(self.index_name)
            return True
        except Exception:
            return False

    def get_index_stats(self) -> dict:
        """Get statistics about the index.

        Returns:
            Dictionary with index statistics

        Raises:
            Exception: If stats retrieval fails
        """
        try:
            from azure.search.documents import SearchClient

            # Get search client to query stats
            if isinstance(self.index_client._credential, AzureKeyCredential):
                search_client = SearchClient(
                    endpoint=self.endpoint,
                    index_name=self.index_name,
                    credential=self.index_client._credential,
                )
            else:
                search_client = SearchClient(
                    endpoint=self.endpoint,
                    index_name=self.index_name,
                    credential=DefaultAzureCredential(),
                )

            # Get document count
            results = search_client.search(search_text="*", include_total_count=True)
            count = results.get_count()

            return {
                "index_name": self.index_name,
                "document_count": count,
                "exists": True,
            }

        except Exception as e:
            logger.error(f"Failed to get index stats for {self.index_name}: {e}")
            raise

    def close(self):
        """Close the client and cleanup resources."""
        if self.index_client:
            self.index_client.close()
