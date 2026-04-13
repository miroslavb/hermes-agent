#!/usr/bin/env python3
"""
Unit tests for the rlm_repl tool.
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestRLMToolRegistration(unittest.TestCase):
    """Test that the rlm_repl tool is properly registered."""

    def test_tool_is_registered(self):
        from tools.registry import registry
        # Force import triggers registration
        import tools.rlm_tool  # noqa: F401
        entry = registry._tools.get("rlm_repl")
        self.assertIsNotNone(entry, "rlm_repl should be registered")
        self.assertEqual(entry.toolset, "rlm_repl")
        self.assertEqual(entry.name, "rlm_repl")

    def test_tool_schema_structure(self):
        from tools.registry import registry
        import tools.rlm_tool  # noqa: F401
        entry = registry._tools.get("rlm_repl")
        schema = entry.schema
        self.assertEqual(schema["name"], "rlm_repl")
        self.assertIn("prompt", schema["parameters"]["properties"])
        self.assertIn("prompt", schema["parameters"]["required"])
        self.assertIn("model", schema["parameters"]["properties"])
        self.assertIn("max_depth", schema["parameters"]["properties"])
        self.assertIn("max_iterations", schema["parameters"]["properties"])

    def test_tool_schema_available_via_definitions(self):
        from tools.registry import registry
        import tools.rlm_tool  # noqa: F401
        defs = registry.get_definitions({"rlm_repl"})
        self.assertEqual(len(defs), 1)
        self.assertEqual(defs[0]["type"], "function")
        self.assertEqual(defs[0]["function"]["name"], "rlm_repl")

    def test_toolset_resolution(self):
        from toolsets import resolve_toolset
        tools = resolve_toolset("rlm_repl")
        self.assertIn("rlm_repl", tools)
        self.assertEqual(len(tools), 1)

    def test_in_core_tools(self):
        from toolsets import _HERMES_CORE_TOOLS
        self.assertIn("rlm_repl", _HERMES_CORE_TOOLS)


class TestRLMToolAvailabilityCheck(unittest.TestCase):
    """Test the availability check function."""

    def test_available_when_rlm_and_key_present(self):
        with patch.dict(os.environ, {"NOUS_API_KEY": "test-key"}, clear=False):
            from tools.rlm_tool import check_rlm_requirements
            self.assertTrue(check_rlm_requirements())

    def test_available_with_openrouter_key(self):
        env = os.environ.copy()
        env.pop("NOUS_API_KEY", None)
        env["OPENROUTER_API_KEY"] = "test-key"
        with patch.dict(os.environ, env, clear=False):
            from tools.rlm_tool import check_rlm_requirements
            self.assertTrue(check_rlm_requirements())

    def test_unavailable_without_keys(self):
        env = os.environ.copy()
        env.pop("NOUS_API_KEY", None)
        env.pop("OPENROUTER_API_KEY", None)
        with patch.dict(os.environ, env, clear=False):
            from tools.rlm_tool import check_rlm_requirements
            self.assertFalse(check_rlm_requirements())


class TestRLMToolHandler(unittest.TestCase):
    """Test the tool handler with mocked RLM."""

    def test_missing_prompt_returns_error(self):
        from tools.rlm_tool import rlm_repl_tool
        result = rlm_repl_tool({})
        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("prompt", data["error"].lower())

    def test_empty_prompt_returns_error(self):
        from tools.rlm_tool import rlm_repl_tool
        result = rlm_repl_tool({"prompt": "   "})
        data = json.loads(result)
        self.assertIn("error", data)

    @patch("rlm.RLM")
    def test_successful_completion(self, mock_rlm_cls):
        mock_rlm = MagicMock()
        mock_rlm_cls.return_value = mock_rlm

        mock_result = MagicMock()
        mock_result.response = "The answer is 42"
        mock_result.metadata = MagicMock()
        mock_result.metadata.total_iterations = 5
        mock_result.usage_summary = MagicMock()
        mock_result.usage_summary.total_cost = 0.001
        mock_result.usage_summary.total_input_tokens = 100
        mock_result.usage_summary.total_output_tokens = 50

        mock_rlm.completion.return_value = mock_result

        from tools.rlm_tool import rlm_repl_tool
        result = rlm_repl_tool({
            "prompt": "What is 6 * 7?",
            "model": "test-model",
        })
        data = json.loads(result)

        self.assertEqual(data["response"], "The answer is 42")
        self.assertEqual(data["model"], "test-model")
        self.assertEqual(data["iterations"], 5)
        self.assertIn("usage", data)
        self.assertEqual(data["usage"]["total_cost"], 0.001)

    @patch("rlm.RLM")
    def test_custom_parameters(self, mock_rlm_cls):
        mock_rlm = MagicMock()
        mock_rlm_cls.return_value = mock_rlm

        mock_result = MagicMock()
        mock_result.response = "done"
        mock_result.metadata = None
        mock_result.usage_summary = None
        mock_rlm.completion.return_value = mock_result

        from tools.rlm_tool import rlm_repl_tool
        rlm_repl_tool({
            "prompt": "test",
            "model": "custom-model",
            "base_url": "openrouter",
            "max_depth": 5,
            "max_iterations": 20,
            "max_timeout": 600,
            "max_budget": 1.0,
            "environment": "docker",
        })

        mock_rlm_cls.assert_called_once()
        call_kwargs = mock_rlm_cls.call_args[1]
        self.assertEqual(call_kwargs["backend"], "hermes")
        self.assertEqual(call_kwargs["backend_kwargs"]["model_name"], "custom-model")
        self.assertEqual(call_kwargs["backend_kwargs"]["base_url"], "openrouter")
        self.assertEqual(call_kwargs["max_depth"], 5)
        self.assertEqual(call_kwargs["max_iterations"], 20)
        self.assertEqual(call_kwargs["max_timeout"], 600)
        self.assertEqual(call_kwargs["max_budget"], 1.0)
        self.assertEqual(call_kwargs["environment"], "docker")

    @patch("rlm.RLM")
    def test_exception_returns_error(self, mock_rlm_cls):
        mock_rlm_cls.side_effect = RuntimeError("API connection failed")

        from tools.rlm_tool import rlm_repl_tool
        result = rlm_repl_tool({"prompt": "test"})
        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("API connection failed", data["error"])

    @patch("rlm.RLM")
    def test_dispatch_via_registry(self, mock_rlm_cls):
        mock_rlm = MagicMock()
        mock_rlm_cls.return_value = mock_rlm

        mock_result = MagicMock()
        mock_result.response = "ok"
        mock_result.metadata = None
        mock_result.usage_summary = None
        mock_rlm.completion.return_value = mock_result

        from tools.registry import registry
        import tools.rlm_tool  # noqa: F401
        result = registry.dispatch("rlm_repl", {"prompt": "hello"})
        data = json.loads(result)
        self.assertEqual(data["response"], "ok")


class TestRLMToolDefaults(unittest.TestCase):
    """Test default configuration values."""

    def test_default_values(self):
        from tools.rlm_tool import (
            _DEFAULT_MODEL,
            _DEFAULT_BACKEND,
            _DEFAULT_MAX_DEPTH,
            _DEFAULT_MAX_ITERATIONS,
            _DEFAULT_MAX_TIMEOUT,
            _DEFAULT_ENVIRONMENT,
        )
        self.assertEqual(_DEFAULT_MODEL, "xiaomi/mimo-v2-pro")
        self.assertEqual(_DEFAULT_BACKEND, "hermes")
        self.assertEqual(_DEFAULT_MAX_DEPTH, 2)
        self.assertEqual(_DEFAULT_MAX_ITERATIONS, 15)
        self.assertEqual(_DEFAULT_MAX_TIMEOUT, 300)
        self.assertEqual(_DEFAULT_ENVIRONMENT, "local")


if __name__ == "__main__":
    unittest.main()
