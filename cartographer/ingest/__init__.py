"""Ingest adapters — turn real-world sources into the corpus format.

Each module here reads some external shape of text (a Project Gutenberg play,
an exported chat, a forum dump) and emits the plain conversation dicts the rest
of the cartographer already understands (see :mod:`cartographer.corpus`):

    {"id": "...", "turns": ["first message", "second message", ...]}

Keeping ingestion at the edge means the instrument itself never has to know
where a corpus came from — every source collapses to the same simple shape
before it reaches the extractor, the paths, or the loop reader.
"""
