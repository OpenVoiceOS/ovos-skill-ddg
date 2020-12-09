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
import requests
from mycroft.messagebus.message import Message
from mycroft.skills.core import intent_handler
from mycroft.configuration import LocalConf, USER_CONFIG
from mycroft.skills.common_query_skill import CommonQuerySkill, CQSMatchLevel
from google_trans_new import google_translator
import logging
logging.getLogger("urllib3.connectionpool").setLevel("INFO")


class DuckDuckGoSkill(CommonQuerySkill):
    def __init__(self):
        super().__init__()
        self.translator = google_translator()
        self.tx_cache = {}  # avoid translating twice
        self.duck_cache = {}

    def initialize(self):
        self.blacklist_default_skill()

    def blacklist_default_skill(self):
        # load the current list of already blacklisted skills
        blacklist = self.config_core["skills"]["blacklisted_skills"]

        # check the folder name (skill_id) of the skill you want to replace
        skill_id = "mycroft-fallback-duck-duck-go.mycroftai"

        # add the skill to the blacklist
        if skill_id not in blacklist:
            self.log.debug("Blacklisting official mycroft skill")
            blacklist.append(skill_id)

            # load the user config file (~/.mycroft/mycroft.conf)
            conf = LocalConf(USER_CONFIG)
            if "skills" not in conf:
                conf["skills"] = {}

            # update the blacklist field
            conf["skills"]["blacklisted_skills"] = blacklist

            # save the user config file
            conf.store()

        # tell the intent service to unload the skill in case it was loaded already
        # this should avoid the need to restart
        self.bus.emit(Message("detach_skill", {"skill_id": skill_id}))

    def translate(self, utterance, lang_tgt=None, lang_src="en"):
        lang_tgt = lang_tgt or self.lang

        # if langs are the same do nothing
        if not lang_tgt.startswith(lang_src):
            if lang_tgt not in self.tx_cache:
                self.tx_cache[lang_tgt] = {}
            # if translated before, dont translate again
            if utterance in self.tx_cache[lang_tgt]:
                # get previous translated value
                translated_utt = self.tx_cache[lang_tgt][utterance]
            else:
                # translate this utterance
                translated_utt = self.translator.translate(utterance,
                                                           lang_tgt=lang_tgt,
                                                           lang_src=lang_src).strip()
                # save the translation if we need it again
                self.tx_cache[lang_tgt][utterance] = translated_utt
            self.log.debug("translated {src} -- {tgt}".format(src=utterance,
                                                              tgt=translated_utt))
        else:
            translated_utt = utterance.strip()
        return translated_utt

    @intent_handler("search_duck.intent")
    def handle_search(self, message):
        query = message.data["query"]
        response = self.ask_the_duck(query)
        if response:
            self.speak(response)
        else:
            self.speak_dialog("no_answer")

    def CQS_match_query_phrase(self, utt):
        self.log.debug("DuckDuckGo query: " + utt)
        # TODO extract queries, the full utterance will never trigger right
        # maybe use little_questions package?
        response = self.ask_the_duck(utt)
        if response:
            return (utt, CQSMatchLevel.GENERAL, response,
                    {'query': utt, 'answer': response})

    def ask_the_duck(self, query):
        # Automatic translation to English
        utt = self.translate(query, "en", self.lang)

        # cache so we dont hit the api twice for the same query
        if query not in self.duck_cache:
            self.duck_cache[query] = requests.get("https://api.duckduckgo.com",
                                                  params={"format": "json",
                                                          "q": utt}).json()
        data = self.duck_cache[query]
        self.log.debug("DuckDuckGo data: " + str(data))

        # info
        related_topics = [t["Text"] for t in data.get("RelatedTopics") or []]
        infobox = {}
        infodict = data.get("Infobox") or {}
        for entry in infodict.get("content", []):
            infobox[entry["label"]] = entry["value"]

        # GUI
        title = data.get("Heading")
        image = data.get("Image", "")

        # summary
        summary = data.get("AbstractText")

        if not summary:
            return None

        def duck_img(img_id):
            # get url from imgid
            return "https://duckduckgo.com" + img_id

        self.log.debug("DuckDuckGo answer: " + summary)
        self.gui['summary'] = summary
        self.gui['imgLink'] = duck_img(image)
        self.gui.show_page("DuckDelegate.qml", override_idle=60)

        # context for follow up questions
        # TODO intents for this, with this context intents can look up all data
        self.set_context("DuckKnows", query)
        return summary

    def stop(self):
        self.gui.release()


def create_skill():
    return DuckDuckGoSkill()
