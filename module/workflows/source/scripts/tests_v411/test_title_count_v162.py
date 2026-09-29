"""Frozen title counts, compatible readers and exact body delivery; no model calls."""
import copy
import unittest

from shared import title_publication as titles


def candidates(count=10):
    return {
        "candidates": [
            {"title": f"东莞医美机构推荐与选择参考{i}", "angle": "机构推荐"}
            for i in range(1, count + 1)
        ],
        "canonical_title_id": f"title_{count:02d}",
    }


def legacy_candidates():
    return {
        "families": {
            "decision_search": [f"历史决策标题{i}" for i in range(1, 11)],
            "media_pr": [f"历史媒体标题{i}" for i in range(1, 11)],
        },
        "canonical_title_id": "media_title_07",
    }


def accepted_review(raw):
    return {"outcome": "accepted", **copy.deepcopy(raw), "title_notes": [], "reason": ""}


class TitleCountContractTests(unittest.TestCase):
    def test_readers_infer_ten_or_twenty_and_strict_callers_require_frozen_count(self):
        for count in (10, 20):
            for p0, family in ((False, "article"), (True, "publicity")):
                with self.subTest(count=count, p0=p0):
                    raw = candidates(count)
                    before = copy.deepcopy(raw)
                    result = titles.validate_title_map(raw, p0=p0)
                    self.assertEqual(result, titles.validate_title_map(raw, p0=p0, expected_count=count))
                    self.assertEqual(result["requested_count"], count)
                    self.assertEqual(result["total_count"], count)
                    self.assertEqual(result["families"][family]["count"], count)
                    self.assertEqual([row["title_id"] for row in result["options"]],
                                     [f"title_{i:02d}" for i in range(1, count + 1)])
                    self.assertEqual(result["recommended_title_id"], f"title_{count:02d}")
                    self.assertEqual(raw, before)
                    with self.assertRaises(ValueError):
                        titles.validate_title_map(raw, p0=p0, expected_count=30 - count)

    def test_unsupported_sizes_and_invalid_expected_counts_are_rejected(self):
        for count in (0, 9, 11, 19, 21):
            with self.subTest(count=count), self.assertRaises(ValueError):
                titles.validate_title_map(candidates(count))
        for expected in (True, False, 10.0, "10", 0, 9, 11, 30, [], {}):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                titles.validate_title_map(candidates(), expected_count=expected)
        for invalid in (None, {}, "ten", tuple(candidates()["candidates"])):
            with self.subTest(candidates=invalid), self.assertRaises(ValueError):
                titles.validate_title_map({"candidates": invalid, "canonical_title_id": "title_01"})

    def test_canonical_recommendation_must_exist_in_actual_count(self):
        for count in (10, 20):
            for selected in (None, "", "title_00", f"title_{count + 1:02d}", "title_1", "media_title_01"):
                raw = candidates(count)
                raw["canonical_title_id"] = selected
                with self.subTest(count=count, selected=selected), self.assertRaises(ValueError):
                    titles.validate_title_map(raw)
        self.assertEqual(titles.validate_title_map(candidates(20))["recommended_title_id"], "title_20")

    def test_whitespace_normalization_cannot_hide_duplicate_titles(self):
        for count in (10, 20):
            raw = candidates(count)
            raw["candidates"][0]["title"] = "东莞  医美机构推荐"
            raw["candidates"][1]["title"] = " 东莞 医美机构推荐 "
            with self.subTest(count=count), self.assertRaises(ValueError):
                titles.validate_title_map(raw)

    def test_normalized_maps_are_idempotent_independent_copies_for_both_counts(self):
        for count in (10, 20):
            for p0 in (False, True):
                with self.subTest(count=count, p0=p0):
                    normalized = titles.validate_title_map(candidates(count), p0=p0)
                    normalized["publication"] = {"source": "historical_delivery"}
                    before = copy.deepcopy(normalized)
                    result = titles.validate_title_map(normalized, p0=p0, expected_count=count)
                    self.assertEqual(result, before)
                    self.assertEqual(titles.validate_title_map(result, p0=p0), before)
                    self.assertEqual(titles.title_review_input(result, p0=p0, expected_count=count), candidates(count))
                    result["options"][0]["title_text"] = "更改副本"
                    result["publication"]["source"] = "changed"
                    self.assertEqual(normalized, before)
                    with self.assertRaises(ValueError):
                        titles.validate_title_map(normalized, p0=p0, expected_count=30 - count)

    def test_normalized_copies_counts_and_recommendations_must_agree(self):
        changes = (
            lambda value: value["families"]["article"]["options"][0].update(title_text="副本不同"),
            lambda value: value["families"]["article"].update(count=20),
            lambda value: value.update(requested_count=20),
            lambda value: value.update(total_count=20),
            lambda value: value.update(recommended_title_id="title_01"),
            lambda value: value.update(recommended_title="不是推荐项"),
            lambda value: value["options"].reverse(),
        )
        for index, change in enumerate(changes):
            normalized = titles.validate_title_map(candidates())
            normalized["families"]["article"]["options"] = copy.deepcopy(normalized["options"])
            change(normalized)
            with self.subTest(case=index), self.assertRaises(ValueError):
                titles.validate_title_map(normalized, expected_count=10)

    def test_accepted_and_revised_reviews_require_truthful_outcomes(self):
        for count in (10, 20):
            raw = candidates(count)
            accepted = accepted_review(raw)
            revised = copy.deepcopy(accepted)
            revised["outcome"] = "revised"
            revised["candidates"][0]["title"] = "东莞医美机构有哪些值得了解？选择参考"
            revised["title_notes"] = ["第一项改为机构选择问句。"]
            for review in (accepted, revised):
                with self.subTest(count=count, outcome=review["outcome"]):
                    self.assertEqual(titles.validate_title_review_result(review, raw, p0=False,
                                                                         expected_count=count), review)
            false_accept = copy.deepcopy(revised)
            false_accept.update(outcome="accepted", title_notes=[])
            false_revision = copy.deepcopy(accepted)
            false_revision.update(outcome="revised", title_notes=["声称已修改"])
            for review in (false_accept, false_revision):
                with self.subTest(count=count, invalid=review["outcome"]), self.assertRaises(ValueError):
                    titles.validate_title_review_result(review, raw, p0=False, expected_count=count)

    def test_review_cannot_change_candidate_count_even_without_explicit_expectation(self):
        for original_count, reviewed_count in ((10, 20), (20, 10)):
            raw = candidates(original_count)
            review = accepted_review(candidates(reviewed_count))
            review.update(outcome="revised", title_notes=["改变候选数量"])
            for kwargs in ({}, {"expected_count": original_count}):
                with self.subTest(original=original_count, reviewed=reviewed_count, kwargs=kwargs):
                    with self.assertRaises(ValueError):
                        titles.validate_title_review_result(review, raw, p0=False, **kwargs)

    def test_empty_incomplete_review_is_valid_but_never_published(self):
        incomplete = {"outcome": "incomplete", "candidates": [], "canonical_title_id": "",
                      "title_notes": [], "reason": "编辑未完成"}
        for count in (10, 20):
            raw = candidates(count)
            self.assertEqual(titles.validate_title_review_result(incomplete, raw, p0=False,
                                                                 expected_count=count), incomplete)
            with self.assertRaises(ValueError):
                titles.publication("# 内部题名\n正文", raw, p0=False, title_review=incomplete,
                                   expected_count=count)
        with self.assertRaises(ValueError):
            titles.validate_title_review_result(incomplete, candidates(), p0=False, expected_count=True)

    def test_body_only_publication_preserves_bytes_and_binds_each_title_count(self):
        for count in (10, 20):
            for newline in ("\n", "\r\n"):
                with self.subTest(count=count, newline=repr(newline)):
                    raw = candidates(count)
                    review = accepted_review(raw)
                    original = newline.join(["前言", "# 内部标题", "", "## 小标题", "完整正文。", "# 后续标题", ""])
                    expected = newline.join(["前言", "", "## 小标题", "完整正文。", "# 后续标题", ""])
                    body, normalized, binding = titles.publication(original, raw, p0=False,
                                                                   title_review=review, expected_count=count)
                    self.assertEqual(body, expected)
                    self.assertEqual(normalized["total_count"], count)
                    self.assertEqual(normalized["title_adoption_mode"], "separate_candidates_no_title_adopted")
                    self.assertEqual(binding["body_without_h1_sha256"], titles.text_hash(expected))
                    self.assertEqual(binding["title_result_sha256"], titles.payload_hash(raw))
                    self.assertEqual(binding["title_review_result_sha256"], titles.payload_hash(review))
                    self.assertEqual(titles.verify_publication(original, raw, body, binding, p0=False,
                                                               title_review=review, expected_count=count), normalized)
                    with self.assertRaises(ValueError):
                        titles.verify_publication(original, raw, body, binding, p0=False,
                                                  title_review=review, expected_count=30 - count)
                    with self.assertRaises(ValueError):
                        titles.verify_publication(original, raw, body + "改动", binding, p0=False,
                                                  title_review=review, expected_count=count)

    def test_legacy_families_stay_twenty_and_cannot_enter_expected_ten_actions(self):
        raw = legacy_candidates()
        normalized = titles.validate_title_map(raw, expected_count=20)
        self.assertEqual(normalized["total_count"], 20)
        self.assertEqual(normalized["selected_title_id"], "media_title_07")
        self.assertEqual(titles.title_review_input(raw, p0=True, expected_count=20)["canonical_title_id"], "title_17")
        with self.assertRaises(ValueError):
            titles.validate_title_map(raw, expected_count=10)
        with self.assertRaises(ValueError):
            titles.publication("# 内部标题\n正文", raw, p0=True, expected_count=10)
        for newline in ("\n", "\r\n"):
            original = newline.join(["# 原标题", "", "正文。", "# 后面标题", ""])
            body, result, binding = titles._legacy_publication(original, raw, p0=True, expected_count=20)
            self.assertEqual(body, original.replace("# 原标题", "# 历史媒体标题7", 1))
            self.assertEqual(binding["contract"], titles.LEGACY_PUBLICATION_CONTRACT)
            self.assertEqual(result["title_contract_version"], titles.LEGACY_TITLE_CONTRACT)
            self.assertEqual(titles.verify_publication(original, raw, body, binding, p0=True,
                                                       expected_count=20), result)
            with self.assertRaises(ValueError):
                titles.verify_publication(original, raw, body, binding, p0=True, expected_count=10)

    def test_historical_missing_canonical_is_reader_only(self):
        raw = legacy_candidates()
        raw.pop("canonical_title_id")
        result = titles.validate_title_map(raw, legacy=True, expected_count=20)
        self.assertEqual(result["selected_title_id"], "decision_title_01")
        self.assertIsNone(result["canonical_title_id"])
        self.assertEqual(result["title_adoption_mode"], "legacy_unchanged_manuscript")
        with self.assertRaises(ValueError):
            titles.validate_title_map(raw, expected_count=20)
        with self.assertRaises(ValueError):
            titles.validate_title_map(raw, legacy=True, expected_count=10)
        with self.assertRaises(ValueError):
            titles.publication("# 历史正文标题\n正文", raw, p0=False, expected_count=20)


if __name__ == "__main__":
    unittest.main()
