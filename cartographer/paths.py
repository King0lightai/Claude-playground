"""Paths and edges — the first topology layer of the cartographer.

A single conversation traces a *path*: the ordered sequence of questions the
person moved through, turn after turn. The bag-of-questions view (see ``run.py``
before this module existed) counts *what* a corpus asks. The map lives one level
up, in *what follows what* — the transitions between questions. Lay many paths
on top of each other and the recurring transitions are the roads of the map.

This module turns conversations into paths, paths into directed edges, and
accumulates both into a :class:`PathGraph`. It is still deliberately naive: two
questions are "the same node" only if they normalize to the same string (see
``extract.normalize``). Real node-merging — folding paraphrases together — is the
next big step and lives in a future session. See JOURNAL.md.
"""

import collections

from .corpus import conversation_texts
from .extract import extract_questions

# A directed transition from one normalized question to the next.
Edge = tuple[str, str]


def conversation_path(conversation: dict) -> list[str]:
    """Extract the ordered path of questions through a single conversation.

    Turns are read in order and their questions concatenated, so the path
    reflects the real sequence the person moved through — across turns, not just
    within one. Returns an empty list for a conversation with no questions.
    """
    path: list[str] = []
    for text in conversation_texts(conversation):
        path.extend(extract_questions(text))
    return path


def path_edges(path: list[str]) -> list[Edge]:
    """The directed edges of a path: each consecutive (from, to) pair.

    A path of one question has no edges. A question repeated back-to-back
    produces a self-edge ``(q, q)`` — an honest signal that the conversation
    circled on the same node, which the loop/resolve work will build on.
    """
    return list(zip(path, path[1:]))


class PathGraph:
    """An accumulating map of a corpus: nodes, directed edges, and paths.

    Not a fancy graph library — just the counts that matter for reading
    topology: how often each question shows up (``nodes``), how often each
    transition happens (``edges``), and the raw paths so later passes (loop vs.
    resolve, clustering) have the sequences to work from.
    """

    def __init__(self) -> None:
        self.nodes: "collections.Counter[str]" = collections.Counter()
        self.edges: "collections.Counter[Edge]" = collections.Counter()
        self.paths: list[list[str]] = []

    def add_path(self, path: list[str]) -> None:
        """Fold one path into the graph."""
        if not path:
            return
        self.paths.append(path)
        for node in path:
            self.nodes[node] += 1
        for edge in path_edges(path):
            self.edges[edge] += 1

    def add_conversation(self, conversation: dict) -> None:
        """Extract a conversation's path and fold it in."""
        self.add_path(conversation_path(conversation))

    @property
    def path_count(self) -> int:
        return len(self.paths)

    @property
    def node_count(self) -> int:
        """Number of distinct question-nodes seen."""
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        """Number of distinct transitions seen."""
        return len(self.edges)

    def successors(self, node: str) -> "collections.Counter[str]":
        """Where does this node lead? Counted next-questions, most common first.

        The seed of navigation: from a given question, what do people ask next?
        """
        out: "collections.Counter[str]" = collections.Counter()
        for (src, dst), weight in self.edges.items():
            if src == node:
                out[dst] += weight
        return out

    def most_common_transitions(self, n: int | None = None) -> list[tuple[Edge, int]]:
        """The most-travelled transitions, most frequent first."""
        return self.edges.most_common(n)


def build_graph(conversations: list[dict]) -> PathGraph:
    """Build a :class:`PathGraph` from a list of conversation dicts."""
    graph = PathGraph()
    for conversation in conversations:
        graph.add_conversation(conversation)
    return graph
