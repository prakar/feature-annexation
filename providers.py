"""
providers.py — multi-provider abstraction for the Feature Annexation
verification pipeline.

HONESTY NOTE FOR WHOEVER RUNS THIS (read before trusting output from anything
other than --provider anthropic): the Anthropic path in this file is the
SAME streaming/pause_turn/heartbeat logic that was already debugged across
several real runs against real data in this project -- it's known-good. The
OpenAI, Gemini, and Grok paths below were written from current API
documentation but have NOT been run against a live API by the author (no
network access in the environment that wrote this code). They are
mechanically reasonable based on each vendor's documented SDK shape as of
mid-2026, but the model ID strings, exact tool-config field names, and
response object shapes are exactly the kind of thing that drifts between
SDK minor versions. Treat your first run on each new provider as a real
test, not a known-working path -- run with --limit 1 first, the same
caution that caught real bugs on the Anthropic path early on.

Design choice: rather than reimplement token-level streaming for three
unfamiliar SDKs (high risk of subtly wrong event-type guessing, the kind of
bug that's hard to catch without live testing), these three providers use a
plain blocking call wrapped in a background-thread heartbeat. This gives the
same UX guarantee that fixed the "looks hung" complaint on the Anthropic
path -- a log line every ~5s no matter how slow the call is -- without
needing to get an unfamiliar streaming event schema exactly right on a
single untested attempt.
"""

import os
import re
import json
import time
import threading
import logging

log = logging.getLogger("feature_annexation_pipeline")

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5.5",
    "gemini": "gemini-3.5-flash",
    "grok": "grok-4.3",
}


def extract_json(full_text):
    """
    Provider-agnostic JSON extraction, carried over unchanged from the
    Anthropic-only version of this pipeline. Tolerant of preamble text
    before a fenced ```json block (observed in practice on the Anthropic
    path -- the model frequently writes a sentence before the JSON despite
    being told not to) and falls back to first-brace/last-brace matching.
    There's no reason to expect OpenAI/Gemini/Grok will behave any better
    about following "JSON only" instructions, so this same tolerance is
    applied to all providers rather than assuming the others will comply.
    """
    if not full_text or not full_text.strip():
        raise RuntimeError("Model returned no text content at all.")

    full_text = full_text.strip()
    json_text = None

    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", full_text, re.DOTALL)
    if fence_match:
        json_text = fence_match.group(1).strip()
        log.debug("  Extracted JSON from a fenced code block (preamble of %d chars discarded).",
                  fence_match.start())
    else:
        # BUG FIX NOTE: this used to only look for '{' ... '}', which silently
        # mangled any response that was a top-level JSON ARRAY rather than an
        # object -- exactly what score_fam_dimensions.py asks for (a JSON array
        # of 50 entries). Grabbing from the first '{' to the last '}' in that
        # case skips the array's own '[' and ']' entirely, producing
        # comma-joined-but-unwrapped objects that fail with a misleading
        # "Extra data" error at the boundary between the first and second
        # object -- confirmed by reproducing it directly against Grok's actual
        # response text. Fix: detect whether '[' or '{' comes first in the
        # text, and grab the matching outer bracket type accordingly.
        first_brace = full_text.find("{")
        first_bracket = full_text.find("[")

        if first_bracket != -1 and (first_brace == -1 or first_bracket < first_brace):
            start, end_char = first_bracket, "]"
        else:
            start, end_char = first_brace, "}"

        end = full_text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            json_text = full_text[start:end + 1]
            log.debug("  No fenced block found; extracted via first '%s' / last '%s' "
                      "(preamble of %d chars discarded).", full_text[start], end_char, start)

    if json_text is None:
        preview = full_text[:500] + ("..." if len(full_text) > 500 else "")
        log.error("  Could not locate any JSON object in the response. Raw text:\n%s", preview)
        raise json.JSONDecodeError("No JSON object found in response text", full_text, 0)

    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        preview = json_text[:500] + ("..." if len(json_text) > 500 else "")
        log.error("  Extracted text still failed to parse as JSON:\n%s", preview)
        raise


def _run_with_heartbeat(blocking_fn, label):
    """
    Run a blocking API call in a background thread while logging a
    heartbeat every 5s in the main thread -- gives the OpenAI/Gemini/Grok
    paths the same "never silent for more than ~5s" guarantee the Anthropic
    streaming path has, without needing token-level streaming.
    """
    result_box = {}
    error_box = {}

    def target():
        try:
            result_box["value"] = blocking_fn()
        except Exception as e:
            error_box["error"] = e

    thread = threading.Thread(target=target, daemon=True)
    start = time.monotonic()
    thread.start()

    while thread.is_alive():
        thread.join(timeout=5.0)
        if thread.is_alive():
            log.info("  [%.1fs] ...still waiting on %s (no token-level visibility for this "
                      "provider, but the request is still in flight)...",
                      time.monotonic() - start, label)

    if "error" in error_box:
        raise error_box["error"]
    return result_box["value"]


def call_anthropic(prompt, model, max_uses=4, max_tokens=8000, verbose=False):
    """
    The known-good path. Streaming, web search cap, pause_turn continuation,
    5s heartbeat -- identical logic to what was already debugged in
    verify_events.py across several real runs. Returns (full_text,
    search_count, stop_reason, input_tokens, output_tokens).
    """
    from anthropic import Anthropic
    client = Anthropic(timeout=180.0)

    call_start = time.monotonic()
    text_parts = []
    search_count = 0
    web_search_tool = {"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}
    last_heartbeat = [call_start]

    messages = [{"role": "user", "content": prompt}]
    final_message = None
    continuation_round = 0

    while True:
        continuation_round += 1
        if continuation_round > 1:
            log.info("  [%.1fs] stop_reason was 'pause_turn' -- continuing (round %d)...",
                      time.monotonic() - call_start, continuation_round)

        round_text_parts = []
        with client.messages.stream(
            model=model, max_tokens=max_tokens, messages=messages, tools=[web_search_tool],
        ) as stream:
            for event in stream:
                etype = getattr(event, "type", None)
                if etype == "content_block_start":
                    block = getattr(event, "content_block", None)
                    block_type = getattr(block, "type", None)
                    if block_type == "server_tool_use":
                        search_count += 1
                        log.info("  [%.1fs] Web search #%d starting...",
                                  time.monotonic() - call_start, search_count)
                    elif block_type == "text":
                        log.info("  [%.1fs] Model is composing its JSON answer now...",
                                  time.monotonic() - call_start)
                elif etype == "content_block_stop":
                    block = getattr(event, "content_block", None)
                    if getattr(block, "type", None) == "web_search_tool_result":
                        log.info("  [%.1fs] Web search #%d returned results.",
                                  time.monotonic() - call_start, search_count)
                elif etype == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if getattr(delta, "type", None) == "text_delta":
                        round_text_parts.append(delta.text)
                        now = time.monotonic()
                        if now - last_heartbeat[0] >= 5.0:
                            last_heartbeat[0] = now
                            log.info("  [%.1fs] ...still streaming the answer (%d chars so far)...",
                                      now - call_start, sum(len(t) for t in round_text_parts))
            final_message = stream.get_final_message()

        text_parts.extend(round_text_parts)
        stop_reason = getattr(final_message, "stop_reason", None)
        if stop_reason != "pause_turn":
            break
        messages = messages + [{"role": "assistant", "content": final_message.content}]
        if continuation_round > 6:
            raise RuntimeError(f"Stuck in pause_turn loop after {continuation_round} rounds.")

    return ("".join(text_parts), search_count, stop_reason,
            getattr(final_message.usage, "input_tokens", -1),
            getattr(final_message.usage, "output_tokens", -1))


def call_openai(prompt, model, verbose=False):
    """
    UNTESTED against a live API (see module docstring). Built against
    OpenAI's documented Responses API shape: client.responses.create(model=,
    tools=[{"type": "web_search"}], input=). Returns (full_text, search_count
    [best-effort, may be 0 if usage doesn't expose it], stop_reason
    [approximated], input_tokens, output_tokens).
    """
    from openai import OpenAI
    client = OpenAI()

    def do_call():
        return client.responses.create(
            model=model,
            input=prompt,
            tools=[{"type": "web_search"}],
        )

    response = _run_with_heartbeat(do_call, f"OpenAI ({model})")

    full_text = getattr(response, "output_text", None) or ""
    # Best-effort search count: count web_search_call items in response.output if present.
    search_count = 0
    output_items = getattr(response, "output", None) or []
    for item in output_items:
        if getattr(item, "type", None) == "web_search_call":
            search_count += 1

    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", -1) if usage else -1
    output_tokens = getattr(usage, "output_tokens", -1) if usage else -1
    stop_reason = "end_turn"  # Responses API doesn't expose an equivalent of pause_turn as of writing

    return full_text, search_count, stop_reason, input_tokens, output_tokens


def call_gemini(prompt, model, verbose=False):
    """
    UNTESTED against a live API (see module docstring). Built against
    google-genai's documented shape: client.models.generate_content(model=,
    contents=, config=GenerateContentConfig(tools=[Tool(google_search=GoogleSearch())])).
    Reads GOOGLE_API_KEY or GEMINI_API_KEY from environment (the genai SDK
    checks GOOGLE_API_KEY by default; GEMINI_API_KEY is aliased by some SDK
    versions -- if this fails with an auth error, try renaming your env var).
    """
    from google import genai
    from google.genai.types import Tool, GenerateContentConfig, GoogleSearch

    client = genai.Client()
    search_tool = Tool(google_search=GoogleSearch())

    def do_call():
        return client.models.generate_content(
            model=model,
            contents=prompt,
            config=GenerateContentConfig(tools=[search_tool]),
        )

    response = _run_with_heartbeat(do_call, f"Gemini ({model})")

    full_text = getattr(response, "text", None) or ""
    search_count = 0
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        grounding = getattr(candidates[0], "grounding_metadata", None)
        queries = getattr(grounding, "web_search_queries", None) if grounding else None
        search_count = len(queries) if queries else 0

    usage_meta = getattr(response, "usage_metadata", None)
    input_tokens = getattr(usage_meta, "prompt_token_count", -1) if usage_meta else -1
    output_tokens = getattr(usage_meta, "candidates_token_count", -1) if usage_meta else -1
    stop_reason = "end_turn"

    return full_text, search_count, stop_reason, input_tokens, output_tokens


def call_grok(prompt, model, verbose=False):
    """
    UNTESTED against a live API (see module docstring). Built against xAI's
    documented Responses API shape (OpenAI-compatible base_url):
    client.responses.create(model=, input=, tools=[{"type": "web_search"}]).
    Reuses the openai Python package pointed at xAI's base_url, per xAI's
    own documented "drop-in OpenAI compatibility" approach -- avoids needing
    a separate xai_sdk dependency for this simple case.
    """
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("XAI_API_KEY"), base_url="https://api.x.ai/v1")

    def do_call():
        return client.responses.create(
            model=model,
            input=[{"role": "user", "content": prompt}],
            tools=[{"type": "web_search"}],
        )

    response = _run_with_heartbeat(do_call, f"Grok ({model})")

    full_text = getattr(response, "output_text", None) or ""
    search_count = 0
    output_items = getattr(response, "output", None) or []
    for item in output_items:
        if getattr(item, "type", None) in ("web_search_call",):
            search_count += 1

    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", -1) if usage else -1
    output_tokens = getattr(usage, "output_tokens", -1) if usage else -1
    stop_reason = "end_turn"

    return full_text, search_count, stop_reason, input_tokens, output_tokens


CALLERS = {
    "anthropic": call_anthropic,
    "openai": call_openai,
    "gemini": call_gemini,
    "grok": call_grok,
}

REQUIRED_ENV_VAR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY (or GEMINI_API_KEY, depending on SDK version)",
    "grok": "XAI_API_KEY",
}

REQUIRED_PACKAGE = {
    "anthropic": "anthropic",
    "openai": "openai",
    "gemini": "google-genai",
    "grok": "openai",  # reused via xAI's OpenAI-compatible endpoint
}