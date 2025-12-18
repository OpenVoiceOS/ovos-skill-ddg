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
#
from typing import Optional, Tuple

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session, SessionManager
from ovos_ddg_solver import DuckDuckGoSolver
from ovos_utils import classproperty
from ovos_utils.gui import can_use_gui
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.decorators import intent_handler, common_query
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.ovos import OVOSSkill


class DuckDuckGoSkill(OVOSSkill):
    def initialize(self):
        self.session_results = {}
        self.duck = DuckDuckGoSolver()

    @classproperty
    def runtime_requirements(self):
        """this skill requires internet"""
        return RuntimeRequirements(internet_before_load=True,
                                   network_before_load=True,
                                   gui_before_load=False,
                                   requires_internet=True,
                                   requires_network=True,
                                   requires_gui=False,
                                   no_internet_fallback=False,
                                   no_network_fallback=False,
                                   no_gui_fallback=True)

    # intents
    @intent_handler("search_duck.intent",
                    voc_blacklist=["Weather", "Help"])
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

        summary = self.ask_the_duck(sess)
        if summary:
            self.speak_result(sess)
        else:
            self.speak_dialog("no_answer")

    @intent_handler(IntentBuilder("DuckMore").require("More").
                    require("DuckKnows"))
    def handle_tell_more(self, message):
        """Follow up query handler, "tell me more".

        If a "spoken_lines" entry exists in the active contexts
        this can be triggered.
        """
        sess = SessionManager.get(message)
        self.speak_result(sess)

    def cq_callback(self, utterance: str, answer: str, lang: str):
        """ If selected show gui """
        sess = SessionManager.get()
        self.display_ddg(sess)

    @common_query(callback=cq_callback)
    def match_common_query(self, phrase: str, lang: str) -> Optional[Tuple[str, float]]:
        if (self.voc_match(phrase, "MiscBlacklist") or
                self.voc_match(phrase, "Weather")):
            return None
        sess = SessionManager.get()
        self.session_results[sess.session_id] = {
            "query": phrase,
            "results": [],
            "idx": 0,
            "lang": lang,
            "title": phrase,
            "image": None
        }
        summary = self.ask_the_duck(sess)
        if summary:
            self.log.info(f"DDG answer: {summary}")
            return summary, 0.6

    # duck duck go api
    def ask_the_duck(self, sess: Session, lang: Optional[str] = None):
        lang = lang or sess.lang
        query = self.session_results[sess.session_id]["query"]
        results = self.duck.long_answer(query, lang=lang, units=sess.system_unit)
        self.session_results[sess.session_id]["results"] = results
        if results:
            self.set_context("DuckKnows", query)
            return results[0]["summary"]

    def display_ddg(self, sess: Session):
        if not can_use_gui(self.bus):
            return
        if sess.session_id in self.session_results:
            idx = self.session_results[sess.session_id]["idx"]
            query = self.session_results[sess.session_id].get("query")
            results = self.session_results[sess.session_id]["results"]
            summary = results[idx]["summary"]
            image = self.session_results[sess.session_id].get("image") or self.duck.get_image(query,
                                                                                              lang=sess.lang,
                                                                                              units=sess.system_unit)
            if sess.session_id == "default":
                if not image:
                    self.gui.show_image("logo.png")
                else:
                    if image.startswith("/"):
                        image = "https://duckduckgo.com" + image
                    self.gui['summary'] = summary or ""
                    self.gui['imgLink'] = image
                    self.gui.show_page("DuckDelegate", override_idle=60)

    def speak_result(self, sess: Session):

        if sess in self.session_results:
            results = self.session_results[sess.session_id]["results"]
            idx = self.session_results[sess.session_id]["idx"]
            title = self.session_results[sess.session_id].get("title") or \
                    "DuckDuckGo"

            if idx + 1 > len(results):
                self.speak_dialog("thats all")
                self.remove_context("DuckKnows")
                self.session_results[sess.session_id]["idx"] = 0
            else:
                self.speak(results[idx]["summary"])
                self.set_context("DuckKnows", "DuckDuckGo")
                self.display_ddg(sess)
                self.session_results[sess.session_id]["idx"] += 1
        else:
            self.speak_dialog("thats all")

    def can_stop(self, message: Message) -> bool:
        return False

    def stop(self):
        session = SessionManager.get()
        # called during global stop only
        if session.session_id in self.session_results:
            self.session_results.pop(session.session_id)
        if session.session_id == "default":
            self.gui.release()

