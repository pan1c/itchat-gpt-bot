# Configurable message checks

The generic TypeSafe integration lives in `app/modules/message_checker.py`. The
normal `app/main.py` entry point is unchanged. Before invoking GPT, the existing
message handler runs every enabled check defined in `app/data/message_checks.json`.

The included checks file enables independent `zrada` and `peremoha` checks. The
original politics check remains as a disabled example.

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
  "enabled": true,
  "instructions": "Is this message unsolicited advertising?",
  "true_criteria": "Advertising, repeated promotions, or suspicious links.",
  "false_criteria": "Normal conversation or a relevant requested recommendation.",
  "response": "SPAM DETECTED",
  "threshold": 0.9
}
```

`name` must be unique. `enabled` is optional and defaults to `true`; disabled checks
remain in the file but are not included in TypeSafe requests. At least one check must
be enabled. `threshold` is also optional; when omitted, the global
`MESSAGE_CHECK_THRESHOLD` applies.

All enabled checks are evaluated together in one TypeSafe request and receive
independent probabilities. They do not run as sequential requests, and their
probabilities do not need to add up to one. Every matching check posts its configured
`response`, so a message can produce more than one response. If one or more checks
match, GPT handling stops for that message.

Each response includes the raw TypeSafe probability rounded to two decimal places,
for example `ЗРАДА DETECTED (score: 0.77)`. A combination shows every participating
score, for example
`ЗРАДОПЕРЕМОГА DETECTED (zrada: 0.83, peremoha: 0.74)`.

Optional top-level `combinations` replace individual responses when all named checks
match. The default configuration combines `zrada` and `peremoha` into one response:

```json
{
  "checks": ["zrada", "peremoha"],
  "response": "ЗРАДОПЕРЕМОГА DETECTED",
  "threshold": 0.7
}
```

Combination check names must be unique and refer to enabled checks. Checks that are
not consumed by a matching combination still send their individual responses. An
optional combination `threshold` applies to every named check only when deciding
whether to use the combined response. When omitted, each check's normal threshold
applies. This allows mixed context to use a more tolerant threshold without making
standalone `zrada` or `peremoha` responses less strict.

The default `zrada` and `peremoha` rules evaluate public, political, governmental,
diplomatic, military, security, and economic events by their likely effect on
Ukraine, even when Ukraine is not explicitly mentioned. An unspecified public office
or institution is interpreted in the Ukrainian context unless the message names
another country. Ordinary personal successes and setbacks are not matches. Sarcasm
that mocks a supposed victory is classified as `zrada`, not `peremoha`. Slang,
profanity, misspellings, and colloquial phrasing are interpreted by meaning. `zrada`
uses a per-check threshold of `0.7`, as does `peremoha`. The lower default-rule
threshold favors catching short and colloquial chat messages; other checks can keep
using the global threshold or define their own.

For `peremoha`, any damage, loss, failure, setback, or weakening suffered by the
Russian state, its government, leadership, armed forces, security services, economy,
infrastructure, territorial control, or international position counts as beneficial
to Ukraine. This also covers Russia harming its own forces, territory, assets, or
institutions and does not require Ukraine to be mentioned. Private individuals'
ordinary personal setbacks are outside this rule.

## Runtime behavior

The bot needs permission to receive group messages (admin or disabled Privacy Mode).
It checks new non-command text messages and media captions in groups allowed by
`ALLOWED_CHAT_IDS`. It ignores private messages, edits, bot messages, service
messages, and media without captions. Images and audio are not interpreted.

API failures skip all checks and preserve the existing bot behavior. At `INFO`, logs
contain only matched check names, probabilities, and message identifiers. Results
below the threshold and successful allow-list checks are available at `DEBUG`.
Neither level logs message text or the API key.

Launch normally:

```sh
docker compose up -d --build
```

API reference: https://api.typesafe.ai/docs

Offline tests: `python -m unittest discover -s tests -v`.
