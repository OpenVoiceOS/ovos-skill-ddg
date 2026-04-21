# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from typing import Optional, Tuple

from ovos_bus_client.message import Message
from ovos_bus_client.session import SessionManager
from ovos_ddg_plugin import DuckDuckGoRetrievalEngine
from ovos_utils import classproperty
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.decorators import intent_handler, common_query, fallback_handler
from ovos_workshop.skills.fallback import FallbackSkill


class DuckDuckGoSkill(FallbackSkill):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.engine = DuckDuckGoRetrievalEngine(config=dict(self.settings))

    @classproperty
    def runtime_requirements(self):
        return RuntimeRequirements(
            internet_before_load=True,
            network_before_load=True,
            gui_before_load=False,
            requires_internet=True,
            requires_network=True,
            requires_gui=False,
            no_internet_fallback=False,
            no_network_fallback=False,
            no_gui_fallback=True,
        )

    @intent_handler("search_duck.intent", voc_blacklist=["Weather", "Help"])
    def handle_search(self, message):
        query = message.data["query"]
        sess = SessionManager.get(message)
        if sess.session_id == "default":
            self.gui.show_animated_image("duck.gif")
        results = self.engine.query(query, lang=sess.lang, k=1)
        if results:
            answer, _ = results[0]
            self.speak(answer)
            if sess.session_id == "default":
                self._show_gui(query, sess.lang)
        else:
            self.speak_dialog("no_answer")

    def cq_callback(self, utterance: str, answer: str, lang: str):
        sess = SessionManager.get()
        if sess.session_id == "default":
            self._show_gui(utterance, sess.lang)

    @common_query(callback=cq_callback)
    def match_common_query(self, phrase: str, lang: str) -> Optional[Tuple[str, float]]:
        if self.voc_match(phrase, "MiscBlacklist") or self.voc_match(phrase, "Weather"):
            return None
        results = self.engine.query(phrase, lang=lang, k=1)
        if results:
            answer, score = results[0]
            self.log.info(f"DDG answer: {answer}")
            return answer, score

    def can_answer(self, message: Message) -> bool:
        utterances = message.data.get("utterances") or []
        utterance = utterances[0] if utterances else ""
        return not (
            self.voc_match(utterance, "MiscBlacklist")
            or self.voc_match(utterance, "Weather")
        )

    @fallback_handler(priority=90)
    def handle_fallback(self, message: Message) -> bool:
        utterance = message.data.get("utterance", "")
        if self.voc_match(utterance, "MiscBlacklist") or self.voc_match(utterance, "Weather"):
            return False
        sess = SessionManager.get(message)
        results = self.engine.query(utterance, lang=sess.lang, k=1)
        if results:
            answer, _ = results[0]
            self.speak(answer)
            if sess.session_id == "default":
                self._show_gui(utterance, sess.lang)
            return True
        return False

    def _show_gui(self, query: str, lang: str):
        image = self.engine.get_image(query, lang=lang) or "logo.png"
        if image.startswith("/"):
            image = "https://duckduckgo.com" + image
        self.gui.show_image(image)
