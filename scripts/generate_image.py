"""Provider-agnostic image generation for article supporting imagery.

See IMAGES.md before using this. Primary validated provider is OpenAI's GPT Image 2 —
confirmed working with real billing and real measured cost as of 2026-08-09. Google
Imagen 4 is NOT included here because it was scheduled for shutdown by Google on
2026-08-17; if you add a Google provider, verify current model status first (this
framework's own cross-model consultation confidently recommended Imagen 4 without
knowing it was about to be deprecated — don't repeat that mistake).

A free-tier API key is not proof a provider works: this framework's own GEMINI_API_KEY
returned a hard 0-quota error for image generation despite working fine for text. Do a
single cheap test call before planning around any provider.
"""

import argparse
import base64
import json
import os
import urllib.request

from check_image import check_image_asset

PROVIDERS = {
    "openai": {
        "base_url": "https://api.openai.com/v1/images/generations",
        "api_key_env": "OPENAI_API_KEY",
        "default_model": "gpt-image-2",
        "default_size": "1536x1024",
        # OpenAI's published token pricing (verify before relying on this for budgeting
        # at scale — it can change): $5/M text input tokens, $30/M image output tokens.
        "input_token_cost_per_million": 5.0,
        "output_token_cost_per_million": 30.0,
    },
}


def generate_image(
    prompt, out_path, provider="openai", model=None, size=None, timeout=120
):
    cfg = PROVIDERS[provider]
    api_key = os.environ.get(cfg["api_key_env"])
    if not api_key:
        raise RuntimeError(f"{cfg['api_key_env']} not set (check your .env file)")

    body = json.dumps(
        {
            "model": model or cfg["default_model"],
            "prompt": prompt,
            "size": size or cfg["default_size"],
            "n": 1,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        cfg["base_url"],
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    img_b64 = data["data"][0]["b64_json"]
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(img_b64))

    usage = data.get("usage", {})
    in_tok = usage.get("input_tokens", 0)
    out_tok = usage.get("output_tokens", 0)
    cost = (
        in_tok * cfg["input_token_cost_per_million"]
        + out_tok * cfg["output_token_cost_per_million"]
    ) / 1_000_000

    return {
        "path": out_path,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": cost,
    }


def convert_to_webp(png_path, webp_path, quality=82):
    from PIL import Image

    im = Image.open(png_path).convert("RGB")
    im.save(webp_path, "WEBP", quality=quality, method=6)
    return os.path.getsize(webp_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate one supporting image and convert to WebP"
    )
    parser.add_argument(
        "--prompt-file", required=True, help="Path to a text file with the image prompt"
    )
    parser.add_argument("--out", required=True, help="Output .webp path")
    parser.add_argument(
        "--alt", required=True, help="Descriptive alt text for the visible scene"
    )
    parser.add_argument(
        "--against",
        action="append",
        default=[],
        help="Prior image file or directory to scan for duplicate reuse; repeatable",
    )
    parser.add_argument("--receipt", help="Optional JSON image-quality receipt path")
    parser.add_argument("--provider", default="openai", choices=sorted(PROVIDERS))
    parser.add_argument("--model")
    parser.add_argument("--size")
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv()

    with open(args.prompt_file, "r", encoding="utf-8") as f:
        prompt_text = f.read()

    tmp_png = args.out.rsplit(".", 1)[0] + ".tmp.png"
    result = generate_image(
        prompt_text, tmp_png, provider=args.provider, model=args.model, size=args.size
    )
    size_bytes = convert_to_webp(tmp_png, args.out)
    os.remove(tmp_png)

    status, detail, receipt = check_image_asset(args.out, args.alt, args.against)
    if args.receipt:
        with open(args.receipt, "w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2)
            f.write("\n")
    if status != "PASS":
        os.remove(args.out)
        raise RuntimeError(f"Generated image failed quality gate: {detail}")

    print(f"Saved {args.out} ({size_bytes / 1024:.1f} KB)")
    print(
        f"Tokens: in={result['input_tokens']} out={result['output_tokens']} | cost ~${result['cost_usd']:.4f}"
    )
    print(f"Quality gate: {detail}")
    print(
        "Now run the visual QC checklist in IMAGES.md §6 before shipping — do not skip it."
    )
