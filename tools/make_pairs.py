"""Turn Cyrillic text into (context, Latin, Cyrillic) training rows.

Each Cyrillic word is spelled in Latin the way people type in chat, with
the habits seen in real messages (tests/real_chat.tsv):

    ө/ү typed o/u, sometimes u for ө     хөрвүүлэх -> hurvuuleh
    я/ю/ы/е often just y                 явдаг -> yvdag, ер -> yr
    vowels dropped in common words       байж -> bj, гэвэл -> gvl
    question and other particles glued   хурдан уу -> hurdanuu
    known chat abbreviations             байна -> bn

Usage:
    python3 -I tools/make_pairs.py OUTPUT.tsv CORPUS [CORPUS...] [--limit N]

CORPUS is a Wikipedia CirrusSearch dump (*.json.bz2) or a Leipzig
*-sentences.txt file. Output rows: context<TAB>latin<TAB>cyrillic, where
context is the previous (up to) two Cyrillic words.
"""

import bz2
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

CONTEXT_WORDS = 2

# Only the most common words get shortened; nobody types blmjtoi for a
# word they use once a year.
COMMON_WORDS = 2000
DROP_COMMON = 0.35
DROP_RARE = 0.03

GLUE = 0.5
ABBREVIATE = 0.5

# Words that people glue onto the word before them.
PARTICLES = {"уу", "үү", "юу", "юм", "даа", "дээ", "доо", "л", "бэ", "вэ", "шүү", "биз", "ш"}

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
CYRILLIC_WORD = re.compile(r"[а-яёөү]+")

# Each Cyrillic letter: list of (Latin spelling, weight).
SPELLINGS = {
    "а": [("a", 1)], "б": [("b", 1)], "в": [("v", 1)], "г": [("g", 1)],
    "д": [("d", 1)], "ж": [("j", 1)], "з": [("z", 1)], "и": [("i", 1)],
    "й": [("i", 1)], "к": [("k", 1)], "л": [("l", 1)], "м": [("m", 1)],
    "н": [("n", 1)], "о": [("o", 1)], "п": [("p", 1)], "р": [("r", 1)],
    "с": [("s", 1)], "т": [("t", 1)], "у": [("u", 1)], "ф": [("f", 1)],
    "х": [("h", 1)], "ц": [("ts", 1)], "ч": [("ch", 1)], "ш": [("sh", 1)],
    "щ": [("sh", 1)], "ъ": [("", 1)], "ь": [("", 1)], "э": [("e", 1)],
    "ө": [("o", 3), ("u", 1)],
    "ү": [("u", 1)],
    "ы": [("y", 3), ("ii", 3), ("i", 2)],  # утгыг -> utgiig
    "ё": [("yo", 8), ("y", 1), ("o", 1)],
    "ю": [("yu", 6), ("u", 3), ("y", 1)],
    "я": [("ya", 6), ("y", 3), ("a", 1)],
}

LATIN_VOWELS = set("aeiouy")


def pick(choices):
    spellings, weights = zip(*choices)
    return random.choices(spellings, weights)[0]


def load_abbreviations():
    """cyrillic -> [latin, ...] from data/abbreviations.tsv (latin<TAB>cyrillic)."""
    table = {}
    for line in (DATA / "abbreviations.tsv").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            latin, cyrillic = line.split("\t")
            table.setdefault(cyrillic, []).append(latin)
    return table


def shorten(word):
    """Chat shortcuts inside a Cyrillic word, before spelling it."""
    if word.endswith("гүй") and random.random() < 0.5:
        word = word[:-1]                      # ойлгохгүй -> oilgohgu
    if "чих" in word and random.random() < 0.5:
        word = word.replace("чих", "ч")       # болчихлоо -> bolchloo
    if random.random() < 0.3:
        word = re.sub(r"([бвгджзклмнпрстфхцчш])\1", r"\1", word)  # кирилл -> kiril
    return word


def spell(word):
    """Spell one Cyrillic word in Latin, picking a random common variant."""
    word = shorten(word)
    out = []
    for i, ch in enumerate(word):
        if ch == "ь" and word[i + 1:i + 2] == "е":
            # үзье -> uzye or uzey; the е is skipped on the next step.
            out.append(pick([("ye", 1), ("ey", 1)]))
        elif ch == "е" and i > 0 and word[i - 1] == "ь":
            continue
        elif ch == "е":
            # After a consonant е sounds like э; elsewhere like йэ.
            after_consonant = i > 0 and word[i - 1] not in "аэиоөуүыеёюя"
            out.append("e" if after_consonant else pick([("ye", 7), ("e", 2), ("y", 1)]))
        elif ch == "й" and i > 0 and word[i - 1] == "и":
            # ий: ii or just i
            out.append(pick([("i", 2), ("", 1)]))
        else:
            out.append(pick(SPELLINGS.get(ch, [(ch, 1)])))
    latin = "".join(out)
    if random.random() < 0.15:
        # Long vowels typed once: ойлголоо -> oilgolo
        latin = re.sub(r"([aeiou])\1", r"\1", latin)
    return latin


def drop_vowels(latin):
    """байгаагаас -> bgagaas: drop or shorten vowel groups before the last one.

    The first letter always stays, and the last vowel group is sometimes
    dropped too (байна -> bn, сайн -> sn).
    """
    parts = re.split(r"([aeiouy]+)", latin[1:])
    vowel_groups = [i for i, p in enumerate(parts) if p and p[0] in LATIN_VOWELS]
    for n, i in enumerate(vowel_groups):
        last = n == len(vowel_groups) - 1
        if last:
            if random.random() < 0.3:
                parts[i] = ""
        elif random.random() < 0.8:
            parts[i] = ""
        else:
            parts[i] = parts[i][0]
    return latin[0] + "".join(parts)


def type_word(word, common, abbreviations):
    """How a person might type one Cyrillic word (or glued words) in Latin."""
    if word in abbreviations and random.random() < ABBREVIATE:
        return random.choice(abbreviations[word])
    latin = spell(word.replace(" ", ""))
    # Two-letter words (ой, ус) shortened to one letter would mean anything.
    if len(word) >= 3 and random.random() < (DROP_COMMON if word in common else DROP_RARE):
        latin = drop_vowels(latin)
    return latin


def tokens(words):
    """Group words into what gets typed as one Latin token.

    хурдан уу -> one token "хурдан уу" about half the time.
    """
    out = []
    for word in words:
        if out and word in PARTICLES and random.random() < GLUE:
            out[-1] += " " + word
        else:
            out.append(word)
    return out


def wikipedia_texts(path):
    with bz2.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            doc = json.loads(line)
            # Every document line is preceded by an {"index": ...} line.
            if "text" in doc:
                yield from SENTENCE_END.split(doc["text"])


def leipzig_texts(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            yield line.partition("\t")[2]


def sentences(paths, limit):
    count = 0
    for path in paths:
        texts = wikipedia_texts(path) if path.endswith(".json.bz2") else leipzig_texts(path)
        for text in texts:
            words = CYRILLIC_WORD.findall(text.lower())
            # Skip lists, tables and mostly-Latin lines.
            if len(words) < 3 or len(words) < 0.7 * len(text.split()):
                continue
            yield words
            count += 1
            if count >= limit:
                return


def main(args):
    limit = float("inf")
    if "--limit" in args:
        at = args.index("--limit")
        limit = int(args[at + 1])
        del args[at:at + 2]
    output, corpora = args[0], args[1:]

    random.seed(1)
    corpus = list(sentences(corpora, limit))
    counts = Counter(w for words in corpus for w in words)
    common = {w for w, _ in counts.most_common(COMMON_WORDS)}
    abbreviations = load_abbreviations()

    rows = 0
    with open(output, "w", encoding="utf-8") as f:
        for words in corpus:
            context = []
            for token in tokens(words):
                latin = type_word(token, common, abbreviations)
                f.write(f"{' '.join(context)}\t{latin}\t{token}\n")
                context = (context + token.split())[-CONTEXT_WORDS:]
                rows += 1
    print(f"{len(corpus)} sentences, {rows} rows -> {output}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
