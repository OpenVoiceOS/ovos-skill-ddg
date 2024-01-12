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
import simplematch
from ovos_bus_client.session import Session, SessionManager
from ovos_classifiers.heuristics.keyword_extraction import HeuristicExtractor
from ovos_utils import classproperty
from ovos_utils.gui import can_use_gui
from ovos_utils.process_utils import RuntimeRequirements

from ovos_plugin_manager.templates.solvers import QuestionSolver
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.common_query_skill import CommonQuerySkill, CQSMatchLevel


class DDGIntents:

    # TODO use padacioso and allow localization with .intent files

    @staticmethod
    def match(query, lang):
        if not lang.startswith("en"):
            return None, None

        query = query.lower()

        # known for
        match = simplematch.match("what is {query} known for", query) or \
                simplematch.match("what is {query} famous for", query)
        if match:
            return match["query"], "known for"

        # resting place
        match = simplematch.match("where is {query} resting place*", query) or \
                simplematch.match("where is {query} resting buried*", query)
        if match:
            return match["query"], "resting place"

        # birthday
        match = simplematch.match("when was {query} born*", query) or \
                simplematch.match("when is {query} birth*", query)
        if match:
            return match["query"], "born"

        # death
        match = simplematch.match("when was {query} death*", query) or \
                simplematch.match("when did {query} die*", query) or \
                simplematch.match("what was {query} *death", query) or \
                simplematch.match("what is {query} *death", query)

        if match:
            return match["query"], "died"

        # children
        match = simplematch.match("how many children did {query} have*",
                                  query) or \
                simplematch.match("how many children does {query} have*",
                                  query)
        if match:
            return match["query"], "children"

        # alma mater
        match = simplematch.match("what is {query} alma mater", query) or \
                simplematch.match("where did {query} study*", query)
        if match:
            return match["query"], "alma mater"

        return None, None


class DuckDuckGoSolver(QuestionSolver):
    enable_tx = True
    priority = 75

    def __init__(self, config=None):
        config = config or {}
        config["lang"] = "en"  # only supports english
        super().__init__(config)

    def extract_keyword(self, query, lang="en"):
        # TODO - from mycroft.conf
        keyword_extractor = HeuristicExtractor()
        return keyword_extractor.extract_subject(query, lang)

    def get_infobox(self, query, context=None):
        data = self.extract_and_search(query, context)  # handles translation
        # parse infobox
        related_topics = [t.get("Text") for t in data.get("RelatedTopics", [])]
        infobox = {}
        infodict = data.get("Infobox") or {}
        for entry in infodict.get("content", []):
            k = entry["label"].lower().strip()
            infobox[k] = entry["value"]
        return infobox, related_topics

    def extract_and_search(self, query, context=None):
        """
        extract search term from query and perform search
        """
        query, context, lang = self._tx_query(query, context)

        # match the full query
        data = self.get_data(query, context)
        if data:
            return data

        # extract the best keyword with some regexes or fallback to RAKE
        kw = self.extract_keyword(query, lang)
        return self.get_data(kw, context)

    # officially exported Solver methods
    def get_data(self, query, context):
        """
        query assured to be in self.default_lang
        return a dict response
        """
        # duck duck go api request
        try:
            data = requests.get("https://api.duckduckgo.com",
                                params={"format": "json",
                                        "q": query}).json()
        except:
            return {}
        return data

    def get_image(self, query, context=None):
        """
        query assured to be in self.default_lang
        return path/url to a single image to acompany spoken_answer
        """
        data = self.extract_and_search(query, context)
        image = data.get("Image") or \
                "https://github.com/JarbasSkills/skill-ddg/raw/master/ui/logo.png"
        if image.startswith("/"):
            image = "https://duckduckgo.com" + image
        return image

    def get_spoken_answer(self, query, context=None):
        """
        query assured to be in self.default_lang
        return a single sentence text response
        """

        # match an infobox field with some basic regexes
        # (primitive intent parsing)
        selected, key = DDGIntents.match(query, self.default_lang)

        if key:
            selected = self.extract_keyword(selected, self.default_lang)
            infobox = self.get_infobox(selected, context)[0] or {}
            answer = infobox.get(key)
            if answer:
                return answer

        # return summary
        data = self.extract_and_search(query, context)
        return data.get("AbstractText")

    def get_expanded_answer(self, query, context=None):
        """
        query assured to be in self.default_lang
        return a list of ordered steps to expand the answer, eg, "tell me more"

        {
            "title": "optional",
            "summary": "speak this",
            "img": "optional/path/or/url
        }
        :return:
        """
        data = self.get_data(query, context)
        img = self.get_image(query, context)
        steps = [{
            "title": query,
            "summary": s,
            "img": img
        } for s in self.sentence_split(data.get("AbstractText", ""), -1) if s]

        infobox, _ = self.get_infobox(query)
        steps += [{"title": k,
                   "summary": k + " - " + str(v),
                   "img": img} for k, v in infobox.items()
                  if not k.endswith(" id") and  # itunes id
                  not k.endswith(" profile") and  # twitter profile
                  k != "instance of"]  # spammy and sounds bad when spokem
        return steps


class DuckDuckGoSkill(CommonQuerySkill):
    def initialize(self):
        self.session_results = {}
        self.duck = DuckDuckGoSolver()

    @classproperty
    def runtime_requirements(self):
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
    @intent_handler("search_duck.intent")
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

        summary = self.ask_the_duck(query, self.lang)
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

    # common query
    def CQS_match_query_phrase(self, phrase):
        sess = SessionManager.get()
        self.session_results[sess.session_id] = {
            "query": phrase,
            "results": [],
            "idx": 0,
            "lang": sess.lang,
            "title": phrase,
            "image": None
        }
        summary = self.ask_the_duck(sess)
        if summary:
            self.log.info(f"DDG answer: {summary}")
            return (phrase, CQSMatchLevel.GENERAL, summary,
                    {'query': phrase,
                     'answer': summary})

    def CQS_action(self, phrase, data):
        """ If selected show gui """
        sess = SessionManager.get()
        if sess in self.session_results:
            self.display_wiki_entry()
        self.display_ddg(sess)

    # duck duck go api
    def ask_the_duck(self, sess):
        if sess.lang.startswith("en"):
            self.log.debug(f"skipping auto translation for DuckDuckGo, "
                           f"{sess.lang} is supported")
            DuckDuckGoSolver.enable_tx = False
        else:
            self.log.info(f"enabling auto translation for DuckDuckGo, "
                          f"{sess.lang} is not supported internally")
            DuckDuckGoSolver.enable_tx = True

        query = self.session_results[sess.session_id]["query"]
        self.set_context("DuckKnows", query)
        results = self.duck.long_answer(query, lang=sess.lang)
        self.session_results[sess.session_id]["results"] = results
        return results[0]["summary"]

    def display_ddg(self, sess: Session):
        if not can_use_gui(self.bus):
            return
        if sess.session_id in self.session_results:
            idx = self.session_results[sess.session_id]["idx"]
            query = self.session_results[sess.session_id].get("query")
            results = self.session_results[sess.session_id]["results"]
            summary = results[idx]["summary"]
            image = self.session_results[sess.session_id].get("image") or self.duck.get_image(query)
            title = self.session_results[sess.session_id].get("title") or "DuckDuckGo"
            image = image or "https://github.com/JarbasSkills/skill-ddg/raw/master/ui/logo.png"
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

            if idx + 1 > len(self.results):
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

    def stop(self):
        self.gui.release()

    def stop_session(self, sess):
        if sess.session_id in self.session_results:
            self.session_results.pop(sess.session_id)


if __name__ == "__main__":

    d = DuckDuckGoSolver()

    query = "who is Isaac Newton"

    # full answer
    ans = d.spoken_answer(query)
    print(ans)
    # Sir Isaac Newton was an English mathematician, physicist, astronomer, alchemist, theologian, and author widely recognised as one of the greatest mathematicians and physicists of all time and among the most influential scientists. He was a key figure in the philosophical revolution known as the Enlightenment. His book Philosophiæ Naturalis Principia Mathematica, first published in 1687, established classical mechanics. Newton also made seminal contributions to optics, and shares credit with German mathematician Gottfried Wilhelm Leibniz for developing infinitesimal calculus. In the Principia, Newton formulated the laws of motion and universal gravitation that formed the dominant scientific viewpoint until it was superseded by the theory of relativity.

    # chunked answer, "tell me more"
    for sentence in d.long_answer(query):
        print(sentence["title"])
        print(sentence["summary"])
        print(sentence.get("img"))

        # who is Isaac Newton
        # Sir Isaac Newton was an English mathematician, physicist, astronomer, alchemist, theologian, and author widely recognised as one of the greatest mathematicians and physicists of all time and among the most influential scientists.
        # https://duckduckgo.com/i/ea7be744.jpg

        # who is Isaac Newton
        # He was a key figure in the philosophical revolution known as the Enlightenment.
        # https://duckduckgo.com/i/ea7be744.jpg

        # who is Isaac Newton
        # His book Philosophiæ Naturalis Principia Mathematica, first published in 1687, established classical mechanics.
        # https://duckduckgo.com/i/ea7be744.jpg

        # who is Isaac Newton
        # Newton also made seminal contributions to optics, and shares credit with German mathematician Gottfried Wilhelm Leibniz for developing infinitesimal calculus.
        # https://duckduckgo.com/i/ea7be744.jpg

        # who is Isaac Newton
        # In the Principia, Newton formulated the laws of motion and universal gravitation that formed the dominant scientific viewpoint until it was superseded by the theory of relativity.
        # https://duckduckgo.com/i/ea7be744.jpg

    # bidirectional auto translate by passing lang context
    sentence = d.spoken_answer("Quem é Isaac Newton",
                               context={"lang": "pt"})
    print(sentence)
    # Sir Isaac Newton foi um matemático inglês, físico, astrônomo, alquimista, teólogo e autor amplamente reconhecido como um dos maiores matemáticos e físicos de todos os tempos e entre os cientistas mais influentes. Ele era uma figura chave na revolução filosófica conhecida como o Iluminismo. Seu livro Philosophiæ Naturalis Principia Mathematica, publicado pela primeira vez em 1687, estabeleceu a mecânica clássica. Newton também fez contribuições seminais para a óptica, e compartilha crédito com o matemático alemão Gottfried Wilhelm Leibniz para desenvolver cálculo infinitesimal. No Principia, Newton formulou as leis do movimento e da gravitação universal que formaram o ponto de vista científico dominante até ser superado pela teoria da relatividade
