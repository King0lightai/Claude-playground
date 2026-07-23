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
    python run.py examples/socratic_dialogues.jsonl --cluster   # the first real corpus

The Socratic corpus (Plato's *Meno* and *Euthyphro*, public domain) is the first
time the instrument is pointed at real text — see cartographer/ingest/gutenberg.py
and JOURNAL.md. Run it with ``--cluster`` and the map both lights up (nodes and
loops finally stack) and shows its ceiling (the clusterer over-merges rhetorical
questions). Both readings are honest; the second is the next session's work.
"""

import argparse

from cartographer.corpus import load_jsonl
from cartographer.grade import association_strength, grade
from cartographer.loops import ESCAPED, LOOPING, RESOLVED, shape_graph
from cartographer.paths import build_graph
from cartographer.readings import compare_readings


def print_grade(conversations: list, label_key: str) -> None:
    """Print the shape-vs-ground-truth grade for a labeled corpus.

    Turns session 010's hand-computed crosstab into a first-class output: the 2×2
    of the instrument's loop/resolve shape against the corpus's own answer key
    (for CMV, the ``delta`` label), plus the phi correlation and the raw counts
    that phi is standing on — so a small number reads as "starved of events," not
    "clean null." Clustering is always on here: shape only exists once nodes merge.
    """
    report = grade(conversations, label_key=label_key)
    if not report.n:
        print(
            f"no gradable paths: no conversation carries a boolean '{label_key}' "
            "label (this corpus has no external ground truth to grade against)."
        )
        return

    print(
        f"grading {report.n} labeled paths against ground truth '{label_key}' "
        f"({report.label_total(True)} true · {report.label_total(False)} false)\n"
    )
    print(f"does the instrument's shape predict '{label_key}'?")
    print("                       circled back    resolved (line)")
    for label, name in ((True, f"{label_key}=true "), (False, f"{label_key}=false")):
        print(
            f"  {name}          {report.count(True, label):4d}            "
            f"{report.count(False, label):4d}"
            f"     (circled {report.circled_rate(label):.0%})"
        )
    phi = report.phi
    print(
        f"\n  phi correlation: {phi:+.3f} "
        f"({association_strength(phi)} association)"
    )
    circled_total = report.count(True, True) + report.count(True, False)
    print(
        f"  {circled_total} of {report.n} paths circled at all "
        f"({report.can_loop_count} were long enough to) — "
        "the shape signal barely fires on these short paths, so read phi as weak "
        "evidence, not a verdict."
    )
    print("\n  outcome shape by label (resolved / looping / escaped)")
    for label, name in ((True, f"{label_key}=true "), (False, f"{label_key}=false")):
        counts = report.outcome_counts(label)
        print(
            f"    {name}  {counts[RESOLVED]:4d} / {counts[LOOPING]:4d} / "
            f"{counts[ESCAPED]:4d}"
        )


def print_compare(conversations: list, label_key: str) -> None:
    """Put rival readings on one bench and print them, strongest correlation first.

    The single-reading grade can only ask "does the loop/resolve shape predict
    the label?" — and on CMV the honest answer is "barely." This view adds a
    second, persuasion-shaped reading (does the OP get the last word?) so the two
    can be compared. The point is the *juxtaposition*: the speaker reading scores
    a near-perfect correlation, but its caveat says why that is a leak, not a
    discovery — a flawless number here is a red flag. See cartographer/readings.py.
    """
    grades = compare_readings(conversations, label_key=label_key)
    if not grades or not grades[0].n:
        print(
            f"no gradable paths: no conversation carries a boolean '{label_key}' "
            "label (this corpus has no external ground truth to grade against)."
        )
        return

    print(
        f"comparing {len(grades)} readings on {grades[0].n} labeled paths "
        f"against ground truth '{label_key}'\n"
    )
    for grade_result in grades:
        phi = grade_result.phi
        print(f"  {grade_result.name}  (phi {phi:+.3f}, {association_strength(phi)})")
        print(f"      asks: {grade_result.question}")
        print(
            f"      fired on {grade_result.positive_rate(True):.0%} of "
            f"{label_key}=true · {grade_result.positive_rate(False):.0%} of "
            f"{label_key}=false"
        )
        if grade_result.caveat:
            print(f"      caveat: {grade_result.caveat}")
        print()
    print(
        "  read the winner's caveat before its number: on this corpus the "
        "strongest reading is the leakiest one."
    )


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
    parser.add_argument(
        "--grade",
        nargs="?",
        const="delta",
        default=None,
        metavar="LABEL_KEY",
        help="grade the instrument's loop/resolve shape against a ground-truth "
        "label on each conversation (default label key: 'delta', the CMV corpus). "
        "Shows the shape-vs-label crosstab and its correlation instead of the map.",
    )
    parser.add_argument(
        "--compare",
        nargs="?",
        const="delta",
        default=None,
        metavar="LABEL_KEY",
        help="put rival readings on one bench and compare their correlation with "
        "a ground-truth label (default 'delta'). Unlike --grade (one reading), "
        "this scores several — and shows why the strongest one may be a leak.",
    )
    args = parser.parse_args()

    conversations = load_jsonl(args.corpus)

    if args.compare is not None:
        print_compare(conversations, args.compare)
        return

    if args.grade is not None:
        print_grade(conversations, args.grade)
        return

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
