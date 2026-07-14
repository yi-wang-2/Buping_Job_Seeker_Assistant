"""
This module contains utility functions for the Resume and Cover Letter Builder service.
"""

# app/libs/resume_and_cover_builder/utils.py
import json
import openai
import time
from datetime import datetime
from typing import Dict, List
from langchain_core.messages.ai import AIMessage
from langchain_core.prompt_values import StringPromptValue
from langchain_openai import ChatOpenAI
from .config import global_config
from loguru import logger
from requests.exceptions import HTTPError as HTTPStatusError


class LLMLogger:

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    @staticmethod
    def log_request(prompts, parsed_reply: Dict[str, Dict]):
        calls_log = global_config.LOG_OUTPUT_FILE_PATH / "open_ai_calls.json"
        if isinstance(prompts, StringPromptValue):
            prompts = prompts.text
        elif isinstance(prompts, Dict):
            # Convert prompts to a dictionary if they are not in the expected format
            prompts = {
                f"prompt_{i+1}": prompt.content
                for i, prompt in enumerate(prompts.messages)
            }
        else:
            prompts = {
                f"prompt_{i+1}": prompt.content
                for i, prompt in enumerate(prompts.messages)
            }

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Extract token usage details from the response
        token_usage = parsed_reply["usage_metadata"]
        output_tokens = token_usage["output_tokens"]
        input_tokens = token_usage["input_tokens"]
        total_tokens = token_usage["total_tokens"]

        # Extract model details from the response
        model_name = parsed_reply["response_metadata"]["model_name"]
        prompt_price_per_token = 0.00000015
        completion_price_per_token = 0.0000006

        # Calculate the total cost of the API call
        total_cost = (input_tokens * prompt_price_per_token) + (
            output_tokens * completion_price_per_token
        )

        # Create a log entry with all relevant information
        log_entry = {
            "model": model_name,
            "time": current_time,
            "prompts": prompts,
            "replies": parsed_reply["content"],  # Response content
            "total_tokens": total_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_cost": total_cost,
        }

        # Write the log entry to the log file in JSON format
        with open(calls_log, "a", encoding="utf-8") as f:
            json_string = json.dumps(log_entry, ensure_ascii=False, indent=4)
            f.write(json_string + "\n")


class LoggerChatModel:

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    def __call__(self, messages: List[Dict[str, str]]) -> str:
        # 401 (auth) and 400 (bad request) errors should not be retried
        NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404}

        max_retries = 3  # Reduced from 15 to avoid hour-long waits
        retry_delay = 5
        max_total_wait = 60  # Cap total retry wait time at 60 seconds
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                reply = self.llm.invoke(messages)
                parsed_reply = self.parse_llmresult(reply)
                LLMLogger.log_request(prompts=messages, parsed_reply=parsed_reply)
                return reply
            except HTTPStatusError as err:
                last_error = err
                # Check status code — fail fast on auth/config errors
                status_code = err.response.status_code if hasattr(err, "response") else 0
                if status_code in NON_RETRYABLE_STATUS_CODES:
                    logger.error(f"Non-retryable HTTP {status_code}: {str(err)[:200]}")
                    raise
                if status_code == 429:
                    wait_time = min(retry_delay, max_total_wait)
                    logger.warning(f"HTTP 429: Waiting {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    retry_delay = min(retry_delay * 2, 30)
                else:
                    wait_time = min(self.parse_wait_time_from_error_message(str(err)), max_total_wait)
                    logger.warning(f"HTTP error: Waiting {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
            except openai.RateLimitError as err:
                last_error = err
                wait_time = min(self.parse_wait_time_from_error_message(str(err)), max_total_wait)
                logger.warning(f"Rate limit: Waiting {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            except Exception as e:
                last_error = e
                # Check if this is a non-retryable HTTP error (401, 400, etc.)
                error_str = str(e)
                is_non_retryable = any(
                    code in error_str
                    for code in ["401", "400", "403", "404", "invalid api key", "authentication_error", "unexpected keyword argument"]
                )
                if is_non_retryable:
                    logger.error(f"Non-retryable error: {error_str[:200]}")
                    raise  # Fail fast on auth/config errors

                wait_time = min(retry_delay, max_total_wait)
                logger.error(f"Unexpected error: {error_str[:200]}, retrying in {wait_time}s (Attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                retry_delay = min(retry_delay * 2, 30)  # Cap delay at 30s

        logger.critical("Failed to get a response from the model after multiple attempts.")
        detail = str(last_error) if last_error else "unknown model error"
        raise Exception(f"Failed to get a response from the model: {detail}")

    def parse_llmresult(self, llmresult: AIMessage) -> Dict[str, Dict]:
        # Parse the LLM result into a structured format.
        content = llmresult.content
        response_metadata = llmresult.response_metadata
        id_ = llmresult.id
        usage_metadata = llmresult.usage_metadata

        parsed_result = {
            "content": content,
            "response_metadata": {
                "model_name": response_metadata.get("model_name", ""),
                "system_fingerprint": response_metadata.get("system_fingerprint", ""),
                "finish_reason": response_metadata.get("finish_reason", ""),
                "logprobs": response_metadata.get("logprobs", None),
            },
            "id": id_,
            "usage_metadata": {
                "input_tokens": usage_metadata.get("input_tokens", 0),
                "output_tokens": usage_metadata.get("output_tokens", 0),
                "total_tokens": usage_metadata.get("total_tokens", 0),
            },
        }
        return parsed_result
