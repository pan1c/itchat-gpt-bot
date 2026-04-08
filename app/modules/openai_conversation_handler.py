import openai
import base64
from openai import OpenAI

from .logging import logger
from .settings import (
    gpt_model_name,
    gpt_system_role,
    openai_api_key,
    openai_enable_chat_fallback,
    openai_image_model,
    openai_use_responses,
)


def _build_messages(question: str, prev_message: str) -> list[dict[str, str]]:
    messages = [
        {"role": "system", "content": gpt_system_role},
        {"role": "user", "content": question},
    ]
    if prev_message:
        messages.append({"role": "assistant", "content": prev_message})
    return messages


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


async def generate_response(question: str, prev_message: str) -> str:
    """Use OpenAI to generate a response to the given question."""
    if not question:
        return "You didn't ask your question. Try /help"

    client = OpenAI(api_key=openai_api_key)
    messages = _build_messages(question, prev_message)

    if openai_use_responses:
        try:
            response = client.responses.create(model=gpt_model_name, input=messages)
            response_text = _extract_response_text(response)
            if response_text:
                return response_text
            logger.warning("Responses API returned empty text; evaluating fallback.")
        except openai.OpenAIError as err:
            logger.warning("Responses API failed: %s", err)
        except Exception as err:
            logger.exception("Unexpected error from Responses API: %s", err)

    if openai_enable_chat_fallback:
        try:
            return _chat_completions_response(client, messages)
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
        response = client.images.generate(
            model=openai_image_model,
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
        image_item = response.data[0]
        image_url = getattr(image_item, "url", None)
        image_b64 = getattr(image_item, "b64_json", None)
        revised_prompt = getattr(image_item, "revised_prompt", "")

        if image_url:
            return image_url, revised_prompt, None

        if image_b64:
            image_bytes = base64.b64decode(image_b64)
            return image_bytes, revised_prompt, None

        return None, None, "Image generated, but no URL or image bytes were returned."
    except openai.OpenAIError as err:
        error_msg = f"OpenAI image API error: {err}"
        logger.error(error_msg)
        return None, None, error_msg
    except Exception as err:
        error_msg = f"Unexpected image generation error: {err}"
        logger.exception(error_msg)
        return None, None, error_msg
