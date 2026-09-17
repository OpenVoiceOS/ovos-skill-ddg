"""Multilingual golden-utterance end-to-end coverage for ovos-skill-ddg.

Every locale ships one intent, ``search_duck.intent``, with a free-text
``{query}`` slot (no ``.entity`` file backs it; padacioso's presence match
does not need one). Rows use the filler word "wikipedia" for that slot
across every locale -- a slot value, not translated prose, the same way
ovos-skill-count's golden rows fill ``{number}`` with a digit string.

The real ``DuckDuckGoRetrievalEngine`` hits the network, so its
``query``/``get_image`` methods are stubbed for deterministic, network-free
routing assertions, matching this repo's own (now-replaced)
``test_golden_utterances.py``.

One MiniCroft is booted per locale (``get_minicroft([SKILL_ID], max_wait=150,
lang=LANG)``) and torn down before moving to the next locale, avoiding the
open ovoscope harness bug in the shared secondary_langs boot path that
keeps ovos-skill-alerts' own multilang suite skipped upstream.
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
_STUB_ANSWER = ("Isaac Newton was an English mathematician and physicist.", 0.9)

END2END_DIR = Path(__file__).parent

LANGS = [
    "en-US", "ar-XA", "bg-BG", "ca-ES", "cs-CZ", "da-DK", "de-DE", "el-GR",
    "es-ES", "et-EE", "fi-FI", "fil-PH", "fr-FR", "he-IL", "hr-HR", "hu-HU",
    "id-ID", "it-IT", "ja-JP", "kab", "ko-KR", "lt-LT", "lv-LV", "ms-MY",
    "nb-NO", "nl-NL", "pl-PL", "pt-PT", "ro-RO", "ru-RU", "sk-SK", "sl-SI",
    "sv-SE", "th-TH", "tr-TR", "uk-UA", "vi-VN", "zh-CN",
]


def _load_rows(lang):
    path = END2END_DIR / f"golden_utterances_{lang}.jsonl"
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


ALL_ROWS = []
for _lang in LANGS:
    for _row in _load_rows(_lang):
        ALL_ROWS.append(_row)


def _golden_id(row):
    return f"{row['lang']}-{row['intent_label']}-{row['utterance']}"


GOLDEN_ROWS = [pytest.param(r, id=_golden_id(r)) for r in ALL_ROWS]

# Real locale-content defects found and fixed in-place during this pass
# (red-before/green-after verified), keyed by (lang, utterance):
KNOWN_BUGS = {}


@pytest.fixture(scope="module")
def ddg_stub():
    with mock.patch.object(DuckDuckGoRetrievalEngine, "query", return_value=[_STUB_ANSWER]), \
         mock.patch.object(DuckDuckGoRetrievalEngine, "get_image", return_value=None):
        yield


@pytest.fixture(scope="module")
def minicroft_factory(ddg_stub):
    cache = {"lang": None, "mc": None}

    def _get(lang):
        if cache["lang"] != lang:
            if cache["mc"] is not None:
                cache["mc"].stop()
            cache["mc"] = get_minicroft([SKILL_ID], max_wait=150, lang=lang)
            cache["lang"] = lang
        return cache["mc"]

    yield _get
    if cache["mc"] is not None:
        cache["mc"].stop()


def _capture(mc, text, lang, session_id):
    session = Session(session_id)
    session.lang = lang
    session.pipeline = ["ovos-padacioso-pipeline-plugin-high"]
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": lang},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(mc)
    capture.capture(utterance, timeout=30)
    return [m.msg_type for m in capture.finish()]


@pytest.mark.timeout(600)
@pytest.mark.parametrize("row", GOLDEN_ROWS, ids=_golden_id)
def test_golden_utterance_multilang(minicroft_factory, row):
    mc = minicroft_factory(row["lang"])
    expected = f"{SKILL_ID}:{row['intent_label']}"
    types = _capture(mc, row["utterance"], row["lang"], f"golden-{_golden_id(row)}")
    matched = expected in types
    bug_key = (row["lang"], row["utterance"])
    if bug_key in KNOWN_BUGS and not matched:
        pytest.xfail(reason=f"known-bug: {KNOWN_BUGS[bug_key]}")
    assert matched, f"[{row['lang']}] {row['utterance']!r}: expected {expected!r}, got {types!r}"
