"""MCQ option-extraction regression tests.

Every case below is a reduced reproduction of a real failure observed in the
21-file controlled 11+ corpus validation (see VALIDATION_REPORT.md). The
inputs are verbatim text_content patterns from those documents, including
the KSOL table layout that puts each option label on its own line.

These tests fail against the pre-fix extract_options(): the table layout
returned no options at all (284/319 occurrences), and naive label runs
glued following question text into the option text.
"""
from __future__ import annotations

from src.pipeline.detect import extract_options

# 11ComprehensionPracticePaper.pdf p5 — real, clean KSOL table layout.
COMPREHENSION_TABLE = (
    "Choose your answer from A-D below. Mark the letter which goes with your\n"
    "choice on the answer sheet.\n"
    "What is an example of personification in paragraph 1? (1 mark)\n"
    "A\nB\nC\nD\n"
    "The tall, grey stones loomed over her\n"
    "The stone walls made the air around her ghostly cold\n"
    "Suppressing the tears\n"
    "The dark hallway that swallowed her up\n"
)

# 11MathsPracticePaper2.pdf p4 q2 — interleaved column extraction: only some
# labels have adjacent text, the rest are stacked. Option text cannot be
# recovered reliably, so nothing may be invented or borrowed from the next
# question ("The pie-chart below ...").
MATHS_INTERLEAVED = (
    "How much did all of her presents cost?\n"
    "A\n\u00fa81.43 \u00fa76.93\nB\n C\n D\n\u00fa63.64\u00fa94.42\n"
    "The pie-chart below shows the favourite colour of 120 children. How\n"
    "many more children liked blue compared with yellow?\n"
)

# 11NVRPaper2.pdf p4/p6 — non-verbal pages mark answers with bubble rows.
NVR_SAMELINE_BUBBLES = (
    "Which option from A-E completes the series? Mark the letter which goes "
    "with your\nchoice on the answer sheet.\nA B C D E\n?\nA B C D E\n?\n"
)
NVR_STACKED_BUBBLES = "A B C D E\nA B C D E\nA B C D E\nA B C D E\nA B C D E\n"

# 11VerbalReasoning.pdf p9 — instruction line mentions "A   B   C   D".
INSTRUCTION_LINE = (
    "Example\nF         |         |\nA        B        C        D\n"
    "MARK boxes clearly like this, with at least 2/3 of the box shaded\n"
)


def test_table_layout_labels_then_text_is_extracted():
    """Real 11+ table layout: label column, then option texts."""
    options = extract_options(COMPREHENSION_TABLE)
    assert [o["letter"] for o in options] == ["A", "B", "C", "D"]
    assert options[0]["text"] == "The tall, grey stones loomed over her"
    assert options[3]["text"] == "The dark hallway that swallowed her up"


def test_interleaved_layout_does_not_fabricate_option_text():
    """Interleaved labels must not borrow text from the next question."""
    options = extract_options(MATHS_INTERLEAVED)
    texts = " ".join(o["text"] for o in options)
    assert "pie-chart" not in texts
    assert "favourite colour" not in texts
    assert "many more children" not in texts


def test_same_line_bubble_runs_are_not_options():
    """NVR bubble rows (A B C D E) are not option text."""
    assert extract_options(NVR_SAMELINE_BUBBLES) == []


def test_stacked_bubble_letters_without_text_are_not_options():
    """Bare letters with no following option text are not a valid set."""
    assert extract_options(NVR_STACKED_BUBBLES) == []


def test_instruction_text_mentioning_labels_is_not_options():
    """"Choose from A-D below" instructions must not become options."""
    assert extract_options(INSTRUCTION_LINE) == []


def test_truncated_label_run_is_not_options():
    """A run that starts at B (no A) must not be treated as an option row."""
    assert extract_options("3) continued\nB\n C\n D\nsome later text\n") == []


def test_classic_dot_options_still_work():
    """Existing separator formats keep working (no regression)."""
    text = "1. Pick one.\nA. apple\nB. banana\nC. cherry"
    options = extract_options(text)
    assert [o["letter"] for o in options] == ["A", "B", "C"]
    assert options[1]["text"] == "banana"


def test_parenthesized_maths_subparts_are_not_options():
    """Lowercase (a)/(b)/(c) sub-parts must not become A/B/C options.

    Real corpus: `11_Sample_ maths_exam_questions.pptx` p3 q236 and p4 q57
    turn `(a)/(b)/(c)` sub-questions into promoted A/B/C option sets.
    """
    text = ("236)\nPlot the points.\n\n(a) Plot the points.\n\n"
            "(b) What is the area?\n(c) Reflect the rectangle.\n")
    assert extract_options(text) == []
    upper = "Q1. Pick one.\n(A) apple\n(B) banana\n(C) cherry"
    assert [o["letter"] for o in extract_options(upper)] == ["A", "B", "C"]


# 2008 intake English.pdf p3 q3 — source lists A-F; only A-E can be captured,
# so the E text would swallow the F line. Incomplete run must stay unresolved.
TICK_BOX_A_F = (
    "What reaction do the other boys have to Trevor when he joins the gang\n"
    "as a new recruit?\n"
    "A. They are quite awed by him.\n"
    "B. They demand that he fulfils some dare or challenge.\n"
    "C. They laugh at his name behind his back.\n"
    "D. The gang are not quite sure what Trevor might do next.\n"
    "E. They call him T because he prefers it to Trevor.\n"
    "F. They are slightly afraid of him.\n"
)

# 2008 intake English.pdf p3 q7 — a A-J matching exercise, not an MCQ.
MATCHING_A_J = (
    "Word from passage Look in lines\n"
    "A. meditating ................. 6 - 8\n"
    "B. bravado ................. 9 - 12\n"
    "C. dishonourable ................. 16 - 19\n"
    "D. definite ................. 19 - 22\n"
    "E. supporting brace ................. 23 - 25\n"
    "F. uneven ................. 25 - 29\n"
    "G. dejectedly ................. 40 - 43\n"
)

# 2008 intake English.pdf p4 q8 — write-in question: A/B/C are dot-only blanks.
WRITE_IN_DOTS = (
    "WRITE IN YOUR OWN WORDS in the three spaces below.\n"
    "A. ................................................\n"
    "B. ................................................\n"
    "C. ................................................\n"
)


def test_source_labels_beyond_e_make_run_unresolved():
    """A-F / A-J sources must not be truncated into a fake A-E option set."""
    assert extract_options(TICK_BOX_A_F) == []
    assert extract_options(MATCHING_A_J) == []


def test_dot_only_answer_blanks_are_not_options():
    """Write-in dot blanks are not option text."""
    assert extract_options(WRITE_IN_DOTS) == []


def test_five_real_uppercase_options_still_extract():
    """The completeness/content guards must not reject a genuine A-E set."""
    text = ("Q4. Which statements are correct?\n"
            "A. Mike was surprised.\n"
            "B. Mike was younger.\n"
            "C. The gang sensed a newcomer.\n"
            "D. Trevor is the oldest.\n"
            "E. Mike might get a frog in his throat.\n")
    options = extract_options(text)
    assert [o["letter"] for o in options] == ["A", "B", "C", "D", "E"]
    assert options[0]["text"] == "Mike was surprised."


def test_shuffled_and_gapped_label_runs_are_not_options():
    """Shuffled, gapped, or repeated label runs are unreliable evidence.

    Real corpus example: `9+ Sample papers 2013 2.pdf` produces a 7-option
    set with shuffled labels (A, C, B, ...) and garbage text. Such matches
    must stay unresolved (`[]`) rather than become malformed option sets.
    """
    assert extract_options("Q7. Pick one.\nA. alpha\nC. gamma\nB. beta") == []
    assert extract_options("Q7. Pick one.\nA. alpha\nB. beta\nD. delta") == []
    assert extract_options("Q7. Pick one.\nB. beta\nB. beta2\nC. gamma") == []
    assert extract_options("Q7. Pick one.\nA. alpha\nB. beta\nC. gamma") != []


def test_real_corpus_option_text_is_preserved_verbatim():
    """Extracted option text must be the source text, unmodified."""
    options = extract_options(COMPREHENSION_TABLE)
    assert options[1]["text"] == (
        "The stone walls made the air around her ghostly cold")
    assert options[2]["text"] == "Suppressing the tears"
