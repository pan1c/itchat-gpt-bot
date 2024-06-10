from .logging import logger
import openai
from openai import OpenAI
from .settings import openai_api_key, gpt_system_role, gpt_model_name


async def generate_response(question: str, prev_message: str) -> str:
    """Use GPT to generate a response to the given question."""
    client = OpenAI(api_key=openai_api_key)
    if question:
        # Make your OpenAI API request here
        response = client.chat.completions.create(
            model=gpt_model_name,
            messages=[
                {
                    "role": "system",
                    "content": gpt_system_role
                },
                {
                    "role": "user",
                    "content": question
                },
                {
                    "role": "assistant",
                    "content": prev_message
                }
            ])
        logger.info(f"OpenAI response: {response}")
        response_text = response.choices[0].message.content
    else:
        response_text = "You didn't ask your question. Try /help"

    return response_text


def generate_image(prompt):
    client = openai.OpenAI(api_key=openai_api_key)
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="hd",
            n=1,
        )
        logger.info(f"Image generation response: {response}")
        image_url = response.data[0].url
        revised_prompt = response.data[0].revised_prompt
        return image_url, revised_prompt, None
    except openai.OpenAIError as e:
        error_msg = f"OpenAI API error: {e}"
        logger.error(error_msg)
        return None, None, error_msg
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.error(error_msg)
        return None, None, error_msg
