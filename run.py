#!/usr/bin/env python3
"""Map the questions — and the transitions — in a corpus.

Two views of the same corpus:

  * the *nodes*: what this corpus asks, by frequency (a bag of questions);
  * the *transitions*: what tends to follow what (the first look at topology).

    python run.py examples/sample_corpus.jsonl
    python run.py examples/sample_corpus.jsonl -n 50
"""

import argparse

from cartographer.corpus import load_jsonl
from cartographer.paths import build_graph


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corpus", help="path to a JSONL corpus file")
    parser.add_argument(
        "-n", type=int, default=20, help="how many rows to show per view (default 20)"
    )
    args = parser.parse_args()

    conversations = load_jsonl(args.corpus)
    graph = build_graph(conversations)

    print(
        f"{graph.path_count} paths · "
        f"{graph.node_count} distinct questions · "
        f"{graph.edge_count} distinct transitions\n"
    )

    print("most-asked questions")
    for question, count in graph.nodes.most_common(args.n):
        print(f"{count:4d}  {question}")

    print("\nmost-travelled transitions (question → next question)")
    for (src, dst), count in graph.most_common_transitions(args.n):
        print(f"{count:4d}  {src} → {dst}")


if __name__ == "__main__":
    main()
