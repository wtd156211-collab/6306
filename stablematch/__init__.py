"""稳定匹配引擎：解析、求解、核验、输出。"""

from .parser import ParseError, parse_case
from .engine import build_case, solve, verify_blocking
from .report import to_text, to_json_payload, write_json

__all__ = [
    "ParseError",
    "parse_case",
    "build_case",
    "solve",
    "verify_blocking",
    "to_text",
    "to_json_payload",
    "write_json",
]
