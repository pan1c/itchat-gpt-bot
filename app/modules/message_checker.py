"""Generic TypeSafe-powered checks for Telegram messages."""

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path

import httpx

from .logging import logger


DEFAULT_CHECKS_FILE = (
    Path(__file__).resolve().parent.parent / "data" / "message_checks.json"
)


def enabled() -> bool:
    return os.getenv("MESSAGE_CHECKS_ENABLED", "false").strip().lower() in {
        "true",
        "1",
        "yes",
        "on",
    }


@dataclass(frozen=True)
class CheckDefinition:
    name: str
    instructions: str
    true_criteria: str
    false_criteria: str
    response: str
    threshold: float | None = None

    @classmethod
    def from_dict(cls, value: dict):
        check = cls(
            name=str(value["name"]).strip(),
            instructions=str(value["instructions"]).strip(),
            true_criteria=str(value["true_criteria"]).strip(),
            false_criteria=str(value["false_criteria"]).strip(),
            response=str(value["response"]).strip(),
            threshold=(
                None if value.get("threshold") is None else float(value["threshold"])
            ),
        )
        if not all(
            (
                check.name,
                check.instructions,
                check.true_criteria,
                check.false_criteria,
                check.response,
            )
        ):
            raise ValueError("Message check fields must not be empty")
        if check.threshold is not None and not _valid_probability(check.threshold):
            raise ValueError(f"Invalid threshold for message check {check.name!r}")
        return check

    def effective_threshold(self, default: float) -> float:
        return default if self.threshold is None else self.threshold


@dataclass(frozen=True)
class Config:
    api_key: str
    checks: tuple[CheckDefinition, ...]
    model: str = "jev-latest"
    threshold: float = 0.8
    timeout: float = 5.0

    @classmethod
    def from_env(cls):
        key = os.getenv("TYPESAFE_API_KEY", "").strip()
        model = os.getenv("TYPESAFE_MODEL", "jev-latest").strip()
        threshold = float(os.getenv("MESSAGE_CHECK_THRESHOLD", "0.8"))
        timeout = float(os.getenv("MESSAGE_CHECK_TIMEOUT_SECONDS", "5"))
        checks_file = Path(os.getenv("MESSAGE_CHECKS_FILE", str(DEFAULT_CHECKS_FILE)))

        if not key or not model:
            raise ValueError("Message checks require TYPESAFE_API_KEY and a model")
        if not _valid_probability(threshold):
            raise ValueError("MESSAGE_CHECK_THRESHOLD must be between 0 and 1")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("MESSAGE_CHECK_TIMEOUT_SECONDS must be positive")

        checks = load_checks(checks_file)
        return cls(key, checks, model, threshold, timeout)


def _valid_probability(value) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and 0 <= value <= 1
    )


def load_checks(path: Path) -> tuple[CheckDefinition, ...]:
    document = json.loads(path.read_text(encoding="utf-8"))
    values = document.get("checks")
    if not isinstance(values, list) or not values:
        raise ValueError("Message checks file must contain a non-empty checks list")

    checks = tuple(CheckDefinition.from_dict(value) for value in values)
    names = [check.name for check in checks]
    if len(names) != len(set(names)):
        raise ValueError("Message check names must be unique")
    return checks


def request_payload(text: str, config: Config) -> dict:
    return {
        "model": config.model,
        "state": {"message": text},
        "questions": {
            check.name: {
                "type": "noul",
                "instructions": check.instructions,
                "criteria": {
                    "true": check.true_criteria,
                    "false": check.false_criteria,
                },
            }
            for check in config.checks
        },
    }


def parse_probabilities(payload: dict, checks) -> dict[str, float]:
    probabilities = {}
    for check in checks:
        answer = payload["answers"][check.name]
        value = answer["noul"]
        if answer["type"] != "noul" or not _valid_probability(value):
            raise ValueError(f"Invalid probability for message check {check.name!r}")
        probabilities[check.name] = float(value)
    return probabilities


def _load_config():
    if not enabled():
        return None
    try:
        return Config.from_env()
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.error("Message checks disabled: %s", exc)
        return None


_config = _load_config()


async def _request_probabilities(text: str, config: Config) -> dict[str, float]:
    async with httpx.AsyncClient(
        base_url="https://api.typesafe.ai",
        headers={"Authorization": f"Bearer {config.api_key}"},
        timeout=config.timeout,
    ) as client:
        response = await client.post(
            "/v1/systemone", json=request_payload(text, config)
        )
        response.raise_for_status()
        return parse_probabilities(response.json(), config.checks)


async def check_message(message) -> bool:
    """Run configured checks and reply for every match."""
    if _config is None:
        return False
    if not message or message.chat.type not in {"group", "supergroup"}:
        return False
    if message.from_user and message.from_user.is_bot:
        return False

    text = (message.text or message.caption or "").strip()
    if not text:
        return False

    try:
        probabilities = await _request_probabilities(text, _config)
    except Exception as exc:
        # Do not log request bodies, keys, message text or API error bodies.
        logger.warning(
            "Message checks failed chat=%s message=%s error=%s",
            message.chat_id,
            message.message_id,
            type(exc).__name__,
        )
        return False

    matches = []
    for check in _config.checks:
        probability = probabilities[check.name]
        threshold = check.effective_threshold(_config.threshold)
        logger.info(
            "Message check result chat=%s message=%s check=%s probability=%.3f",
            message.chat_id,
            message.message_id,
            check.name,
            probability,
        )
        if probability >= threshold:
            matches.append(check)

    for check in matches:
        try:
            await message.reply_text(check.response)
        except Exception as exc:
            logger.warning(
                "Message check reply failed chat=%s message=%s check=%s error=%s",
                message.chat_id,
                message.message_id,
                check.name,
                type(exc).__name__,
            )
    return bool(matches)
