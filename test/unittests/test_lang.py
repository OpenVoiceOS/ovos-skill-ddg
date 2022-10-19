import json
import unittest
from time import sleep
from unittest.mock import Mock

from ovos_utils.messagebus import FakeBus, Message
from skill_ovos_ddg import DuckDuckGoSkill


class TestTranslation(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.bus.emitted_msgs = []

        def get_msg(msg):
            self.bus.emitted_msgs.append(json.loads(msg))

        self.bus.on("message", get_msg)

        self.skill = DuckDuckGoSkill()
        self.skill._startup(self.bus, "ddg.test")

        self.skill.duck.translator.translate = Mock()
        self.skill.duck.translator.translate.return_value = "this text is in portuguese, trust me!"
        self.skill.duck.get_expanded_answer = Mock()
        self.skill.duck.get_expanded_answer.return_value = [
            {"title": f"title 1", "summary": f"this is the answer number 1", "img": "/tmp/ddg.jpeg"},
            {"title": f"title 2", "summary": f"this is the answer number 2", "img": "/tmp/ddg.jpeg"}
        ]
        self.skill.duck.get_image = Mock()
        self.skill.duck.get_image.return_value = "/tmp/ddg.jpeg"

    def test_native_lang(self):
        # no translation
        self.skill.handle_search(Message("search_ddg.intent",
                                         {"query": "english question here"}))
        sleep(0.5)
        self.assertEqual(self.bus.emitted_msgs[-1],
                         {'context': {'skill_id': 'ddg.test'},
                          'data': {'expect_response': False,
                                   'lang': 'en-us',
                                   'meta': {'skill': 'ddg.test'},
                                   'utterance': 'this is the answer number 1'},
                          'type': 'speak'})

    def test_unk_lang(self):
        # translation
        self.skill.handle_search(Message("search_ddg.intent",
                                         {"query": "not english!",
                                          "lang": "pt-pt"}))
        sleep(0.5)
        self.assertEqual(self.bus.emitted_msgs[-1],
                         {'context': {'skill_id': 'ddg.test'},
                          'data': {'expect_response': False,
                                   'lang': 'pt-pt',
                                   'meta': {'skill': 'ddg.test'},
                                   'utterance': "this text is in portuguese, trust me!"},
                          'type': 'speak'})
