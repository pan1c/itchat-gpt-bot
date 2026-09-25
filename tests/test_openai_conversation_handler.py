import base64
import os
import runpy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from modules import openai_conversation_handler as handler, settings


class ModelSettingsTests(unittest.TestCase):
    def test_default_and_environment_override(self):
        for environment, expected in (
            ({}, "gpt-6-luna"),
            ({"GPT_MODEL_NAME": "gpt-5.4-nano"}, "gpt-5.4-nano"),
        ):
            with self.subTest(environment=environment), patch.dict(
                os.environ, environment, clear=True
            ), patch.object(settings.logger, "info"):
                values = runpy.run_path(
                    settings.__file__, run_name="modules._test_settings"
                )
                self.assertEqual(values["gpt_model_name"], expected)


class ModelRequestTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = Mock()
        self.client.responses.create.return_value = SimpleNamespace(output_text="answer")
        self.client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))]
        )
        self.messages = [
            {"role": "system", "content": handler.gpt_system_role},
            {"role": "user", "content": "question"},
        ]
        for name, value in (
            ("OpenAI", Mock(return_value=self.client)),
            ("_conversation_history", {}),
            ("openai_use_responses", True),
            ("openai_enable_chat_fallback", True),
        ):
            patcher = patch.object(handler, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_responses_model_and_reasoning(self):
        for model in ("gpt-6-luna", "gpt-5.4-nano"):
            with self.subTest(model=model), patch.object(handler, "gpt_model_name", model):
                handler._conversation_history.clear()
                self.assertEqual(await handler.generate_response("question", 1, 2), "answer")
                expected = {"model": model, "input": self.messages}
                if model == "gpt-6-luna":
                    expected["reasoning"] = {"effort": "none"}
                self.assertEqual(self.client.responses.create.call_args.kwargs, expected)
                self.client.chat.completions.create.assert_not_called()

    async def test_empty_responses_uses_chat_fallback_with_correct_reasoning(self):
        self.client.responses.create.return_value = SimpleNamespace(output_text="", output=[])
        for model in ("gpt-6-luna", "gpt-5.4-nano"):
            with self.subTest(model=model), patch.object(handler, "gpt_model_name", model):
                handler._conversation_history.clear()
                self.assertEqual(await handler.generate_response("question", 1, 2), "answer")
                expected = {"model": model, "messages": self.messages}
                if model == "gpt-6-luna":
                    expected["reasoning_effort"] = "none"
                self.assertEqual(self.client.chat.completions.create.call_args.kwargs, expected)

    def test_image_model_reasoning_and_unchanged_image_options(self):
        self.client.responses.create.return_value = SimpleNamespace(
            output=[SimpleNamespace(
                type="image_generation_call",
                result=base64.b64encode(b"image").decode(),
                revised_prompt="revised",
            )]
        )
        for model in ("gpt-6-luna", "gpt-5.4-nano"):
            with self.subTest(model=model), patch.object(handler, "gpt_model_name", model):
                self.assertEqual(handler.generate_image("draw"), (b"image", "revised", None))
                expected = {
                    "model": model,
                    "input": "draw",
                    "tools": [{
                        "type": "image_generation",
                        "action": "generate",
                        "size": "1024x1024",
                    }],
                }
                if model == "gpt-6-luna":
                    expected["reasoning"] = {"effort": "none"}
                self.assertEqual(self.client.responses.create.call_args.kwargs, expected)
