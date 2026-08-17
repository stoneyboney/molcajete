"""The glossing prompt, and the JSON shape the model must answer in.

`PROMPT_VERSION` is stored on every cached row. When the instructions change in
a way that would change a gloss, bump it — that is how a later build can tell
which rows are stale without re-running the whole book.

The instruction block is deliberately long. It is sent identically on every
request and cached, and **Sonnet 5 will not cache a prefix under 1024 tokens** —
it fails silently, reporting `cache_creation_input_tokens: 0` with no error. The
worked examples earn their place twice over: they set the register of a gloss
far better than prose rules do, and they carry the block over the threshold.
"""

from __future__ import annotations

from molcajete_prep.glossing.models import MAX_UNITS, MAX_WORDS_PER_UNIT

PROMPT_VERSION = 1

# Answering with a fixed schema rather than free text is what lets 25 lemmas
# ride in one request without their answers drifting out of alignment. Every
# object echoes the lemma and tag it answers for, so results are matched by
# identity and never by position.
#
# JSON Schema cannot express "one to three words" — no `maxLength`, no array
# length bounds are supported — so that rule lives in the prose below and is
# re-checked in Python afterwards.
GLOSS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "glosses": {
            "type": "array",
            "description": "One object per lemma given, in any order.",
            "items": {
                "type": "object",
                "properties": {
                    "lemma": {
                        "type": "string",
                        "description": "Echo the lemma exactly as given.",
                    },
                    "pos": {
                        "type": "string",
                        "description": "Echo the part-of-speech tag exactly as given.",
                    },
                    "de": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "German gloss, one to three words. Null if none is possible.",
                    },
                    "en": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "English gloss, one to three words. Null if none is possible.",
                    },
                    "mexicanism": {
                        "type": "boolean",
                        "description": "True if this word or sense is Mexican or Latin-American where Spain differs.",
                    },
                    "region_note": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "German region and register note, e.g. 'Mexiko, umgangssprachlich'. Null if neutral.",
                    },
                    "not_spanish": {
                        "type": "boolean",
                        "description": "True if the string is not a real Spanish word.",
                    },
                    "corrected_lemma": {
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                        "description": "The real lemma this is a mangling of, or null.",
                    },
                },
                "required": [
                    "lemma",
                    "pos",
                    "de",
                    "en",
                    "mexicanism",
                    "region_note",
                    "not_spanish",
                    "corrected_lemma",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["glosses"],
    "additionalProperties": False,
}


SYSTEM_PROMPT = """\
You write vocabulary glosses for a Spanish reading app. The reader is a German \
speaker learning Mexican Spanish by reading novels. Each gloss you write becomes \
the back of a flashcard and a tap-to-reveal hint in the reader, so it is read in \
a second, from a phone, mid-sentence.

You will be given a batch of lemmas. Each carries its part-of-speech tag, and \
usually a sentence from the book where it appears. Answer with one object per \
lemma, echoing the lemma and tag you were given.

## What a gloss is

A gloss is a translation, not a definition. One to three words. If several \
translations are natural, give at most three, separated by commas, best first.

Write what a bilingual dictionary would put in bold, not what an encyclopedia \
would put in a paragraph. "lunes" is "Montag" — not "der erste Wochentag". \
"madriguera" is "Bau, Höhle" — not "unterirdischer Unterschlupf eines Tieres". \
If you find yourself writing a relative clause, you are defining rather than \
translating; delete it and name the thing.

German is the primary gloss and English the secondary one. Write both. English \
earns its place as a disambiguator when the German is broad, so do not simply \
translate your own German — gloss the Spanish independently in each language.

For German nouns, include the definite article: "der Bau", "die Höhle", \
"das Pferd". The article carries the gender, which the learner needs and which \
the Spanish word does not supply. For German verbs, use the infinitive. Do not \
prefix English verbs with "to".

## Choosing the sense

Gloss the lemma in the sense the book actually uses. The example sentence is \
there to settle exactly this, and it outranks whatever sense is most common in \
general Spanish.

"banco" beside a sentence about a river is "das Ufer", not "die Bank". \
"pluma" beside a sentence about a bird is "die Feder" in the plumage sense. \
When no sentence is given, gloss the most frequent everyday sense.

Ignore senses that are grammatical rather than lexical. If a lemma looks like an \
inflected form, gloss the meaning of the word, never "third-person singular of …".

## Mexican usage

Set "mexicanism" to true when the word, or the sense the book uses, is Mexican \
or Latin-American in a way that differs from peninsular Spanish. This is the \
signal the app exists to surface, so judge the sense in front of you rather than \
the word in the abstract.

True: "chido", "popote", "padre" meaning great, "carro" meaning car, "platicar", \
"ahorita", "güey", "chamaco", "escuincle".
False: words that are simply common in Mexico but identical in Spain. A word is \
not a mexicanism merely because it appears in a Mexican novel, and marking one \
that way puts a card in front of the learner that teaches nothing.

Fill "region_note" **in German** whenever there is a region or a register worth \
knowing, whether or not "mexicanism" is true. Use terms like "Mexiko", \
"Lateinamerika", "umgangssprachlich", "vulgär", "abwertend", "veraltet", \
"ländlich", "scherzhaft". Combine at most three, region first: \
"Mexiko, umgangssprachlich". Leave it null for neutral standard vocabulary.

## Words that are not words

These lemmas come from an automatic lemmatizer that invents things. When a \
string is not a real Spanish word, set "not_spanish" to true and both glosses to \
null. Do not guess a plausible meaning from the word's shape — a fabricated \
gloss is worse than a missing one, because nothing downstream can tell them apart.

When the string is a recognisable mangling of a real lemma, put that real lemma \
in "corrected_lemma" as well. Reflexive verbs are the common case: the \
lemmatizer emits "abalanzar él" for "se abalanzó". Set "not_spanish" to true, \
"corrected_lemma" to "abalanzarse", and still leave the glosses null — the \
correction is a diagnostic, not a substitute.

If a lemma is a real but obscure or archaic Spanish word, it is not "not_spanish". \
Gloss it normally.

## Worked examples

Input:  madriguera · NOUN · "Mi papá dice que somos gente de la madriguera."
Output: de "der Bau, die Höhle" · en "burrow, den" · mexicanism false · region_note null

Input:  chido · ADJ · "Está bien chido tu carro."
Output: de "cool, super" · en "cool, great" · mexicanism true · region_note "Mexiko, umgangssprachlich"

Input:  banco · NOUN · "Se sentó en el banco del río a mirar el agua."
Output: de "das Ufer" · en "bank, riverbank" · mexicanism false · region_note null

Input:  lunes · NOUN · "El lunes salimos temprano."
Output: de "der Montag" · en "Monday" · mexicanism false · region_note null

Input:  acaeceír · VERB · "Lo que acaeció aquella noche nadie lo supo."
Output: de null · en null · not_spanish true · corrected_lemma "acaecer"

Input:  abalanzar él · VERB · "Se abalanzó sobre el fusil."
Output: de null · en null · not_spanish true · corrected_lemma "abalanzarse"

Input:  fusil · NOUN · "Limpiaba su fusil a la luz de la lumbre."
Output: de "das Gewehr" · en "rifle" · mexicanism false · region_note null

Return an object for every lemma you were given, and no others.\
"""


def render_batch(items: list[dict]) -> str:
    """The user turn: the lemmas of one request, one per line.

    Kept terse and positional-free. Everything that explains how to read this
    block lives in the cached system prompt, so the per-request tokens stay
    close to the information itself.
    """
    lines = []
    for item in items:
        parts = [f"{item['lemma']} · {item['pos']}"]
        if item.get("example_es"):
            parts.append(f'example: "{item["example_es"]}"')
        if item.get("wiktionary_en"):
            parts.append(f"en.wiktionary: {item['wiktionary_en']}")
        if item.get("wiktionary_de"):
            parts.append(f"de.wiktionary: {item['wiktionary_de']}")
        if item.get("region_hint"):
            parts.append(f"labels: {item['region_hint']}")
        lines.append(" · ".join(parts))

    return "Gloss these lemmas:\n\n" + "\n".join(lines)


# The word limit, restated for a model that has just broken it. The system
# prompt says it once in prose among a page of other rules; a model that ignored
# it there needs it alone, next to its own bad answer, with nothing else to
# attend to.
_RULES_AGAIN = f"""\
Rules, again, and nothing else matters here:
- A gloss is at most {MAX_UNITS} alternatives separated by commas.
- Each alternative is at most {MAX_WORDS_PER_UNIT} words.
- Translate the word. Do not define it. No relative clauses, no "a kind of".
- Echo the lemma and the tag exactly as they were given.
- Answer for every lemma listed, and for no others.\
"""


def render_correction(
    items: list[dict],
    *,
    offending: str,
    reason: str,
) -> str:
    """The retry turn: the same question, with the failure named.

    Written for a local model, which follows a long system prompt less reliably
    than Claude does. Three things in order — what was wrong, the rule it broke,
    and the original question again — because a correction that omits the
    question invites the model to answer the complaint instead.

    The offending text is quoted back deliberately. Naming the rule alone
    produces the same answer again; showing the model its own output is what
    makes the second attempt different from the first.
    """
    quoted = offending.strip()
    if len(quoted) > 400:
        quoted = quoted[:400] + " …"

    return (
        "Your previous answer was rejected.\n\n"
        f"Problem: {reason}.\n"
        f"You wrote: {quoted}\n\n"
        f"{_RULES_AGAIN}\n\n"
        f"{render_batch(items)}"
    )
