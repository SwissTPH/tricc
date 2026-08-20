"""Regression tests for FHIRStrategy image support (itemMedia / itemAnswerMedia).

Covers (see fix/20260814-questionnaire-item-media.md):
1. A question node's ``.image`` becomes a Binary resource + an SDC itemMedia
   extension with a ``Binary/<id>`` URL on the Questionnaire.item (no inline
   ``Attachment.data`` — bytes live once on the Binary).
2. A select option's own ``.image`` becomes its own Binary resource + an SDC
   itemAnswerMedia extension with the same URL-only attachment.
3. Re-registering the same image file name is idempotent: one Binary, same id.
4. A node/option with no ``.image`` gets no extension and no Binary.
5. An ``.image`` with no matching ``project.images`` content is skipped
   (logged, not raised).

Run with:
    python -m pytest tests/test_strategies/test_fhir_item_media.py -v
"""

import unittest
from unittest.mock import MagicMock

from tricc_oo.converters.fhir.questionnaire_item_mapper import (
    SDC_EXT_ITEM_ANSWER_MEDIA,
    SDC_EXT_ITEM_MEDIA,
)
from tricc_oo.models.tricc import TriccNodeSelectOne, TriccNodeSelectOption
from tricc_oo.strategies.output.fhir_form import FHIRStrategy

IMAGE_PAYLOAD = "aGVsbG8="  # base64("hello") — content is opaque to these tests


def _make_strategy(images=None):
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    project.images = images or []
    return FHIRStrategy(project, "/tmp/fhir_item_media_test_out")


class TestItemMediaExtension(unittest.TestCase):
    def test_question_image_emits_item_media_and_binary(self):
        strategy = _make_strategy(
            images=[{"file_path": "q.png", "image_content": IMAGE_PAYLOAD}]
        )
        select = TriccNodeSelectOne(id="select_sex", name="select_sex", label="Sex", list_name="sex")
        select.image = "q.png"

        strategy.generate_base(select)

        item = strategy.questionnaires["main"]["item"][0]
        media_exts = [e for e in item.get("extension", []) if e["url"] == SDC_EXT_ITEM_MEDIA]
        self.assertEqual(len(media_exts), 1)
        attachment = media_exts[0]["valueAttachment"]
        self.assertEqual(attachment["contentType"], "image/png")
        self.assertTrue(attachment["url"].startswith("Binary/"))
        self.assertNotIn("data", attachment)

        binary_id = attachment["url"].split("/", 1)[1]
        self.assertEqual(len(strategy.binaries), 1)
        binary = strategy.binaries[0]
        self.assertEqual(binary["id"], binary_id)
        self.assertEqual(binary["resourceType"], "Binary")
        self.assertEqual(binary["contentType"], "image/png")
        self.assertEqual(binary["data"], IMAGE_PAYLOAD)

    def test_answer_option_image_emits_item_answer_media(self):
        strategy = _make_strategy(
            images=[
                {"file_path": "male.png", "image_content": IMAGE_PAYLOAD},
                {"file_path": "female.jpg", "image_content": IMAGE_PAYLOAD},
            ]
        )
        select = TriccNodeSelectOne(id="select_sex", name="select_sex", label="Sex", list_name="sex")
        male = TriccNodeSelectOption(
            id="opt_male", name="demo.male", label="Male", select=select, list_name="sex"
        )
        male.image = "male.png"
        female = TriccNodeSelectOption(
            id="opt_female", name="demo.female", label="Female", select=select, list_name="sex"
        )
        female.image = "female.jpg"
        select.options = {0: male, 1: female}

        strategy.generate_base(select)

        item = strategy.questionnaires["main"]["item"][0]
        options = item["answerOption"]
        self.assertEqual(len(options), 2)

        male_ext = options[0]["extension"][0]
        self.assertEqual(male_ext["url"], SDC_EXT_ITEM_ANSWER_MEDIA)
        self.assertEqual(male_ext["valueAttachment"]["contentType"], "image/png")
        self.assertTrue(male_ext["valueAttachment"]["url"].startswith("Binary/"))
        self.assertNotIn("data", male_ext["valueAttachment"])

        female_ext = options[1]["extension"][0]
        self.assertEqual(female_ext["url"], SDC_EXT_ITEM_ANSWER_MEDIA)
        # .jpg is normalized to the "jpeg" IANA subtype
        self.assertEqual(female_ext["valueAttachment"]["contentType"], "image/jpeg")
        self.assertTrue(female_ext["valueAttachment"]["url"].startswith("Binary/"))
        self.assertNotIn("data", female_ext["valueAttachment"])

        self.assertEqual(len(strategy.binaries), 2)

    def test_same_image_reused_is_registered_once(self):
        strategy = _make_strategy(
            images=[{"file_path": "shared.png", "image_content": IMAGE_PAYLOAD}]
        )
        select = TriccNodeSelectOne(id="select_a", name="select_a", label="A", list_name="a")
        select.image = "shared.png"
        opt = TriccNodeSelectOption(
            id="opt_a", name="demo.a", label="A", select=select, list_name="a"
        )
        opt.image = "shared.png"
        select.options = {0: opt}

        strategy.generate_base(select)

        self.assertEqual(len(strategy.binaries), 1)
        item = strategy.questionnaires["main"]["item"][0]
        item_media = next(e for e in item["extension"] if e["url"] == SDC_EXT_ITEM_MEDIA)
        option_media = item["answerOption"][0]["extension"][0]
        self.assertEqual(
            item_media["valueAttachment"]["url"], option_media["valueAttachment"]["url"]
        )

    def test_no_image_emits_no_extension_no_binary(self):
        strategy = _make_strategy()
        select = TriccNodeSelectOne(id="select_b", name="select_b", label="B", list_name="b")
        opt = TriccNodeSelectOption(
            id="opt_b", name="demo.b", label="B", select=select, list_name="b"
        )
        select.options = {0: opt}

        strategy.generate_base(select)

        item = strategy.questionnaires["main"]["item"][0]
        item_media = [e for e in item.get("extension", []) if e["url"] == SDC_EXT_ITEM_MEDIA]
        self.assertEqual(item_media, [])
        self.assertNotIn("extension", item["answerOption"][0])
        self.assertEqual(strategy.binaries, [])

    def test_missing_image_content_logged_and_skipped(self):
        strategy = _make_strategy(images=[])
        select = TriccNodeSelectOne(id="select_c", name="select_c", label="C", list_name="c")
        select.image = "missing.png"

        strategy.generate_base(select)

        item = strategy.questionnaires["main"]["item"][0]
        item_media = [e for e in item.get("extension", []) if e["url"] == SDC_EXT_ITEM_MEDIA]
        self.assertEqual(item_media, [])
        self.assertEqual(strategy.binaries, [])


if __name__ == "__main__":
    unittest.main()
