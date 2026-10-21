# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring, invalid-name


import os
import pathlib
import csv
import hashlib
import hmac
import re
import itertools
import json
from datetime import datetime, timedelta
from typing import Iterable, List, NamedTuple, Tuple, TYPE_CHECKING

from io import StringIO
from codecs import getincrementalencoder

import msgspec
from flask_babel import gettext, format_date  # type: ignore

from searx import logger, get_setting

from searx.engines import DEFAULT_CATEGORY

if TYPE_CHECKING:
    from searx.enginelib import Engine
    from searx.results import ResultContainer
    from searx.search import SearchQuery
    from searx.results import Timing, UnresponsiveEngine

VALID_LANGUAGE_CODE = re.compile(r'^[a-z]{2,3}(-[a-zA-Z]{2})?$')

logger = logger.getChild('webutils')

timeout_text = gettext('timeout')
parsing_error_text = gettext('parsing error')
http_protocol_error_text = gettext('HTTP protocol error')
network_error_text = gettext('network error')
ssl_cert_error_text = gettext("SSL error: certificate validation has failed")
exception_classname_to_text = {
    None: gettext('unexpected crash'),
    'timeout': timeout_text,
    'asyncio.TimeoutError': timeout_text,
    'curl_cffi.requests.exceptions.Timeout': timeout_text,
    'curl_cffi.requests.exceptions.ConnectTimeout': timeout_text,
    'curl_cffi.requests.exceptions.ReadTimeout': timeout_text,
    'curl_cffi.requests.exceptions.HTTPError': gettext('HTTP error'),
    'curl_cffi.requests.exceptions.ConnectionError': gettext("HTTP connection error"),
    'curl_cffi.requests.exceptions.DNSError': gettext("HTTP connection error"),
    'curl_cffi.requests.exceptions.IncompleteRead': http_protocol_error_text,
    'curl_cffi.requests.exceptions.SSLError': ssl_cert_error_text,
    'curl_cffi.requests.exceptions.CertificateVerifyError': ssl_cert_error_text,
    'curl_cffi.requests.exceptions.ProxyError': gettext("proxy error"),
    'curl_cffi.requests.exceptions.RequestException': network_error_text,
    'searx.exceptions.SearxEngineCaptchaException': gettext("CAPTCHA"),
    'searx.exceptions.SearxEngineTooManyRequestsException': gettext("too many requests"),
    'searx.exceptions.SearxEngineAccessDeniedException': gettext("access denied"),
    'searx.exceptions.SearxEngineAPIException': gettext("server API error"),
    'searx.exceptions.SearxEngineXPathException': parsing_error_text,
    'KeyError': parsing_error_text,
    'json.decoder.JSONDecodeError': parsing_error_text,
    'lxml.etree.ParserError': parsing_error_text,
    'ssl.SSLCertVerificationError': ssl_cert_error_text,  # for Python > 3.7
    'ssl.CertificateError': ssl_cert_error_text,  # for Python 3.7
}


def get_translated_errors(unresponsive_engines: "Iterable[UnresponsiveEngine]"):
    translated_errors = []

    for unresponsive_engine in unresponsive_engines:
        error_user_text = exception_classname_to_text.get(unresponsive_engine.error_type)
        if not error_user_text:
            error_user_text = exception_classname_to_text[None]
        error_msg = gettext(error_user_text)
        if unresponsive_engine.suspended:
            error_msg = gettext('Suspended') + ': ' + error_msg
        translated_errors.append((unresponsive_engine.engine, error_msg))

    return sorted(translated_errors, key=lambda e: e[0])


class EngineTimingRow(NamedTuple):
    engine_name: str
    response_time: float | None
    response_time_label: str | None
    error_message: str | None
    bar_percent: int | None


class EngineTimingDisplay(NamedTuple):
    rows: list[EngineTimingRow]
    max_response_time: float | None
    max_response_time_label: str | None
    expanded: bool


def format_engine_time(seconds: float) -> str:
    if seconds <= 0:
        return "0.0"
    if seconds < 0.1:
        return f"{seconds:.2f}"
    return f"{seconds:.1f}"


def engine_time_bar_percent(seconds: float, max_seconds: float | None) -> int:
    if max_seconds is None or max_seconds <= 0 or seconds <= 0:
        return 0
    return min(100, max(0, int(round((100 * seconds) / max_seconds))))


def _translated_error_message(unresponsive_engines: "Iterable[UnresponsiveEngine]") -> str | None:
    translated_errors: list[str] = []
    for _engine_name, translated_error in get_translated_errors(unresponsive_engines):
        if translated_error not in translated_errors:
            translated_errors.append(translated_error)
    if not translated_errors:
        return None
    translated_errors.sort()
    return ", ".join(translated_errors)


def build_engine_timing_display(
    timings: "Iterable[Timing]",
    unresponsive_engines: "Iterable[UnresponsiveEngine]",
    has_results: bool,
) -> EngineTimingDisplay:
    unresponsive_by_engine_name: dict[str, list["UnresponsiveEngine"]] = {}
    for unresponsive_engine in unresponsive_engines:
        unresponsive_by_engine_name.setdefault(unresponsive_engine.engine, []).append(unresponsive_engine)

    engine_timings = list(timings)
    max_response_time = max((timing.total for timing in engine_timings), default=None)
    engine_names_with_response_time = {timing.engine for timing in engine_timings}
    timed_rows = [
        EngineTimingRow(
            engine_name=timing.engine,
            response_time=timing.total,
            response_time_label=format_engine_time(timing.total),
            error_message=_translated_error_message(unresponsive_by_engine_name.get(timing.engine, ())),
            bar_percent=engine_time_bar_percent(timing.total, max_response_time),
        )
        for timing in engine_timings
    ]
    timed_rows.sort(key=lambda timing_row: (-(timing_row.response_time or 0.0), timing_row.engine_name))
    rows_without_response_time = [
        EngineTimingRow(
            engine_name=engine_name,
            response_time=None,
            response_time_label=None,
            error_message=_translated_error_message(unresponsive_by_engine_name[engine_name]),
            bar_percent=None,
        )
        for engine_name in sorted(unresponsive_by_engine_name)
        if engine_name not in engine_names_with_response_time
    ]

    timing_rows = rows_without_response_time + timed_rows
    any_engine_succeeded = any(
        timing_row.response_time is not None and not timing_row.error_message for timing_row in timing_rows
    )
    return EngineTimingDisplay(
        rows=timing_rows,
        max_response_time=max_response_time,
        max_response_time_label=None if max_response_time is None else format_engine_time(max_response_time),
        expanded=not has_results or not any_engine_succeeded,
    )


class CSVWriter:
    """A CSV writer which will write rows to CSV file "f", which is encoded in
    the given encoding."""

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        # Redirect output to a queue
        self.queue = StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow(row)
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.strip('\x00')
        # ... and re-encode it into the target encoding
        data = self.encoder.encode(data)
        # write to the target stream
        self.stream.write(data.decode())
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


def write_csv_response(csv: CSVWriter, rc: "ResultContainer") -> None:  # pylint: disable=redefined-outer-name
    """Write rows of the results to a query (``application/csv``) into a CSV
    table (:py:obj:`CSVWriter`).  First line in the table contain the column
    names.  The column "type" specifies the type, the following types are
    included in the table:

    - result
    - answer
    - suggestion
    - correction

    """

    keys = ('title', 'url', 'content', 'host', 'engine', 'score', 'type')
    csv.writerow(keys)

    for res in rc.get_ordered_results():
        row = res.as_dict()
        row['host'] = row['parsed_url'].netloc
        row['type'] = 'result'
        csv.writerow([row.get(key, '') for key in keys])

    for a in rc.answers:
        row = a.as_dict()
        row['host'] = row['parsed_url'].netloc
        csv.writerow([row.get(key, '') for key in keys])

    for a in rc.suggestions:
        row = {'title': a, 'type': 'suggestion'}
        csv.writerow([row.get(key, '') for key in keys])

    for a in rc.corrections:
        row = {'title': a, 'type': 'correction'}
        csv.writerow([row.get(key, '') for key in keys])


class JSONEncoder(json.JSONEncoder):  # pylint: disable=missing-class-docstring
    def default(self, o):
        if isinstance(o, msgspec.Struct):
            return msgspec.to_builtins(o)
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, timedelta):
            return o.total_seconds()
        if isinstance(o, set):
            return list(o)
        return super().default(o)


def get_json_response(sq: "SearchQuery", rc: "ResultContainer") -> str:
    """Returns the JSON string of the results to a query (``application/json``)"""
    data = {
        'query': sq.query,
        'results': [_.as_dict() for _ in rc.get_ordered_results()],
        'answers': [_.as_dict() for _ in rc.answers],
        'corrections': list(rc.corrections),
        'infoboxes': rc.infoboxes,
        'suggestions': list(rc.suggestions),
        'unresponsive_engines': get_translated_errors(rc.unresponsive_engines),
    }
    response = json.dumps(data, cls=JSONEncoder)
    return response


def get_themes(templates_path):
    """Returns available themes list."""
    return os.listdir(templates_path)


def get_static_file_list() -> list[str]:
    file_list = []
    static_path = pathlib.Path(str(get_setting("ui.static_path")))

    def _walk(path: pathlib.Path):
        for f in path.iterdir():
            if f.name.startswith('.'):
                # ignore hidden file
                continue
            if f.is_file():
                file_list.append(str(f.relative_to(static_path)))
            if f.is_dir():
                _walk(f)

    _walk(static_path)
    return file_list


def get_result_templates(templates_path):
    result_templates = set()
    templates_path_length = len(templates_path) + 1
    for directory, _, files in os.walk(templates_path):
        if directory.endswith('result_templates'):
            for filename in files:
                f = os.path.join(directory[templates_path_length:], filename)
                result_templates.add(f)
    return result_templates


def new_hmac(secret_key, url):
    return hmac.new(secret_key.encode(), url, hashlib.sha256).hexdigest()


def is_hmac_of(secret_key, value, hmac_to_check):
    hmac_of_value = new_hmac(secret_key, value)
    return len(hmac_of_value) == len(hmac_to_check) and hmac.compare_digest(hmac_of_value, hmac_to_check)


def prettify_url(url, max_length=74):
    if len(url) > max_length:
        chunk_len = int(max_length / 2 + 1)
        return '{0}[...]{1}'.format(url[:chunk_len], url[-chunk_len:])
    return url


def contains_cjko(s: str) -> bool:
    """This function check whether or not a string contains Chinese, Japanese,
    or Korean characters. It employs regex and uses the u escape sequence to
    match any character in a set of Unicode ranges.

    Args:
        s (str): string to be checked.

    Returns:
        bool: True if the input s contains the characters and False otherwise.
    """
    unicode_ranges = (
        '\u4e00-\u9fff'  # Chinese characters
        '\u3040-\u309f'  # Japanese hiragana
        '\u30a0-\u30ff'  # Japanese katakana
        '\u4e00-\u9faf'  # Japanese kanji
        '\uac00-\ud7af'  # Korean hangul syllables
        '\u1100-\u11ff'  # Korean hangul jamo
    )
    return bool(re.search(fr'[{unicode_ranges}]', s))


def regex_highlight_cjk(word: str) -> str:
    """Generate the regex pattern to match for a given word according
    to whether or not the word contains CJK characters or not.
    If the word is and/or contains CJK character, the regex pattern
    will match standalone word by taking into account the presence
    of whitespace before and after it; if not, it will match any presence
    of the word throughout the text, ignoring the whitespace.

    Args:
        word (str): the word to be matched with regex pattern.

    Returns:
        str: the regex pattern for the word.
    """
    rword = re.escape(word)
    if contains_cjko(rword):
        return fr'({rword})'
    return fr'\b({rword})(?!\w)'


def highlight_content(content, query):

    if not content:
        return None

    # ignoring html contents
    if content.find('<') != -1:
        return content

    querysplit = query.split()
    queries = []
    for qs in querysplit:
        qs = qs.replace("'", "").replace('"', '').replace(" ", "")
        if len(qs) > 0:
            queries.extend(re.findall(regex_highlight_cjk(qs), content, flags=re.I | re.U))
    if len(queries) > 0:
        regex = re.compile("|".join(map(regex_highlight_cjk, queries)))
        return regex.sub(lambda match: f'<span class="highlight">{match.group(0)}</span>'.replace('\\', r'\\'), content)
    return content


def searxng_l10n_timespan(dt: datetime) -> str:  # pylint: disable=invalid-name
    """Returns a human-readable and translated string indicating how long ago
    a date was in the past / the time span of the date to the present.

    On January 1st, midnight, the returned string only indicates how many years
    ago the date was.
    """
    # TODO, check if timezone is calculated right  # pylint: disable=fixme
    d = dt.date()
    t = dt.time()
    if d.month == 1 and d.day == 1 and t.hour == 0 and t.minute == 0 and t.second == 0:
        return str(d.year)
    if dt.replace(tzinfo=None) >= datetime.now() - timedelta(days=1):
        timedifference = datetime.now() - dt.replace(tzinfo=None)
        minutes = int((timedifference.seconds / 60) % 60)
        hours = int(timedifference.seconds / 60 / 60)
        if hours == 0:
            return gettext('{minutes} minute(s) ago').format(minutes=minutes)
        return gettext('{hours} hour(s), {minutes} minute(s) ago').format(hours=hours, minutes=minutes)
    return format_date(dt)


NO_SUBGROUPING = 'without further subgrouping'


def group_engines_in_tab(engines: "Iterable[Engine]") -> List[Tuple[str, "Iterable[Engine]"]]:
    """Groups an Iterable of engines by their first non tab category (first subgroup)"""

    def get_subgroup(eng):
        non_tab_categories = [c for c in eng.categories if c not in tabs + [DEFAULT_CATEGORY]]
        return non_tab_categories[0] if len(non_tab_categories) > 0 else NO_SUBGROUPING

    def group_sort_key(group):
        return (group[0] == NO_SUBGROUPING, group[0].lower())

    def engine_sort_key(engine):
        return (engine.language, engine.name)

    tabs = list(get_setting('categories_as_tabs').keys())
    subgroups = itertools.groupby(sorted(engines, key=get_subgroup), get_subgroup)
    sorted_groups = sorted(((name, list(engines)) for name, engines in subgroups), key=group_sort_key)

    ret_val = []
    for groupname, _engines in sorted_groups:
        group_bang = '!' + groupname.replace(' ', '_') if groupname != NO_SUBGROUPING else ''
        ret_val.append((groupname, group_bang, sorted(_engines, key=engine_sort_key)))

    return ret_val
