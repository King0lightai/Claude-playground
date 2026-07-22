#!/usr/bin/env python3
"""Map the questions — and the transitions — in a corpus.

Three views of the same corpus:

  * the *nodes*: what this corpus asks, by frequency (a bag of questions);
  * the *transitions*: what tends to follow what (the first look at topology);
  * the *shapes*: did each conversation circle back or move on, and which nodes
    do people keep returning to (loop vs. resolve — only visible once nodes
    merge, so it earns its keep under ``--cluster``).

Pass ``--cluster`` to fold paraphrases of the same question into one node before
counting. Without it every phrasing is its own node and the map stays a scatter
of count-1 roads; with it, questions that share their topical words merge and the
map starts to stack.

    python run.py examples/sample_corpus.jsonl
    python run.py examples/sample_corpus.jsonl --cluster
    python run.py examples/sample_corpus.jsonl --cluster -n 50
"""

import argparse

from cartographer.corpus import load_jsonl
from cartographer.loops import ESCAPED, LOOPING, RESOLVED, shape_graph
from cartographer.paths import build_graph


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corpus", help="path to a JSONL corpus file")
    parser.add_argument(
        "-n", type=int, default=20, help="how many rows to show per view (default 20)"
    )
    parser.add_argument(
        "--cluster",
        action="store_true",
        help="merge paraphrases into one node before counting",
    )
    args = parser.parse_args()

    conversations = load_jsonl(args.corpus)
    graph = build_graph(conversations, cluster=args.cluster)

    header = (
        f"{graph.path_count} paths · "
        f"{graph.node_count} distinct questions · "
        f"{graph.edge_count} distinct transitions"
    )
    if graph.clustering is not None:
        header += f" · {graph.clustering.merged_node_count} merged nodes"
    print(header + "\n")

    print("most-asked questions")
    for question, count in graph.nodes.most_common(args.n):
        print(f"{count:4d}  {question}")
        if graph.clustering is not None:
            variants = [m for m in graph.clustering.members.get(question, []) if m != question]
            for variant in variants:
                print(f"        ↳ also: {variant}")

    print("\nmost-travelled transitions (question → next question)")
    for (src, dst), count in graph.most_common_transitions(args.n):
        print(f"{count:4d}  {src} → {dst}")

    report = shape_graph(graph)
    print("\npath shapes (did the conversation circle back, or move on?)")
    print(
        f"     resolved {report.outcome_counts[RESOLVED]}"
        f" · escaped {report.outcome_counts[ESCAPED]}"
        f" · looping {report.outcome_counts[LOOPING]}"
        f"  ({report.loop_rate:.0%} circled back)"
    )
    if report.loop_lengths:
        print("\n     loop lengths (steps back to the node's previous visit)")
        for length, count in sorted(report.loop_lengths.items()):
            label = " (immediate re-ask)" if length == 1 else ""
            step_word = "step" if length == 1 else "steps"
            print(f"{count:4d}  {length} {step_word}{label}")
        print(f"     {report.immediate_reask_rate:.0%} of circles were immediate re-asks")

    if report.revisited_nodes:
        print("\n     nodes people keep circling back onto")
        for node, count in report.revisited_nodes.most_common(args.n):
            print(f"{count:4d}  {node}")


if __name__ == "__main__":
    main()
