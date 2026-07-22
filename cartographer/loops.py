"""Loop vs. resolve — reading the *shape* of a single path.

This is the layer the journal has pointed at since session 001, and clustering
(session 003) is what finally makes it reachable: only once paraphrases fold
into one node can a conversation *return* to a node it already visited. Before
merging, every node in a path was distinct by construction, so nothing could
ever loop. After merging, the MONAD→MONAD self-edge appeared on the sample
corpus on its own — a person re-asking the same question because the first
answer didn't land. That revisit is the atom this module reads.

A path is a sequence of nodes. Its *shape* is the answer to one question: did it
move forward through new ground and stop, or did it circle back?

  * **resolved** — every node is distinct. The path walked a line of new
    questions and ended somewhere it had never been. Forward motion, then a stop.
  * **looping** — the path *ends* on a node it had already visited. It came back
    to old ground and stayed there: still circling when the transcript ran out.
  * **escaped** — the path revisited a node partway through but then broke out and
    ended somewhere fresh. It circled, then found new ground and stopped.

"resolved" and "escaped" both end on new ground; the difference is whether they
struggled to get there. "looping" is the one that ends unresolved. All three are
honest, mechanical reads of revisits — no judgment about whether the *answer*
was good, only about whether the *path* came back on itself. That's the ceiling,
and it's the right one for a topology instrument: shape, not content.

Beyond *whether* a path circled, this module also reads *how big* each circle
was — its **loop length**: the number of steps back from a revisit to that
node's previous occurrence. A length of 1 is an *immediate re-ask* (the same
node two turns running — "explain what a monad is" → "what is a monad, really");
a larger length is a *return* after intervening ground (wandered off, then came
back). A revisit is a revisit either way, but a tight self-circle and a wide
return after a long detour are different animals, and the length is what tells
them apart. Measured against the node's *previous* occurrence, not its first, so
the number is the size of the circle just closed rather than a distance to the
origin that only grows.

What this is naive about (write it down so the next me doesn't mistake it for
truth): a revisit is only visible when two turns land on the *same node*, which
means it inherits every blind spot of the clusterer. Two turns that a human
reads as "the same question, re-asked" but that the lexical clusterer keeps
apart will read here as *resolved* when they truly *looped*. The shape is only
as good as the merge beneath it. See ``cluster.py`` and JOURNAL.md.
"""

import collections
from dataclasses import dataclass

RESOLVED = "resolved"
LOOPING = "looping"
ESCAPED = "escaped"


@dataclass(frozen=True)
class PathShape:
    """The shape of one path: where it circled, and how it ended.

    ``path`` is the (already node-labelled) sequence of questions. ``revisits``
    lists every step that returned to earlier ground, as ``(index, node)`` pairs
    where ``path[index]`` had already appeared in ``path[:index]`` — the moments
    the conversation came back on itself, in order.
    """

    path: tuple
    revisits: tuple

    @property
    def looped(self) -> bool:
        """Did the path ever return to a node it had already visited?"""
        return bool(self.revisits)

    @property
    def outcome(self) -> str:
        """One of ``RESOLVED`` / ``LOOPING`` / ``ESCAPED`` — how the path ended.

        Ended on new ground with no revisits at all → resolved. Ended on a node
        it had seen before → looping (still circling at the last turn). Revisited
        earlier but ended on fresh ground → escaped (circled, then broke out).
        """
        if not self.revisits:
            return RESOLVED
        # The path ends looping iff its final node is itself a revisit — i.e. the
        # last thing the person did was land back on old ground.
        if self.revisits[-1][0] == len(self.path) - 1:
            return LOOPING
        return ESCAPED

    @property
    def revisited_nodes(self) -> tuple:
        """The distinct nodes this path returned to, in order of first revisit."""
        seen, out = set(), []
        for _, node in self.revisits:
            if node not in seen:
                seen.add(node)
                out.append(node)
        return tuple(out)

    @property
    def loop_lengths(self) -> tuple:
        """The size of each circle this path closed, in order — one per revisit.

        For every step that lands on a node already seen, the length is how many
        steps back that node's *previous* occurrence was: ``1`` for an immediate
        re-ask (the same node two turns running), larger for a return after
        intervening ground. Measured against the previous occurrence, not the
        first, so a node touched three times reports the size of each fresh
        circle rather than an ever-growing distance to where it started.

        Aligns one-to-one with :attr:`revisits`: same steps, same order.
        """
        last_seen: dict = {}
        lengths = []
        for i, node in enumerate(self.path):
            if node in last_seen:
                lengths.append(i - last_seen[node])
            last_seen[node] = i
        return tuple(lengths)

    @property
    def widest_loop(self) -> int:
        """The largest circle this path closed (``0`` if it never circled).

        The path's single most telling loop number: a small value means it only
        ever re-asked or made tight circles; a large one means it wandered far
        before finding its way back.
        """
        lengths = self.loop_lengths
        return max(lengths) if lengths else 0


def classify_path(path: list) -> PathShape:
    """Read the shape of a single path.

    Walks the path once, marking each step that lands on a node already seen.
    A path of zero or one node has no revisits and resolves trivially (there was
    never anywhere to circle back to).
    """
    seen: set = set()
    revisits = []
    for i, node in enumerate(path):
        if node in seen:
            revisits.append((i, node))
        seen.add(node)
    return PathShape(path=tuple(path), revisits=tuple(revisits))


@dataclass
class ShapeReport:
    """The shapes of every path in a graph, plus the aggregate reads.

    ``shapes`` is one :class:`PathShape` per path, in graph order.
    ``outcome_counts`` tallies how many paths resolved, looped, or escaped.
    ``revisited_nodes`` counts, across all paths, how often each node was
    *returned to* — the corpus's stickiest questions, the ones people keep
    circling back onto. That last one is the first genuinely map-level reading of
    the vision: not "what gets asked" but "what won't let go."
    ``loop_lengths`` tallies, across *every* revisit in the corpus, how big the
    circle was — the distribution that separates a corpus of tight re-asks (mass
    at length 1) from one of wide, wandering returns (a long tail).
    """

    shapes: list
    outcome_counts: "collections.Counter"
    revisited_nodes: "collections.Counter"
    loop_lengths: "collections.Counter"

    @property
    def loop_rate(self) -> float:
        """Fraction of paths that circled back at least once, in ``[0.0, 1.0]``.

        Counts both *looping* and *escaped* — any path with a revisit. Returns
        ``0.0`` for an empty report rather than dividing by zero.
        """
        total = len(self.shapes)
        if not total:
            return 0.0
        return (total - self.outcome_counts[RESOLVED]) / total

    @property
    def immediate_reask_rate(self) -> float:
        """Fraction of all revisits that were immediate re-asks (length 1).

        A threshold-free split of the corpus's circles into tight self-loops
        (the same node two turns running) versus returns after intervening
        ground. ``0.0`` when nothing circled — no revisits to divide by.
        """
        total = sum(self.loop_lengths.values())
        if not total:
            return 0.0
        return self.loop_lengths[1] / total


def shape_graph(graph) -> ShapeReport:
    """Classify every path in a :class:`~cartographer.paths.PathGraph`.

    Reads ``graph.paths`` (the node-labelled sequences the graph already keeps),
    so this reflects whatever merging built the graph: run it on a clustered
    graph and the revisits are real returns to a shared node; run it on an
    unclustered graph and almost nothing will loop, because unmerged paraphrases
    can't collide. The map only shows circles once the nodes beneath it merge.
    """
    shapes = [classify_path(path) for path in graph.paths]
    outcome_counts: "collections.Counter" = collections.Counter(
        shape.outcome for shape in shapes
    )
    revisited_nodes: "collections.Counter" = collections.Counter()
    loop_lengths: "collections.Counter" = collections.Counter()
    for shape in shapes:
        for node in shape.revisited_nodes:
            revisited_nodes[node] += 1
        for length in shape.loop_lengths:
            loop_lengths[length] += 1
    return ShapeReport(
        shapes=shapes,
        outcome_counts=outcome_counts,
        revisited_nodes=revisited_nodes,
        loop_lengths=loop_lengths,
    )
