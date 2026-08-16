"""Glossing: German and English glosses for lexicon lemmas.

Three sources, in priority order (SPEC §9, §13.1):

1. English Wiktionary via kaikki.org — English glosses, region labels.
2. German Wiktionary via kaikki.org — German glosses, but only ~6,600 Spanish
   entries exist, and most of those are definitional sentences rather than the
   one-to-three words a flashcard can carry.
3. Claude, batched — everything still missing a German gloss.

Nothing in this package talks to the reader. It fills `de`, `en`, `mexicanism`
and `regionNote` in the lexicon, and the bundle writer serializes them.
"""
