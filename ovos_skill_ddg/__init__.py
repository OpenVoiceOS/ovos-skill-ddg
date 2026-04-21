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
from ovos_bus_client.session import Session, SessionManager
from ovos_ddg_plugin import DuckDuckGoRetrievalEngine
from ovos_utils import classproperty
from ovos_utils.gui import can_use_gui
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.decorators import intent_handler, common_query
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.ovos import OVOSSkill


class DuckDuckGoSkill(OVOSSkill):
    def initialize(self):
        self.session_results = {}
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
        self.session_results[sess.session_id] = {
            "query": query,
            "results": [],
            "idx": 0,
            "lang": sess.lang,
            "image": None,
        }
        if self._fetch_results(sess):
            self.speak_result(sess)
        else:
            self.speak_dialog("no_answer")

    @intent_handler(IntentBuilder("DuckMore").require("More").require("DuckKnows"))
    def handle_tell_more(self, message):
        sess = SessionManager.get(message)
        self.speak_result(sess)

    def cq_callback(self, utterance: str, answer: str, lang: str):
        sess = SessionManager.get()
        self._display(sess)

    @common_query(callback=cq_callback)
    def match_common_query(self, phrase: str, lang: str) -> Optional[Tuple[str, float]]:
        if self.voc_match(phrase, "MiscBlacklist") or self.voc_match(phrase, "Weather"):
            return None
        sess = SessionManager.get()
        self.session_results[sess.session_id] = {
            "query": phrase,
            "results": [],
            "idx": 0,
            "lang": lang,
            "image": None,
        }
        if self._fetch_results(sess):
            top = self.session_results[sess.session_id]["results"][0]
            self.log.info(f"DDG answer: {top}")
            return top, 0.6
        return None

    def _fetch_results(self, sess: Session) -> bool:
        query = self.session_results[sess.session_id]["query"]
        lang = self.session_results[sess.session_id]["lang"]
        pairs = self.engine.query(query, lang=lang, k=3)
        results = [text for text, _score in pairs]
        self.session_results[sess.session_id]["results"] = results
        if results:
            self.set_context("DuckKnows", query)
        return bool(results)

    def _display(self, sess: Session):
        if not can_use_gui(self.bus):
            return
        if sess.session_id not in self.session_results:
            return
        data = self.session_results[sess.session_id]
        idx = data["idx"]
        results = data["results"]
        if idx >= len(results):
            return
        summary = results[idx]
        image = data.get("image") or self.engine.get_image(data["query"], lang=data["lang"])
        self.session_results[sess.session_id]["image"] = image
        if sess.session_id == "default":
            if not image:
                self.gui.show_image("logo.png")
            else:
                if image.startswith("/"):
                    image = "https://duckduckgo.com" + image
                self.gui["summary"] = summary
                self.gui["imgLink"] = image
                self.gui.show_page("DuckDelegate", override_idle=60)

    def speak_result(self, sess: Session):
        if sess.session_id not in self.session_results:
            self.speak_dialog("thats_all")
            return
        data = self.session_results[sess.session_id]
        results = data["results"]
        idx = data["idx"]
        if idx >= len(results):
            self.speak_dialog("thats_all")
            self.remove_context("DuckKnows")
            self.session_results[sess.session_id]["idx"] = 0
        else:
            self.speak(results[idx])
            self.set_context("DuckKnows", "DuckDuckGo")
            self._display(sess)
            self.session_results[sess.session_id]["idx"] += 1

    def can_stop(self, message: Message) -> bool:
        return False

    def stop(self):
        session = SessionManager.get()
        if session.session_id in self.session_results:
            self.session_results.pop(session.session_id)
        if session.session_id == "default":
            self.gui.release()
