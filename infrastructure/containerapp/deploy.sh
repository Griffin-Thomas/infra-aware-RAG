#!/bin/bash
# Deploy Infra-Aware RAG API to Azure Container Apps
#
# Prerequisites:
# - Azure CLI installed and logged in (az login)
# - Docker installed (for building image)
# - Azure Container Registry created
# - Azure Container Apps environment created
# - Required Azure resources (OpenAI, Search, Cosmos DB) deployed
#
# Usage:
#   ./deploy.sh <environment> <version>
#   Example: ./deploy.sh prod v1.0.0

set -e  # Exit on error

# Configuration
ENVIRONMENT=${1:-dev}
VERSION=${2:-latest}
RESOURCE_GROUP="rg-infra-rag-${ENVIRONMENT}"
LOCATION="canadaeast"  # IMPORTANT: Must be Canada East or Canada Central
ACR_NAME="acrinfrarag${ENVIRONMENT}"
APP_NAME="infra-rag-api"
CONTAINER_ENV_NAME="env-infra-rag-${ENVIRONMENT}"
IMAGE_NAME="${ACR_NAME}.azurecr.io/${APP_NAME}:${VERSION}"

echo "=========================================="
echo "Deploying Infra-Aware RAG API"
echo "=========================================="
echo "Environment: $ENVIRONMENT"
echo "Version: $VERSION"
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "Container Registry: $ACR_NAME"
echo "Image: $IMAGE_NAME"
echo "=========================================="
echo ""

# Step 1: Build Docker image
echo "Step 1: Building Docker image..."
docker build -t ${APP_NAME}:${VERSION} -t ${APP_NAME}:latest .
echo "✓ Docker image built successfully"
echo ""

# Step 2: Login to Azure Container Registry
echo "Step 2: Logging in to Azure Container Registry..."
az acr login --name ${ACR_NAME}
echo "✓ Logged in to ACR"
echo ""

# Step 3: Tag and push image
echo "Step 3: Pushing image to ACR..."
docker tag ${APP_NAME}:${VERSION} ${IMAGE_NAME}
docker push ${IMAGE_NAME}
echo "✓ Image pushed to ACR"
echo ""

# Step 4: Get Azure resource endpoints
echo "Step 4: Retrieving Azure resource endpoints..."

# Get OpenAI endpoint
OPENAI_ENDPOINT=$(az cognitiveservices account show \
  --name "openai-infra-rag-${ENVIRONMENT}" \
  --resource-group ${RESOURCE_GROUP} \
  --query "properties.endpoint" -o tsv)

# Get Search endpoint
SEARCH_ENDPOINT=$(az search service show \
  --name "search-infra-rag-${ENVIRONMENT}" \
  --resource-group ${RESOURCE_GROUP} \
  --query "endpoint" -o tsv)

# Get Cosmos DB endpoint
COSMOS_ENDPOINT=$(az cosmosdb show \
  --name "cosmos-infra-rag-${ENVIRONMENT}" \
  --resource-group ${RESOURCE_GROUP} \
  --query "documentEndpoint" -o tsv)

# Get Cosmos DB Gremlin endpoint
COSMOS_GREMLIN_ENDPOINT=$(az cosmosdb show \
  --name "cosmos-infra-rag-${ENVIRONMENT}" \
  --resource-group ${RESOURCE_GROUP} \
  --query "writeLocations[0].documentEndpoint" -o tsv | sed 's/https/wss/g' | sed 's/$/:443/')

echo "✓ Endpoints retrieved"
echo ""

# Step 5: Deploy or update Container App
echo "Step 5: Deploying to Azure Container Apps..."

# Check if Container App exists
if az containerapp show --name ${APP_NAME} --resource-group ${RESOURCE_GROUP} &>/dev/null; then
  echo "Updating existing Container App..."
  az containerapp update \
    --name ${APP_NAME} \
    --resource-group ${RESOURCE_GROUP} \
    --image ${IMAGE_NAME} \
    --set-env-vars \
      "AZURE_OPENAI_ENDPOINT=${OPENAI_ENDPOINT}" \
      "AZURE_SEARCH_ENDPOINT=${SEARCH_ENDPOINT}" \
      "COSMOS_DB_ENDPOINT=${COSMOS_ENDPOINT}" \
      "COSMOS_DB_GREMLIN_ENDPOINT=${COSMOS_GREMLIN_ENDPOINT}" \
      "AZURE_REGION=${LOCATION}" \
      "API_VERSION=${VERSION}"
else
  echo "Creating new Container App..."
  az containerapp create \
    --name ${APP_NAME} \
    --resource-group ${RESOURCE_GROUP} \
    --environment ${CONTAINER_ENV_NAME} \
    --image ${IMAGE_NAME} \
    --target-port 8000 \
    --ingress external \
    --registry-server ${ACR_NAME}.azurecr.io \
    --registry-identity system \
    --cpu 1.0 \
    --memory 2.0Gi \
    --min-replicas 1 \
    --max-replicas 10 \
    --env-vars \
      "AZURE_OPENAI_ENDPOINT=${OPENAI_ENDPOINT}" \
      "AZURE_SEARCH_ENDPOINT=${SEARCH_ENDPOINT}" \
      "COSMOS_DB_ENDPOINT=${COSMOS_ENDPOINT}" \
      "COSMOS_DB_GREMLIN_ENDPOINT=${COSMOS_GREMLIN_ENDPOINT}" \
      "AZURE_REGION=${LOCATION}" \
      "API_VERSION=${VERSION}" \
      "AZURE_OPENAI_API_VERSION=2024-02-01" \
      "AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large" \
      "AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o" \
      "AZURE_SEARCH_INDEX_NAME=infra-rag-index" \
      "COSMOS_DB_DATABASE=infra-rag" \
      "COSMOS_DB_CONTAINER=documents" \
      "COSMOS_DB_GREMLIN_DATABASE=graph" \
      "RATE_LIMIT_PER_MINUTE=60" \
      "RATE_LIMIT_PER_HOUR=1000" \
      "CORS_ORIGINS=*" \
    --system-assigned
fi

echo "✓ Container App deployed"
echo ""

# Step 6: Enable managed identity access to resources
echo "Step 6: Configuring managed identity access..."

# Get the Container App's managed identity
IDENTITY_ID=$(az containerapp show \
  --name ${APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --query "identity.principalId" -o tsv)

# Grant access to OpenAI
az role assignment create \
  --assignee ${IDENTITY_ID} \
  --role "Cognitive Services OpenAI User" \
  --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.CognitiveServices/accounts/openai-infra-rag-${ENVIRONMENT}"

# Grant access to Search
az role assignment create \
  --assignee ${IDENTITY_ID} \
  --role "Search Index Data Contributor" \
  --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Search/searchServices/search-infra-rag-${ENVIRONMENT}"

# Grant access to Cosmos DB
az role assignment create \
  --assignee ${IDENTITY_ID} \
  --role "Cosmos DB Account Reader Role" \
  --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.DocumentDB/databaseAccounts/cosmos-infra-rag-${ENVIRONMENT}"

# Grant ACR pull access
az role assignment create \
  --assignee ${IDENTITY_ID} \
  --role "AcrPull" \
  --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.ContainerRegistry/registries/${ACR_NAME}"

echo "✓ Managed identity configured"
echo ""

# Step 7: Get the application URL
echo "Step 7: Getting application URL..."
APP_URL=$(az containerapp show \
  --name ${APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --query "properties.configuration.ingress.fqdn" -o tsv)

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo "Application URL: https://${APP_URL}"
echo "Health Check: https://${APP_URL}/health"
echo "API Docs: https://${APP_URL}/docs"
echo "=========================================="
echo ""
echo "Test the deployment with:"
echo "  curl https://${APP_URL}/health"
echo ""
