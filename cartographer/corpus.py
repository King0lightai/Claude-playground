"""Loading corpora to map.

A corpus is a collection of conversations. We keep the input format dead simple
so any source — public datasets, forum threads, exported chats — can be coerced
into it: one JSON object per line (JSONL), each with either

    {"id": "...", "turns": ["first message", "second message", ...]}

or a single blob

    {"id": "...", "text": "..."}

The ``id`` is optional but recommended so paths can be traced back to a source.
"""

import json


def load_jsonl(path: str) -> list[dict]:
    """Read a JSONL corpus file into a list of conversation dicts."""
    conversations = []
    with open(path, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                conversations.append(json.loads(line))
            except json.JSONDecodeError as err:
                raise ValueError(f"{path}:{line_number}: invalid JSON — {err}") from err
    return conversations


def conversation_texts(conversation: dict) -> list[str]:
    """Return the text turns of a conversation, whatever shape it arrived in."""
    if "turns" in conversation:
        return [str(turn) for turn in conversation["turns"]]
    if "text" in conversation:
        return [str(conversation["text"])]
    return []
