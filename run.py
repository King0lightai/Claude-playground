#!/usr/bin/env python3
"""Map the questions in a corpus.

The first pixel of the weather map: point it at a corpus and see what that
corpus is asking, by frequency.

    python run.py examples/sample_corpus.jsonl
    python run.py examples/sample_corpus.jsonl -n 50
"""

import argparse
import collections

from cartographer.corpus import conversation_texts, load_jsonl
from cartographer.extract import extract_questions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corpus", help="path to a JSONL corpus file")
    parser.add_argument(
        "-n", type=int, default=20, help="how many top questions to show (default 20)"
    )
    args = parser.parse_args()

    counter: "collections.Counter[str]" = collections.Counter()
    total = 0
    conversations = load_jsonl(args.corpus)
    for conversation in conversations:
        for text in conversation_texts(conversation):
            for question in extract_questions(text):
                counter[question] += 1
                total += 1

    print(
        f"{len(conversations)} conversations · "
        f"{total} questions extracted · "
        f"{len(counter)} distinct\n"
    )
    for question, count in counter.most_common(args.n):
        print(f"{count:4d}  {question}")


if __name__ == "__main__":
    main()
