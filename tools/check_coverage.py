"""How many real typed words does the training data teach correctly?

Usage:
    python3 -I tools/check_coverage.py data/synthetic.tsv tests/real_chat.tsv [more.tsv...]

For every word of the real files (latin<TAB>cyrillic sentences with the
same number of words), look for that exact latin -> cyrillic row in the
training data. Missing words point at typing habits make_pairs.py lacks.
"""

import sys
from collections import defaultdict


def word_pairs(path):
    for line in open(path, encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        latin, cyrillic = line.rstrip("\n").split("\t")
        latin, cyrillic = latin.split(), cyrillic.split()
        # Glued words (bolu -> болов уу) can't be paired word by word.
        if len(latin) == len(cyrillic):
            yield from zip(latin, cyrillic)


def main(training, real_files):
    wanted = {pair for path in real_files for pair in word_pairs(path)}
    latin_words = {latin for latin, _ in wanted}

    answers = defaultdict(set)
    with open(training, encoding="utf-8") as f:
        for line in f:
            _, latin, cyrillic = line.rstrip("\n").split("\t")
            if latin in latin_words:
                answers[latin].add(cyrillic)

    found = [p for p in wanted if p[1] in answers[p[0]]]
    other = [p for p in wanted if p not in found and answers[p[0]]]
    unseen = [p for p in wanted if not answers[p[0]]]
    print(f"taught correctly: {len(found)}/{len(wanted)}")
    print(f"latin seen, other answers only ({len(other)}):")
    for latin, cyrillic in sorted(other):
        print(f"  {latin} -> {cyrillic}, data has {sorted(answers[latin])[:3]}")
    print(f"latin never seen ({len(unseen)}):")
    print("  " + ", ".join(f"{l}->{c}" for l, c in sorted(unseen)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
