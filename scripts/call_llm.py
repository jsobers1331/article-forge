"""Provider-agnostic LLM caller.

Works with any OpenAI-compatible chat-completions endpoint (DeepSeek, OpenAI,
OpenRouter, Groq, local Ollama, etc.) plus native Anthropic — one function,
swap providers via config or CLI flags. No provider-specific SDKs required.
"""

import json
import os
import urllib.request

PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/chat/completions",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "kind": "openai_compatible",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1/chat/completions",
        "api_key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
        "kind": "openai_compatible",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "api_key_env": "OPENROUTER_API_KEY",
        "default_model": "deepseek/deepseek-chat:free",
        "kind": "openai_compatible",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "api_key_env": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
        "kind": "openai_compatible",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1/chat/completions",
        "api_key_env": None,
        "default_model": "llama3.1",
        "kind": "openai_compatible",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1/messages",
        "api_key_env": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-5",
        "kind": "anthropic",
    },
}


def call_llm(prompt, provider=None, model=None, base_url=None, api_key_env=None,
             kind=None, max_tokens=4000, temperature=0.4, timeout=180):
    """Send `prompt` to a chat model and return the response text.

    Pass a known `provider` name (see PROVIDERS) to use its defaults, or
    supply `base_url`/`api_key_env`/`kind` directly to hit any other
    OpenAI-compatible or Anthropic-compatible endpoint.
    """
    if provider:
        cfg = PROVIDERS[provider]
        base_url = base_url or cfg["base_url"]
        api_key_env = api_key_env if api_key_env is not None else cfg["api_key_env"]
        model = model or cfg["default_model"]
        kind = kind or cfg["kind"]

    if not base_url or not model or not kind:
        raise ValueError("Need either a known `provider`, or base_url + model + kind")

    api_key = os.environ.get(api_key_env) if api_key_env else None
    if api_key_env and not api_key:
        raise RuntimeError(f"{api_key_env} not set (check your .env file)")

    if kind == "openai_compatible":
        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode("utf-8")
        headers = {"content-type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(base_url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    if kind == "anthropic":
        body = json.dumps({
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        headers = {
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        req = urllib.request.Request(base_url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return "".join(block["text"] for block in data["content"] if block["type"] == "text")

    raise ValueError(f"Unknown kind: {kind}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Send a prompt to any configured LLM provider")
    parser.add_argument("--provider", choices=sorted(PROVIDERS), help="Known provider shortcut")
    parser.add_argument("--model", help="Override the provider's default model")
    parser.add_argument("--base-url", help="Custom OpenAI-compatible/Anthropic endpoint")
    parser.add_argument("--api-key-env", help="Env var name holding the API key for --base-url")
    parser.add_argument("--kind", choices=["openai_compatible", "anthropic"], help="Request shape for --base-url")
    parser.add_argument("--prompt-file", required=True, help="Path to a text/markdown file containing the prompt")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    with open(args.prompt_file, "r", encoding="utf-8") as f:
        prompt_text = f.read()

    print(call_llm(
        prompt_text,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
        kind=args.kind,
    ))
