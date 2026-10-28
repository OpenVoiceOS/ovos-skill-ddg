"""``search_duck`` names the search engine, so every locale pairs it with a ``.required``.

The keywords come from the locale files, and each golden row and each sample of
the intent must contain one of them, by the whole-word occurrence rule of
OVOS-INTENT-2 §4.5.
"""
import json
from pathlib import Path

import pytest
from ovos_spec_tools import LocaleResources, utterance_contains

ROOT = Path(__file__).parents[2]
LOCALE_DIR = ROOT / "ovos_skill_ddg" / "locale"
GOLDEN_DIR = ROOT / "test" / "end2end"
INTENT = "search_duck"
# Scripts without word spaces: the engine name is attached to the words around
# it, so no keyword occurs as a whole word. These locales have no
# `.required` until the occurrence rule covers unsegmented text.
UNSEGMENTED = {"ja-JP", "zh-CN"}
INTENT_LANGS = sorted(d.name for d in LOCALE_DIR.iterdir() if (d / f"{INTENT}.intent").is_file())
LANGS = [lang for lang in INTENT_LANGS if lang not in UNSEGMENTED]
RESOURCES = LocaleResources(str(LOCALE_DIR))


def _golden(lang):
    path = GOLDEN_DIR / f"golden_utterances_{lang}.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [row["utterance"] for row in rows if row["intent_label"] == INTENT]


def test_locales_are_found():
    assert len(LANGS) >= 40
    assert UNSEGMENTED <= set(INTENT_LANGS)


@pytest.mark.parametrize("lang", LANGS)
def test_locale_has_required_keywords(lang):
    assert (LOCALE_DIR / lang / f"{INTENT}.required").is_file()
    assert RESOURCES.load_required_keywords(INTENT, lang)


@pytest.mark.parametrize("lang", LANGS)
def test_golden_positives_contain_a_keyword(lang):
    keywords = RESOURCES.load_required_keywords(INTENT, lang)
    missing = [u for u in _golden(lang) if not utterance_contains(u, keywords)]
    assert _golden(lang) and not missing, f"{lang} golden rows without a keyword: {missing}"


@pytest.mark.parametrize("lang", LANGS)
def test_intent_samples_contain_a_keyword(lang):
    keywords = RESOURCES.load_required_keywords(INTENT, lang)
    samples = RESOURCES.load_intent(INTENT, lang)
    missing = [s for s in samples if not utterance_contains(s, keywords)]
    assert not missing, f"{lang} samples without a keyword: {missing}"
