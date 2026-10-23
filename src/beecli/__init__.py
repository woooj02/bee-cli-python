"""Python client for Bee (bee.computer), through the official `bee` CLI."""

from .client import Bee, BeeError
from .stream import EVENT_TYPES, Event, Stream, infer_type, parse_lines
from .transcript import speakers, to_ms, unwrap, utterances, word_count

__all__ = ["Bee", "BeeError", "Event", "Stream", "EVENT_TYPES", "infer_type", "parse_lines",
           "to_ms", "unwrap", "utterances", "word_count", "speakers"]
__version__ = "0.1.0"
