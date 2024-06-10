# itchat-gpt-bot

Telegram bot that allows you to speak with gpt-3.5-turbo model.
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
 TELEGRAM_BOT_TOKEN=<your tg token> OPENAI_API_KEY=<your open AI token> python3 app.py
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
