"""`needs_review` qoidalari — har tetik uchun bittadan holat."""

from src.modules.pipeline.tests.stubs import SAMPLE_TRANSCRIPT
from src.modules.scoring.application.review_rules import ReviewReason, decide

LONG_TEXT = " ".join(["so'z"] * 200)


def _decide(**overrides):
    base = dict(
        confidence=0.95,
        transcript_quality="high",
        transcript_text=LONG_TEXT,
        duration_sec=180,
        red_flag_types=[],
        ai_score=78,
        client_rating=4.0,
        client_rating_count=10,
    )
    base.update(overrides)
    return decide(**base)


def test_clean_call_is_not_flagged() -> None:
    assert _decide().needs_review is False


def test_low_confidence_triggers() -> None:
    decision = _decide(confidence=0.52)
    assert decision.needs_review is True
    assert decision.codes == [ReviewReason.LOW_CONFIDENCE]


def test_low_transcript_quality_triggers() -> None:
    decision = _decide(transcript_quality="low")
    assert ReviewReason.LOW_CONFIDENCE in decision.codes


def test_short_transcript_triggers() -> None:
    decision = _decide(transcript_text="Assalomu alaykum. Noto'g'ri raqam.")
    assert ReviewReason.SHORT_TRANSCRIPT in decision.codes


def test_sparse_long_call_triggers() -> None:
    """10 daqiqalik suhbatda 100 so'z — matnning katta qismi yo'qolgan."""
    decision = _decide(transcript_text=" ".join(["so'z"] * 100), duration_sec=600)
    assert ReviewReason.SHORT_TRANSCRIPT in decision.codes


def test_red_flag_triggers() -> None:
    decision = _decide(red_flag_types=["shouting"])
    assert ReviewReason.RED_FLAG in decision.codes
    assert "shouting" in decision.summary_uz


def test_client_gap_triggers() -> None:
    decision = _decide(ai_score=90, client_rating=2.0, client_rating_count=8)
    assert ReviewReason.CLIENT_GAP in decision.codes


def test_client_gap_ignored_when_too_few_responses() -> None:
    decision = _decide(ai_score=90, client_rating=2.0, client_rating_count=1)
    assert ReviewReason.CLIENT_GAP not in decision.codes


def test_sample_transcript_is_long_enough() -> None:
    """Namuna transkript qisqalik tetigini ishlatib yubormasligi kerak."""
    decision = _decide(transcript_text=SAMPLE_TRANSCRIPT, duration_sec=75)
    assert ReviewReason.SHORT_TRANSCRIPT not in decision.codes
