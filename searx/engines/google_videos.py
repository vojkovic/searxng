# SPDX-License-Identifier: AGPL-3.0-or-later
"""Google Videos via WML HTML UI."""

import random
import re
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from lxml import html

from searx.engines.google import fetch_traits  # pylint: disable=unused-import
from searx.engines.google import (
    get_google_info,
    time_range_dict,
    filter_mapping,
    detect_google_sorry,
    nokia_useragents,
)
from searx.utils import (
    eval_xpath_getindex,
    eval_xpath_list,
    extract_text,
    get_embeded_stream_url,
)

# about
about = {
    "website": "https://www.google.com",
    "wikidata_id": "Q219885",
    "official_api_documentation": "https://developers.google.com/custom-search",
    "use_official_api": False,
    "require_api_key": False,
    "results": "HTML",
}

# engine dependent config
categories = ["videos", "web"]
paging = True
max_page = 50
"""`Google max 50 pages`_

.. _Google max 50 pages: https://github.com/searxng/searxng/issues/2982
"""
language_support = True
time_range_support = True
safesearch = True

_duration_re = re.compile(r"^\d+:\d+")


def request(query, params):
    """Google-Video search request"""

    google_info = get_google_info(params, traits)
    start = (params["pageno"] - 1) * 10

    args = {"q": query, "tbm": "vid", **google_info["params"]}
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

    for result in eval_xpath_list(dom, '//div[contains(@class, "zMzFAb")]'):
        title = extract_text(
            eval_xpath_getindex(
                result,
                './/a[contains(@class, "fuLhoc")]//span[contains(@class, "CVA68e")]',
                0,
                default=None,
            ),
            allow_none=True,
        )
        raw_url = eval_xpath_getindex(
            result, './/a[contains(@class, "fuLhoc")]/@href', 0, default=None
        )
        if not title or not raw_url:
            continue

        if raw_url.startswith("/url?q="):
            url = unquote(raw_url[7:].split("&sa=U")[0])
        else:
            url = raw_url

        thumbnail = eval_xpath_getindex(
            result,
            './/img[contains(@src, "ytimg") or contains(@src, "encrypted-tbn")]/@src',
            0,
            default=None,
        )
        length = None
        for span in eval_xpath_list(result, './/span[contains(@class, "YVIcad")]'):
            candidate = extract_text(span) or ""
            if _duration_re.match(candidate):
                length = candidate
                break

        video_id = None
        if "youtube.com" in url:
            video_id = parse_qs(urlparse(url).query).get("v", [None])[0]
        if not thumbnail and video_id:
            thumbnail = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

        results.append(
            {
                "url": url,
                "title": title,
                "content": "",
                "thumbnail": thumbnail,
                "length": length,
                "iframe_src": get_embeded_stream_url(url),
                "template": "videos.html",
            }
        )

    return results
