"""Structured extraction (structure_service.py). The OpenAI call is mocked."""

import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from recipes.structure_service import clean_structure, extract_recipe_structure

GOOD_RESPONSE = {
    "ingredients": [
        {"name": "Chicken Breast", "display": "2 fillets", "grams": 300},
        {"name": "rice", "display": "150 g", "grams": 150},
        {"name": "olive oil", "display": "1 tbsp", "grams": 14},
    ],
    "ai_kcal_per_serving": 520,
    "classic": {
        "is_classic": True,
        "classic_name": "Chicken burger",
        "core_ingredients": ["chicken breast", "burger bun", "lettuce", "mayonnaise"],
        "usual_minutes": 30,
        "missing": [{"ingredient": "lettuce", "reason": "not_in_your_ingredients", "replaced_with": "",
                     "equipment": "", "note": ""}],
    },
}


class CleanStructureTests(SimpleTestCase):
    def test_good_response_is_kept_and_tidied(self):
        structure, warnings = clean_structure(GOOD_RESPONSE)
        self.assertEqual(warnings, [])
        self.assertEqual(structure["ingredients"][0]["name"], "chicken breast")
        self.assertEqual(structure["classic"]["classic_name"], "Chicken burger")
        self.assertEqual(structure["ai_kcal_per_serving"], 520)

    def test_impossible_weights_are_dropped_with_a_warning(self):
        raw = {"ingredients": [{"name": "onion", "display": "1", "grams": 0},
                               {"name": "flour", "display": "1", "grams": 90000},
                               {"name": "salt", "display": "pinch", "grams": "lots"}]}
        structure, warnings = clean_structure(raw)
        self.assertEqual([i["grams"] for i in structure["ingredients"]], [0.0, 0.0, 0.0])
        self.assertEqual(len(warnings), 3)

    def test_unknown_reason_becomes_none_given(self):
        raw = json.loads(json.dumps(GOOD_RESPONSE))
        raw["classic"]["missing"][0]["reason"] = "because I said so"
        structure, _ = clean_structure(raw)
        self.assertEqual(structure["classic"]["missing"][0]["reason"], "none_given")

    def test_not_a_classic_clears_the_classic_fields(self):
        raw = json.loads(json.dumps(GOOD_RESPONSE))
        raw["classic"]["is_classic"] = False
        structure, _ = clean_structure(raw)
        self.assertEqual(structure["classic"]["core_ingredients"], [])
        self.assertEqual(structure["classic"]["missing"], [])

    def test_garbage_gives_an_empty_structure(self):
        structure, _ = clean_structure("not a dict")
        self.assertEqual(structure["ingredients"], [])
        self.assertFalse(structure["classic"]["is_classic"])


@override_settings(OPENAI_API_KEY="sk-test")
class ExtractTests(SimpleTestCase):
    def test_extraction_uses_a_strict_json_schema(self):
        client = MagicMock()
        client.responses.create.return_value = MagicMock(output_text=json.dumps(GOOD_RESPONSE))
        with patch("recipes.structure_service.OpenAI", return_value=client):
            result = extract_recipe_structure("RECIPE TITLE: Chicken burger", {"ingredients": "chicken"})
        self.assertEqual(len(result["structure"]["ingredients"]), 3)
        text_format = client.responses.create.call_args.kwargs["text"]["format"]
        self.assertEqual(text_format["type"], "json_schema")
        self.assertTrue(text_format["strict"])

    def test_a_failed_call_returns_none_instead_of_raising(self):
        client = MagicMock()
        client.responses.create.side_effect = RuntimeError("network down")
        with patch("recipes.structure_service.OpenAI", return_value=client):
            self.assertIsNone(extract_recipe_structure("RECIPE TITLE: x", {}))
