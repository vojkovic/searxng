# SPDX-License-Identifier: AGPL-3.0-or-later
"""Google News via WML HTML UI (``tbm=nws``)."""

import random
from urllib.parse import unquote, urlencode

from lxml import html

from searx.engines.google import fetch_traits  # pylint: disable=unused-import
from searx.engines.google import (
    get_google_info,
    detect_google_sorry,
    nokia_useragents,
)
from searx.utils import (
    eval_xpath_getindex,
    eval_xpath_list,
    extract_text,
)

# about
about = {
    "website": "https://www.google.com",
    "wikidata_id": "Q12020",
    "official_api_documentation": "https://developers.google.com/custom-search",
    "use_official_api": False,
    "require_api_key": False,
    "results": "HTML",
}

# engine dependent config
categories = ["news"]
paging = True
max_page = 50
"""`Google max 50 pages`_

.. _Google max 50 pages: https://github.com/searxng/searxng/issues/2982
"""
time_range_support = False
language_support = True
safesearch = False


def request(query, params):
    """Google-News search request"""

    google_info = get_google_info(params, traits)
    start = (params["pageno"] - 1) * 10

    args = {"q": query, "tbm": "nws", **google_info["params"]}
    if start:
        args["start"] = start

    params["url"] = (
        "https://" + google_info["subdomain"] + "/wml/search" + "?" + urlencode(args)
    )
    params["headers"] = {"User-Agent": random.choice(nokia_useragents)}
    return params


def response(resp):
    """Get response from google's search request"""
    results = []
    detect_google_sorry(resp)

    # convert the text to dom (remove xml declaration for lxml)
    text = resp.text
    if text.lstrip().startswith("<?xml"):
        text = text.split("?>", 1)[-1]
    dom = html.fromstring(text)

    seen = set()
    for link in eval_xpath_list(dom, '//a[contains(@href, "/url?q=")]'):
        href = link.get("href")
        if not href:
            continue

        url = unquote(href[7:].split("&sa=U")[0])
        if url in seen or "google.com/search" in url:
            continue

        title = extract_text(
            eval_xpath_getindex(
                link, './/span[contains(@class, "M3vVJe")]', 0, default=None
            ),
            allow_none=True,
        )
        if not title:
            title = extract_text(
                eval_xpath_getindex(
                    link, './/span[contains(@class, "fuLhoc")]', 0, default=None
                ),
                allow_none=True,
            )
        if not title:
            continue

        source = extract_text(
            eval_xpath_getindex(
                link, './/span[contains(@class, "dXDvrc")]', 0, default=None
            ),
            allow_none=True,
        )
        pub_date = extract_text(
            eval_xpath_getindex(
                link, './/span[contains(@class, "YVIcad")]', 0, default=None
            ),
            allow_none=True,
        )
        thumbnail = eval_xpath_getindex(
            link, './/img[contains(@src, "encrypted-tbn")]/@src', 0, default=None
        )

        seen.add(url)
        results.append(
            {
                "url": url,
                "title": title,
                "content": " / ".join(x for x in [source, pub_date] if x),
                "thumbnail": thumbnail,
            }
        )

    return results
