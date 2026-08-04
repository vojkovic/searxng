# SPDX-License-Identifier: AGPL-3.0-or-later
"""Google Images via WML HTML UI."""

import random
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from lxml import html

from searx.engines.google import fetch_traits  # pylint: disable=unused-import
from searx.engines.google import (
    get_google_info,
    time_range_dict,
    detect_google_sorry,
    nokia_useragents,
)
from searx.utils import eval_xpath_list

# about
about = {
    "website": "https://images.google.com",
    "wikidata_id": "Q521550",
    "official_api_documentation": "https://developers.google.com/custom-search",
    "use_official_api": False,
    "require_api_key": False,
    "results": "HTML",
}

# engine dependent config
categories = ["images", "web"]
paging = True
max_page = 50
"""`Google max 50 pages`_

.. _Google max 50 pages: https://github.com/searxng/searxng/issues/2982
"""

time_range_support = True
language_support = True
safesearch = True

filter_mapping = {0: "images", 1: "active", 2: "active"}


def request(query, params):
    """Google-Image search request"""

    google_info = get_google_info(params, traits)
    start = (params["pageno"] - 1) * 10

    args = {"q": query, "tbm": "isch", **google_info["params"]}
    if start:
        args["start"] = start

    query_url = (
        "https://" + google_info["subdomain"] + "/wml/search" + "?" + urlencode(args)
    )

    if params["time_range"] in time_range_dict:
        query_url += "&" + urlencode(
            {"tbs": "qdr:" + time_range_dict[params["time_range"]]}
        )
    if params["safesearch"]:
        query_url += "&" + urlencode({"safe": filter_mapping[params["safesearch"]]})
    params["url"] = query_url

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

    for link in eval_xpath_list(dom, '//a[contains(@href, "/imgres?")]'):
        href = link.get("href")
        if not href:
            continue
        qs = parse_qs(urlparse(href).query)
        img_src = unquote(qs.get("imgurl", [""])[0])
        url = unquote(qs.get("imgrefurl", [""])[0])
        if not img_src or not url:
            continue
        width, height = qs.get("w", [""])[0], qs.get("h", [""])[0]
        thumb = eval_xpath_list(link, ".//img/@src")
        results.append(
            {
                "template": "images.html",
                "url": url,
                "title": unquote(urlparse(img_src).path.rsplit("/", 1)[-1])
                or urlparse(url).netloc,
                "content": "",
                "img_src": img_src,
                "thumbnail_src": thumb[0] if thumb else img_src,
                "resolution": f"{width} x {height}" if width and height else "",
            }
        )

    return results
