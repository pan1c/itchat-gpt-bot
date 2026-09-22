import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from modules import message_checker


def make_check(name="politics", response="POLITICS DETECTED", threshold=None):
    return message_checker.CheckDefinition(
        name=name,
        instructions=f"Is this message {name}?",
        true_criteria=f"The message is {name}.",
        false_criteria=f"The message is not {name}.",
        response=response,
        threshold=threshold,
    )


class MessageCheckerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.politics = make_check()
        self.config = message_checker.Config(
            "test-key", (self.politics,), threshold=0.8
        )
        self.message = SimpleNamespace(
            chat=SimpleNamespace(type="supergroup"),
            chat_id=-1001,
            message_id=42,
            from_user=SimpleNamespace(is_bot=False),
            text="Обсуждаем результаты выборов",
            caption=None,
            reply_text=AsyncMock(),
        )

    async def test_replies_at_threshold(self):
        with patch.object(message_checker, "_config", self.config), patch.object(
            message_checker,
            "_request_probabilities",
            AsyncMock(return_value={"politics": 0.8}),
        ):
            matched = await message_checker.check_message(self.message)

        self.assertTrue(matched)
        self.message.reply_text.assert_awaited_once_with("POLITICS DETECTED")

    async def test_does_not_reply_below_threshold(self):
        with patch.object(message_checker, "_config", self.config), patch.object(
            message_checker,
            "_request_probabilities",
            AsyncMock(return_value={"politics": 0.79}),
        ):
            matched = await message_checker.check_message(self.message)

        self.assertFalse(matched)
        self.message.reply_text.assert_not_awaited()

    async def test_replies_for_each_matching_check(self):
        spam = make_check("spam", "SPAM DETECTED", threshold=0.9)
        config = message_checker.Config(
            "test-key", (self.politics, spam), threshold=0.8
        )
        with patch.object(message_checker, "_config", config), patch.object(
            message_checker,
            "_request_probabilities",
            AsyncMock(return_value={"politics": 0.91, "spam": 0.95}),
        ):
            matched = await message_checker.check_message(self.message)

        self.assertTrue(matched)
        self.assertEqual(self.message.reply_text.await_count, 2)
        self.message.reply_text.assert_any_await("POLITICS DETECTED")
        self.message.reply_text.assert_any_await("SPAM DETECTED")

    async def test_disabled_checker_does_nothing(self):
        with patch.object(message_checker, "_config", None), patch.object(
            message_checker, "_request_probabilities", AsyncMock()
        ) as request:
            matched = await message_checker.check_message(self.message)

        self.assertFalse(matched)
        request.assert_not_awaited()


class ConfigurationTests(unittest.TestCase):
    def test_loads_multiple_checks(self):
        document = {
            "checks": [
                {
                    "name": "politics",
                    "instructions": "Politics?",
                    "true_criteria": "Political discussion",
                    "false_criteria": "Ordinary conversation",
                    "response": "POLITICS DETECTED",
                },
                {
                    "name": "spam",
                    "instructions": "Spam?",
                    "true_criteria": "Unsolicited advertising",
                    "false_criteria": "Normal conversation",
                    "response": "SPAM DETECTED",
                    "threshold": 0.9,
                },
            ]
        }
        path = Mock()
        path.read_text.return_value = json.dumps(document)

        checks = message_checker.load_checks(path)

        self.assertEqual([check.name for check in checks], ["politics", "spam"])
        self.assertEqual(checks[1].threshold, 0.9)
        path.read_text.assert_called_once_with(encoding="utf-8")

    def test_builds_all_questions_in_one_request(self):
        spam = make_check("spam", "SPAM DETECTED")
        config = message_checker.Config("test-key", (self.politics, spam))

        payload = message_checker.request_payload("hello", config)

        self.assertEqual(set(payload["questions"]), {"politics", "spam"})

    def setUp(self):
        self.politics = make_check()


class ResponseParsingTests(unittest.TestCase):
    def test_parses_probabilities(self):
        checks = (make_check(), make_check("spam", "SPAM DETECTED"))
        payload = {
            "answers": {
                "politics": {"type": "noul", "noul": 0.91},
                "spam": {"type": "noul", "noul": 0.12},
            }
        }
        self.assertEqual(
            message_checker.parse_probabilities(payload, checks),
            {"politics": 0.91, "spam": 0.12},
        )

    def test_rejects_out_of_range_probability(self):
        payload = {"answers": {"politics": {"type": "noul", "noul": 1.1}}}
        with self.assertRaises(ValueError):
            message_checker.parse_probabilities(payload, (make_check(),))


if __name__ == "__main__":
    unittest.main()
