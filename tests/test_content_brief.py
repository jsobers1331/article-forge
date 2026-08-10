import copy
import unittest

from scripts.generate_prompt import render
from scripts.validate_content_brief import validate_config


def config():
    return {
        "site_name": "Example",
        "domain": "example.test",
        "category_frame": "bill tracker",
        "not_positioned_as": "budgeting app",
        "icp": "household organizers",
        "canonical_definition_sentence": "Example is a bill tracker for households.",
        "verified_facts": {
            "real_differentiators": [],
            "coming_soon_features": [],
            "pricing_and_billing": {},
            "has_real_testimonials": False,
            "has_real_press_mentions": False,
            "has_real_usage_stats": False,
        },
        "competitors": [],
        "existing_pages": ["/pricing"],
        "current_month_year": "August 2026",
        "voice": {},
        "content_targeting": {
            "allow_personal_data": False,
            "prohibit_protected_class_targeting": True,
            "allow_programmatic_location_pages": False,
            "min_local_evidence_sources": 2,
            "max_evidence_age_days": 365,
        },
        "audience_segments": [{
            "id": "unequal-income-households",
            "label": "Households dividing recurring bills with different incomes",
            "type": "life_situation",
            "needs": ["an agreed fair split"],
        }],
        "locations": [{
            "id": "global-en",
            "label": "International English-speaking households",
            "scope": "global",
            "language": "en",
        }],
        "evidence_sources": [],
        "topic_backlog": [{
            "title": "How to split bills based on income",
            "type": "standard",
            "target_query": "how to split bills based on income",
            "audience_segment_ids": ["unequal-income-households"],
            "location_id": "global-en",
            "evidence_source_ids": [],
            "image_plan": [{
                "role": "editorial_hero",
                "subject": "two house keys on separate hooks",
                "composition": "side-on close-up by a front door",
                "named_props": ["keys"],
                "alt": "Two house keys on separate hooks beside a front door",
            }],
        }],
    }


class ContentBriefTests(unittest.TestCase):
    def test_valid_global_brief_renders_targeting_context(self):
        value = config()
        errors, warnings = validate_config(value, strict=True)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        prompt = render(value, value["topic_backlog"][0])
        self.assertIn("Audience, locale, sources, and visuals", prompt)
        self.assertIn("Households dividing recurring bills", prompt)
        self.assertIn("International English-speaking households", prompt)

    def test_city_requires_unique_value_and_evidence(self):
        value = config()
        value["locations"] = [{"id": "london", "label": "London", "scope": "city"}]
        value["topic_backlog"][0]["location_id"] = "london"
        errors, _ = validate_config(value, strict=True)
        self.assertTrue(any("original_editorial" in error for error in errors))
        self.assertTrue(any("unique_local_value" in error for error in errors))
        self.assertTrue(any("evidence_source_ids" in error for error in errors))

    def test_duplicate_visual_fingerprint_is_blocked(self):
        value = config()
        duplicate = copy.deepcopy(value["topic_backlog"][0])
        duplicate["target_query"] = "another question"
        value["topic_backlog"].append(duplicate)
        errors, _ = validate_config(value, strict=True)
        self.assertTrue(any("repeats the visual fingerprint" in error for error in errors))

    def test_demographic_profile_is_not_a_valid_segment_type(self):
        value = config()
        value["audience_segments"][0]["type"] = "demographic"
        errors, _ = validate_config(value, strict=True)
        self.assertTrue(any("demographic profiling" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
