You are generating one supporting image for an article on {site_name}.

## Placement

- Article: {article_title}
- Placement: {placement} (e.g. "hero", "mood — <section name>")
- This image supports the article; it is NOT a product screenshot and must not imply
  one. Do not attempt to render any app UI, dashboard, or interface.
- Make the composition distinct from prior article assets: vary the camera angle,
  subject distance, and named props while keeping the site's palette and light quality
  coherent. Run `scripts/check_image.py` after export with the final alt text and prior
  asset directory.

## Hard rules (see IMAGES.md for full rationale)

1. Every paper, notebook, phone, or screen surface in the scene must be described as
   structurally blank, closed, or turned away from the camera — never "no visible text"
   as a bare negative instruction. Naming the blank/closed/face-down state is what
   actually prevents garbled pseudo-text; saying "no text" alone does not.
2. Exactly one accent color across the whole scene: {accent_color}. Every other surface
   is warm-neutral/muted (cream, charcoal, walnut wood, or equivalent for this site's
   palette).
3. People and hands are allowed when this placement benefits from a human-centered
   scene. If included, use a fictional, non-identifiable editorial subject with a
   natural action and expression; never imply a real customer, testimonial, or review.
   If the placement is object-only, omit people and hands entirely.
4. No logos, no bank/financial-institution branding, no fake app UI, no charts, no
   graphs, no data visualizations, no legible numbers anywhere in frame.
5. No glossy 3D-render look — this must read as real photography: name a lens (e.g.
   50mm), a light source (e.g. soft morning window light from the left), and one small
   real-world imperfection (a coffee ring, a folded corner, a worn edge).
6. If a social-proof read is even remotely possible (a posed person, a device that
   could look like it's displaying a review, or a caption naming a subject), remove
   that implication — this site has zero real testimonials and no image may imply
   otherwise. A candid fictional person is fine when the scene's action clearly
   supports the article rather than the product's claimed usage.

## Scene

{scene_description}

Compose as: {composition_notes}

Write this as a single, concrete, photographic prompt — not a list of requirements
restated. Ground it in the camera/light/material details above.
