"""
End-to-end tests for DuckDuckGoSkill via ovoscope.

Covers:
- Explicit padacioso intent (search_duck.intent) fires and handler completes
- Fallback handler fires for open questions with no other pipeline match
- Multi-lang sessions (en-US, de-DE, es-ES, pt-PT) route correctly
- Blacklisted utterances ("weather") do NOT activate the fallback handler
"""
from copy import deepcopy
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_utils.log import LOG

from ovoscope import End2EndTest, get_minicroft

SKILL_ID = "ovos-skill-ddg.openvoiceos"

# Messages that carry variable content or are noise for these routing tests
_IGNORE = [
    "speak",
    "ovos.common_play.stop.response",
    "common_query.openvoiceos.stop.response",
    "persona.openvoiceos.stop.response",
    "ovos-hivemind-pipeline-plugin.stop.response",
    "stop.openvoiceos.stop.response",
]

_FALLBACK_RANGE = [5, 90]  # range emitted by ovos-fallback-pipeline-plugin


# ---------------------------------------------------------------------------
# Explicit padacioso intent
# ---------------------------------------------------------------------------

class TestDDGExplicitIntent(TestCase):
    """search_duck.intent matched via padacioso pipeline."""

    def setUp(self):
        LOG.set_level("DEBUG")
        self.minicroft = get_minicroft(
            [SKILL_ID],
            secondary_langs=["de-DE", "es-ES", "pt-PT"],
        )

    def tearDown(self):
        if self.minicroft:
            self.minicroft.stop()
        LOG.set_level("CRITICAL")

    def _run(self, utterance: str, lang: str):
        session = Session(f"ddg-intent-{lang}")
        session.lang = lang
        session.pipeline = ["ovos-padacioso-pipeline-plugin-high"]

        message = Message(
            "recognizer_loop:utterance",
            {"utterances": [utterance], "lang": lang},
            {"session": session.serialize()},
        )

        final_session = deepcopy(session)
        final_session.active_skills = [(SKILL_ID, 0.0)]

        test = End2EndTest(
            minicroft=self.minicroft,
            skill_ids=[SKILL_ID],
            eof_msgs=["ovos.utterance.handled"],
            flip_points=["recognizer_loop:utterance"],
            ignore_messages=_IGNORE,
            source_message=message,
            final_session=final_session,
            activation_points=[f"{SKILL_ID}:search_duck.intent"],
            expected_messages=[
                message,
                Message(f"{SKILL_ID}.activate", {}, {"skill_id": SKILL_ID}),
                Message(f"{SKILL_ID}:search_duck.intent",
                        {"utterance": utterance, "lang": lang},
                        {"skill_id": SKILL_ID}),
                Message("mycroft.skill.handler.start",
                        {"name": "DuckDuckGoSkill.handle_search"},
                        {"skill_id": SKILL_ID}),
                Message("mycroft.skill.handler.complete",
                        {"name": "DuckDuckGoSkill.handle_search"},
                        {"skill_id": SKILL_ID}),
                Message("ovos.utterance.handled", {}, {"skill_id": SKILL_ID}),
            ],
        )
        test.execute(timeout=30)

    def test_en_explicit_search(self):
        self._run("search duckduckgo for Isaac Newton", "en-US")

    def test_de_explicit_search(self):
        self._run("suche bei duckduckgo nach Isaac Newton", "de-DE")

    def test_es_explicit_search(self):
        self._run("busca en duckduckgo Isaac Newton", "es-ES")

    def test_pt_explicit_search(self):
        self._run("pesquisa no duckduckgo por Isaac Newton", "pt-PT")


# ---------------------------------------------------------------------------
# Fallback handler
# ---------------------------------------------------------------------------

class TestDDGFallback(TestCase):
    """DDG fallback fires for open factual questions not matched by other pipelines."""

    def setUp(self):
        LOG.set_level("DEBUG")
        self.minicroft = get_minicroft([SKILL_ID])

    def tearDown(self):
        if self.minicroft:
            self.minicroft.stop()
        LOG.set_level("CRITICAL")

    def _run(self, utterance: str, lang: str):
        session = Session(f"ddg-fallback-{lang}")
        session.lang = lang
        session.pipeline = ["ovos-fallback-pipeline-plugin"]

        message = Message(
            "recognizer_loop:utterance",
            {"utterances": [utterance], "lang": lang},
            {"session": session.serialize()},
        )

        test = End2EndTest(
            minicroft=self.minicroft,
            skill_ids=[SKILL_ID],
            eof_msgs=["ovos.utterance.handled"],
            flip_points=["recognizer_loop:utterance"],
            ignore_messages=_IGNORE,
            source_message=message,
            activation_points=[f"ovos.skills.fallback.{SKILL_ID}.request"],
            expected_messages=[
                message,
                Message("ovos.skills.fallback.ping",
                        {"utterances": [utterance], "lang": lang, "range": _FALLBACK_RANGE}),
                Message("ovos.skills.fallback.pong",
                        {"skill_id": SKILL_ID, "can_handle": True}),
                Message(f"ovos.skills.fallback.{SKILL_ID}.request",
                        {"utterances": [utterance], "lang": lang, "range": _FALLBACK_RANGE, "skill_id": SKILL_ID}),
                Message(f"ovos.skills.fallback.{SKILL_ID}.start", {}),
                Message(f"ovos.skills.fallback.{SKILL_ID}.response",
                        {"fallback_handler": "DuckDuckGoSkill.handle_fallback"},
                        {"skill_id": SKILL_ID}),
                Message("ovos.utterance.handled", {}),
            ],
        )
        test.execute(timeout=30)

    def test_en_who_question(self):
        self._run("who is Marie Curie", "en-US")

    def test_en_what_question(self):
        self._run("what is the Eiffel Tower", "en-US")

    def test_de_entity_query(self):
        # Direct entity name — works without keyword extractor
        self._run("Albert Einstein", "de-DE")

    def test_es_entity_query(self):
        self._run("Isaac Newton", "es-ES")

    def test_pt_entity_query(self):
        self._run("Marie Curie", "pt-PT")


# ---------------------------------------------------------------------------
# Blacklisted utterances must NOT activate the skill
# ---------------------------------------------------------------------------

class TestDDGBlacklist(TestCase):
    """Weather utterances are rejected by can_answer → pong has can_handle=False."""

    def setUp(self):
        LOG.set_level("DEBUG")
        self.minicroft = get_minicroft([SKILL_ID])

    def tearDown(self):
        if self.minicroft:
            self.minicroft.stop()
        LOG.set_level("CRITICAL")

    def test_weather_not_handled_by_ddg(self):
        session = Session("ddg-blacklist-weather")
        session.lang = "en-US"
        session.pipeline = ["ovos-fallback-pipeline-plugin"]

        message = Message(
            "recognizer_loop:utterance",
            {"utterances": ["what is the weather today"], "lang": "en-US"},
            {"session": session.serialize()},
        )

        test = End2EndTest(
            minicroft=self.minicroft,
            skill_ids=[SKILL_ID],
            eof_msgs=["ovos.utterance.handled"],
            flip_points=["recognizer_loop:utterance"],
            ignore_messages=_IGNORE,
            source_message=message,
            expected_messages=[
                message,
                Message("ovos.skills.fallback.ping",
                        {"utterances": ["what is the weather today"], "lang": "en-US", "range": _FALLBACK_RANGE}),
                Message("ovos.skills.fallback.pong",
                        {"skill_id": SKILL_ID, "can_handle": False}),
                Message("mycroft.audio.play_sound", {"uri": "snd/error.mp3"}),
                Message("complete_intent_failure", {}),
                Message("ovos.utterance.handled", {}),
            ],
        )
        test.execute(timeout=15)
