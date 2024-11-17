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
import datetime
import os.path
from typing import Optional, List, Tuple, Dict, Any

import requests
from lingua_franca.format import nice_date
from ovos_bus_client.session import Session, SessionManager
from ovos_config import Configuration
from ovos_plugin_manager.templates.solvers import QuestionSolver
from ovos_utils import classproperty
from ovos_utils.gui import can_use_gui
from ovos_utils.log import LOG
from ovos_utils.process_utils import RuntimeRequirements
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.common_query_skill import CommonQuerySkill, CQSMatchLevel
from padacioso import IntentContainer
from padacioso.bracket_expansion import expand_parentheses
from quebra_frases import sentence_tokenize


class DuckDuckGoSolver(QuestionSolver):
    priority = 75
    enable_tx = True
    kw_matchers: Dict[str, IntentContainer] = {}

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        config["lang"] = "en"  # only supports English
        super().__init__(config)
        self.register_from_file()

    # utils to extract keyword from text
    @classmethod
    def register_kw_extractors(cls, samples: List[str], lang: str) -> None:
        """Register keyword extractors for a given language.

        Args:
            samples: A list of keyword extraction samples.
            lang: Language code.
        """
        lang = lang.split("-")[0]
        if lang not in cls.kw_matchers:
            cls.kw_matchers[lang] = IntentContainer()
        cls.kw_matchers[lang].add_intent("question", samples)

    @classmethod
    def extract_keyword(cls, utterance: str, lang: str) -> Optional[str]:
        """Extract keywords from an utterance in a given language.

        Args:
            utterance: The utterance from which to extract keywords.
            lang: Language code.

        Returns:
            The extracted keyword, or the original utterance if no keyword is found.
        """
        lang = lang.split("-")[0]
        if lang not in cls.kw_matchers:
            return None
        matcher: IntentContainer = cls.kw_matchers[lang]
        match = matcher.calc_intent(utterance)
        kw = match.get("entities", {}).get("keyword")
        if kw:
            LOG.debug(f"DDG Keyword: {kw} - Confidence: {match['conf']}")
        else:
            LOG.debug(f"Could not extract search keyword for '{lang}' from '{utterance}'")
        return kw or utterance

    @classmethod
    def register_infobox_intent(cls, key: str, samples: List[str], lang: str) -> None:
        """Register infobox intents for a given language.

        Args:
            key: The key identifying the intent.
            samples: A list of intent samples.
            lang: Language code.
        """
        lang = lang.split("-")[0]
        if lang not in cls.kw_matchers:
            cls.kw_matchers[lang] = IntentContainer()
        cls.kw_matchers[lang].add_intent(key.split(".intent")[0], samples)

    @classmethod
    def match_infobox_intent(cls, utterance: str, lang: str) -> Tuple[Optional[str], str]:
        """Match infobox intents in an utterance.

        Args:
            utterance: The utterance to match intents from.
            lang: Language code.

        Returns:
            A tuple of the matched intent and the extracted keyword or original utterance.
        """
        lang = lang.split("-")[0]
        if lang not in cls.kw_matchers:
            return None, utterance
        matcher: IntentContainer = cls.kw_matchers[lang]
        match = matcher.calc_intent(utterance)
        kw = match.get("entities", {}).get("keyword")
        intent = None
        if kw:
            intent = match["name"]
            LOG.debug(f"DDG Intent: {intent} Keyword: {kw} - Confidence: {match['conf']}")
        else:
            LOG.debug(f"Could not match intent for '{lang}' from '{utterance}'")
        return intent, kw or utterance

    @classmethod
    def register_from_file(cls) -> None:
        """Register internal Padacioso intents for DuckDuckGo."""
        files = [
            "query.intent",
            "known_for.intent",
            "resting_place.intent",
            "born.intent",
            "died.intent",
            "children.intent",
            "alma_mater.intent",
            "age_at_death.intent",
            "education.intent",
            "fields.intent",
            "thesis.intent",
            "official_website.intent"
        ]
        for lang in os.listdir(f"{os.path.dirname(__file__)}/locale"):
            for fn in files:
                filename = f"{os.path.dirname(__file__)}/locale/{lang}/{fn}"
                if not os.path.isfile(filename):
                    LOG.warning(f"{filename} not found for '{lang}'")
                    continue
                samples = []
                with open(filename) as f:
                    for l in f.read().split("\n"):
                        if not l.strip() or l.startswith("#"):
                            continue
                        if "(" in l:
                            samples += expand_parentheses(l)
                        else:
                            samples.append(l)
                if fn == "query.intent":
                    cls.register_kw_extractors(samples, lang)
                else:
                    cls.register_infobox_intent(fn.split(".intent")[0], samples, lang)

    def get_infobox(self, query: str,
                    lang: Optional[str] = None,
                    units: Optional[str] = None) -> Tuple[Dict[str, Any], List[str]]:
        """Retrieve infobox information and related topics for a query.

        Args:
            query: The search query.
            lang: Language code.
            units: Unit system (e.g., 'metric').

        Returns:
            A tuple of infobox data and related topics.
        """
        time_keys = ["died", "born"]
        data = self.extract_and_search(query, lang=lang, units=units)  # handles translation
        # parse infobox
        related_topics = [t.get("Text") for t in data.get("RelatedTopics", [])]
        infobox = {}
        infodict = data.get("Infobox") or {}
        for entry in infodict.get("content", []):
            k = entry["label"].lower().strip()
            v = entry["value"]
            try:
                if k in time_keys and "time" in v:
                    dt = datetime.datetime.strptime(v["time"], "+%Y-%m-%dT%H:%M:%SZ")
                    infobox[k] = nice_date(dt, lang=self.default_lang)
                else:
                    infobox[k] = v
            except:  # probably a LF error
                continue
        return infobox, related_topics

    def extract_and_search(self, query: str,
                           lang: Optional[str] = None,
                           units: Optional[str] = None) -> Dict[str, Any]:
        """Extract search term from query and perform search.

        Args:
            query: The search query.
            lang: Language code.
            units: Unit system (e.g., 'metric').

        Returns:
            The search result data.
        """
        # match the full query
        data = self.get_data(query, lang, units)
        if data:
            return data

        # extract the best keyword
        kw = self.extract_keyword(query, lang=lang)
        return self.get_data(kw, lang=lang, units=units)

    def get_data(self, query: str,
                 lang: Optional[str] = None,
                 units: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve data from DuckDuckGo API.

        Args:
            query: The search query.
            lang: Language code.
            units: Unit system (e.g., 'metric').

        Returns:
            The search result data.
        """
        units = units or Configuration().get("system_unit", "metric")
        # duck duck go api request
        try:
            data = requests.get("https://api.duckduckgo.com",
                                params={"format": "json",
                                        "q": query}).json()
        except:
            return {}
        return data

    def get_image(self, query: str,
                  lang: Optional[str] = None,
                  units: Optional[str] = None) -> str:
        """Retrieve image URL for a query.

        Args:
            query: The search query.
            lang: Language code.
            units: Unit system (e.g., 'metric').

        Returns:
            The image URL.
        """
        data = self.extract_and_search(query, lang, units)
        image = data.get("Image") or f"{os.path.dirname(__file__)}/logo.png"
        if image.startswith("/"):
            image = "https://duckduckgo.com" + image
        return image

    def get_spoken_answer(self, query: str,
                          lang: Optional[str] = None,
                          units: Optional[str] = None) -> str:
        """Retrieve spoken answer for a query.

        Args:
            query: The search query.
            lang: Language code.
            units: Unit system (e.g., 'metric').

        Returns:
            The spoken answer.
        """
        lang = lang or Configuration().get("lang", "en-us")
        # match an infobox field with some basic regexes
        # (primitive intent parsing)
        intent, query = self.match_infobox_intent(query, lang=lang)

        if intent not in ["question"]:
            infobox = self.get_infobox(query, lang=lang, units=units)[0] or {}
            answer = infobox.get(intent)
            if answer:
                return answer

        # return summary
        data = self.extract_and_search(query, lang=lang, units=units)
        return data.get("AbstractText")

    def get_expanded_answer(self, query: str,
                            lang: Optional[str] = None,
                            units: Optional[str] = None) -> List[Dict[str, str]]:
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
        img = self.get_image(query, lang=lang, units=units)
        lang = lang or Configuration().get("lang", "en-us")
        # match an infobox field with some basic regexes
        # (primitive intent parsing)
        intent, query = self.match_infobox_intent(query, lang)
        if intent not in ["question"]:
            infobox = self.get_infobox(query, lang=lang, units=units)[0] or {}
            answer = infobox.get(intent)
            if answer:
                return [{
                    "title": query,
                    "summary": answer,
                    "img": img
                }]

        data = self.get_data(query, lang=lang, units=units)
        steps = [{
            "title": query,
            "summary": s,
            "img": img
        } for s in sentence_tokenize(data.get("AbstractText", "")) if s]

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
    @intent_handler("search_duck.intent")
    def handle_search(self, message):
        query = message.data["keyword"]

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
            return (phrase, CQSMatchLevel.CATEGORY, summary,
                    {'query': phrase,
                     'answer': summary})

    def CQS_action(self, phrase, data):
        """ If selected show gui """
        sess = SessionManager.get()
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
        results = self.duck.long_answer(query, lang=sess.lang, units=sess.system_unit)
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
    from ovos_utils.fakebus import FakeBus
    from ovos_config.locale import setup_locale

    setup_locale()
    s = DuckDuckGoSkill(bus=FakeBus(), skill_id="fake.duck")
    s.CQS_match_query_phrase("when was Stephen Hawking born")
    exit()
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
    # sentence = d.spoken_answer("Quem é Stephen Hawking",
    #                           context={"lang": "pt"})
    # print(sentence)
    # Sir Isaac Newton foi um matemático inglês, físico, astrônomo, alquimista, teólogo e autor amplamente reconhecido como um dos maiores matemáticos e físicos de todos os tempos e entre os cientistas mais influentes. Ele era uma figura chave na revolução filosófica conhecida como o Iluminismo. Seu livro Philosophiæ Naturalis Principia Mathematica, publicado pela primeira vez em 1687, estabeleceu a mecânica clássica. Newton também fez contribuições seminais para a óptica, e compartilha crédito com o matemático alemão Gottfried Wilhelm Leibniz para desenvolver cálculo infinitesimal. No Principia, Newton formulou as leis do movimento e da gravitação universal que formaram o ponto de vista científico dominante até ser superado pela teoria da relatividade

    info = d.get_infobox("Stephen Hawking")[0]
    from pprint import pprint

    pprint(info)
    # {'age at death': '76 years',
    #  'born': {'after': 0,
    #           'before': 0,
    #           'calendarmodel': 'http://www.wikidata.org/entity/Q1985727',
    #           'precision': 11,
    #           'time': '+1942-01-08T00:00:00Z',
    #           'timezone': 0},
    #  'children': '3, including Lucy',
    #  'died': {'after': 0,
    #           'before': 0,
    #           'calendarmodel': 'http://www.wikidata.org/entity/Q1985727',
    #           'precision': 11,
    #           'time': '+2018-03-14T00:00:00Z',
    #           'timezone': 0},
    #  'education': 'University College, Oxford (BA), Trinity Hall, Cambridge (PhD)',
    #  'facebook profile': 'stephenhawking',
    #  'fields': 'General relativity, quantum gravity',
    #  'imdb id': 'nm0370071',
    #  'instance of': {'entity-type': 'item', 'id': 'Q5', 'numeric-id': 5},
    #  'institutions': 'University of Cambridge, California Institute of Technology, '
    #                  'Perimeter Institute for Theoretical Physics',
    #  'official website': 'https://hawking.org.uk',
    #  'other academic advisors': 'Robert Berman',
    #  'resting place': 'Westminster Abbey',
    #  'rotten tomatoes id': 'celebrity/stephen_hawking',
    #  'thesis': 'Properties of Expanding Universes (1966)',
    #  'wikidata aliases': ['Stephen Hawking',
    #                       'Hawking',
    #                       'Stephen William Hawking',
    #                       'S. W. Hawking',
    #                       'stephen'],
    #  'wikidata description': 'British theoretical physicist, cosmologist and '
    #                          'author (1942–2018)',
    #  'wikidata id': 'Q17714',
    #  'wikidata label': 'Stephen Hawking',
    #  'youtube channel': 'UCPyd4mR0p8zHd8Z0HvHc0fw'}
