# <img src='./gui/all/ddg.png' card_color='#de5833' width='50' height='50' style='vertical-align:bottom'/> DuckDuckGo

Answer factual questions using [DuckDuckGo Instant Answers](https://duckduckgo.com/api).

Powered by [ovos-ddg-plugin](https://github.com/OpenVoiceOS/ovos-ddg-plugin).

![](./gui/all/logo.png)

## Examples

* "search DuckDuckGo for Stephen Hawking"
* "who is Marie Curie"
* "what is the Eiffel Tower"
* "when was Albert Einstein born"
* "Isaac Newton"

## How it works

The skill participates in three OVOS pipeline stages:

| Pipeline | Trigger | Priority |
|---|---|---|
| **Padacioso intent** (`search_duck.intent`) | Explicit "search DuckDuckGo for …" phrases | High |
| **Common Query** | Open factual questions routed by the common-query pipeline | — |
| **Fallback** | Any utterance not claimed by another skill | 90 (last resort) |

Queries are forwarded to the DuckDuckGo Instant Answers API via [ovos-ddg-plugin](https://github.com/OpenVoiceOS/ovos-ddg-plugin), which handles:

- **Infobox field extraction** — structured facts (birthdate, nationality, occupation, …) matched via locale-aware Padacioso intents
- **Abstract text** — encyclopaedic summary sentences
- **Keyword extraction fallback** — when a conversational phrase returns no result, keywords are extracted and re-queried (requires `ovos-rake-keyword-extractor` or compatible plugin)

Blacklisted domains (weather, reminders, alarms, timers, music, calls) are detected via per-locale vocabulary files and routed to the appropriate skill instead.

## Supported languages

37 locales covering all languages in the DuckDuckGo API locale mapping:
ar, bg, ca, cs, da, de, el, en, es, et, fi, fil, fr, he, hr, hu, id, it, ja, ko, lt, lv, ms, nb, nl, pl, pt, ro, ru, sk, sl, sv, th, tr, uk, vi, zh.

## Category
**Information**

## Tags
#duckduckgo
#query
#search-engine
#searchengine
