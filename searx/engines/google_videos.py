# SPDX-License-Identifier: AGPL-3.0-or-later
"""Google Videos: see :py:obj:`searx.engines.google`."""

import typing as t

from searx.engines.google import fetch_traits  # pylint: disable=unused-import
from searx.engines.google import google_request, opera_card_fields, opera_result_nodes, resolve_opera_urls, response_dom
from searx.result_types import EngineResults
from searx.utils import (
    eval_xpath_list,
    extract_text,
    parse_duration_string,
)

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Response
    from searx.search.processors import OnlineParams

# about
about = {
    "website": "https://www.google.com",
    "wikidata_id": "Q219885",
    "official_api_documentation": "https://developers.google.com/custom-search",
    "use_official_api": False,
    "require_api_key": False,
    "results": "XML",
}

# engine dependent config
categories = ["videos", "web"]
paging = True
max_page = 50
"""Google supports up to 50 pages of results, see the `Google max_page discussion`_.

.. _Google max_page discussion: https://github.com/searxng/searxng/issues/2982
"""
language_support = True
time_range_support = True
safesearch = True


def request(query: str, params: "OnlineParams") -> None:
    google_request(
        query,
        params,
        {"tbm": "vid"},
        eng_traits=traits,
        use_locales=False,
    )


def response(resp: "SXNG_Response") -> EngineResults:
    results = EngineResults()
    dom = response_dom(resp)
    cards = []
    raw_urls = []
    lengths = []
    for card in opera_result_nodes(dom):
        title, raw_url, _content = opera_card_fields(card)
        if not title or not raw_url:
            continue
        length = None
        for span in eval_xpath_list(card, './/span[contains(@class, "UK5aid")]'):
            length = parse_duration_string(extract_text(span) or "")
            if length:
                break
        cards.append(title)
        raw_urls.append(raw_url)
        lengths.append(length)

    for title, url, length in zip(cards, resolve_opera_urls(raw_urls), lengths):
        if not url:
            continue
        results.add(results.types.Video(url=url, title=title, length=length))

    return results
