"""Unit tests for orchestration prompts."""

import pytest

from src.orchestration.prompts import (
    get_system_prompt,
    get_plan_analysis_prompt,
    get_error_recovery_prompt,
    get_summarization_prompt,
    get_resource_explanation_prompt,
    SYSTEM_PROMPT_TEMPLATE,
    PLAN_ANALYSIS_PROMPT,
    ERROR_RECOVERY_PROMPT,
    SUMMARIZATION_PROMPT,
)


class TestSystemPromptTemplate:
    """Tests for system prompt template."""

    def test_template_has_context_placeholder(self):
        """Test that template has context placeholder."""
        assert "{context}" in SYSTEM_PROMPT_TEMPLATE

    def test_template_mentions_capabilities(self):
        """Test that template describes capabilities."""
        assert "Search" in SYSTEM_PROMPT_TEMPLATE
        assert "Query" in SYSTEM_PROMPT_TEMPLATE
        assert "Terraform" in SYSTEM_PROMPT_TEMPLATE

    def test_template_mentions_tools(self):
        """Test that template mentions tool names."""
        assert "search_infrastructure" in SYSTEM_PROMPT_TEMPLATE
        assert "get_resource_terraform" in SYSTEM_PROMPT_TEMPLATE


class TestGetSystemPrompt:
    """Tests for get_system_prompt function."""

    def test_no_context(self):
        """Test prompt with no context."""
        prompt = get_system_prompt()

        assert "No specific context provided" in prompt
        assert "Azure" in prompt

    def test_with_user_name(self):
        """Test prompt with user name."""
        prompt = get_system_prompt({"user_name": "Alice"})

        assert "User: Alice" in prompt

    def test_with_subscriptions(self):
        """Test prompt with subscriptions."""
        prompt = get_system_prompt({
            "subscriptions": ["sub-1", "sub-2", "sub-3"]
        })

        assert "sub-1" in prompt
        assert "sub-2" in prompt
        assert "sub-3" in prompt

    def test_with_permissions(self):
        """Test prompt with permissions."""
        prompt = get_system_prompt({"permissions": "read-only"})

        assert "Permissions: read-only" in prompt

    def test_with_preferences(self):
        """Test prompt with user preferences."""
        prompt = get_system_prompt({
            "preferences": {
                "default_subscription": "sub-main",
                "preferred_region": "canadaeast",
            }
        })

        assert "sub-main" in prompt
        assert "canadaeast" in prompt

    def test_with_all_context(self):
        """Test prompt with all context fields."""
        prompt = get_system_prompt({
            "user_name": "Bob",
            "subscriptions": ["sub-1"],
            "permissions": "admin",
            "preferences": {
                "default_subscription": "sub-1",
            }
        })

        assert "Bob" in prompt
        assert "sub-1" in prompt
        assert "admin" in prompt


class TestPlanAnalysisPrompt:
    """Tests for plan analysis prompt."""

    def test_template_structure(self):
        """Test template has required sections."""
        assert "Summary" in PLAN_ANALYSIS_PROMPT
        assert "Risk Level" in PLAN_ANALYSIS_PROMPT
        assert "Key Changes" in PLAN_ANALYSIS_PROMPT
        assert "Recommendations" in PLAN_ANALYSIS_PROMPT

    def test_get_plan_analysis_prompt(self):
        """Test generating plan analysis prompt."""
        plan_json = '{"changes": [{"action": "create"}]}'
        prompt = get_plan_analysis_prompt(plan_json)

        assert plan_json in prompt
        assert "Summary" in prompt

    def test_mentions_risk_factors(self):
        """Test that template mentions risk factors."""
        assert "Deletions" in PLAN_ANALYSIS_PROMPT
        assert "networking" in PLAN_ANALYSIS_PROMPT.lower()
        assert "security" in PLAN_ANALYSIS_PROMPT.lower()


class TestErrorRecoveryPrompt:
    """Tests for error recovery prompt."""

    def test_template_structure(self):
        """Test template has required sections."""
        assert "{error}" in ERROR_RECOVERY_PROMPT
        assert "{user_question}" in ERROR_RECOVERY_PROMPT

    def test_get_error_recovery_prompt(self):
        """Test generating error recovery prompt."""
        prompt = get_error_recovery_prompt(
            error="Resource not found",
            user_question="Show me VM details",
        )

        assert "Resource not found" in prompt
        assert "Show me VM details" in prompt

    def test_suggests_alternatives(self):
        """Test that template suggests alternatives."""
        assert "alternative" in ERROR_RECOVERY_PROMPT.lower()
        assert "tools" in ERROR_RECOVERY_PROMPT.lower()


class TestSummarizationPrompt:
    """Tests for summarization prompt."""

    def test_template_structure(self):
        """Test template has required placeholder."""
        assert "{conversation}" in SUMMARIZATION_PROMPT

    def test_get_summarization_prompt(self):
        """Test generating summarization prompt."""
        conversation = "User: Hello\nAssistant: Hi there!"
        prompt = get_summarization_prompt(conversation)

        assert conversation in prompt
        assert "summary" in prompt.lower()

    def test_mentions_concise(self):
        """Test that template asks for concise summary."""
        assert "2-3 sentences" in SUMMARIZATION_PROMPT


class TestResourceExplanationPrompt:
    """Tests for resource explanation prompt."""

    def test_get_resource_explanation_prompt(self):
        """Test generating resource explanation prompt."""
        prompt = get_resource_explanation_prompt(
            resource_type="Microsoft.Compute/virtualMachines",
            resource_name="my-vm",
            location="canadaeast",
            properties='{"vmSize": "Standard_D2s_v3"}',
        )

        assert "Microsoft.Compute/virtualMachines" in prompt
        assert "my-vm" in prompt
        assert "canadaeast" in prompt
        assert "vmSize" in prompt

    def test_asks_for_explanation_parts(self):
        """Test that prompt asks for specific parts."""
        prompt = get_resource_explanation_prompt(
            resource_type="test",
            resource_name="test",
            location="test",
            properties="{}",
        )

        assert "What this resource does" in prompt
        assert "configuration" in prompt.lower()
        assert "relationships" in prompt.lower()


class TestPromptConsistency:
    """Tests for prompt consistency and quality."""

    def test_no_double_braces(self):
        """Test that prompts don't have unintended double braces."""
        # Single braces are for format strings, double would break
        prompts = [
            SYSTEM_PROMPT_TEMPLATE,
            PLAN_ANALYSIS_PROMPT,
            ERROR_RECOVERY_PROMPT,
            SUMMARIZATION_PROMPT,
        ]

        for prompt in prompts:
            # Should not have {{ or }} except in code blocks
            lines = prompt.split('\n')
            for line in lines:
                if not line.strip().startswith('```'):
                    # Allow {{ in code examples but not elsewhere
                    assert '{{' not in line or 'code' in line.lower()

    def test_prompts_are_markdown_friendly(self):
        """Test that prompts use proper markdown formatting."""
        prompts = [SYSTEM_PROMPT_TEMPLATE, PLAN_ANALYSIS_PROMPT]

        for prompt in prompts:
            # Should have headers
            assert "##" in prompt or "**" in prompt
