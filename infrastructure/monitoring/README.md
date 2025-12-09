# Monitoring and Alerting

This directory contains monitoring configurations for the Infra-Aware RAG API.

## Components

### 1. Application Insights
Collects telemetry data including:
- Request/response metrics
- Exception tracking
- Custom metrics and events
- User activity tracking
- Dependency calls

### 2. Azure Dashboard
Pre-configured dashboard with key metrics:
- **Availability**: API uptime percentage
- **Request Rate**: Requests per minute
- **Response Time**: Average response duration
- **Failed Requests**: HTTP 4xx and 5xx errors
- **Top Endpoints**: Most frequently called endpoints
- **Top Users**: Users by request count
- **Exceptions**: Error tracking
- **Request Timeline**: Historical trends

### 3. Alerts
Automated alerts for critical issues:
- **High Error Rate**: > 5% failed requests
- **High Response Time**: > 2 seconds average
- **Low Availability**: < 99% uptime
- **High Exception Rate**: > 10 exceptions per 5 minutes

## Deployment

### Prerequisites
- Azure CLI installed and authenticated
- Application Insights resource created
- Resource group created

### Deploy Dashboard

```bash
# Deploy the monitoring dashboard
az deployment group create \
  --resource-group <resource-group-name> \
  --template-file dashboard.json \
  --parameters \
    applicationInsightsName=<app-insights-name> \
    dashboardName="Infra-RAG-API-Dashboard"
```

### Deploy Alerts

```bash
# Deploy alerts and action groups
az deployment group create \
  --resource-group <resource-group-name> \
  --template-file alerts.json \
  --parameters \
    applicationInsightsName=<app-insights-name> \
    emailRecipients='["email1@example.com", "email2@example.com"]'
```

## Viewing the Dashboard

1. Go to the Azure Portal
2. Navigate to **Dashboards**
3. Select **Infra-RAG-API-Dashboard**

Or use direct link:
```
https://portal.azure.com/#@<tenant-id>/dashboard/arm/<subscription-id>/<resource-group-name>/providers/Microsoft.Portal/dashboards/<dashboard-name>
```

## Custom Queries

### Top API Endpoints by Usage

```kusto
customMetrics
| where name == "api_request_count"
| extend endpoint = tostring(customDimensions.endpoint)
| summarize TotalRequests = sum(value) by endpoint
| order by TotalRequests desc
| take 10
```

### User Activity by Hour

```kusto
customMetrics
| where name == "api_request_count"
| extend user_id = tostring(customDimensions.user_id)
| where isnotempty(user_id)
| summarize RequestCount = sum(value) by user_id, bin(timestamp, 1h)
| render timechart
```

### Error Rate Over Time

```kusto
requests
| summarize
    TotalRequests = count(),
    FailedRequests = countif(success == false)
    by bin(timestamp, 5m)
| extend ErrorRate = (FailedRequests * 100.0) / TotalRequests
| render timechart
```

### Slowest Endpoints

```kusto
requests
| summarize
    AvgDuration = avg(duration),
    P95Duration = percentile(duration, 95),
    RequestCount = count()
    by name
| where RequestCount > 10
| order by P95Duration desc
| take 10
```

### User Request Patterns

```kusto
customMetrics
| where name == "api_request_count"
| extend
    user_id = tostring(customDimensions.user_id),
    endpoint = tostring(customDimensions.endpoint),
    method = tostring(customDimensions.method)
| where isnotempty(user_id)
| summarize
    TotalRequests = sum(value),
    UniqueEndpoints = dcount(endpoint)
    by user_id
| order by TotalRequests desc
```

## Metrics Reference

### Standard Metrics
| Metric | Description | Unit |
|--------|-------------|------|
| `requests/count` | Total number of requests | Count |
| `requests/duration` | Average response time | Milliseconds |
| `requests/failed` | Failed requests (4xx, 5xx) | Count |
| `availabilityResults/availabilityPercentage` | Availability percentage | Percent |
| `exceptions/count` | Total exceptions | Count |

### Custom Metrics
| Metric | Description | Dimensions |
|--------|-------------|------------|
| `api_request_count` | API request counter | user_id, endpoint, method, status_code |
| `api_request_duration` | Request duration | user_id, endpoint, method |

## Setting Up Alerts

### Email Notifications
Configure email recipients in the `alerts.json` parameters:

```json
{
  "emailRecipients": [
    "devops@example.com",
    "oncall@example.com"
  ]
}
```

### Webhook Notifications
Add webhook receivers to the action group:

```json
{
  "webhookReceivers": [
    {
      "name": "Slack",
      "serviceUri": "https://hooks.slack.com/services/xxx/yyy/zzz"
    }
  ]
}
```

### SMS Notifications
Add SMS receivers:

```json
{
  "smsReceivers": [
    {
      "name": "OnCall",
      "countryCode": "1",
      "phoneNumber": "5551234567"
    }
  ]
}
```

## Best Practices

1. **Review alerts weekly** - Tune thresholds based on actual usage
2. **Set up multiple notification channels** - Don't rely on email alone
3. **Use severity levels appropriately**:
   - Severity 0: Critical (immediate action required)
   - Severity 1: Error (action required soon)
   - Severity 2: Warning (investigate)
   - Severity 3: Informational (awareness)
4. **Monitor dashboard daily** - Check for anomalies and trends
5. **Archive old data** - Configure data retention policies
6. **Test alerts** - Trigger test alerts to verify notifications work

## Troubleshooting

### No data in Application Insights
1. Check that `APPLICATIONINSIGHTS_CONNECTION_STRING` is set
2. Verify the connection string format
3. Check application logs for initialization errors
4. Ensure the API is receiving traffic

### Alerts not firing
1. Verify alert rules are enabled
2. Check that action group has valid recipients
3. Review alert condition thresholds
4. Check alert evaluation frequency

### Dashboard not loading
1. Verify Application Insights resource exists
2. Check dashboard template deployment succeeded
3. Ensure you have permissions to view the dashboard
4. Try refreshing the browser cache

## Cost Optimization

1. **Sampling**: Configure sampling in Application Insights to reduce ingestion costs
2. **Retention**: Set appropriate data retention (default 90 days)
3. **Log levels**: Use appropriate log levels in production
4. **Alert frequency**: Balance between responsiveness and noise

## Related Documentation

- [Application Insights Overview](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview)
- [Kusto Query Language](https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/)
- [Azure Monitor Alerts](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview)
- [Azure Dashboards](https://learn.microsoft.com/en-us/azure/azure-portal/azure-portal-dashboards)
