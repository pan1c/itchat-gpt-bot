import openai
import base64
from openai import OpenAI

from .logging import logger
from .settings import (
    gpt_model_name,
    gpt_system_role,
    openai_api_key,
    openai_enable_chat_fallback,
    openai_use_responses,
    gpt_max_history_turns,
)

ConversationKey = tuple[int, int]
Message = dict[str, str]
_conversation_history: dict[ConversationKey, list[Message]] = {}


def _get_conversation_key(chat_id: int, user_id: int) -> ConversationKey:
    return chat_id, user_id


def _get_history(chat_id: int, user_id: int) -> list[Message]:
    key = _get_conversation_key(chat_id, user_id)
    return _conversation_history.setdefault(key, [])


def _trim_history(history: list[Message]) -> None:
    max_messages = max(gpt_max_history_turns, 0) * 2
    if max_messages == 0:
        history.clear()
        return
    if len(history) > max_messages:
        del history[:-max_messages]


def _build_messages(chat_id: int, user_id: int, question: str) -> list[Message]:
    history = list(_get_history(chat_id, user_id))
    return [{"role": "system", "content": gpt_system_role}, *history, {"role": "user", "content": question}]


def _append_history(chat_id: int, user_id: int, question: str, response_text: str) -> None:
    history = _get_history(chat_id, user_id)
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": response_text})
    _trim_history(history)


def reset_conversation(chat_id: int, user_id: int) -> bool:
    key = _get_conversation_key(chat_id, user_id)
    return _conversation_history.pop(key, None) is not None


def _extract_response_text(response) -> str:
    # The latest SDK exposes "output_text" for Responses API.
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    # Fallback extraction for SDK/type variations.
    output = getattr(response, "output", None) or []
    collected_text: list[str] = []
    for item in output:
        content = getattr(item, "content", None) or []
        for block in content:
            text = getattr(block, "text", None)
            if text:
                collected_text.append(text)
    return "\n".join(collected_text).strip()


def _chat_completions_response(client: OpenAI, messages: list[dict[str, str]]) -> str:
    response = client.chat.completions.create(model=gpt_model_name, messages=messages)
    return (response.choices[0].message.content or "").strip()


async def generate_response(question: str, chat_id: int, user_id: int) -> str:
    """Use OpenAI to generate a response to the given question."""
    if not question:
        return "You didn't ask your question. Try /help"

    client = OpenAI(api_key=openai_api_key)
    messages = _build_messages(chat_id, user_id, question)

    if openai_use_responses:
        try:
            response = client.responses.create(model=gpt_model_name, input=messages)
            response_text = _extract_response_text(response)
            if response_text:
                _append_history(chat_id, user_id, question, response_text)
                return response_text
            logger.warning("Responses API returned empty text; evaluating fallback.")
        except openai.OpenAIError as err:
            logger.warning("Responses API failed: %s", err)
        except Exception as err:
            logger.exception("Unexpected error from Responses API: %s", err)

    if openai_enable_chat_fallback:
        try:
            response_text = _chat_completions_response(client, messages)
            if response_text:
                _append_history(chat_id, user_id, question, response_text)
                return response_text
            logger.warning("Chat Completions fallback returned empty text.")
            return "No response generated. Please try again later."
        except openai.OpenAIError as err:
            logger.error("Chat Completions fallback failed: %s", err)
            return "OpenAI API error. Please try again later."
        except Exception as err:
            logger.exception("Unexpected error from Chat Completions fallback: %s", err)
            return "Unexpected error while generating a response. Please try again later."

    return "No response generated. Please try again later."


def generate_image(prompt):
    client = OpenAI(api_key=openai_api_key)
    try:
        response = client.responses.create(
            model=gpt_model_name,
            input=prompt,
            tools=[
                {
                    "type": "image_generation",
                    "action": "generate",
                    "size": "1024x1024",
                }
            ],
        )
        image_calls = [
            output
            for output in response.output
            if getattr(output, "type", None) == "image_generation_call"
        ]
        if not image_calls:
            return None, None, "Image generation completed without an image result."

        image_call = image_calls[0]
        image_b64 = getattr(image_call, "result", None)
        revised_prompt = getattr(image_call, "revised_prompt", "")
        if not image_b64:
            return None, None, "Image generated, but no image bytes were returned."

        return base64.b64decode(image_b64), revised_prompt, None
    except openai.OpenAIError as err:
        error_msg = f"OpenAI image API error: {err}"
        logger.error(error_msg)
        return None, None, error_msg
    except Exception as err:
        error_msg = f"Unexpected image generation error: {err}"
        logger.exception(error_msg)
        return None, None, error_msg
