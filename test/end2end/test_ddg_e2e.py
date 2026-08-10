"""
End-to-end tests for DuckDuckGoSkill via ovoscope.

Covers:
- Explicit padacioso intent (search_duck.intent) fires and handler completes
- Fallback handler fires for open questions with no other pipeline match
- Multi-lang sessions (en-US, de-DE, es-ES, pt-PT) route correctly
- Blacklisted utterances ("weather") do NOT activate the fallback handler
"""
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_spec_tools import SpecMessage
from ovos_utils.log import LOG

from ovoscope import End2EndTest, get_minicroft

SKILL_ID = "ovos-skill-ddg.openvoiceos"

# Messages that carry variable content or are noise for these routing tests
_IGNORE = [
    str(SpecMessage.SPEAK),
    "recognizer_loop:audio_output_start",
    "recognizer_loop:audio_output_end",
    "mycroft.audio.play_sound",
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
    """search_duck.intent matched via padacioso pipeline.

    Each language gets its own MiniCroft (single ``lang=``, no
    ``secondary_langs``): padacioso's ``__detach_intent`` (padacioso#opm.py)
    removes a canonical intent name from *every* registered language, not
    just the one being re-registered, so registering the same skill for
    several languages on one shared pipeline instance leaves only the
    last-registered language matchable. Isolating each language in its own
    MiniCroft sidesteps that collision instead of asserting on it.
    """

    def setUp(self):
        LOG.set_level("DEBUG")

    def tearDown(self):
        LOG.set_level("CRITICAL")

    def _run(self, utterance: str, lang: str):
        minicroft = get_minicroft([SKILL_ID], lang=lang)
        try:
            session = Session(f"ddg-intent-{lang}")
            session.lang = lang
            session.pipeline = ["ovos-padacioso-pipeline-plugin-high"]

            message = Message(
                "recognizer_loop:utterance",
                {"utterances": [utterance], "lang": lang},
                {"session": session.serialize()},
            )

            intent_msg_type = f"{SKILL_ID}:search_duck"

            test = End2EndTest(
                minicroft=minicroft,
                skill_ids=[SKILL_ID],
                eof_msgs=["ovos.utterance.handled"],
                flip_points=["recognizer_loop:utterance"],
                ignore_messages=_IGNORE,
                source_message=message,
                test_msg_context=False,
                activation_points=[str(SpecMessage.INTENT_MATCHED)],
                expected_messages=[
                    message,
                    Message(f"{SKILL_ID}.activate", {}, {"skill_id": SKILL_ID}),
                    Message(str(SpecMessage.INTENT_MATCHED), {}, {"skill_id": SKILL_ID}),
                    Message(str(SpecMessage.INTENT_HANDLER_START), {}, {"skill_id": SKILL_ID}),
                    Message(intent_msg_type, {}, {"skill_id": SKILL_ID}),
                    Message("mycroft.skill.handler.start",
                            {"name": "DuckDuckGoSkill.handle_search"},
                            {"skill_id": SKILL_ID}),
                    Message("mycroft.skill.handler.complete",
                            {"name": "DuckDuckGoSkill.handle_search"},
                            {"skill_id": SKILL_ID}),
                    Message(str(SpecMessage.INTENT_HANDLER_COMPLETE), {}, {"skill_id": SKILL_ID}),
                    Message("ovos.utterance.handled", {}, {"skill_id": SKILL_ID}),
                ],
            )
            test.execute(timeout=30)
        finally:
            minicroft.stop()

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
            test_msg_context=False,
            test_message_number=False,
            activation_points=[f"ovos.skills.fallback.{SKILL_ID}.request"],
            expected_messages=[
                message,
                Message("ovos.skills.fallback.ping",
                        {"utterances": [utterance], "lang": lang, "range": _FALLBACK_RANGE}),
                Message("ovos.skills.fallback.pong",
                        {"skill_id": SKILL_ID, "can_handle": True}),
                Message(str(SpecMessage.INTENT_MATCHED), {}, {"skill_id": SKILL_ID}),
                Message(str(SpecMessage.INTENT_HANDLER_START), {}, {"skill_id": SKILL_ID}),
                Message(f"ovos.skills.fallback.{SKILL_ID}.request",
                        {"utterances": [utterance], "lang": lang, "range": _FALLBACK_RANGE, "skill_id": SKILL_ID}),
                Message(f"ovos.skills.fallback.{SKILL_ID}.start", {}),
                Message("mycroft.skill.handler.start",
                        {}, {"skill_id": SKILL_ID}),
                Message(f"ovos.skills.fallback.{SKILL_ID}.response",
                        {"fallback_handler": "DuckDuckGoSkill.handle_fallback"},
                        {"skill_id": SKILL_ID}),
                Message("mycroft.skill.handler.complete",
                        {}, {"skill_id": SKILL_ID}),
                Message(str(SpecMessage.INTENT_HANDLER_COMPLETE), {}, {"skill_id": SKILL_ID}),
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
            test_msg_context=False,
            expected_messages=[
                message,
                Message("ovos.skills.fallback.ping",
                        {"utterances": ["what is the weather today"], "lang": "en-US", "range": _FALLBACK_RANGE}),
                Message("ovos.skills.fallback.pong",
                        {"skill_id": SKILL_ID, "can_handle": False}),
                Message(str(SpecMessage.INTENT_UNMATCHED), {}),
                Message("ovos.utterance.handled", {}),
            ],
        )
        test.execute(timeout=15)
