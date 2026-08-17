"""Validator testlari — bazasiz, kalitsiz.

Ishga tushirish:
    docker compose exec -T backend pytest src/modules/scoring/tests -q
"""

import json

import pytest

from src.modules.pipeline.tests.stubs import build_payload
from src.modules.scoring.application.validator import (
    ScoreValidationError,
    validate,
)
from src.modules.scoring.domain.rubric_default import DEFAULT_RUBRIC

BLOCKS = DEFAULT_RUBRIC["blocks"]
FLAGS = DEFAULT_RUBRIC["red_flags"]


def _dump(**kwargs) -> str:
    return json.dumps(build_payload(BLOCKS, FLAGS, **kwargs), ensure_ascii=False)


def test_valid_payload_passes() -> None:
    draft = validate(_dump(seed=1), rubric_blocks=BLOCKS, rubric_red_flags=FLAGS)
    assert draft.overall == draft.blocks_total
    assert set(draft.block_scores) == {b["key"] for b in BLOCKS}


def test_markdown_fence_is_tolerated() -> None:
    raw = "```json\n" + _dump(seed=2) + "\n```"
    draft = validate(raw, rubric_blocks=BLOCKS, rubric_red_flags=FLAGS)
    assert draft.overall > 0


def test_wrong_total_is_rejected() -> None:
    """96 deb yozilgan, bloklar esa 84 — saqlanmasligi SHART."""
    with pytest.raises(ScoreValidationError) as exc:
        validate(
            _dump(seed=3, overall_override=96),
            rubric_blocks=BLOCKS,
            rubric_red_flags=FLAGS,
        )
    assert "arifmetikasi noto'g'ri" in exc.value.message


def test_invented_red_flag_is_rejected() -> None:
    with pytest.raises(ScoreValidationError) as exc:
        validate(
            _dump(seed=4, invented_flag="rude_tone"),
            rubric_blocks=BLOCKS,
            rubric_red_flags=FLAGS,
        )
    assert "rude_tone" in exc.value.message


def test_unknown_block_is_rejected() -> None:
    payload = build_payload(BLOCKS, FLAGS, seed=5)
    payload["blocks"]["teamwork"] = {"score": 5, "criteria": []}
    with pytest.raises(ScoreValidationError):
        validate(
            json.dumps(payload), rubric_blocks=BLOCKS, rubric_red_flags=FLAGS
        )


def test_criteria_must_sum_to_block_score() -> None:
    payload = build_payload(BLOCKS, FLAGS, seed=6)
    payload["blocks"]["script"]["score"] += 3
    payload["overall_score"] += 3
    with pytest.raises(ScoreValidationError) as exc:
        validate(
            json.dumps(payload), rubric_blocks=BLOCKS, rubric_red_flags=FLAGS
        )
    assert "kriteriyalar yig'indisi" in exc.value.message


def test_block_score_above_maximum_is_rejected() -> None:
    payload = build_payload(BLOCKS, FLAGS, seed=7)
    payload["blocks"]["script"]["score"] = 99
    with pytest.raises(ScoreValidationError):
        validate(
            json.dumps(payload), rubric_blocks=BLOCKS, rubric_red_flags=FLAGS
        )


def test_profanity_zeroes_the_score() -> None:
    draft = validate(
        _dump(seed=8, red_flags=("profanity",)),
        rubric_blocks=BLOCKS,
        rubric_red_flags=FLAGS,
    )
    assert draft.overall == 0
    assert draft.zeroed is True
    assert draft.red_flags[0]["penalty"] == -100


def test_penalty_comes_from_rubric_not_from_model() -> None:
    payload = build_payload(BLOCKS, FLAGS, seed=9, red_flags=("shouting",))
    payload["red_flags"][0]["penalty"] = -1  # model o'zi jarima o'ylab topdi
    draft = validate(
        json.dumps(payload), rubric_blocks=BLOCKS, rubric_red_flags=FLAGS
    )
    assert draft.red_flags[0]["penalty"] == -20
    assert draft.penalty_total == -20


def test_confidence_out_of_range_is_rejected() -> None:
    payload = build_payload(BLOCKS, FLAGS, seed=10)
    payload["confidence"] = 4.2
    with pytest.raises(ScoreValidationError):
        validate(
            json.dumps(payload), rubric_blocks=BLOCKS, rubric_red_flags=FLAGS
        )


def test_garbage_is_rejected_with_uzbek_message() -> None:
    with pytest.raises(ScoreValidationError) as exc:
        validate("mana sizga baho: yaxshi", rubric_blocks=BLOCKS, rubric_red_flags=FLAGS)
    assert "JSON" in exc.value.message
