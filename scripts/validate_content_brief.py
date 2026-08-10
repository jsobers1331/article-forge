"""Validate Article Forge's audience, locale, evidence, and image-plan brief.

The generator can write for a specific audience need and location, but this is
not a license to mass-produce near-duplicate city pages or profile people. This
deterministic preflight catches configuration mistakes before an LLM sees a
topic. It validates the brief, not a source's truth; a human must still read
every cited source and keep its claims current.
"""

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path


ALLOWED_AUDIENCE_TYPES = {"life_situation", "job_to_be_done", "role"}
ALLOWED_LOCATION_SCOPES = {"global", "country", "region", "city"}
ALLOWED_IMAGE_ROLES = {
    "editorial_hero",
    "contextual_editorial",
    "feature_proof_screenshot",
    "explanatory_visual",
    "data_visualization",
}


def _as_ids(items):
    return {item.get("id") for item in items if isinstance(item, dict) and item.get("id")}


def _age_in_days(value):
    try:
        return (dt.date.today() - dt.date.fromisoformat(value)).days
    except (TypeError, ValueError):
        return None


def _fingerprint(image):
    """A planning guard, not a perceptual-image matcher.

    Naming the subject, camera/composition, and props catches the recurring
    same-dashboard / same-tablescape failure before images are generated.
    """
    fields = [
        image.get("role", ""),
        image.get("subject", ""),
        image.get("composition", ""),
        ",".join(image.get("named_props", [])),
    ]
    return "|".join(re.sub(r"\s+", " ", str(value).strip().lower()) for value in fields)


def validate_config(config, topic_index=None, strict=False):
    """Return ``(errors, warnings)`` for an Article Forge config.

    Legacy configurations remain valid unless ``content_targeting`` is present
    or ``strict`` is requested. Existing users can adopt the safety gate without
    silently weakening their current generation path.
    """
    errors, warnings = [], []
    policy = config.get("content_targeting")
    if not policy and not strict:
        return errors, warnings
    if not isinstance(policy, dict):
        return ["content_targeting must be an object when targeting validation is enabled"], warnings

    if policy.get("allow_personal_data", False):
        errors.append("content_targeting.allow_personal_data must be false")
    if policy.get("allow_programmatic_location_pages", False):
        errors.append("content_targeting.allow_programmatic_location_pages must be false")
    if policy.get("prohibit_protected_class_targeting") is not True:
        errors.append("content_targeting.prohibit_protected_class_targeting must be true")

    audiences = config.get("audience_segments", [])
    locations = config.get("locations", [])
    sources = config.get("evidence_sources", [])
    audience_ids, location_ids, source_ids = _as_ids(audiences), _as_ids(locations), _as_ids(sources)

    if len(audience_ids) != len(audiences):
        errors.append("every audience_segments entry needs a unique id")
    if len(location_ids) != len(locations):
        errors.append("every locations entry needs a unique id")
    if len(source_ids) != len(sources):
        errors.append("every evidence_sources entry needs a unique id")

    for audience in audiences:
        if not isinstance(audience, dict):
            errors.append("audience_segments entries must be objects")
            continue
        audience_type = audience.get("type")
        if audience_type not in ALLOWED_AUDIENCE_TYPES:
            errors.append(
                f"audience segment {audience.get('id', '<missing>')!r} must use one of "
                f"{sorted(ALLOWED_AUDIENCE_TYPES)}, not demographic profiling"
            )
        if not audience.get("label") or not audience.get("needs"):
            errors.append(f"audience segment {audience.get('id', '<missing>')!r} needs label and needs")

    for location in locations:
        if not isinstance(location, dict):
            errors.append("locations entries must be objects")
            continue
        scope = location.get("scope")
        location_id = location.get("id", "<missing>")
        if scope not in ALLOWED_LOCATION_SCOPES:
            errors.append(f"location {location_id!r} has unsupported scope {scope!r}")
            continue
        if scope == "country" and not (location.get("country_code") and location.get("language")):
            errors.append(f"country location {location_id!r} needs country_code and language")
        if scope in {"region", "city"}:
            if location.get("generation_mode") != "original_editorial":
                errors.append(f"{scope} location {location_id!r} must set generation_mode to original_editorial")
            if len(location.get("unique_local_value", [])) < 2:
                errors.append(f"{scope} location {location_id!r} needs at least two unique_local_value items")
            if len(location.get("evidence_source_ids", [])) < 2:
                errors.append(f"{scope} location {location_id!r} needs at least two evidence_source_ids")

    for source in sources:
        if not isinstance(source, dict):
            errors.append("evidence_sources entries must be objects")
            continue
        source_id = source.get("id", "<missing>")
        if not source.get("label") or not re.match(r"^https://", source.get("url", "")):
            errors.append(f"evidence source {source_id!r} needs a label and an https URL")
        age = _age_in_days(source.get("verified_on"))
        if age is None:
            errors.append(f"evidence source {source_id!r} needs verified_on as YYYY-MM-DD")
        elif age > policy.get("max_evidence_age_days", 365):
            warnings.append(f"evidence source {source_id!r} was last verified {age} days ago")

    topics = config.get("topic_backlog", [])
    selected = [(topic_index, topics[topic_index])] if topic_index is not None else enumerate(topics)
    image_fingerprints = {}
    for index, topic in selected:
        if not isinstance(topic, dict):
            errors.append(f"topic {index} must be an object")
            continue
        prefix = f"topic {index} ({topic.get('target_query', topic.get('title', '<untitled>'))!r})"
        segment_ids = topic.get("audience_segment_ids", [])
        if not segment_ids:
            errors.append(f"{prefix} needs at least one audience_segment_ids entry")
        unknown_audiences = set(segment_ids) - audience_ids
        if unknown_audiences:
            errors.append(f"{prefix} names unknown audience segments: {sorted(unknown_audiences)}")

        location_id = topic.get("location_id")
        if location_id not in location_ids:
            errors.append(f"{prefix} needs a valid location_id")
        evidence_ids = set(topic.get("evidence_source_ids", []))
        unknown_sources = evidence_ids - source_ids
        if unknown_sources:
            errors.append(f"{prefix} names unknown evidence sources: {sorted(unknown_sources)}")
        location = next((item for item in locations if item.get("id") == location_id), {})
        needs_local_evidence = location.get("scope") in {"country", "region", "city"} or topic.get("requires_local_evidence")
        min_sources = policy.get("min_local_evidence_sources", 2)
        if needs_local_evidence and len(evidence_ids) < min_sources:
            errors.append(f"{prefix} needs at least {min_sources} verified evidence sources for local claims")

        image_plan = topic.get("image_plan", [])
        if not image_plan:
            errors.append(f"{prefix} needs an image_plan with at least one image")
        roles = set()
        for image_index, image in enumerate(image_plan):
            if not isinstance(image, dict):
                errors.append(f"{prefix} image {image_index} must be an object")
                continue
            role = image.get("role")
            if role not in ALLOWED_IMAGE_ROLES:
                errors.append(f"{prefix} image {image_index} has invalid role {role!r}")
            if role in roles:
                errors.append(f"{prefix} repeats image role {role!r}")
            roles.add(role)
            if not image.get("alt") or not image.get("subject") or not image.get("composition"):
                errors.append(f"{prefix} image {image_index} needs alt, subject, and composition")
            if role == "feature_proof_screenshot" and not image.get("verified_feature"):
                errors.append(f"{prefix} screenshot image {image_index} needs verified_feature")
            fingerprint = _fingerprint(image)
            if fingerprint in image_fingerprints:
                errors.append(
                    f"{prefix} image {image_index} repeats the visual fingerprint from "
                    f"topic {image_fingerprints[fingerprint]}"
                )
            else:
                image_fingerprints[fingerprint] = index

    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description="Validate an Article Forge audience/locale/evidence/image brief")
    parser.add_argument("--config", required=True)
    parser.add_argument("--topic-index", type=int)
    parser.add_argument("--strict", action="store_true", help="Require the new targeting schema even for legacy configs")
    args = parser.parse_args()

    with Path(args.config).open(encoding="utf-8") as handle:
        config = json.load(handle)
    try:
        errors, warnings = validate_config(config, args.topic_index, args.strict)
    except IndexError:
        print(f"FAIL: topic index {args.topic_index} is out of range", file=sys.stderr)
        sys.exit(1)
    for warning in warnings:
        print(f"WARN: {warning}")
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
    print("PASS: audience, locale, evidence, and image-plan brief is valid")


if __name__ == "__main__":
    main()
