import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from modules import message_checker


def make_check(
    name="zrada", response="ЗРАДА DETECTED", threshold=None, enabled=True
):
    return message_checker.CheckDefinition(
        name=name,
        instructions=f"Is this message {name}?",
        true_criteria=f"The message is {name}.",
        false_criteria=f"The message is not {name}.",
        response=response,
        threshold=threshold,
        enabled=enabled,
    )


def make_combination():
    return message_checker.CombinationDefinition(
        checks=("zrada", "peremoha"),
        response="ЗРАДОПЕРЕМОГА DETECTED",
        threshold=0.7,
    )


class MessageCheckerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.zrada = make_check()
        self.config = message_checker.Config(
            "test-key", (self.zrada,), threshold=0.8
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
            AsyncMock(return_value={"zrada": 0.8}),
        ):
            matched = await message_checker.check_message(self.message)

        self.assertTrue(matched)
        self.message.reply_text.assert_awaited_once_with(
            "ЗРАДА DETECTED (score: 0.80)"
        )

    async def test_does_not_reply_below_threshold(self):
        with patch.object(message_checker, "_config", self.config), patch.object(
            message_checker,
            "_request_probabilities",
            AsyncMock(return_value={"zrada": 0.79}),
        ):
            matched = await message_checker.check_message(self.message)

        self.assertFalse(matched)
        self.message.reply_text.assert_not_awaited()

    async def test_replies_for_each_matching_check(self):
        peremoha = make_check("peremoha", "ПЕРЕМОГА DETECTED", threshold=0.9)
        config = message_checker.Config(
            "test-key", (self.zrada, peremoha), threshold=0.8
        )
        with patch.object(message_checker, "_config", config), patch.object(
            message_checker,
            "_request_probabilities",
            AsyncMock(return_value={"zrada": 0.91, "peremoha": 0.95}),
        ):
            matched = await message_checker.check_message(self.message)

        self.assertTrue(matched)
        self.assertEqual(self.message.reply_text.await_count, 2)
        self.message.reply_text.assert_any_await(
            "ЗРАДА DETECTED (score: 0.91)"
        )
        self.message.reply_text.assert_any_await(
            "ПЕРЕМОГА DETECTED (score: 0.95)"
        )

    async def test_combination_replaces_individual_responses(self):
        peremoha = make_check("peremoha", "ПЕРЕМОГА DETECTED")
        config = message_checker.Config(
            "test-key",
            (self.zrada, peremoha),
            threshold=0.8,
            combinations=(make_combination(),),
        )
        with patch.object(message_checker, "_config", config), patch.object(
            message_checker,
            "_request_probabilities",
            AsyncMock(return_value={"zrada": 0.76, "peremoha": 0.71}),
        ):
            matched = await message_checker.check_message(self.message)

        self.assertTrue(matched)
        self.message.reply_text.assert_awaited_once_with(
            "ЗРАДОПЕРЕМОГА DETECTED (zrada: 0.76, peremoha: 0.71)"
        )

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
                    "enabled": False,
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

        self.assertEqual([check.name for check in checks], ["spam"])
        self.assertEqual(checks[0].threshold, 0.9)
        self.assertTrue(checks[0].enabled)
        path.read_text.assert_called_once_with(encoding="utf-8")

    def test_default_checks_disable_politics(self):
        checks, combinations = message_checker.load_configuration(
            message_checker.DEFAULT_CHECKS_FILE
        )
        config = message_checker.Config(
            "test-key", checks, combinations=combinations
        )

        self.assertEqual([check.name for check in checks], ["zrada", "peremoha"])
        self.assertEqual(checks[0].threshold, 0.7)
        self.assertEqual(checks[1].threshold, 0.7)
        self.assertEqual(combinations, (make_combination(),))
        self.assertEqual(
            set(message_checker.request_payload("hello", config)["questions"]),
            {"zrada", "peremoha"},
        )

    def test_builds_all_questions_in_one_request(self):
        peremoha = make_check("peremoha", "ПЕРЕМОГА DETECTED")
        config = message_checker.Config("test-key", (self.zrada, peremoha))

        payload = message_checker.request_payload("hello", config)

        self.assertEqual(set(payload["questions"]), {"zrada", "peremoha"})

    def test_rejects_non_boolean_enabled(self):
        path = Mock()
        path.read_text.return_value = json.dumps(
            {
                "checks": [
                    {
                        "name": "spam",
                        "enabled": "false",
                        "instructions": "Spam?",
                        "true_criteria": "Spam",
                        "false_criteria": "Not spam",
                        "response": "SPAM DETECTED",
                    }
                ]
            }
        )

        with self.assertRaisesRegex(ValueError, "enabled must be true or false"):
            message_checker.load_checks(path)

    def test_rejects_configuration_with_all_checks_disabled(self):
        path = Mock()
        path.read_text.return_value = json.dumps(
            {
                "checks": [
                    {
                        "name": "politics",
                        "enabled": False,
                        "instructions": "Politics?",
                        "true_criteria": "Politics",
                        "false_criteria": "Not politics",
                        "response": "POLITICS DETECTED",
                    }
                ]
            }
        )

        with self.assertRaisesRegex(ValueError, "enable at least one check"):
            message_checker.load_checks(path)

    def test_rejects_combination_with_disabled_check(self):
        path = Mock()
        path.read_text.return_value = json.dumps(
            {
                "checks": [
                    {
                        "name": "zrada",
                        "instructions": "Zrada?",
                        "true_criteria": "Zrada",
                        "false_criteria": "Not zrada",
                        "response": "ЗРАДА DETECTED",
                    },
                    {
                        "name": "politics",
                        "enabled": False,
                        "instructions": "Politics?",
                        "true_criteria": "Politics",
                        "false_criteria": "Not politics",
                        "response": "POLITICS DETECTED",
                    },
                ],
                "combinations": [
                    {
                        "checks": ["zrada", "politics"],
                        "response": "COMBINED",
                    }
                ],
            }
        )

        with self.assertRaisesRegex(ValueError, "disabled or unknown"):
            message_checker.load_configuration(path)

    def setUp(self):
        self.zrada = make_check()


class ResponseParsingTests(unittest.TestCase):
    def test_parses_probabilities(self):
        checks = (make_check(), make_check("peremoha", "ПЕРЕМОГА DETECTED"))
        payload = {
            "answers": {
                "zrada": {"type": "noul", "noul": 0.91},
                "peremoha": {"type": "noul", "noul": 0.12},
            }
        }
        self.assertEqual(
            message_checker.parse_probabilities(payload, checks),
            {"zrada": 0.91, "peremoha": 0.12},
        )

    def test_rejects_out_of_range_probability(self):
        payload = {"answers": {"zrada": {"type": "noul", "noul": 1.1}}}
        with self.assertRaises(ValueError):
            message_checker.parse_probabilities(payload, (make_check(),))


if __name__ == "__main__":
    unittest.main()
