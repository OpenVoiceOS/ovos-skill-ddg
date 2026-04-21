"""
Unit tests for DuckDuckGoSkill.

Uses FakeBus and mocked DuckDuckGoRetrievalEngine — no network, no OVOS daemon required.
"""
import unittest
from unittest.mock import MagicMock, patch

from ovos_bus_client.message import Message
from ovos_utils.fakebus import FakeBus


def _make_skill():
    with patch("ovos_skill_ddg.DuckDuckGoRetrievalEngine") as mock_cls:
        mock_cls.return_value = MagicMock()
        from ovos_skill_ddg import DuckDuckGoSkill
        skill = DuckDuckGoSkill(bus=FakeBus(), skill_id="test.ddg")
        skill.engine = mock_cls.return_value
        return skill


# ---------------------------------------------------------------------------
# Skill instantiation
# ---------------------------------------------------------------------------

class TestSkillInit(unittest.TestCase):

    def test_skill_creates_engine(self):
        with patch("ovos_skill_ddg.DuckDuckGoRetrievalEngine") as mock_cls:
            from ovos_skill_ddg import DuckDuckGoSkill
            DuckDuckGoSkill(bus=FakeBus(), skill_id="test.ddg")
        mock_cls.assert_called_once()

    def test_runtime_requires_internet(self):
        skill = _make_skill()
        req = skill.runtime_requirements
        self.assertTrue(req.requires_internet)
        self.assertTrue(req.internet_before_load)
        self.assertFalse(req.no_internet_fallback)


# ---------------------------------------------------------------------------
# handle_search — explicit intent handler
# ---------------------------------------------------------------------------

class TestHandleSearch(unittest.TestCase):

    def setUp(self):
        self.skill = _make_skill()
        self.skill.speak = MagicMock()
        self.skill.speak_dialog = MagicMock()
        self.skill.gui = MagicMock()

    def _msg(self, query="Isaac Newton"):
        return Message("ovos.skills.test", data={"query": query})

    def test_speaks_answer(self):
        self.skill.engine.query.return_value = [("Isaac Newton was a physicist.", 0.9)]
        with patch("ovos_skill_ddg.SessionManager") as sm:
            sm.get.return_value.session_id = "default"
            sm.get.return_value.lang = "en-US"
            self.skill.handle_search(self._msg())
        self.skill.speak.assert_called_once_with("Isaac Newton was a physicist.")

    def test_speaks_no_answer_when_empty(self):
        self.skill.engine.query.return_value = []
        with patch("ovos_skill_ddg.SessionManager") as sm:
            sm.get.return_value.session_id = "default"
            sm.get.return_value.lang = "en-US"
            self.skill.handle_search(self._msg("xyzzy"))
        self.skill.speak_dialog.assert_any_call("no_answer")
        self.skill.speak.assert_not_called()

    def test_gui_animation_shown_for_default_session(self):
        self.skill.engine.query.return_value = [("Answer.", 0.9)]
        with patch("ovos_skill_ddg.SessionManager") as sm:
            sm.get.return_value.session_id = "default"
            sm.get.return_value.lang = "en-US"
            self.skill.handle_search(self._msg())
        self.skill.gui.show_animated_image.assert_called_once_with("duck.gif")

    def test_gui_animation_not_shown_for_remote_session(self):
        self.skill.engine.query.return_value = [("Answer.", 0.9)]
        with patch("ovos_skill_ddg.SessionManager") as sm:
            sm.get.return_value.session_id = "remote-abc"
            sm.get.return_value.lang = "en-US"
            self.skill.handle_search(self._msg())
        self.skill.gui.show_animated_image.assert_not_called()

    def test_query_called_with_correct_lang(self):
        self.skill.engine.query.return_value = [("Answer.", 0.9)]
        with patch("ovos_skill_ddg.SessionManager") as sm:
            sm.get.return_value.session_id = "default"
            sm.get.return_value.lang = "pt-PT"
            self.skill.handle_search(self._msg("Newton"))
        self.skill.engine.query.assert_called_once_with("Newton", lang="pt-PT", k=1)

    def test_show_gui_called_for_default_session_with_answer(self):
        self.skill.engine.query.return_value = [("Answer.", 0.9)]
        self.skill._show_gui = MagicMock()
        with patch("ovos_skill_ddg.SessionManager") as sm:
            sm.get.return_value.session_id = "default"
            sm.get.return_value.lang = "en-US"
            self.skill.handle_search(self._msg("Newton"))
        self.skill._show_gui.assert_called_once_with("Newton", "en-US")

    def test_show_gui_not_called_for_remote_session(self):
        self.skill.engine.query.return_value = [("Answer.", 0.9)]
        self.skill._show_gui = MagicMock()
        with patch("ovos_skill_ddg.SessionManager") as sm:
            sm.get.return_value.session_id = "remote-abc"
            sm.get.return_value.lang = "en-US"
            self.skill.handle_search(self._msg("Newton"))
        self.skill._show_gui.assert_not_called()


# ---------------------------------------------------------------------------
# match_common_query
# ---------------------------------------------------------------------------

class TestMatchCommonQuery(unittest.TestCase):

    def setUp(self):
        self.skill = _make_skill()
        self.skill.voc_match = MagicMock(return_value=False)

    def test_returns_answer_and_score(self):
        self.skill.engine.query.return_value = [("Marie Curie was a scientist.", 0.9)]
        result = self.skill.match_common_query("who is Marie Curie", "en-US")
        self.assertEqual(result, ("Marie Curie was a scientist.", 0.9))

    def test_returns_none_when_no_results(self):
        self.skill.engine.query.return_value = []
        result = self.skill.match_common_query("xyzzy nonsense", "en-US")
        self.assertIsNone(result)

    def test_returns_none_for_misc_blacklist(self):
        self.skill.voc_match.side_effect = lambda phrase, voc: voc == "MiscBlacklist"
        result = self.skill.match_common_query("play music", "en-US")
        self.assertIsNone(result)
        self.skill.engine.query.assert_not_called()

    def test_returns_none_for_weather_query(self):
        self.skill.voc_match.side_effect = lambda phrase, voc: voc == "Weather"
        result = self.skill.match_common_query("what is the weather", "en-US")
        self.assertIsNone(result)
        self.skill.engine.query.assert_not_called()

    def test_query_called_with_phrase_and_lang(self):
        self.skill.engine.query.return_value = [("Answer.", 0.9)]
        self.skill.match_common_query("Marie Curie", "de-DE")
        self.skill.engine.query.assert_called_once_with("Marie Curie", lang="de-DE", k=1)


# ---------------------------------------------------------------------------
# handle_fallback
# ---------------------------------------------------------------------------

class TestFallback(unittest.TestCase):

    def setUp(self):
        self.skill = _make_skill()
        self.skill.speak = MagicMock()
        self.skill.gui = MagicMock()
        self.skill.voc_match = MagicMock(return_value=False)

    def _msg(self, utterance="who is Einstein"):
        return Message("ovos.skills.test", data={"utterance": utterance})

    def test_returns_true_and_speaks_when_answer_found(self):
        self.skill.engine.query.return_value = [("Albert Einstein was a physicist.", 0.9)]
        with patch("ovos_skill_ddg.SessionManager") as sm:
            sm.get.return_value.session_id = "default"
            sm.get.return_value.lang = "en-US"
            result = self.skill.handle_fallback(self._msg())
        self.assertTrue(result)
        self.skill.speak.assert_called_once_with("Albert Einstein was a physicist.")

    def test_returns_false_when_no_answer(self):
        self.skill.engine.query.return_value = []
        with patch("ovos_skill_ddg.SessionManager") as sm:
            sm.get.return_value.session_id = "default"
            sm.get.return_value.lang = "en-US"
            result = self.skill.handle_fallback(self._msg("xyzzy"))
        self.assertFalse(result)
        self.skill.speak.assert_not_called()

    def test_returns_false_for_misc_blacklist(self):
        self.skill.voc_match.side_effect = lambda u, voc: voc == "MiscBlacklist"
        result = self.skill.handle_fallback(self._msg("play music"))
        self.assertFalse(result)
        self.skill.engine.query.assert_not_called()

    def test_returns_false_for_weather(self):
        self.skill.voc_match.side_effect = lambda u, voc: voc == "Weather"
        result = self.skill.handle_fallback(self._msg("will it rain"))
        self.assertFalse(result)
        self.skill.engine.query.assert_not_called()

    def test_show_gui_called_for_default_session(self):
        self.skill.engine.query.return_value = [("Answer.", 0.9)]
        self.skill._show_gui = MagicMock()
        with patch("ovos_skill_ddg.SessionManager") as sm:
            sm.get.return_value.session_id = "default"
            sm.get.return_value.lang = "en-US"
            self.skill.handle_fallback(self._msg("who is Einstein"))
        self.skill._show_gui.assert_called_once_with("who is Einstein", "en-US")

    def test_show_gui_not_called_for_remote_session(self):
        self.skill.engine.query.return_value = [("Answer.", 0.9)]
        self.skill._show_gui = MagicMock()
        with patch("ovos_skill_ddg.SessionManager") as sm:
            sm.get.return_value.session_id = "remote-xyz"
            sm.get.return_value.lang = "en-US"
            self.skill.handle_fallback(self._msg("who is Einstein"))
        self.skill._show_gui.assert_not_called()


# ---------------------------------------------------------------------------
# cq_callback
# ---------------------------------------------------------------------------

class TestCqCallback(unittest.TestCase):

    def setUp(self):
        self.skill = _make_skill()
        self.skill._show_gui = MagicMock()

    def test_show_gui_called_for_default_session(self):
        with patch("ovos_skill_ddg.SessionManager") as sm:
            sm.get.return_value.session_id = "default"
            sm.get.return_value.lang = "en-US"
            self.skill.cq_callback("Marie Curie", "She was a scientist.", "en-US")
        self.skill._show_gui.assert_called_once_with("Marie Curie", "en-US")

    def test_show_gui_not_called_for_remote_session(self):
        with patch("ovos_skill_ddg.SessionManager") as sm:
            sm.get.return_value.session_id = "remote-xyz"
            sm.get.return_value.lang = "en-US"
            self.skill.cq_callback("Marie Curie", "She was a scientist.", "en-US")
        self.skill._show_gui.assert_not_called()


# ---------------------------------------------------------------------------
# _show_gui
# ---------------------------------------------------------------------------

class TestShowGui(unittest.TestCase):

    def setUp(self):
        self.skill = _make_skill()
        self.skill.gui = MagicMock()

    def test_shows_image_url(self):
        self.skill.engine.get_image.return_value = "https://duckduckgo.com/i/abc.jpg"
        self.skill._show_gui("Eiffel Tower", "en-US")
        self.skill.gui.show_image.assert_called_once_with("https://duckduckgo.com/i/abc.jpg")

    def test_prepends_host_for_relative_path(self):
        self.skill.engine.get_image.return_value = "/i/abc.jpg"
        self.skill._show_gui("Eiffel Tower", "en-US")
        self.skill.gui.show_image.assert_called_once_with("https://duckduckgo.com/i/abc.jpg")

    def test_falls_back_to_logo_when_no_image(self):
        self.skill.engine.get_image.return_value = None
        self.skill._show_gui("unknown", "en-US")
        self.skill.gui.show_image.assert_called_once_with("logo.png")

    def test_get_image_called_with_query_and_lang(self):
        self.skill.engine.get_image.return_value = None
        self.skill._show_gui("Eiffel Tower", "fr-FR")
        self.skill.engine.get_image.assert_called_once_with("Eiffel Tower", lang="fr-FR")


if __name__ == "__main__":
    unittest.main()
