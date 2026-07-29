"""Douyin request signer.

The bundled JavaScript asset is copied from MediaCrawler and is governed by
its NON-COMMERCIAL LEARNING LICENSE 1.1. See ``vendor/NOTICE.md``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import execjs


@lru_cache(maxsize=1)
def _signer():
    source = (Path(__file__).parent / "vendor" / "douyin.js").read_text(encoding="utf-8-sig")
    return execjs.compile(source)


def sign_query(query_string: str, user_agent: str, uri: str) -> str:
    """Return the a_bogus query value required by the Douyin web APIs."""
    function = "sign_reply" if "/reply" in uri else "sign_datail"
    return str(_signer().call(function, query_string, user_agent))
