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
from adapt.intent import IntentBuilder
from google_trans_new import google_translator
from RAKEkeywords import Rake
import logging
logging.getLogger("urllib3.connectionpool").setLevel("INFO")


class DuckDuckGoSkill(CommonQuerySkill):
    def __init__(self):
        super().__init__()
        self.translator = google_translator()
        self.tx_cache = {}  # avoid translating twice
        self.duck_cache = {}
        self.rake = Rake()  # only english for now
        # for usage in tell me more
        self.idx = 0
        self.results = []
        self.image = None

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
        summary = self.ask_the_duck(query)
        if summary:
            self.speak_result()
        else:
            self.speak_dialog("no_answer")

    @intent_handler(IntentBuilder("DuckMore").require("More").
                    require("DuckKnows"))
    def handle_tell_more(self, message):
        """ Follow up query handler, "tell me more".

            If a "spoken_lines" entry exists in the active contexts
            this can be triggered.
        """
        self.speak_result()

    def CQS_match_query_phrase(self, utt):
        self.log.debug("DuckDuckGo query: " + utt)
        # Automatic translation to English
        utt = self.translate(utt, "en", self.lang)
        # extract most relevant keyword
        keywords = self.rake.extract_keywords(utt)
        self.log.debug("Extracted keywords: " + str(keywords))
        # TODO better selection / merging of top keywords with same
        #  confidence??
        query = keywords[0][0]
        self.log.debug("Selected keyword: " + query)

        summary = self.ask_the_duck(query, translate=False)

        if summary:
            self.idx += 1
            return (utt, CQSMatchLevel.GENERAL, self.results[0],
                    {'query': query, 'answer': self.results[0],
                     "keywords": keywords, "image": self.image})

    def CQS_action(self, phrase, data):
        """ If selected show gui """
        self.display_ddg(data["answer"], data["image"])

    def ask_the_duck(self, query, translate=True):
        if translate:
            # Automatic translation to English
            utt = self.translate(query, "en", self.lang)
        else:
            utt = query

        # cache so we dont hit the api twice for the same query
        if query not in self.duck_cache:
            self.duck_cache[query] = requests.get("https://api.duckduckgo.com",
                                                  params={"format": "json",
                                                          "q": utt}).json()
        data = self.duck_cache[query]

        # info
        related_topics = [t["Text"] for t in data.get("RelatedTopics") or []]
        infobox = {}
        infodict = data.get("Infobox") or {}
        for entry in infodict.get("content", []):
            infobox[entry["label"]] = entry["value"]

        # GUI
        title = data.get("Heading")
        self.image = data.get("Image", "")

        # summary
        summary = data.get("AbstractText")

        if not summary:
            return None, None

        self.log.debug("DuckDuckGo answer: " + summary)

        # context for follow up questions
        # TODO intents for this, with this context intents can look up all data
        self.set_context("DuckKnows", query)
        self.idx = 0
        self.results = summary.split(". ")
        return summary

    def display_ddg(self, summary, image):
        if image.startswith("/"):
            image = "https://duckduckgo.com" + image
        self.gui['summary'] = summary
        self.gui['imgLink'] = image
        self.gui.show_page("DuckDelegate.qml", override_idle=60)

    def speak_result(self):
        if self.idx + 1 > len(self.results):
            self.speak_dialog("thats all")
            self.remove_context("ddg")
            self.idx = 0
        else:
            if self.image:
                self.display_ddg(self.results[self.idx], self.image)
            self.speak(self.results[self.idx])
            self.idx += 1

    def stop(self):
        self.gui.release()


def create_skill():
    return DuckDuckGoSkill()
