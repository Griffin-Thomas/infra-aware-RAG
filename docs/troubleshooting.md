# Troubleshooting Guide

This guide helps diagnose and resolve common issues with the Infra-Aware RAG system.

## Quick Diagnostics

### Check System Health

```bash
# API health check
curl http://localhost:8000/health

# Readiness check (shows all dependencies)
curl http://localhost:8000/ready
```

### View Logs

```bash
# API server logs (local)
uvicorn src.api.main:app --reload --log-level debug

# Container Apps logs
az containerapp logs show \
  --name infra-rag-api \
  --resource-group <rg> \
  --follow
```

---

## Connection Issues

### "Could not connect to API"

**Symptoms:**
- CLI shows "Could not connect to API at http://localhost:8000/api/v1"
- Frontend shows network error

**Solutions:**

1. **Check if API is running:**
   ```bash
   curl http://localhost:8000/health
   ```

2. **Verify correct URL:**
   ```bash
   # Check CLI config
   infra-rag config

   # Set correct URL
   export INFRA_RAG_API_URL=http://localhost:8000/api/v1
   ```

3. **Check firewall/network:**
   - Ensure port 8000 is not blocked
   - For containers, verify port mapping

### "Connection refused" on Azure services

**Symptoms:**
- API starts but fails to connect to Azure OpenAI, Search, or Cosmos DB

**Solutions:**

1. **Verify environment variables:**
   ```bash
   # Check endpoints are set
   echo $AZURE_OPENAI_ENDPOINT
   echo $AZURE_SEARCH_ENDPOINT
   echo $COSMOS_DB_ENDPOINT
   ```

2. **Check managed identity permissions:**
   ```bash
   # List role assignments
   az role assignment list --assignee <identity-id>
   ```

3. **Verify network access:**
   - Check if Azure services have public access enabled
   - For private endpoints, ensure VNet integration is configured

---

## Authentication Issues

### "401 Unauthorized"

**Symptoms:**
- API returns 401 status code
- "Invalid or expired token" error

**Solutions:**

1. **Re-authenticate with Azure CLI:**
   ```bash
   az logout
   az login
   az account get-access-token
   ```

2. **Check token expiration:**
   - Azure CLI tokens expire after 1 hour
   - Re-run `az login` to refresh

3. **Verify app registration:**
   - Check Entra ID app registration exists
   - Verify client ID is correct

### "403 Forbidden"

**Symptoms:**
- Authenticated but access denied

**Solutions:**

1. **Check RBAC assignments:**
   ```bash
   # View your role assignments
   az role assignment list --assignee $(az ad signed-in-user show --query id -o tsv)
   ```

2. **Verify subscription access:**
   - Ensure you have access to the Azure subscription
   - Check if you're in the correct tenant

### Frontend: "AADSTS50011" or redirect errors

**Symptoms:**
- Login redirects fail
- MSAL authentication errors

**Solutions:**

1. **Check redirect URIs:**
   - In Entra ID App Registration, verify redirect URIs include:
     - `http://localhost:5173` (development)
     - `https://your-app.azurestaticapps.net` (production)

2. **Clear browser cache:**
   - Clear cookies and local storage
   - Try incognito/private window

3. **Verify frontend config:**
   ```javascript
   // Check .env.local or .env.production
   VITE_AZURE_CLIENT_ID=<correct-client-id>
   VITE_AZURE_TENANT_ID=<correct-tenant-id>
   ```

---

## Search Issues

### "No results found"

**Symptoms:**
- Search queries return empty results

**Solutions:**

1. **Check if data is indexed:**
   ```bash
   # Via API
   curl "http://localhost:8000/api/v1/search" \
     -X POST -H "Content-Type: application/json" \
     -d '{"query": "*", "top": 1}'
   ```

2. **Run indexing pipeline:**
   ```bash
   python -m src.indexing.orchestrator --reindex
   ```

3. **Verify search index exists:**
   ```bash
   az search index list --service-name <search-service> --resource-group <rg>
   ```

### "Search timeout" or slow queries

**Symptoms:**
- Queries take > 30 seconds
- Timeout errors

**Solutions:**

1. **Reduce result count:**
   ```bash
   infra-rag search -n 5 "query"  # Instead of default 10
   ```

2. **Use filters:**
   ```bash
   infra-rag search -t azure_resource "query"  # Filter by type
   ```

3. **Check Azure AI Search metrics:**
   - Review query latency in Azure Portal
   - Consider scaling up search service tier

### Poor search relevance

**Symptoms:**
- Results don't match query intent
- Low relevance scores

**Solutions:**

1. **Try different search modes:**
   ```bash
   infra-rag search -m vector "query"   # Semantic search
   infra-rag search -m keyword "query"  # Traditional search
   infra-rag search -m hybrid "query"   # Combined (default)
   ```

2. **Use more specific queries:**
   - Include resource names, types, or identifiers
   - Add context: "production", "Canada East", etc.

---

## LLM/Chat Issues

### "Model not found" or deployment errors

**Symptoms:**
- Chat returns 404 or deployment not found
- "The API deployment for this resource does not exist"

**Solutions:**

1. **Verify deployment name:**
   ```bash
   az cognitiveservices account deployment list \
     --name <openai-account> \
     --resource-group <rg>
   ```

2. **Check environment variables:**
   ```bash
   # Ensure these match your deployment names
   AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o
   AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
   ```

### "Rate limit exceeded"

**Symptoms:**
- 429 status code
- "Rate limit exceeded" error

**Solutions:**

1. **Wait and retry:**
   - Rate limits typically reset after 1 minute

2. **Check OpenAI quota:**
   ```bash
   az cognitiveservices account show \
     --name <openai-account> \
     --resource-group <rg> \
     --query "properties.quotaLimit"
   ```

3. **Request quota increase:**
   - In Azure Portal, request higher TPM (tokens per minute)

### Incomplete or cut-off responses

**Symptoms:**
- Responses stop mid-sentence
- "Maximum tokens reached" message

**Solutions:**

1. **Check token limits:**
   - Default max tokens may be too low
   - Increase `max_tokens` in configuration

2. **Simplify the query:**
   - Ask more focused questions
   - Avoid requesting large data sets

---

## Database Issues

### Cosmos DB connection failures

**Symptoms:**
- "Failed to connect to Cosmos DB"
- Timeout errors

**Solutions:**

1. **Verify endpoint:**
   ```bash
   az cosmosdb show --name <account> --resource-group <rg> --query documentEndpoint
   ```

2. **Check network rules:**
   - Ensure firewall allows your IP
   - Verify VNet integration if using private endpoints

3. **Test connection:**
   ```python
   from azure.cosmos import CosmosClient
   client = CosmosClient(endpoint, credential)
   list(client.list_databases())
   ```

### Graph database (Gremlin) issues

**Symptoms:**
- Dependency queries fail
- "Gremlin endpoint not found"

**Solutions:**

1. **Verify Gremlin API is enabled:**
   ```bash
   az cosmosdb show --name <account> --query "capabilities"
   ```

2. **Check Gremlin endpoint:**
   - Format: `wss://<account>.gremlin.cosmos.azure.com:443/`

3. **Verify graph exists:**
   ```bash
   az cosmosdb gremlin graph list \
     --account-name <account> \
     --database-name <db> \
     --resource-group <rg>
   ```

---

## Frontend Issues

### Blank page or loading forever

**Symptoms:**
- Frontend shows blank white page
- Infinite loading spinner

**Solutions:**

1. **Check browser console:**
   - Press F12 to open developer tools
   - Look for JavaScript errors

2. **Verify API URL:**
   ```javascript
   // Check network tab for API calls
   // Ensure VITE_API_BASE_URL is correct
   ```

3. **Clear cache and reload:**
   - Hard refresh: Ctrl+Shift+R (Cmd+Shift+R on Mac)
   - Clear local storage

### CORS errors

**Symptoms:**
- "Access-Control-Allow-Origin" errors in console

**Solutions:**

1. **Check API CORS configuration:**
   ```python
   # In src/api/main.py
   CORS_ORIGINS = ["http://localhost:5173", "https://your-app.com"]
   ```

2. **Verify origin matches exactly:**
   - Include/exclude trailing slashes consistently
   - Check protocol (http vs https)

### SSE streaming not working

**Symptoms:**
- Chat messages appear all at once instead of streaming
- "EventSource failed" errors

**Solutions:**

1. **Check browser compatibility:**
   - SSE requires modern browser
   - Try Chrome or Firefox

2. **Verify proxy configuration:**
   - Some proxies buffer SSE responses
   - Disable response buffering

3. **Check API endpoint:**
   ```bash
   # Test streaming manually
   curl -N "http://localhost:8000/api/v1/conversations/<id>/messages" \
     -X POST -H "Content-Type: application/json" \
     -d '{"content": "test", "stream": true}'
   ```

---

## CLI Issues

### "Command not found: infra-rag"

**Symptoms:**
- Shell can't find the `infra-rag` command

**Solutions:**

1. **Install the package:**
   ```bash
   pip install -e .
   ```

2. **Check PATH:**
   ```bash
   # Ensure pip bin directory is in PATH
   echo $PATH | grep -q "$(python -m site --user-base)/bin"
   ```

3. **Use module directly:**
   ```bash
   python -m src.cli.main --help
   ```

### Azure CLI warnings

**Symptoms:**
- "Warning: Could not get Azure CLI token"

**Solutions:**

1. **Login to Azure:**
   ```bash
   az login
   ```

2. **Verify Azure CLI installation:**
   ```bash
   az --version
   ```

3. **The CLI works without auth for local development**

---

## Performance Issues

### Slow API responses

**Solutions:**

1. **Check resource utilization:**
   ```bash
   # Container Apps metrics
   az monitor metrics list --resource <app-id> --metric "CpuUsage"
   ```

2. **Scale up resources:**
   - Increase Container App CPU/memory
   - Scale Azure AI Search tier

3. **Optimize queries:**
   - Use filters to narrow results
   - Reduce `top` parameter

### High memory usage

**Solutions:**

1. **Check for memory leaks:**
   - Monitor memory over time
   - Restart containers periodically

2. **Tune batch sizes:**
   - Reduce embedding batch size
   - Limit concurrent operations

---

## Getting More Help

### Collect Diagnostic Information

When reporting issues, include:

```bash
# System info
python --version
az --version
docker --version

# Configuration
infra-rag config

# Health status
curl http://localhost:8000/ready

# Recent logs
az containerapp logs show --name infra-rag-api -g <rg> --tail 100
```

### Support Channels

- GitHub Issues: Report bugs and feature requests
- Documentation: Check docs/ folder for detailed guides
- Azure Support: For Azure service issues
