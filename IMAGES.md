# Image Rules

A model-agnostic, site-agnostic ruleset for adding AI-generated supporting imagery to
articles produced by this framework. Distilled from cross-model research (DeepSeek API,
direct Codex CLI, Claude Fable) plus a real generate-and-inspect test cycle against
OpenAI's GPT Image 2 (2026-08-09) — including one real failure and its fix. Companion
to `RULES.md`; read that first for the article-writing rules this assumes.

## 1. Scope — what this covers and doesn't

- **Covers:** AI-generated hero/OG images and mood/emotional supporting images.
- **Does NOT cover:** real product screenshots. Those are authentic proof the product
  exists and should be captured directly from the app (e.g. via browser automation),
  never AI-generated. Screenshots should dominate an article's imagery; AI-generated
  images are supporting, not primary.
- **Never generate:** anything implying real customer social proof. If
  `verified_facts.has_real_testimonials` is `false` in `site-config.json`, no image may
  be captioned or imply a real customer, review, or testimonial — full stop. Generic
  mood/lifestyle photography that doesn't claim to depict a real customer is fine; a
  photo captioned "HomeWeal user Sarah" would not be.

## 2. Model choice

**Primary: OpenAI GPT Image 2** (`gpt-image-2`, via the Images API,
`/v1/images/generations`). Confirmed working with real billing and validated real cost
in this framework's own test run (§4). Strong at precise, controlled compositions —
which matters more here than raw photorealism-per-dollar, because the failure mode that
actually bit us (§4) was a composition problem (the model rendering fake data/text where
told not to), not a realism problem.

**Do not default to Google Imagen** without checking current status first. Imagen 4
(`imagen-4.0-generate-001`) was scheduled for shutdown by Google on 2026-08-17; Google's
own migration path points to `gemini-2.5-flash-image` ("Nano Banana") via
`generate_content` instead of the dedicated `generate_images` API. This is a fast-moving
space — **before committing to any model, verify it's still the current one**, the same
way this rule itself needed a live check rather than trusting the cross-model
consultation's confident-but-stale recommendation.

**A free-tier API key is not the same as a working key.** In this framework's own test,
a `GEMINI_API_KEY` that worked fine for text generation returned `429
RESOURCE_EXHAUSTED` with a hard `limit: 0` for image generation on the free tier —
image generation needed billing enabled, text generation didn't. Probe the actual
capability with a real cheap call before planning around a provider; don't assume a key
that works for one modality works for another.

## 3. The prompt pattern that works (and what failed first)

**What failed:** a prompt that said *"no readable text on any bill or notebook page"*
as a bare negative instruction. The model rendered four bill-like documents with
garbled pseudo-charts and semi-legible fake numbers anyway — a negative instruction
about text is not enough to stop a photorealistic model from wanting to fill blank
paper with plausible-looking content.

**What worked:** describing every paper/screen surface as **structurally blank, closed,
or turned away from the camera** — not "no text" but "this notebook is closed," "this
bill is face-down showing its blank backside," "this phone shows only its plain back."
Removing the possibility of text rendering by removing the visible surface, rather than
instructing the model not to render text on a visible surface.

**Template pieces that reliably produce a clean, non-slop result:**

1. **Camera/lens direction**: e.g. "overhead editorial photograph, 50mm lens" —
   grounds the model in a real photographic convention instead of a generic render.
2. **Explicit blank/closed/face-down object list**: name every paper, screen, or
   book-like surface and state its state (closed, blank backside, face-down).
3. **Single brand-accent color rule**: one accent color (the site's real brand color)
   on exactly one object, everything else warm-neutral/muted. This is what makes a set
   of generated images read as one consistent house style rather than disconnected
   stock photos — reuse the identical accent-color instruction across every image for
   one article set.
4. **Natural light + material texture cues**: "soft morning window light," "a faint
   coffee ring," "a folded corner" — small imperfections that read as real rather than
   rendered.
5. **The same hard negative list every time**: no people, no hands (unless the
   placement specifically calls for a hand/person — see §5), no glossy 3D render look,
   no charts/graphs/data visualizations, no logos, no legible text anywhere.

See `prompts/image_prompt_template.md` for the fillable version of this pattern.

## 4. Cost — real, not estimated

Cross-model consultation estimated $0.10–00.15/image. Actual measured cost from this
framework's real test generations (GPT Image 2, `1536x1024`, OpenAI's published
token pricing: $5/M text input tokens, $30/M image output tokens):

| Image | Input tokens | Output tokens | Real cost |
|---|---|---|---|
| Test 1 (failed QC) | 125 | 601 | $0.0186 |
| Test 2 (fixed prompt) | 228 | 343 | $0.0114 |
| Set of 3 (simpler compositions) | ~215-229 each | 158 each | ~$0.006 each |

**Real range: $0.006–$0.02/image** — cheaper than every cross-model estimate. At 1–2
images/article and 3–4 articles/month, total monthly cost is **under $0.50** even with
several regeneration attempts per image. Cost is not the constraint; QC time is.

## 5. Images per article

**1–2 AI-generated images per article, maximum**, on top of any real product
screenshots (which are separate and should dominate):

- **Hero/OG image** — always. Placed right after the intro/answer-capsule paragraph,
  before the first H2.
- **One mood/pain-point image** — only if the article has a section describing a real
  emotional pain point (frustration, privacy anxiety, etc.). Placed at the end of that
  specific section, not generically at the top. Skip this second image for
  purely-informational sections (a features list, a pricing table) — it adds nothing
  there.
- Do not exceed 2. More than that dilutes the "screenshots are the real proof, mood
  images are supporting" hierarchy and starts to look like stock-photo padding.

## 6. Post-generation QC checklist

Every image, before it ships:

1. **Garbled text/fake data — the #1 failure mode.** Zoom to 200% on every paper,
   screen, or book-like surface. Any pseudo-text, pseudo-chart, or garbled numbers
   means regenerate with the blank/closed/face-down framing from §3, not a patch.
2. **Anatomy** — if a hand or person appears, check finger count, joints, proportions
   at 200% zoom.
3. **No accidental logos, bank branding, or fake UI** on any object (phones, laptops,
   packaging).
4. **No social-proof implication** — no image + caption combination that reads as a
   real customer, review, or testimonial. Alt text describes the scene, never "user" or
   a name.
5. **Brand palette consistency** — the same single accent color across every image in
   a set; reject anything neon, oversaturated, or off-palette.
6. **Resolution/aspect ratio** — confirm the export matches its placement (hero vs.
   in-article vs. OG/social crop) before shipping.
7. **House-style consistency** — images used across the same article, or across an
   article set, should read as one photographer's work (same grain, warmth, mattness),
   not visibly different generation runs.

This checklist has no automatable pattern — it requires actually looking at the image,
the same way RULES.md §11 requires actually reading a draft against `verified_facts`.
An automated file-size or dimension check is necessary but not sufficient.

## 7. Format and delivery

- Convert to WebP (or AVIF) before shipping; the raw PNG from most generators is far
  larger than needed. `quality=80-85` with PIL's `method=6` (or equivalent) gets a
  1536×1024 photographic image down to roughly 100-135KB.
- Descriptive, kebab-case filenames matching the article/placement (e.g.
  `best-tracker-hero.webp`, not `image1.webp`).
- Alt text describes the literal scene, written the same way you'd describe it to
  someone who can't see it — never a caption implying a real person or event.
