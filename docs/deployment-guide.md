# Deployment Guide

This guide covers deploying the Infra-Aware RAG system to production on Azure.

## Architecture Overview

```
                                    ┌─────────────────┐
                                    │   Azure CDN     │
                                    │   (Frontend)    │
                                    └────────┬────────┘
                                             │
┌──────────────┐                    ┌────────┴────────┐
│   Users      │────────────────────│  Azure Front    │
│              │                    │     Door        │
└──────────────┘                    └────────┬────────┘
                                             │
                              ┌──────────────┴─────────────┐
                              │                            │
                     ┌────────┴────────┐          ┌────────┴────────┐
                     │ Container Apps  │          │  Static Web     │
                     │  (API Backend)  │          │  Apps (UI)      │
                     └────────┬────────┘          └─────────────────┘
                              │
        ┌─────────────────────┼───────────────────┐
        │                     │                   │
┌───────┴───────┐    ┌────────┴──────┐    ┌───────┴────────┐
│ Azure OpenAI  │    │ Azure AI      │    │   Cosmos DB    │
│               │    │  Search       │    │ (NoSQL+Gremlin)│
└───────────────┘    └───────────────┘    └────────────────┘
```

## Prerequisites

### Required Azure Resources

All resources must be deployed in **Canada East** or **Canada Central**.

| Resource | SKU | Purpose |
|----------|-----|---------|
| Azure OpenAI | Standard | LLM chat and embeddings |
| Azure AI Search | Standard | Vector and keyword search |
| Cosmos DB (NoSQL) | Serverless | Document storage |
| Cosmos DB (Gremlin) | Serverless | Graph relationships |
| Container Registry | Basic | Docker images |
| Container Apps Env | Consumption | API hosting |
| Static Web Apps | Free | Frontend hosting |

### Required Tools

- Azure CLI (`az`) v2.50+
- Docker Desktop
- Node.js 18+ (for frontend build)
- Python 3.11+ (for local testing)

### Required Permissions

- Contributor role on the resource group
- User Access Administrator (for RBAC assignments)
- Entra ID App Registration permissions

## Step 1: Create Azure Resources

### Option A: Using Azure CLI

```bash
# Set variables
RESOURCE_GROUP="rg-infra-rag-prod"
LOCATION="canadaeast"

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create Azure OpenAI
az cognitiveservices account create \
  --name "oai-infra-rag" \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --kind OpenAI \
  --sku S0

# Deploy GPT-4o model
az cognitiveservices account deployment create \
  --name "oai-infra-rag" \
  --resource-group $RESOURCE_GROUP \
  --deployment-name "gpt-4o" \
  --model-name "gpt-4o" \
  --model-version "0613" \
  --model-format OpenAI \
  --sku-name "Standard" \
  --sku-capacity 10

# Deploy embedding model
az cognitiveservices account deployment create \
  --name "oai-infra-rag" \
  --resource-group $RESOURCE_GROUP \
  --deployment-name "text-embedding-3-large" \
  --model-name "text-embedding-3-large" \
  --model-version "1" \
  --model-format OpenAI \
  --sku-name "Standard" \
  --sku-capacity 10

# Create Azure AI Search
az search service create \
  --name "srch-infra-rag" \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku standard

# Create Cosmos DB account
az cosmosdb create \
  --name "cosmos-infra-rag" \
  --resource-group $RESOURCE_GROUP \
  --locations regionName=$LOCATION \
  --capabilities EnableGremlin EnableServerless

# Create Container Registry
az acr create \
  --name "acrinfrarag" \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Basic \
  --admin-enabled true

# Create Container Apps Environment
az containerapp env create \
  --name "cae-infra-rag" \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION
```

### Option B: Using Terraform (Recommended)

See [infrastructure/terraform/](../infrastructure/terraform/) for Terraform configurations.

## Step 2: Configure Entra ID Authentication

### Create App Registration

```bash
# Create app registration
APP_ID=$(az ad app create \
  --display-name "Infra-RAG-API" \
  --sign-in-audience AzureADMyOrg \
  --query appId -o tsv)

# Create service principal
az ad sp create --id $APP_ID

# Add API scope
az ad app update --id $APP_ID --identifier-uris "api://$APP_ID"

# Create frontend app registration
FRONTEND_APP_ID=$(az ad app create \
  --display-name "Infra-RAG-Frontend" \
  --sign-in-audience AzureADMyOrg \
  --public-client-redirect-uris "http://localhost:5173" "https://your-frontend.azurestaticapps.net" \
  --query appId -o tsv)
```

### Configure API Permissions

In Azure Portal:
1. Go to Entra ID > App registrations > Infra-RAG-Frontend
2. Add API permission for Infra-RAG-API
3. Grant admin consent

## Step 3: Deploy the API

### Build and Push Docker Image

```bash
cd /path/to/infra-aware-RAG

# Build image
docker build -t infra-rag-api:latest .

# Login to ACR
az acr login --name acrinfrarag

# Tag and push
docker tag infra-rag-api:latest acrinfrarag.azurecr.io/infra-rag-api:v1.0.0
docker push acrinfrarag.azurecr.io/infra-rag-api:v1.0.0
```

### Deploy to Container Apps

Use the automated deployment script:

```bash
cd infrastructure/containerapp
./deploy.sh prod v1.0.0
```

Or deploy manually:

```bash
# Get resource endpoints
OPENAI_ENDPOINT=$(az cognitiveservices account show \
  --name oai-infra-rag \
  --resource-group $RESOURCE_GROUP \
  --query properties.endpoint -o tsv)

SEARCH_ENDPOINT=$(az search service show \
  --name srch-infra-rag \
  --resource-group $RESOURCE_GROUP \
  --query hostName -o tsv)

COSMOS_ENDPOINT=$(az cosmosdb show \
  --name cosmos-infra-rag \
  --resource-group $RESOURCE_GROUP \
  --query documentEndpoint -o tsv)

# Create Container App
az containerapp create \
  --name infra-rag-api \
  --resource-group $RESOURCE_GROUP \
  --environment cae-infra-rag \
  --image acrinfrarag.azurecr.io/infra-rag-api:v1.0.0 \
  --target-port 8000 \
  --ingress external \
  --registry-server acrinfrarag.azurecr.io \
  --registry-identity system \
  --cpu 1.0 \
  --memory 2.0Gi \
  --min-replicas 1 \
  --max-replicas 10 \
  --env-vars \
    "AZURE_OPENAI_ENDPOINT=$OPENAI_ENDPOINT" \
    "AZURE_SEARCH_ENDPOINT=https://$SEARCH_ENDPOINT" \
    "COSMOS_DB_ENDPOINT=$COSMOS_ENDPOINT" \
    "AZURE_AD_TENANT_ID=$TENANT_ID" \
    "AZURE_AD_CLIENT_ID=$APP_ID" \
  --system-assigned
```

### Configure RBAC for Managed Identity

```bash
# Get Container App identity
IDENTITY_ID=$(az containerapp show \
  --name infra-rag-api \
  --resource-group $RESOURCE_GROUP \
  --query identity.principalId -o tsv)

# Azure OpenAI
az role assignment create \
  --assignee $IDENTITY_ID \
  --role "Cognitive Services OpenAI User" \
  --scope $(az cognitiveservices account show --name oai-infra-rag -g $RESOURCE_GROUP --query id -o tsv)

# Azure AI Search
az role assignment create \
  --assignee $IDENTITY_ID \
  --role "Search Index Data Contributor" \
  --scope $(az search service show --name srch-infra-rag -g $RESOURCE_GROUP --query id -o tsv)

# Cosmos DB
az role assignment create \
  --assignee $IDENTITY_ID \
  --role "Cosmos DB Account Reader Role" \
  --scope $(az cosmosdb show --name cosmos-infra-rag -g $RESOURCE_GROUP --query id -o tsv)
```

## Step 4: Deploy the Frontend

### Build Frontend

```bash
cd frontend

# Install dependencies
npm install

# Create production .env
cat > .env.production << EOF
VITE_API_BASE_URL=https://infra-rag-api.<region>.azurecontainerapps.io/api/v1
VITE_AZURE_CLIENT_ID=$FRONTEND_APP_ID
VITE_AZURE_TENANT_ID=$TENANT_ID
EOF

# Build
npm run build
```

### Deploy to Static Web Apps

```bash
# Create Static Web App
az staticwebapp create \
  --name "swa-infra-rag" \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --source "." \
  --branch main \
  --app-location "/frontend" \
  --output-location "dist"

# Or deploy build folder directly
az staticwebapp upload \
  --name swa-infra-rag \
  --source frontend/dist
```

## Step 5: Initialize Search Index

Run the indexing pipeline to populate the search index:

```bash
# SSH or exec into the container, or run locally
python -m src.indexing.orchestrator --init

# Or trigger via API
curl -X POST https://your-api.azurecontainerapps.io/api/v1/admin/reindex \
  -H "Authorization: Bearer $TOKEN"
```

## Step 6: Configure Monitoring

### Deploy Monitoring Dashboard

```bash
cd infrastructure/monitoring

# Deploy dashboard
az portal dashboard create \
  --resource-group $RESOURCE_GROUP \
  --input-path dashboard.json

# Deploy alerts
az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-file alerts.json
```

### Enable Application Insights

```bash
# Create Application Insights
az monitor app-insights component create \
  --app infra-rag-insights \
  --location $LOCATION \
  --resource-group $RESOURCE_GROUP

# Get instrumentation key
INSTRUMENTATION_KEY=$(az monitor app-insights component show \
  --app infra-rag-insights \
  --resource-group $RESOURCE_GROUP \
  --query instrumentationKey -o tsv)

# Update Container App
az containerapp update \
  --name infra-rag-api \
  --resource-group $RESOURCE_GROUP \
  --set-env-vars "APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=$INSTRUMENTATION_KEY"
```

## Environment Configuration

### Production Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_OPENAI_ENDPOINT` | OpenAI endpoint | `https://oai-infra-rag.openai.azure.com` |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | GPT model name | `gpt-4o` |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Embedding model | `text-embedding-3-large` |
| `AZURE_SEARCH_ENDPOINT` | AI Search endpoint | `https://srch-infra-rag.search.windows.net` |
| `AZURE_SEARCH_INDEX_NAME` | Index name | `infra-rag-index` |
| `COSMOS_DB_ENDPOINT` | Cosmos DB endpoint | `https://cosmos-infra-rag.documents.azure.com` |
| `COSMOS_DB_DATABASE` | Database name | `infra-rag` |
| `AZURE_AD_TENANT_ID` | Entra ID tenant | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `AZURE_AD_CLIENT_ID` | API app ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `CORS_ORIGINS` | Allowed origins | `https://swa-infra-rag.azurestaticapps.net` |

## Updating Deployments

### API Updates

```bash
# Build new version
docker build -t infra-rag-api:v1.1.0 .
docker tag infra-rag-api:v1.1.0 acrinfrarag.azurecr.io/infra-rag-api:v1.1.0
docker push acrinfrarag.azurecr.io/infra-rag-api:v1.1.0

# Deploy
az containerapp update \
  --name infra-rag-api \
  --resource-group $RESOURCE_GROUP \
  --image acrinfrarag.azurecr.io/infra-rag-api:v1.1.0
```

### Frontend Updates

```bash
cd frontend
npm run build
az staticwebapp upload --name swa-infra-rag --source dist
```

## Rollback Procedures

### API Rollback

```bash
# List revisions
az containerapp revision list \
  --name infra-rag-api \
  --resource-group $RESOURCE_GROUP

# Activate previous revision
az containerapp revision activate \
  --revision infra-rag-api--<previous-revision> \
  --resource-group $RESOURCE_GROUP
```

### Database Rollback

Cosmos DB provides point-in-time restore for continuous backup accounts.

## Security Checklist

- [ ] HTTPS only (no HTTP)
- [ ] Entra ID authentication enabled
- [ ] Managed Identity for all Azure services
- [ ] CORS restricted to specific origins
- [ ] Rate limiting configured
- [ ] Network isolation (VNet integration)
- [ ] Private endpoints for Azure services
- [ ] Secrets in Key Vault
- [ ] Audit logging enabled
- [ ] DDoS protection enabled

## Cost Estimation

| Resource | SKU | Estimated Monthly Cost |
|----------|-----|----------------------|
| Azure OpenAI | Pay-per-use | $50-500 (usage dependent) |
| Azure AI Search | Standard | $250 |
| Cosmos DB | Serverless | $25-100 |
| Container Apps | Consumption | $50-200 |
| Static Web Apps | Free | $0 |
| Container Registry | Basic | $5 |

**Total Estimated**: $380-1,055/month (varies by usage)

## Related Documentation

- [Container Apps Deployment](../infrastructure/containerapp/README.md)
- [Monitoring Setup](../infrastructure/monitoring/README.md)
- [Troubleshooting Guide](troubleshooting.md)
