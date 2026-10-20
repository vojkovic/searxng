# SPDX-License-Identifier: AGPL-3.0-or-later
"""Google News: see :py:obj:`searx.engines.google`."""

import typing as t

from searx.engines.google import fetch_traits  # pylint: disable=unused-import
from searx.engines.google import (
    google_request,
    opera_card_fields,
    opera_result_nodes,
    resolve_opera_urls,
    response_dom,
)
from searx.result_types import EngineResults
from searx.utils import eval_xpath_getindex, extract_text

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Response
    from searx.search.processors import OnlineParams

# about
about = {
    "website": "https://www.google.com",
    "wikidata_id": "Q12020",
    "official_api_documentation": "https://developers.google.com/custom-search",
    "use_official_api": False,
    "require_api_key": False,
    "results": "XML",
}

# engine dependent config
categories = ["news"]
paging = True
max_page = 50
"""Google supports up to 50 pages of results, see the `Google max_page discussion`_.

.. _Google max_page discussion: https://github.com/searxng/searxng/issues/2982
"""
time_range_support = False
language_support = True
safesearch = False


def request(query: str, params: "OnlineParams") -> None:
    google_request(
        query,
        params,
        {"tbm": "nws"},
        eng_traits=traits,
        use_time_range=False,
        use_safesearch=False,
        use_locales=False,
    )


def response(resp: "SXNG_Response") -> EngineResults:
    results = EngineResults()
    dom = response_dom(resp)
    cards = []
    raw_urls = []
    for card in opera_result_nodes(dom):
        title, raw_url, content = opera_card_fields(card)
        if not title or not raw_url:
            continue
        source = extract_text(
            eval_xpath_getindex(card, './/div[contains(@class, "BamJPe")]', 0, default=None),
            allow_none=True,
        )
        if source and source not in content:
            content = f"{source} / {content}" if content else source
        cards.append((title, content))
        raw_urls.append(raw_url)

    seen = set()
    for (title, content), url in zip(cards, resolve_opera_urls(raw_urls)):
        if not url or url in seen:
            continue
        seen.add(url)
        results.add(results.types.MainResult(url=url, title=title, content=content))

    return results
