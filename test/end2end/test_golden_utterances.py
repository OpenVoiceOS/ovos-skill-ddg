"""Golden-utterance end-to-end coverage for ovos-skill-ddg (en-US).

The master ovoscope corpus carries no rows for
``ovos-skill-ddg.openvoiceos`` (verified: zero matches in
knowledge/datasets/ovoscope/test_dataset.jsonl), so
``golden_utterances.jsonl`` is derived entirely from this skill's own
``search_duck.intent`` template phrasings (padacioso).

Unlike ``test/end2end/test_ddg_e2e.py`` (kept as-is), which drives the real
``ovos_ddg_plugin.DuckDuckGoRetrievalEngine`` against the live DuckDuckGo
API, this suite stubs the engine's ``query``/``get_image`` methods at the
class level for deterministic, network-free routing assertions -- the
DuckDuckGo backend itself is out of scope for a routing test, and hitting a
real network in a golden-utterance suite would make it flaky by
construction. One graceful-failure test (``test_query_failure_is_graceful``)
verifies the skill degrades to the "no_answer" dialog rather than crashing
when the (stubbed) backend raises.

Run:
    uv run pytest test/end2end/test_golden_utterances.py -v
"""
import json
from pathlib import Path
from unittest import mock

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_ddg_plugin import DuckDuckGoRetrievalEngine
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-ddg.openvoiceos"
LANG = "en-US"

GOLDEN_PATH = Path(__file__).parent / "golden_utterances.jsonl"

_STUB_ANSWER = ("Isaac Newton was an English mathematician and physicist.", 0.9)

# Cross-skill negative confusables. ddg is a broad fallback/common-query
# skill, so this suite adds query-skill cross-confusables (wikipedia/wolfie
# domains -- the other "answer factual questions" skills) on top of the
# usual domain-confusable set, per the wave-4 brief.
NEGATIVE_UTTERANCES = [
    ("what's the weather today", "ovos-skill-weather.openvoiceos"),
    ("set a timer for 5 minutes", "ovos-skill-alerts.openvoiceos"),
    ("play some music", "ovos-skill-music.openvoiceos"),
    ("remind me to call mom", "ovos-skill-reminder.openvoiceos"),
    ("what time is it", "ovos-datetime-skill.openvoiceos"),
    # query-skill cross-confusables: other factual-answer skills should be
    # free to also claim these via common_query, but the *explicit*
    # search_duck.intent (padacioso, asserted here) must not fire for them.
    ("search wikipedia for isaac newton", "ovos-skill-wikipedia.openvoiceos"),
    ("wolfram alpha isaac newton", "ovos-skill-wolfie.openvoiceos"),
]


def _load_golden_rows():
    rows = []
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


GOLDEN_ROWS = [pytest.param(r, id=r["utterance"]) for r in _load_golden_rows()]


@pytest.fixture(scope="module")
def minicroft():
    with mock.patch.object(DuckDuckGoRetrievalEngine, "query", return_value=[_STUB_ANSWER]), \
         mock.patch.object(DuckDuckGoRetrievalEngine, "get_image", return_value=None):
        mc = get_minicroft([SKILL_ID])
        yield mc
        mc.stop()


def _capture(mc, text, session_id, pipeline=None):
    session = Session(session_id)
    session.lang = LANG
    if pipeline:
        session.pipeline = pipeline
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": LANG},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(mc)
    capture.capture(utterance, timeout=30)
    return capture.finish()


@pytest.mark.timeout(60)
@pytest.mark.parametrize("row", GOLDEN_ROWS, ids=lambda r: r["utterance"])
def test_golden_utterance(minicroft, row):
    expected_intent = f"{SKILL_ID}:{row['intent_label']}"
    messages = _capture(
        minicroft, row["utterance"], f"golden-{row['utterance']}",
        pipeline=["ovos-padacioso-pipeline-plugin-high"],
    )
    types = [m.msg_type for m in messages]
    assert expected_intent in types, (
        f"{row['utterance']!r}: expected {expected_intent!r} in message types, got {types!r}"
    )
    spoken = [
        m.data.get("utterance", "") for m in messages
        if m.msg_type in ("speak", "ovos.utterance.speak")
    ]
    assert any(spoken), f"{row['utterance']!r}: expected a spoken response, got none"


@pytest.mark.timeout(60)
@pytest.mark.parametrize("negative", NEGATIVE_UTTERANCES, ids=lambda n: n[0])
def test_negative_confusable_not_claimed(minicroft, negative):
    text, source_skill = negative
    messages = _capture(
        minicroft, text, f"negative-{text}",
        pipeline=["ovos-padacioso-pipeline-plugin-high"],
    )
    types = [m.msg_type for m in messages]
    claimed = any(t.startswith(f"{SKILL_ID}:search_duck") for t in types)
    assert not claimed, f"{text!r} (from {source_skill}) was incorrectly claimed by {SKILL_ID}'s explicit intent"


@pytest.mark.timeout(30)
def test_query_failure_is_graceful():
    """If the DDG backend raises, the skill must speak "no_answer" gracefully
    rather than crash the handler or leave the utterance unhandled."""
    with mock.patch.object(
        DuckDuckGoRetrievalEngine, "query", side_effect=RuntimeError("network down")
    ), mock.patch.object(DuckDuckGoRetrievalEngine, "get_image", return_value=None):
        mc = get_minicroft([SKILL_ID])
        try:
            messages = _capture(
                mc, "search duckduckgo for isaac newton", "graceful-failure",
                pipeline=["ovos-padacioso-pipeline-plugin-high"],
            )
        finally:
            mc.stop()
    types = [m.msg_type for m in messages]
    expected_intent = f"{SKILL_ID}:search_duck"
    assert expected_intent in types, (
        f"expected the intent to still route despite backend failure, got {types!r}"
    )
    spoken = [
        m.data.get("utterance", "") for m in messages
        if m.msg_type in ("speak", "ovos.utterance.speak")
    ]
    assert any(spoken), f"expected a graceful spoken fallback response, got {types!r}"
