# <img src='./gui/all/ddg.png' card_color='#de5833' width='50' height='50' style='vertical-align:bottom'/> DuckDuckGo
Use DuckDuckGo to answer questions

![](./gui/all/logo.png)


## About

Uses the [DuckDuckGo API](https://duckduckgo.com/api) to provide information. 

## Examples

* "when was stephen hawking born"
* "ask the duck about the big bang"
* "tell me more"
* "who is elon musk"
* "continue"
* "tell me more"

### Adding more `infobox` intents

internal `.intent` files can be added to allow parsing infoboxes returned by duckduckgo

first print the target infobox to inspect the returned results
```python
from skill_ovos_ddg import DuckDuckGoSolver
d = DuckDuckGoSolver()
info = d.get_infobox("Stephen Hawking")[0]
print(info)
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
```
under `DuckDuckGoSolver.register_from_file` add your new `xxx.intent` file, where `xxx` needs to be a key present in the infobox, underscores are replaced with whitespaces

then that infobox value will be mapped to that intent file


## Category
**Information**

## Tags
#duckduckgo
#query
#search-engine
#searchengine
