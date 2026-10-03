# SPDX-License-Identifier: AGPL-3.0-or-later
"""Google News: see :py:obj:`searx.engines.google`."""

import typing as t

from searx.engines.google import fetch_traits  # pylint: disable=unused-import
from searx.engines.google import google_request, unwrap_google_url, wml_dom
from searx.result_types import EngineResults
from searx.utils import (
    eval_xpath_getindex,
    eval_xpath_list,
    extract_text,
)

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
    seen = set()
    for result in eval_xpath_list(wml_dom(resp), '//div[contains(@class, "Gx5Zad")]'):
        raw_url = eval_xpath_getindex(result, './/a[contains(@href, "/url?")]/@href', 0, default=None)
        if not raw_url:
            continue

        url = unwrap_google_url(raw_url)
        if not url.startswith("http") or url in seen or "google.com/search" in url:
            continue

        title = extract_text(
            eval_xpath_getindex(result, './/h3[contains(@class, "zBAuLc")]', 0, default=None),
            allow_none=True,
        )
        if not title:
            continue

        content = extract_text(
            eval_xpath_getindex(result, './/div[contains(@class, "H66NU")]', 0, default=None),
            allow_none=True,
        )
        thumbnail = eval_xpath_getindex(result, './/img[contains(@src, "http")]/@src', 0, default=None)

        seen.add(url)
        results.add(
            results.types.MainResult(
                url=url,
                title=title,
                content=content or "",
                thumbnail=thumbnail or "",
            )
        )

    return results
