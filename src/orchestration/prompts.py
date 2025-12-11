"""System prompts for the infrastructure-aware assistant.

This module contains all prompt templates used by the orchestration layer
to guide the LLM's behavior when answering infrastructure questions.
"""

from typing import Any

SYSTEM_PROMPT_TEMPLATE = """You are an expert Azure cloud infrastructure assistant. You help users understand, manage, and troubleshoot their Azure infrastructure and Terraform configurations.

## Your Capabilities

You have access to tools that allow you to:
1. **Search** across Azure resources, Terraform code, and Git history
2. **Query** Azure Resource Graph directly using Kusto (KQL)
3. **Retrieve** detailed information about specific resources
4. **Analyze** Terraform plans to explain what will change
5. **Trace** relationships between Azure resources and their Terraform definitions
6. **Show** Git history for infrastructure changes

## How to Respond

1. **Always use tools** to get current information. Never make assumptions about what resources exist.
2. **Be specific** - include resource names, IDs, and file paths in your answers.
3. **Show your work** - explain which tools you used and what you found.
4. **Cite sources** - reference the specific resources, Terraform files, or commits that support your answer.
5. **Handle errors gracefully** - if a tool fails, explain what went wrong and suggest alternatives.

## Query Patterns

When users ask questions, follow these patterns:

**"What resources...?" / "List all..."**
→ Use `search_infrastructure` with appropriate filters, or `query_resource_graph` for complex queries.

**"Show me the Terraform for..."**
→ First find the resource, then use `get_resource_terraform` to find the IaC definition.

**"What changed..." / "Who modified..."**
→ Use `get_git_history` to find relevant commits, then `get_commit_details` for specifics.

**"What will this plan do?"**
→ Use `get_terraform_plan` or `analyze_terraform_plan` for AI-generated analysis.

**"What depends on..." / "What would be affected..."**
→ Use `get_resource_dependencies` to traverse the relationship graph.

## Current Context

{context}

## Important Notes

- You can only READ information, not modify resources.
- Be careful with sensitive information - don't expose secrets or credentials.
- If a query might return too many results, use filters to narrow down.
- Always verify information is current - data may be up to 15 minutes old.
"""


def get_system_prompt(user_context: dict[str, Any] | None = None) -> str:
    """Generate system prompt with user context.

    Args:
        user_context: Optional context about the user including:
            - subscriptions: List of Azure subscription IDs
            - user_name: User's display name
            - user_id: User's unique ID
            - permissions: User's permission level
            - preferences: User preferences dict

    Returns:
        Formatted system prompt string
    """
    context_parts = []

    if user_context:
        if "subscriptions" in user_context:
            subs = user_context["subscriptions"]
            if isinstance(subs, list):
                context_parts.append(f"Available subscriptions: {', '.join(subs)}")

        if "user_name" in user_context:
            context_parts.append(f"User: {user_context['user_name']}")

        if "permissions" in user_context:
            context_parts.append(f"Permissions: {user_context['permissions']}")

        if "preferences" in user_context:
            prefs = user_context["preferences"]
            if isinstance(prefs, dict):
                if prefs.get("default_subscription"):
                    context_parts.append(
                        f"Default subscription: {prefs['default_subscription']}"
                    )
                if prefs.get("preferred_region"):
                    context_parts.append(f"Preferred region: {prefs['preferred_region']}")

    context = "\n".join(context_parts) if context_parts else "No specific context provided."

    return SYSTEM_PROMPT_TEMPLATE.format(context=context)


# Additional prompts for specific tasks

PLAN_ANALYSIS_PROMPT = """Analyze this Terraform plan and provide:

1. **Summary**: What are the main changes in 2-3 sentences?
2. **Risk Level**: Rate as LOW, MEDIUM, or HIGH with justification
3. **Key Changes**: List the most important changes (max 5)
4. **Recommendations**: Any concerns or suggestions?

Consider these factors for risk assessment:
- Deletions or replacements are higher risk than additions
- Changes to networking, security groups, or IAM are higher risk
- Production resources are higher risk than development
- Stateful resources (databases, storage) are higher risk

Plan details:
{plan_json}
"""


ERROR_RECOVERY_PROMPT = """The previous tool call failed with error: {error}

Suggest alternative approaches to answer the user's question:
{user_question}

Consider:
- Different tools that might work
- Modified queries
- Manual alternatives the user could try
"""


SUMMARIZATION_PROMPT = """Summarize the following conversation in 2-3 sentences, focusing on:
- Key topics discussed
- Important findings or conclusions
- Any actions taken or recommended

Keep the summary concise but informative enough to provide context for continuing the conversation.

Conversation:
{conversation}
"""


RESOURCE_EXPLANATION_PROMPT = """Explain this Azure resource in plain language:

Resource Type: {resource_type}
Resource Name: {resource_name}
Location: {location}
Properties:
{properties}

Provide:
1. What this resource does (1-2 sentences)
2. Key configuration details that matter
3. Any relationships with other resources
"""


def get_plan_analysis_prompt(plan_json: str) -> str:
    """Generate prompt for Terraform plan analysis.

    Args:
        plan_json: JSON representation of the Terraform plan

    Returns:
        Formatted analysis prompt
    """
    return PLAN_ANALYSIS_PROMPT.format(plan_json=plan_json)


def get_error_recovery_prompt(error: str, user_question: str) -> str:
    """Generate prompt for error recovery suggestions.

    Args:
        error: The error that occurred
        user_question: The original user question

    Returns:
        Formatted error recovery prompt
    """
    return ERROR_RECOVERY_PROMPT.format(error=error, user_question=user_question)


def get_summarization_prompt(conversation: str) -> str:
    """Generate prompt for conversation summarization.

    Args:
        conversation: The conversation text to summarize

    Returns:
        Formatted summarization prompt
    """
    return SUMMARIZATION_PROMPT.format(conversation=conversation)


def get_resource_explanation_prompt(
    resource_type: str,
    resource_name: str,
    location: str,
    properties: str,
) -> str:
    """Generate prompt for resource explanation.

    Args:
        resource_type: Azure resource type
        resource_name: Resource name
        location: Azure region
        properties: JSON properties string

    Returns:
        Formatted explanation prompt
    """
    return RESOURCE_EXPLANATION_PROMPT.format(
        resource_type=resource_type,
        resource_name=resource_name,
        location=location,
        properties=properties,
    )
