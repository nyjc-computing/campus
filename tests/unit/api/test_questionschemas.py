"""Unit tests for the question-type registry (campus.api.questionschemas).

Covers the #533 groundwork: registry lookup, question/response schema
validation at the payload boundary, the MCQ stable-option-id cross-check,
and the response validation rules for found vs. unknown questions.
"""

import unittest

from campus.common import env

# Configure test storage before importing storage-backed modules
env.set('STORAGE_MODE', "1")


def _mcq_question(**overrides):
    """A valid multiple-choice Question for response cross-checks."""
    from campus.model import Question
    fields = {
        "id": "q1",
        "prompt": "",
        "question": "Which search is O(log n)?",
        "type": "multiple-choice",
        "data": {"options": [
            {"id": "opt_bin", "text": "Binary search"},
            {"id": "opt_lin", "text": "Linear search"},
        ]},
    }
    fields.update(overrides)
    return Question(**fields)


class TestQuestionsFromPayloads(unittest.TestCase):
    """questions_from_payloads: construction + registry validation."""

    def test_defaults_to_free_response(self):
        """A payload without type/data reads as free-response."""
        from campus.api import questionschemas

        questions = questionschemas.questions_from_payloads(
            [{"id": "q1", "prompt": "", "question": "Explain."}],
            "questions",
        )
        self.assertEqual(questions[0].type, "free-response")
        self.assertIsNone(questions[0].data)

    def test_mcq_question_accepted(self):
        """A well-formed multiple-choice question passes."""
        from campus.api import questionschemas

        questions = questionschemas.questions_from_payloads(
            [{"id": "q1", "prompt": "", "question": "Q?",
              "type": "multiple-choice",
              "data": {"options": [
                  {"id": "opt_a", "text": "A"},
                  {"id": "opt_b", "text": "B"},
              ], "randomize": True}}],
            "questions",
        )
        self.assertEqual(questions[0].type, "multiple-choice")

    def test_unknown_type_rejected(self):
        """An unregistered type id answers 422 naming the known types."""
        from campus.api import questionschemas
        from campus.common.errors import ValidationError

        with self.assertRaises(ValidationError) as ctx:
            questionschemas.questions_from_payloads(
                [{"id": "q1", "prompt": "", "question": "Q?",
                  "type": "parsons"}],
                "questions",
            )
        field_errors = ctx.exception.field_errors
        self.assertEqual(field_errors[0]["field"], "questions[0].type")
        self.assertIn("free-response", field_errors[0]["message"])

    def test_mcq_needs_two_options(self):
        """multiple-choice data with fewer than two options is rejected."""
        from campus.api import questionschemas
        from campus.common.errors import ValidationError

        with self.assertRaises(ValidationError) as ctx:
            questionschemas.questions_from_payloads(
                [{"id": "q1", "prompt": "", "question": "Q?",
                  "type": "multiple-choice",
                  "data": {"options": [{"id": "opt_a", "text": "A"}]}}],
                "questions",
            )
        self.assertEqual(
            ctx.exception.field_errors[0]["field"], "questions[0].data"
        )

    def test_malformed_payload_rejected_with_index(self):
        """A payload that fails the model's own fields names questions[i]."""
        from campus.api import questionschemas
        from campus.common.errors import ValidationError

        with self.assertRaises(ValidationError) as ctx:
            questionschemas.questions_from_payloads(
                [{"id": "bad id with spaces", "prompt": "", "question": "Q?"}],
                "questions",
            )
        self.assertEqual(ctx.exception.field_errors[0]["field"],
                         "questions[0]")


class TestResponsesFromPayloads(unittest.TestCase):
    """responses_from_payloads: shape validation + cross-checks."""

    def test_legacy_text_response_passes_for_free_response_question(self):
        """response_text-only payloads mirror into response_data."""
        from campus.api import questionschemas

        responses = questionschemas.responses_from_payloads(
            [{"question_id": "q1", "response_text": "line one\nline two"}],
            "responses",
            questions=[_mcq_question(id="q9", type="free-response",
                                     data=None)],
        )
        self.assertEqual(responses[0].response_data,
                         {"text": "line one\nline two"})

    def test_short_answer_limit_enforced_via_question_type(self):
        """A text answer to a short-answer question is capped at 256."""
        from campus.api import questionschemas
        from campus.common.errors import ValidationError

        question = _mcq_question(id="q1", type="short-answer", data=None)
        with self.assertRaises(ValidationError) as ctx:
            questionschemas.responses_from_payloads(
                [{"question_id": "q1", "response_text": "x" * 257}],
                "responses",
                questions=[question],
            )
        self.assertEqual(
            ctx.exception.field_errors[0]["field"],
            "responses[0].response_data",
        )

    def test_short_answer_rejects_line_breaks(self):
        """Short answers are single-line."""
        from campus.api import questionschemas
        from campus.common.errors import ValidationError

        question = _mcq_question(id="q1", type="short-answer", data=None)
        with self.assertRaises(ValidationError):
            questionschemas.responses_from_payloads(
                [{"question_id": "q1", "response_data": {"text": "a\nb"}}],
                "responses",
                questions=[question],
            )

    def test_question_type_governs_over_payload_cache(self):
        """A found question's type wins over the payload's question_type."""
        from campus.api import questionschemas
        from campus.common.errors import ValidationError

        # Payload claims free-response; the question is multiple-choice,
        # so {"text": ...} must fail the MCQ response schema.
        with self.assertRaises(ValidationError):
            questionschemas.responses_from_payloads(
                [{"question_id": "q1", "question_type": "free-response",
                  "response_data": {"text": "B"}}],
                "responses",
                questions=[_mcq_question()],
            )

    def test_mcq_valid_choice_passes_cross_check(self):
        """A choice naming a real option id is accepted."""
        from campus.api import questionschemas

        responses = questionschemas.responses_from_payloads(
            [{"question_id": "q1", "question_type": "multiple-choice",
              "response_data": {"choice": "opt_lin"}}],
            "responses",
            questions=[_mcq_question()],
        )
        self.assertEqual(responses[0].response_data, {"choice": "opt_lin"})

    def test_mcq_unknown_choice_rejected(self):
        """A choice that names no option id is rejected."""
        from campus.api import questionschemas
        from campus.common.errors import ValidationError

        with self.assertRaises(ValidationError) as ctx:
            questionschemas.responses_from_payloads(
                [{"question_id": "q1", "question_type": "multiple-choice",
                  "response_data": {"choice": "opt_ghost"}}],
                "responses",
                questions=[_mcq_question()],
            )
        self.assertIn("does not match any option id",
                      ctx.exception.field_errors[0]["message"])

    def test_mcq_duplicate_option_ids_rejected(self):
        """Duplicate option ids fail the cross-check (uniqueItems can't)."""
        from campus.api import questionschemas
        from campus.common.errors import ValidationError

        question = _mcq_question(data={"options": [
            {"id": "opt_same", "text": "First"},
            {"id": "opt_same", "text": "Second"},
        ]})
        with self.assertRaises(ValidationError) as ctx:
            questionschemas.responses_from_payloads(
                [{"question_id": "q1", "question_type": "multiple-choice",
                  "response_data": {"choice": "opt_same"}}],
                "responses",
                questions=[question],
            )
        self.assertIn("duplicate ids", ctx.exception.field_errors[0]["message"])

    def test_unknown_question_falls_back_to_payload_type(self):
        """Unknown question_ids validate against the payload's type only.

        Drafts must survive teacher edits that remove questions (#533),
        so the response is not rejected — here the payload declares
        short-answer and the newline violates that schema.
        """
        from campus.api import questionschemas
        from campus.common.errors import ValidationError

        with self.assertRaises(ValidationError):
            questionschemas.responses_from_payloads(
                [{"question_id": "q_gone", "question_type": "short-answer",
                  "response_data": {"text": "a\nb"}}],
                "responses",
                questions=[_mcq_question()],
            )

    def test_unknown_question_with_legacy_text_passes(self):
        """Legacy text answers to removed questions keep working."""
        from campus.api import questionschemas

        responses = questionschemas.responses_from_payloads(
            [{"question_id": "q_gone", "response_text": "still here"}],
            "responses",
            questions=[_mcq_question()],
        )
        self.assertEqual(responses[0].response_data, {"text": "still here"})

    def test_unknown_payload_type_without_question_rejected(self):
        """No found question + unregistered question_type answers 422."""
        from campus.api import questionschemas
        from campus.common.errors import ValidationError

        with self.assertRaises(ValidationError) as ctx:
            questionschemas.responses_from_payloads(
                [{"question_id": "q_gone", "question_type": "parsons",
                  "response_data": {"order": [0, 1]}}],
                "responses",
            )
        self.assertEqual(
            ctx.exception.field_errors[0]["field"],
            "responses[0].question_type",
        )

    def test_no_questions_context_validates_shape_only(self):
        """Without questions, the payload's question_type drives schema."""
        from campus.api import questionschemas

        # Valid short-answer via payload type
        responses = questionschemas.responses_from_payloads(
            [{"question_id": "q1", "question_type": "short-answer",
              "response_data": {"text": "ok"}}],
            "responses",
        )
        self.assertEqual(responses[0].question_type, "short-answer")
        # But no cross-check can run: a bogus choice passes shape
        # validation as a plain string — accepted, per #533 groundwork.
        responses = questionschemas.responses_from_payloads(
            [{"question_id": "q1", "question_type": "multiple-choice",
              "response_data": {"choice": "opt_whatever"}}],
            "responses",
        )
        self.assertEqual(responses[0].response_data,
                         {"choice": "opt_whatever"})


class TestModelsFromPayloadsPassthrough(unittest.TestCase):
    """payloads.models_from_payloads passes constructed models through."""

    def test_model_instances_pass_through(self):
        """Pre-constructed models survive models_from_payloads unchanged."""
        from campus.api import payloads
        from campus.model import Question

        question = Question(id="q1", prompt="", question="Q?")
        result = payloads.models_from_payloads(
            Question, [question], "questions"
        )
        self.assertIs(result[0], question)


if __name__ == '__main__':
    unittest.main()
