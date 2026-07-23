"""Rendering the map — turning the topology into a picture you can actually see.

Twelve sessions built the instrument: extract questions, fold paraphrases into
nodes, lay conversations down as paths, read each path's shape (loop vs.
resolve), tally which nodes people keep circling back onto. Every one of those
readings has, until now, come out as a *table* — counts in columns. But the
project is named for a *map*, and the founding dream (JOURNAL.md, session 001) is
a weather map of thinking you can *zoom out and look at*. A loop is far easier to
believe when you watch the arrow bend back on itself than when you read
"14% circled back."

This module renders a built :class:`~cartographer.paths.PathGraph` as **Graphviz
DOT** — the standard, text-based graph-description language. It stays inside the
charter: pure stdlib, because the DOT is just a string we assemble. It delegates
the one genuinely hard part — *layout*, the force-directed placement of nodes —
to Graphviz, which any reader can run over the text we emit::

    python run.py examples/socratic_dialogues.jsonl --cluster --map > meno.dot
    dot -Tsvg meno.dot -o meno.svg      # needs graphviz; the .dot itself needs nothing

The DOT text is the deliverable of this module and it needs no dependency to
read or to test. Graphviz only turns it into an image.

What the picture shows, faithfully — including the warts:

  * every **node** is a question, its label size growing with how often it was
    asked;
  * every **edge** is a transition, thickening with how many times a conversation
    took it — the roads of the map, wide where they were well travelled;
  * a **self-loop** (a node's arrow curving back to itself) is an immediate
    re-ask, drawn as exactly the bend it is;
  * the nodes people keep **returning** to (``ShapeReport.revisited_nodes``) are
    *filled*, so the corpus's stickiest questions — the ones that won't let go —
    stand out at a glance from the ones asked once and left behind.

It does not prettify. If the clusterer over-merged a rhetorical-question blob
into one fat node (session 006's wall), the map draws that fat node honestly:
the picture is a reading of the instrument as it actually is, not a poster for
it. The map is only ever as good as the merge beneath it — same ceiling as
:mod:`cartographer.loops`, now made visible.
"""

from .loops import shape_graph

# Prominence ranges. Node label font grows with how often a question was asked;
# edge pen grows with how often a transition was travelled. The floors keep even
# a count-1 node/edge legible; the ceilings stop a hub node from swallowing the
# page. Chosen for readability, not derived from anything — a rendering choice.
_NODE_FONT_MIN, _NODE_FONT_MAX = 10.0, 30.0
_EDGE_PEN_MIN, _EDGE_PEN_MAX = 1.0, 7.0

# Fill for a node people returned to, from a light touch (returned once) to a
# saturated warm (returned often). Non-revisited nodes are left unfilled, so the
# eye reads "stuck here" straight off the page. Warm end deliberately — a sticky
# question is a small storm on the weather map.
_STICKY_FILL_LIGHT = "#ffe9d6"
_STICKY_FILL_HEAVY = "#ff9a3c"


def _escape(text: str) -> str:
    """Escape a string for a DOT double-quoted label.

    Backslash first (so we don't double-escape the quotes we add next), then the
    quote itself, then flatten any stray newline to a space so a label stays one
    tidy line. Questions arrive already normalized to a single line, but a corpus
    is a corpus — be safe rather than emit invalid DOT.
    """
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", " ")
        .replace("\r", " ")
    )


def _scale(value: float, vmin: float, vmax: float, lo: float, hi: float) -> float:
    """Linearly map ``value`` from ``[vmin, vmax]`` onto ``[lo, hi]``.

    When the input range is degenerate (every node asked the same number of
    times), there is no spread to show, so everything sits at the floor.
    """
    if vmax <= vmin:
        return lo
    frac = (value - vmin) / (vmax - vmin)
    return lo + frac * (hi - lo)


def _mix(light: str, heavy: str, frac: float) -> str:
    """Blend two ``#rrggbb`` colors, ``frac`` of the way from light to heavy."""
    frac = max(0.0, min(1.0, frac))
    lr, lg, lb = (int(light[i : i + 2], 16) for i in (1, 3, 5))
    hr, hg, hb = (int(heavy[i : i + 2], 16) for i in (1, 3, 5))
    r = round(lr + (hr - lr) * frac)
    g = round(lg + (hg - lg) * frac)
    b = round(lb + (hb - lb) * frac)
    return f"#{r:02x}{g:02x}{b:02x}"


def to_dot(
    graph,
    *,
    report=None,
    max_nodes: "int | None" = None,
    min_edge_weight: int = 1,
    name: str = "cartography",
) -> str:
    """Render a :class:`~cartographer.paths.PathGraph` as a Graphviz DOT string.

    ``report`` is a :class:`~cartographer.loops.ShapeReport` used to fill the
    nodes people returned to; if ``None`` it is computed from the graph, so the
    highlighting always matches the paths the graph actually holds. Pass the same
    report you printed elsewhere to keep one source of truth.

    ``max_nodes`` keeps only the most-asked *N* nodes (and the edges wholly among
    them) — a legibility valve for a big corpus, off by default so the faithful
    map is the default map. ``min_edge_weight`` drops thin roads for the same
    reason. Both prune; neither invents. Any pruning is announced by the caller
    (see ``run.py``), never hidden.

    Determinism: nodes are emitted in ``(-count, name)`` order and given stable
    ``n0, n1, …`` ids from that order, and edges in ``(-weight, src, dst)`` order.
    So the same corpus renders byte-identical every time, and a corpus and its
    reverse render identically — the order-independence the project has guarded
    since session 003.
    """
    if report is None:
        report = shape_graph(graph)
    returned = report.revisited_nodes  # Counter: node -> times returned to

    # Choose the nodes to draw, most-asked first, ties broken lexically so the
    # id assignment is corpus-order-independent.
    ordered = sorted(graph.nodes.items(), key=lambda kv: (-kv[1], kv[0]))
    if max_nodes is not None:
        ordered = ordered[:max_nodes]
    kept = {node for node, _ in ordered}
    node_id = {node: f"n{i}" for i, (node, _) in enumerate(ordered)}

    counts = [c for _, c in ordered]
    cmin, cmax = (min(counts), max(counts)) if counts else (0, 0)
    max_return = max(returned.values(), default=0)

    lines = [
        f"digraph {name} {{",
        "  rankdir=LR;",
        '  node [shape=box, style=rounded, fontname="Helvetica"];',
        '  edge [fontname="Helvetica", fontsize=9, color="#888888"];',
        "",
    ]

    # --- nodes ---
    for node, count in ordered:
        font = _scale(count, cmin, cmax, _NODE_FONT_MIN, _NODE_FONT_MAX)
        stats = f"{count} asked"
        attrs = [f'fontsize={font:.0f}']
        r = returned.get(node, 0)
        if r:
            stats += f", {r} returned"
            frac = r / max_return if max_return else 0.0
            fill = _mix(_STICKY_FILL_LIGHT, _STICKY_FILL_HEAVY, frac)
            # A rounded box needs both 'rounded' and 'filled' to fill.
            attrs.append('style="rounded,filled"')
            attrs.append(f'fillcolor="{fill}"')
        label = f"{_escape(node)}\\n{stats}"
        attrs.insert(0, f'label="{label}"')
        lines.append(f"  {node_id[node]} [{', '.join(attrs)}];")

    lines.append("")

    # --- edges ---
    weights = [w for _, w in graph.edges.items()]
    wmin, wmax = (min(weights), max(weights)) if weights else (0, 0)
    edge_items = sorted(
        graph.edges.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][1])
    )
    for (src, dst), weight in edge_items:
        if weight < min_edge_weight or src not in kept or dst not in kept:
            continue
        pen = _scale(weight, wmin, wmax, _EDGE_PEN_MIN, _EDGE_PEN_MAX)
        attrs = [f"penwidth={pen:.1f}"]
        if weight > 1:
            attrs.append(f'label="{weight}"')
        lines.append(f"  {node_id[src]} -> {node_id[dst]} [{', '.join(attrs)}];")

    lines.append("}")
    return "\n".join(lines) + "\n"


__all__ = ["to_dot"]
