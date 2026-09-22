# Configurable message checks

The generic TypeSafe integration lives in `app/modules/message_checker.py`. The
normal `app/main.py` entry point is unchanged. Before invoking GPT, the existing
message handler runs every check defined in `app/data/message_checks.json`.

The included checks file contains politics detection as the default example.

Add these settings to `secrets.env` (never commit the API key):

```dotenv
MESSAGE_CHECKS_ENABLED=true
TYPESAFE_API_KEY=your-key
TYPESAFE_MODEL=jev-latest
MESSAGE_CHECK_THRESHOLD=0.8
MESSAGE_CHECK_TIMEOUT_SECONDS=5
```

The feature defaults to disabled. Changes to settings or checks require a process
restart. To use another file, set `MESSAGE_CHECKS_FILE` to its path.

## Adding checks

Each entry in the JSON `checks` list defines one independent yes/no question:

```json
{
  "name": "spam",
  "instructions": "Is this message unsolicited advertising?",
  "true_criteria": "Advertising, repeated promotions, or suspicious links.",
  "false_criteria": "Normal conversation or a relevant requested recommendation.",
  "response": "SPAM DETECTED",
  "threshold": 0.9
}
```

`name` must be unique. `threshold` is optional; when omitted, the global
`MESSAGE_CHECK_THRESHOLD` applies. All configured checks are evaluated together in
one TypeSafe request. Every matching check posts its configured `response`. If one
or more checks match, GPT handling stops for that message.

## Runtime behavior

The bot needs permission to receive group messages (admin or disabled Privacy Mode).
It checks new non-command text messages and media captions in groups allowed by
`ALLOWED_CHAT_IDS`. It ignores private messages, edits, bot messages, service
messages, and media without captions. Images and audio are not interpreted.

API failures skip all checks and preserve the existing bot behavior. Logs contain
check names, probabilities or error types, and message identifiers. They do not
contain message text or the API key.

Launch normally:

```sh
docker compose up -d --build
```

API reference: https://api.typesafe.ai/docs

Offline tests: `python -m unittest discover -s tests -v`.
