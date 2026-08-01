# <img src='./gui/all/ddg.png' card_color='#de5833' width='50' height='50' style='vertical-align:bottom'/> DuckDuckGo

This OVOS skill answers factual questions with [DuckDuckGo Instant Answers](https://duckduckgo.com/api). It uses [ovos-ddg-plugin](https://github.com/OpenVoiceOS/ovos-ddg-plugin) to query the API and extract facts from the results.

![](./gui/all/logo.png)

## Install

```bash
pip install ovos-skill-ddg
```

## Examples

* "search DuckDuckGo for Stephen Hawking"
* "who is Marie Curie"
* "what is the Eiffel Tower"
* "when was Albert Einstein born"
* "Isaac Newton"

## How it works

The skill takes part in three OVOS pipeline stages.

| Pipeline | Trigger | Priority |
|---|---|---|
| **Padacioso intent** (`search_duck.intent`) | Explicit "search DuckDuckGo for …" phrases | High |
| **Common Query** | Open factual questions routed by the common-query pipeline | none |
| **Fallback** | Any utterance not claimed by another skill | 90 (last resort) |

The skill sends queries to the DuckDuckGo Instant Answers API through [ovos-ddg-plugin](https://github.com/OpenVoiceOS/ovos-ddg-plugin). The plugin handles:

- **Infobox field extraction**: structured facts (birthdate, nationality, occupation, …) matched with locale-aware Padacioso intents
- **Abstract text**: encyclopedic summary sentences
- **Keyword extraction fallback**: when a conversational phrase returns no result, the skill extracts keywords and re-queries (this needs `ovos-rake-keyword-extractor` or a compatible plugin)

The skill detects blacklisted domains (weather, reminders, alarms, timers, music, calls) with per-locale vocabulary files and routes them to the matching skill instead.

## Supported languages

37 locales cover all languages in the DuckDuckGo API locale mapping.

`ar bg ca cs da de el en es et fi fil fr he hr hu id it ja ko lt lv ms nb nl pl pt ro ru sk sl sv th tr uk vi zh`

## Related projects

* [ovos-ddg-plugin](https://github.com/OpenVoiceOS/ovos-ddg-plugin): the query and answer-extraction backend this skill uses

## Category
**Information**

## Tags
#duckduckgo
#query
#search-engine
#searchengine

## License

Apache-2.0
