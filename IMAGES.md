# Image Rules

A model-agnostic, site-agnostic ruleset for adding AI-generated supporting imagery to
articles produced by this framework. Distilled from cross-model research (DeepSeek API,
direct Codex CLI, Claude Fable) plus a real generate-and-inspect test cycle against
OpenAI's GPT Image 2 (2026-08-09) — including one real failure and its fix. Companion
to `RULES.md`; read that first for the article-writing rules this assumes.

## 1. Scope — what this covers and doesn't

- **Covers:** AI-generated hero/OG images and mood/emotional supporting images.
- **Does NOT cover:** real product screenshots — but see §1a for exactly when a
  screenshot is the right call vs. when it isn't.

### 1a. The screenshot-vs-AI decision rule

**Use a real screenshot only when the placement's specific job is to prove a real
feature exists. Generate AI imagery for everything else.** This is a gate, not a
default toward either option:

- A setup/how-to step describing a concrete UI action ("click Add Bill," "here's the
  settle-up screen") → real screenshot. The reader needs proof that thing exists and
  looks like that, not an illustration of the idea.
- A hero/OG image, a mood shot for a pain-point section, anything establishing tone
  rather than proving a specific feature → AI-generated. Don't screenshot the
  dashboard just because it's available; a generic dashboard shot proves nothing a
  specific reader came to that section to check.

**When you do need a screenshot, capture one that's actually topic-specific — don't
reach for whatever's already sitting in an asset library.** On 2026-08-09 the first
version of this exact pipeline placed an existing `dashboard.webp` (already used
elsewhere on the site, on a different page, for a different purpose) into an article's
setup section — technically real, but not chosen for what that section specifically
needed to prove. The fix was capturing a NEW screenshot of the exact UI moment the
section describes (the "Add a new bill" form itself, for a manual-entry claim) using
the app's own local Playwright + seeded-database harness (most real apps being
marketed already have one, built for exactly this purpose — check for
`scripts/screenshot-capture.mjs` or similar before building a new harness from
scratch). A screenshot chosen because it's on-topic beats one chosen because it's
already there, even when the already-there one is perfectly real and unfabricated.
- **Never generate:** anything implying real customer social proof. If
  `verified_facts.has_real_testimonials` is `false` in `site-config.<project>.json`, no image may
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
   somewhere in the scene, everything else warm-neutral/muted. This is what makes a set
   of generated images read as one consistent house style.
4. **Natural light + material texture cues**: "soft morning window light," "a faint
   coffee ring," "a folded corner" — small imperfections that read as real rather than
   rendered.
5. **The same hard negative list every time**: no people, no hands (unless the
   placement specifically calls for a hand/person — see §5), no glossy 3D render look,
   no charts/graphs/data visualizations, no logos, no legible text anywhere.

**Corrected on 2026-08-09 — the unifying thread must NOT be the whole composition.**
The first four images generated with this pattern all used the identical scene
formula — overhead shot, wooden table, closed notebook, mug, blank paper — varying
only the small props around that formula. The result was four images that read as
near-duplicates of each other, because "keep the house style consistent" had been
misapplied as "repeat the same composition," not just "repeat the same color and
light quality." Fixed by writing an explicit shot list BEFORE generating, with one row
per image:

| Image | Angle/distance | Location/objects | Accent placement |
|---|---|---|---|
| Hero A | Low-angle close-up | Single wallet on a windowsill | Teal stitching on the wallet |
| Hero B | Close-up, wall-mounted | Two keys on a door hook | Teal keychain tag on one key |

Two images from that table shared zero named props and a completely different
camera angle/distance — genuinely distinct — while both still read as the same site's
photography because of the shared light quality and the single teal accent (on a
*different* object each time, never the same recurring prop). **Rule of thumb: no two
images in one set should share more than one named prop or the same angle+distance
combination.** If you catch yourself reaching for the same "overhead tablescape"
setup for a second image, that's the signal to write the shot list instead.

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

### 5a. Give every image a different job

Before generating, put a topic-level `image_plan` in the site config. Each item
must name a role, literal subject, composition, named props, and accessible alt
text. Valid roles are `editorial_hero`, `contextual_editorial`,
`feature_proof_screenshot`, `explanatory_visual`, and `data_visualization`.

- The hero is a representative editorial image, never a blank placeholder or a
  product dashboard by default.
- A feature-proof screenshot is allowed only when it proves the exact verified
  feature described nearby; name the feature and its tier in the plan.
- An explanatory visual or data visualization must be based on supplied,
  verifiable data. Do not use an image model to invent a chart.
- No two images in a topic may share a role, and no two topics may reuse the
  same role + subject + composition + prop fingerprint. The deterministic
  `scripts/validate_content_brief.py` preflight enforces this planning guard;
  still inspect the finished pixels with the checklist below.

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
