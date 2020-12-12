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
from tempfile import gettempdir
from os.path import join, isfile, expanduser
from padatious import IntentContainer

logging.getLogger("urllib3.connectionpool").setLevel("INFO")


class DuckDuckGoSkill(CommonQuerySkill):
    def __init__(self):
        super().__init__()
        self.translator = google_translator()
        self.tx_cache = {}  # avoid translating twice
        self.duck_cache = {}
        self.rake = Rake()  # only english for now

        # for usage in tell me more / follow up questions
        self.idx = 0
        self.results = []
        self.image = None

        # subparser, intents just for this skill
        # not part of main intent service
        intent_cache = expanduser(self.config_core['padatious']['intent_cache'])
        self.intents = IntentContainer(intent_cache)
        self.min_conf = 0.6

    def initialize(self):
        self.load_intents()
        # check for conflicting skills just in case
        # done after all skills loaded to ensure proper shutdown
        self.add_event("mycroft.skills.initialized",
                       self.blacklist_default_skill)

    def load_intents(self):
        # TODO intents for other infobox fields
        for intent in ["who", "birthdate"]:
            path = self.find_resource(intent + '.intent', "locale")
            if path:
                self.intents.load_intent(intent, path)

        self.intents.train(single_thread=True)

    def get_intro_message(self):
        # blacklist conflicting skills on install
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

    def stop(self):
        self.gui.release()

    # intents
    @intent_handler("search_duck.intent")
    def handle_search(self, message):
        query = message.data["query"]
        summary = self.ask_the_duck(query)
        if summary:
            self.speak_result()
        else:
            answer, _, _ = self.parse_subintents(query)
            if answer:
                self.speak(answer)
            else:
                self.speak_dialog("no_answer")

    @intent_handler(IntentBuilder("DuckMore").require("More").
                    require("DuckKnows"))
    def handle_tell_more(self, message):
        """ Follow up query handler, "tell me more"."""
        query = message.data["DuckKnows"]
        data, related_queries = self.get_infobox(query)
        # TODO maybe do something with the infobox data ?
        self.speak_result()

    # common query
    def parse_subintents(self, utt):
        # Get response from intents, this is a subparser that will handle
        # queries about the infobox returned by duckduckgo
        # eg. when was {person} born

        match = self.intents.calc_intent(utt)

        score = match.conf
        if score < self.min_conf:
            return None, None, None
        level = CQSMatchLevel.CATEGORY
        data = match.matches
        intent = match.name
        data["intent"] = intent
        data["score"] = score
        data["answer"] = None
        data["image"] = None
        query = utt

        if score > 0.8:
            level = CQSMatchLevel.EXACT
        elif score > 0.5:
            level = CQSMatchLevel.CATEGORY
        elif score > 0.3:
            level = CQSMatchLevel.GENERAL
        else:
            intent = None

        self.log.debug("DuckDuckGo Intent: " + str(intent))
        if "person" in data:
            query = data["person"]

        summary = self.ask_the_duck(query)
        answer = summary
        if summary:
            answer = self.results[0]
            infobox, related_queries = self.get_infobox(query)
            self.log.debug("DuckDuckGo infobox: " + str(infobox))
            data["infobox"] = infobox
            data["related_queries"] = related_queries

            if intent == "birthdate":
                answer = infobox.get("born")

            data["query"] = query
            data["answer"] = answer
            data["image"] = self.image
        if not answer:
            return None, None, None
        answer = self.translate(answer)
        return answer, level, data

    def CQS_match_query_phrase(self, utt):
        self.log.debug("DuckDuckGo query: " + utt)

        answer, match, data = self.parse_subintents(utt)
        if answer:
            self.idx += 1
            return (utt, match, answer, data)

        # extract most relevant keyword
        utt = self.translate(utt, "en", self.lang)
        keywords = self.rake.extract_keywords(utt)

        self.log.debug("Extracted keywords: " + str(keywords))
        # TODO better selection / merging of top keywords with same
        #  confidence??
        for kw in keywords:
            query = kw[0]
            self.log.debug("Selected keyword: " + query)

            summary = self.ask_the_duck(query, translate=False)
            if summary:
                self.idx += 1
                return (utt, CQSMatchLevel.GENERAL, self.results[0],
                        {'query': query, 'answer': self.results[0],
                         "keywords": keywords, "image": self.image})

    def CQS_action(self, phrase, data):
        """ If selected show gui """
        print(data)
        self.display_ddg(data["answer"], data["image"])

    # duck duck go api
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

        # GUI
        self.gui.clear()  # clear previous answer just in case
        title = data.get("Heading")
        self.image = data.get("Image", "")

        # summary
        summary = data.get("AbstractText")

        if not summary:
            return None

        self.log.debug("DuckDuckGo answer: " + summary)

        # context for follow up questions
        # TODO intents for this, with this context intents can look up all data
        self.set_context("DuckKnows", query)
        self.idx = 0
        summary = self.translate(summary)
        self.results = summary.split(". ")
        return summary

    def display_ddg(self, summary=None, image=None):
        if not image:
            # TODO duckduckgo logo
            return
        if image.startswith("/"):
            image = "https://duckduckgo.com" + image
        self.gui['summary'] = summary or ""
        self.gui['imgLink'] = image
        self.gui.show_page("DuckDelegate.qml", override_idle=60)

    def speak_result(self):
        if self.idx + 1 > len(self.results):
            # TODO ask user if he wants to hear about related topics
            self.speak_dialog("thats all")
            self.remove_context("ddg")
            self.idx = 0
        else:
            if self.image:
                self.display_ddg(self.results[self.idx], self.image)
            self.speak(self.results[self.idx])
            self.idx += 1

    def get_infobox(self, query):
        if query not in self.duck_cache:
            self.ask_the_duck(query)
        data = self.duck_cache[query]
        # info
        related_topics = [t.get("Text") for t in data.get("RelatedTopics", [])]
        infobox = {}
        infodict = data.get("Infobox") or {}
        for entry in infodict.get("content", []):
            k = entry["label"].lower().strip()
            infobox[k] = entry["value"]
        return infobox, related_topics

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


def create_skill():
    return DuckDuckGoSkill()
