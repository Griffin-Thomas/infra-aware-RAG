# Azure Container Apps Deployment

This directory contains configuration files for deploying the Infra-Aware RAG API to Azure Container Apps.

## Files

- `containerapp.yaml` - Container App resource definition (declarative)
- `deploy.sh` - Automated deployment script (imperative)
- `README.md` - This file

## Prerequisites

Before deploying, ensure you have:

1. **Azure CLI** installed and authenticated (`az login`)
2. **Docker** installed for building images
3. **Azure Resources** created:
   - Resource Group (in Canada East or Canada Central)
   - Azure Container Registry
   - Azure Container Apps Environment
   - Azure OpenAI Service
   - Azure AI Search
   - Cosmos DB (NoSQL and Gremlin APIs)

## Deployment Methods

### Method 1: Automated Deployment (Recommended)

Use the deployment script for a complete, automated deployment:

```bash
# Deploy to dev environment
./deploy.sh dev v1.0.0

# Deploy to production
./deploy.sh prod v1.0.0
```

The script will:
1. Build the Docker image
2. Push to Azure Container Registry
3. Retrieve Azure resource endpoints
4. Deploy/update the Container App
5. Configure managed identity and RBAC
6. Display the application URL

### Method 2: Manual Deployment

#### Step 1: Build and Push Docker Image

```bash
# Build image
docker build -t infra-rag-api:latest ../../

# Tag for ACR
docker tag infra-rag-api:latest <acr-name>.azurecr.io/infra-rag-api:latest

# Login to ACR
az acr login --name <acr-name>

# Push image
docker push <acr-name>.azurecr.io/infra-rag-api:latest
```

#### Step 2: Deploy Container App

```bash
# Create Container App
az containerapp create \
  --name infra-rag-api \
  --resource-group <resource-group> \
  --environment <environment-name> \
  --image <acr-name>.azurecr.io/infra-rag-api:latest \
  --target-port 8000 \
  --ingress external \
  --registry-server <acr-name>.azurecr.io \
  --registry-identity system \
  --cpu 1.0 \
  --memory 2.0Gi \
  --min-replicas 1 \
  --max-replicas 10 \
  --env-vars \
    "AZURE_OPENAI_ENDPOINT=<endpoint>" \
    "AZURE_SEARCH_ENDPOINT=<endpoint>" \
    "COSMOS_DB_ENDPOINT=<endpoint>" \
    "COSMOS_DB_GREMLIN_ENDPOINT=<endpoint>" \
    "AZURE_REGION=canadaeast" \
  --system-assigned
```

#### Step 3: Configure Managed Identity

```bash
# Get managed identity principal ID
IDENTITY_ID=$(az containerapp show \
  --name infra-rag-api \
  --resource-group <resource-group> \
  --query "identity.principalId" -o tsv)

# Grant OpenAI access
az role assignment create \
  --assignee $IDENTITY_ID \
  --role "Cognitive Services OpenAI User" \
  --scope <openai-resource-id>

# Grant Search access
az role assignment create \
  --assignee $IDENTITY_ID \
  --role "Search Index Data Contributor" \
  --scope <search-resource-id>

# Grant Cosmos DB access
az role assignment create \
  --assignee $IDENTITY_ID \
  --role "Cosmos DB Account Reader Role" \
  --scope <cosmos-resource-id>
```

### Method 3: Using YAML Configuration

```bash
# Update containerapp.yaml with your values
# Then deploy:
az containerapp create --yaml containerapp.yaml
```

## Configuration

### Environment Variables

The Container App requires the following environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI endpoint URL |
| `AZURE_SEARCH_ENDPOINT` | Yes | Azure AI Search endpoint URL |
| `COSMOS_DB_ENDPOINT` | Yes | Cosmos DB endpoint URL |
| `COSMOS_DB_GREMLIN_ENDPOINT` | Yes | Cosmos DB Gremlin endpoint URL |
| `AZURE_REGION` | Yes | Azure region (canadaeast or canadacentral) |
| `AZURE_OPENAI_API_VERSION` | No | OpenAI API version (default: 2024-02-01) |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | No | Embedding model name (default: text-embedding-3-large) |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | No | Chat model name (default: gpt-4) |
| `AZURE_SEARCH_INDEX_NAME` | No | Search index name (default: infra-rag-index) |
| `RATE_LIMIT_PER_MINUTE` | No | Rate limit (default: 60) |
| `RATE_LIMIT_PER_HOUR` | No | Rate limit (default: 1000) |
| `CORS_ORIGINS` | No | Allowed CORS origins (default: *) |

### Resource Sizing

**Default Configuration:**
- CPU: 1.0 core
- Memory: 2 GiB
- Min Replicas: 1
- Max Replicas: 10

**Scaling Triggers:**
- HTTP concurrent requests > 100
- CPU utilization > 75%

**Adjust for your needs:**
- Increase CPU/memory for higher throughput
- Increase max replicas for more concurrent users
- Adjust scaling rules based on load patterns

## Health Checks

The Container App includes:

- **Liveness probe**: `GET /health` (checks if app is running)
- **Readiness probe**: `GET /ready` (checks if app can handle traffic)

## Monitoring

After deployment, monitor your application:

```bash
# View logs
az containerapp logs show \
  --name infra-rag-api \
  --resource-group <resource-group> \
  --follow

# View metrics
az monitor metrics list \
  --resource <container-app-resource-id> \
  --metric "Requests"
```

## Updating the Application

To deploy a new version:

```bash
# Using the deployment script
./deploy.sh prod v1.1.0

# Or manually
az containerapp update \
  --name infra-rag-api \
  --resource-group <resource-group> \
  --image <acr-name>.azurecr.io/infra-rag-api:v1.1.0
```

## Troubleshooting

### Container fails to start

1. Check logs: `az containerapp logs show --name infra-rag-api --resource-group <rg> --follow`
2. Verify environment variables are set correctly
3. Ensure managed identity has access to all Azure resources
4. Check that Azure resources are in the same region (Canada East/Central)

### Authentication errors

1. Verify managed identity is enabled: `--system-assigned` flag
2. Check RBAC assignments are created
3. Ensure Azure resources allow managed identity access

### Performance issues

1. Review resource limits (CPU/memory)
2. Check scaling configuration
3. Monitor Application Insights for bottlenecks
4. Consider increasing max replicas

## Security Best Practices

1. **Use Managed Identity**: Avoid storing credentials as environment variables
2. **Enable HTTPS only**: Set `allowInsecure: false` in ingress
3. **Restrict CORS**: Set specific origins instead of `*` in production
4. **Network isolation**: Consider using Virtual Networks
5. **Private endpoints**: Use private endpoints for Azure resources
6. **Secrets management**: Store secrets in Azure Key Vault

## Cost Optimization

1. **Scale to zero**: For non-production, set `minReplicas: 0`
2. **Right-size resources**: Monitor usage and adjust CPU/memory
3. **Use spot instances**: Consider spot pricing for dev/test
4. **Resource cleanup**: Delete unused revisions and environments

## Related Documentation

- [Azure Container Apps Documentation](https://learn.microsoft.com/en-us/azure/container-apps/)
- [FastAPI Deployment Guide](https://fastapi.tiangolo.com/deployment/)
- [Azure Managed Identity](https://learn.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/)
