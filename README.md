# itchat-gpt-bot

Telegram bot that allows you to chat with OpenAI models and generate images.
--

## Prerequisite

- You need to have the Telegram bot API key created
https://t.me/BotFather

- You need to have the OpenAI API key created
https://platform.openai.com/docs/quickstart/build-your-application

## Usage

###### Pure python
```
 pip install -r requirements.txt
 TELEGRAM_BOT_TOKEN=<your tg token> OPENAI_API_KEY=<your open AI token> python3 app/main.py
```

###### Docker
- create file _secrets.env_ with your secrets:
```
cat secrets.env
TELEGRAM_BOT_TOKEN=<your tg token>
OPENAI_API_KEY=<your open AI token>
```
Additional options supported, please see settings.py

- run docker compose up command
```
docker compose up
```

## OpenAI integration defaults

- `GPT_MODEL_NAME` default: `gpt-5.4-nano` (overrideable).
- `OPENAI_USE_RESPONSES` default: `true`.
- `OPENAI_ENABLE_CHAT_FALLBACK` default: `true`.
- `OPENAI_IMAGE_MODEL` default: `gpt-image-1`.

### Migration-safe behavior

- The bot uses the OpenAI Responses API first for text generation.
- If Responses is unavailable or returns no text, Chat Completions is used as a fallback by default.
- Existing environment variables continue to work (`OPENAI_API_KEY`, `GPT_MODEL_NAME`, etc.).
