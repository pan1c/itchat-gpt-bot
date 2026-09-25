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
    enabled: bool = True

    @classmethod
    def from_dict(cls, value: dict):
        enabled_value = value.get("enabled", True)
        if not isinstance(enabled_value, bool):
            raise ValueError("Message check enabled must be true or false")

        check = cls(
            name=str(value["name"]).strip(),
            instructions=str(value["instructions"]).strip(),
            true_criteria=str(value["true_criteria"]).strip(),
            false_criteria=str(value["false_criteria"]).strip(),
            response=str(value["response"]).strip(),
            threshold=(
                None if value.get("threshold") is None else float(value["threshold"])
            ),
            enabled=enabled_value,
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
class CombinationDefinition:
    checks: tuple[str, ...]
    response: str
    threshold: float | None = None

    @classmethod
    def from_dict(cls, value: dict):
        names = value["checks"]
        if not isinstance(names, list) or len(names) < 2:
            raise ValueError("Message check combination requires at least two checks")
        normalized_names = tuple(str(name).strip() for name in names)
        response = str(value["response"]).strip()
        threshold = (
            None if value.get("threshold") is None else float(value["threshold"])
        )
        if not all(normalized_names) or not response:
            raise ValueError("Message check combination fields must not be empty")
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("Message check combination names must be unique")
        if threshold is not None and not _valid_probability(threshold):
            raise ValueError("Invalid message check combination threshold")
        return cls(normalized_names, response, threshold)


@dataclass(frozen=True)
class Config:
    api_key: str
    checks: tuple[CheckDefinition, ...]
    model: str = "jev-latest"
    threshold: float = 0.8
    timeout: float = 5.0
    combinations: tuple[CombinationDefinition, ...] = ()

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

        checks, combinations = load_configuration(checks_file)
        return cls(key, checks, model, threshold, timeout, combinations)


def _valid_probability(value) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and 0 <= value <= 1
    )


def load_configuration(
    path: Path,
) -> tuple[tuple[CheckDefinition, ...], tuple[CombinationDefinition, ...]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    values = document.get("checks")
    if not isinstance(values, list) or not values:
        raise ValueError("Message checks file must contain a non-empty checks list")

    configured_checks = tuple(CheckDefinition.from_dict(value) for value in values)
    names = [check.name for check in configured_checks]
    if len(names) != len(set(names)):
        raise ValueError("Message check names must be unique")

    enabled_checks = tuple(check for check in configured_checks if check.enabled)
    if not enabled_checks:
        raise ValueError("Message checks file must enable at least one check")

    combination_values = document.get("combinations", [])
    if not isinstance(combination_values, list):
        raise ValueError("Message check combinations must be a list")
    combinations = tuple(
        CombinationDefinition.from_dict(value) for value in combination_values
    )
    enabled_names = {check.name for check in enabled_checks}
    combination_keys = []
    for combination in combinations:
        unknown_names = set(combination.checks) - enabled_names
        if unknown_names:
            raise ValueError(
                "Message check combination references disabled or unknown checks: "
                + ", ".join(sorted(unknown_names))
            )
        combination_keys.append(frozenset(combination.checks))
    if len(combination_keys) != len(set(combination_keys)):
        raise ValueError("Message check combinations must be unique")
    return enabled_checks, combinations


def load_checks(path: Path) -> tuple[CheckDefinition, ...]:
    checks, _ = load_configuration(path)
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


def _format_check_response(check: CheckDefinition, probability: float) -> str:
    return f"{check.response} (score: {probability:.2f})"


def _format_combination_response(
    combination: CombinationDefinition, probabilities: dict[str, float]
) -> str:
    scores = ", ".join(
        f"{name}: {probabilities[name]:.2f}" for name in combination.checks
    )
    return f"{combination.response} ({scores})"


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
        logger.debug(
            "Message check result chat=%s message=%s check=%s probability=%.3f",
            message.chat_id,
            message.message_id,
            check.name,
            probability,
        )
        if probability >= threshold:
            logger.info(
                "Message check matched chat=%s message=%s check=%s probability=%.3f",
                message.chat_id,
                message.message_id,
                check.name,
                probability,
            )
            matches.append(check)

    checks_by_name = {check.name: check for check in _config.checks}
    combined_names = set()
    responses = []
    for combination in _config.combinations:
        combination_matches = all(
            probabilities[name]
            >= (
                combination.threshold
                if combination.threshold is not None
                else checks_by_name[name].effective_threshold(_config.threshold)
            )
            for name in combination.checks
        )
        if combination_matches:
            logger.info(
                "Message check combination matched chat=%s message=%s checks=%s",
                message.chat_id,
                message.message_id,
                "+".join(combination.checks),
            )
            responses.append(
                _format_combination_response(combination, probabilities)
            )
            combined_names.update(combination.checks)
    responses.extend(
        _format_check_response(check, probabilities[check.name])
        for check in matches
        if check.name not in combined_names
    )

    for response in responses:
        try:
            await message.reply_text(response)
        except Exception as exc:
            logger.warning(
                "Message check reply failed chat=%s message=%s error=%s",
                message.chat_id,
                message.message_id,
                type(exc).__name__,
            )
    return bool(responses)
