import re
import json
import time
import logging
import collections
from urllib.parse import urlparse, urljoin
from typing import Iterable, Union, Dict

import pytest

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.keys import Keys

from firma.browser import \
    RequiredElementNotFoundError

from caatdash.web import format_title_plain



LOG = logging.getLogger("caatdash_test")
logging.getLogger('pytest_selenium.pytest_selenium').setLevel(logging.WARNING)



FILTER_SET_SEARCH_PAUSE = 0.2
JAVASCRIPT_ERROR_URL_IGNORE = {
    "twitter",
    "twimg",
    "facebook",
    "civi-int",
}



# Generic utility functions



def assert_equal(calc, exp):
    try:
        assert calc == exp
    except AssertionError:
        LOG.warning("\n")
        LOG.warning(f"calculated: {calc}")
        LOG.warning(f"expected:   {exp}")
        for key in set(calc.keys()) | set(exp.keys()):
            calc_val = calc.get(key, "not-defined")
            exp_val = exp.get(key, "not-defined")
            if calc_val == exp_val:
                continue
            LOG.warning(f"    {key}: {calc_val} != {exp_val}")
        raise



# General browser functions


def assert_no_errors(
        selenium,
        base_url,
        ignore: Union[Iterable[str], str, None] = None,
):
    ignore_set = (
        set(ignore) if isinstance(ignore, (set, list, dict)) else
        set([ignore]) if ignore else
        set())

    errors = selenium.javascript_errors(
        host=base_url,
        ignore=JAVASCRIPT_ERROR_URL_IGNORE | ignore_set
    )

    for item in errors:
        LOG.error(item["message"])
    assert not errors



# CAAT Dash browser app state functions


def get_state(
        selenium,
        prefix: str,
        result_key: Union[None, str] = None,
) -> str:
    var = (
        f"{prefix}.completeResult.{result_key}" if result_key else
        f"{prefix}.completeState"
    )

    return selenium.execute_script(f"return {var};")



def await_state_prefix(
        selenium,
        prefix: str,
        blacklist: Union[None, str, Iterable[str]] = None,
        wait: Union[None, bool] = None,
        result_key: Union[None, str] = None,
) -> str:
    """
    Wait for the page content to udpate and return a string representing the new state.

    `state_key` may be used to specify a sub-page state to be awaited.

    If `wait` is `None` use the default duration.
    If `value` is non-null, wait until the page state is non-null and not equal to `value`
    """

    if blacklist:
        if not isinstance(blacklist, collections.Iterable):
            blacklist = [blacklist]
    else:
        blacklist = []

    def helper(selenium):
        state = get_state(selenium, prefix, result_key=result_key)
        if not state or state in blacklist:
            return False
        return state

    return selenium.wait_until(helper, wait=wait)



# CAAT Dash browser UI functions



def filter_set_get_filter(
        selenium,
        prefix: str,
        key: str,
        **kwargs,
) -> WebElement:
    return selenium.find(f"div.{prefix}-filter-set-{key}", **kwargs)



def filter_set_get_input(
        selenium,
        prefix: str,
        key: str,
        filter_div=None,
        **kwargs,
) -> WebElement:
    if filter_div is None:
        filter_div = filter_set_get_filter(selenium, prefix, key, **kwargs)

    # Escape in case another menu is covering something:
    elem = selenium.switch_to.active_element
    if elem:
        elem.send_keys(Keys.ESCAPE)

    input_ = selenium.find(
        f"div.{prefix}-filter-option-search input", node=filter_div, **kwargs)

    if not input_.is_displayed():
        open_ = selenium.find(
            f"span.{prefix}-filter-open", node=filter_div, **kwargs, required=True)
        selenium.scroll_and_click(open_)
        time.sleep(0.5)
        assert input_.is_displayed()

    return input_



def filter_set_get_value(
        selenium,
        prefix: str,
        key: str,
        filter_div=None,
        **kwargs,
) -> Dict[str, WebElement]:
    """
    Return a dict of {label: div}.
    """

    if filter_div is None:
        filter_div = filter_set_get_filter(selenium, prefix, key, **kwargs)

    return {
        v.text: v for v in
        selenium.find_all(f"div.{prefix}-filter-option", node=filter_div, **kwargs)
    }



def filter_set_remove_value(
        selenium,
        prefix: str,
        key: str,
        label: str,
        filter_div=None,
        item_el=None,
        **kwargs,
) -> None:
    """
    Return a dict of {label: div}.
    """

    if filter_div is None:
        filter_div = filter_set_get_filter(selenium, prefix, key, **kwargs)

    if item_el is None:
        for item in selenium.find_all(
                f"div.{prefix}-filter-option", node=filter_div, **kwargs):
            if "option-search" in item.get_attribute("class"):
                continue

            text_el = selenium.find(
                f"div.{prefix}-filter-option-text", node=item, required=True, wait=False)
            if text_el.text == label:
                item_el = item
                break

    assert item_el

    remove_el = selenium.find(
        f"a.{prefix}-filter-remove", node=item_el, required=True, wait=False)
    selenium.scroll_and_click(remove_el)



def filter_set_search(
        selenium,
        prefix: str,
        key: str,
        term: str,
        label: Union[str, None] = None,
        state_key: Union[str, None] = None,
        wait: Union[float, bool, None] = None,
) -> Union[list, WebElement]:
    """
    Enter search text in a filter set search input then await and return results.

    `label`: if supplied, return the li element with exact matching label (caller is responsible for clearing the input - either implicitly by selecting it or explicitly).

    Otherwise return the list of option labels found and clear the input.
    """

    selector = f"div.{prefix}-filter-set-{key} div.{prefix}-filter-option-search input"
    xpath = (
        "//ul["
        "contains(concat(' ', @class, ' '), ' ui-autocomplete ')"
        " and "
        "not(contains(@style, 'display: none'))"
        "]"
    )

    filter_div = filter_set_get_filter(selenium, prefix, key, wait=False)

    input_el = selenium.find(selector, wait=False, required=True)

    input_el.send_keys(term)

    # When no AJAX query is made results should be very fast.
    assert state_key is None
    time.sleep(FILTER_SET_SEARCH_PAUSE)

    def is_not_loading(d):
        loading = d.find(f"span.{prefix}-filter-loading", node=filter_div, wait=False)
        return not loading.is_displayed()

    selenium.wait_until(is_not_loading, wait=wait)

    option_ul = selenium.find(xpath, method="xpath", wait=False)

    option_list = [] if option_ul is None else selenium.find_all(
        "li.ui-menu-item div.ui-menu-item-wrapper",
        node=option_ul, wait=False)


    if label is None:
        result = [v.text for v in option_list if v.is_displayed()]
        input_el.clear()
        return result


    try:
        assert option_list

        for option_li in option_list:
            if option_li.text == label:
                return option_li
        raise AssertionError()

    except AssertionError:
        LOG.error("filter key:   %s", key)
        LOG.error("term:      %s", repr(term))
        LOG.error("label:      %s", repr(label))
        LOG.error("options:      %s", repr(
            [v.text for v in option_list] if option_list else None))

        raise



def assert_nav_links(selenium, base_url, build_url, parse_url, expected):
    for item in expected:
        try:
            parent = selenium.find(item["selector"], wait=False, required=True)
            link = selenium.find("a", node=parent, wait=False, required=True)
            if "resource" in item:
                assert link.is_displayed()
                href = link.get_attribute("href")
                assert href
                parts = parse_url(href, base_url)
                href_exp = build_url(base_url, item["resource"], params=item["params"])
                parts_exp = parse_url(href_exp, base_url)
                assert parts == parts_exp
            else:
                assert not link.is_displayed()
        except (AssertionError, RequiredElementNotFoundError):
            LOG.error(item)
            LOG.error(f"text:     {repr(link.text)}")
            LOG.error(f"expected: {repr(parts_exp)}")
            LOG.error(f"found:    {repr(parts)}")
            raise



def get_rank_widget_data(selenium, prefix, widget_css_key, result=None) -> dict:
    """
    State should already be loaded. No elements will be awaited.
    """

    assert result == "first_and_count"

    widget_selector = f".{prefix}-widget-rank-{widget_css_key}"
    widget_el = selenium.find(widget_selector, wait=False)

    title_el = selenium.find(
        f".{prefix}-result-widget-head h3",
        node=widget_el, required=True, wait=False)
    head_text_el = selenium.find(
        f".{prefix}-result-widget-bar-title .{prefix}-result-bar-text",
        node=widget_el, required=True, wait=False)
    head_value_el = selenium.find(
        f".{prefix}-result-widget-bar-title .{prefix}-result-bar-value",
        node=widget_el, required=True, wait=False)

    data = {
        "title": title_el.text,
        "head": {
            "text": head_text_el.text,
            "value": head_value_el.text,
        },
        "items": []
    }

    item_selector = f".{prefix}-result-widget-bar-list .{prefix}-result-bar"
    item_generator = selenium.find_all(
        item_selector, node=widget_el, required=True, wait=False)

    if result == "first_and_count":
        data["count"] = len(item_generator)

    for item_el in item_generator:
        text_el = selenium.find(
            f".{prefix}-result-bar-text",
            node=item_el, required=True, wait=False)
        value_el = selenium.find(
            f".{prefix}-result-bar-value",
            node=item_el, required=False, wait=False)
        bar_el = selenium.find(
            f".{prefix}-result-bar-text",
            node=item_el, required=False, wait=False)
        item = {
            "text": text_el.text,
        }

        if value_el:
            item["value"] = value_el.text
        if bar_el:
            item["bar"] = bar_el.value_of_css_property("width")

        data["items"].append(item)

        if result == "first_and_count":
            break

    return data


# Javascript unit tests



def case_lang_params(case):
    params = {}
    lang = case.get("lang", None)
    if lang:
        params["lang"] = lang
    return params or None



# Test functions



def _test_js_filters_to_params(app_prefix, build_url, base_url, selenium, case):
    """
    If `input` is not `None`, all fields must be present.
    """

    url = build_url(base_url, "/overview", params=case_lang_params(case))
    selenium.get(url)


    def filters_to_params(data=None):
        value = json.dumps(data, indent=2)
        command = f"{app_prefix}.app.dashboard.filtersToParams({value})"

        js = f"return {command};"
        return selenium.execute_script(js)


    # Wait for results to load to ensure constants have loaded.
    assert selenium.find(f"div.{app_prefix}-widget-date")

    if case.get("exception", None):
        with pytest.raises(WebDriverException):
            filters_to_params(case.get("input", None))
        selenium.javascript_errors_clear(required=True)
    else:
        calc = filters_to_params(case.get("input", None))
        assert_equal(calc, case["output"])



def _test_js_uri_to_params(app_prefix, build_url, base_url, selenium, case):

    url = build_url(base_url, "/overview", params=case_lang_params(case))
    selenium.get(url)

    # Wait for results to load to ensure constants have loaded.
    assert selenium.find(f"div.{app_prefix}-widget-date")

    input_url = base_url + case["resource"]

    input_value = json.dumps(input_url)
    output_value = json.dumps(case["output"], indent=2)
    command = f"{app_prefix}.uriToParams({input_value});"
    js = f"return {command}"
    calc = selenium.execute_script(js)
    try:
        assert calc == case["output"]
    except AssertionError:
        LOG.warning(f"command: {command}")
        LOG.warning(f"expected: {output_value}")
        LOG.warning(f"got: {calc}")
        raise



def _test_js_params_to_filters(app_prefix, build_url, base_url, selenium, case):
    selenium.get(base_url + "/overview")

    # Wait for results to load to ensure constants have loaded.
    assert selenium.find(f"div.{app_prefix}-widget-date")

    input_value = json.dumps(case["input"], indent=2)
    output_value = json.dumps(case["output"], indent=2)
    command = f"{app_prefix}.app.dashboard.paramsToFilters({input_value});"
    js = f"return {command}"
    calc = selenium.execute_script(js)
    calc_str = json.dumps(calc, indent=2)

    assert_equal(calc, case["output"])
    try:
        assert calc == case["output"]
    except AssertionError:
        LOG.warning(f"command: {command}")
        LOG.warning(f"expected: {output_value}")
        LOG.warning(f"got: {calc_str}")
        raise



def _test_dashboard_api_redirect_canonical(
        request, base_url, http_request,
        build_url, parse_url_params,
        case
):
    url_original = build_url(
        base_url, case["original"]["resource"],
        case["original"].get("params", None)
    )
    url_canonical = build_url(
        base_url, case["canonical"]["resource"],
        case["canonical"].get("params", None)
    )

    url = url_original

    while True:
        response = http_request(url, pytest_request=request, redirect=False)
        if 300 <= response.status_code <= 399:
            location = response.headers.get("Location")
            if not location.startswith("http"):
                location = urljoin(url, location)

            url = location
            continue

        assert response.status_code == 200
        break

    final_resource = urlparse(url).path
    final_params = parse_url_params(url)
    base_path = urlparse(base_url).path
    assert final_resource.startswith(base_path)
    final_resource = final_resource[len(base_path):]

    canonical_params = case["canonical"].get("params", None)

    try:
        assert final_resource == case["canonical"]["resource"]
        assert final_params == canonical_params
    except AssertionError:
        LOG.warning("")
        LOG.warning("final_resource:  %s", final_resource)
        LOG.warning("case_resource:   %s", case["canonical"]["resource"])
        LOG.warning("final_params:    %s", final_params)
        LOG.warning("case_params:     %s", canonical_params)
        LOG.warning("original url:    %s", url_original)
        LOG.warning("redirected url:  %s", url)
        LOG.warning("canonical url:   %s", url_canonical)
        raise



def _test_dashboard_api_title_phrase(
        build_url, base_url, get_json, case,
        i18n=None, lang=None
):
    params = case.get("params", None) or {}
    if lang:
        params["lang"] = lang

    url = build_url(base_url, "/api/overview", params=params)

    data = get_json(url, headers={
        "Accept": "application/json"
    })

    phrase_expected = case["desc"]["title"]

    if lang and i18n:
        phrase_translated = i18n[lang].pgettext("filter-phrase-test", phrase_expected)
        phrase_expected = phrase_translated

    phrase_found = data["desc"]["title"]

    try:
        assert phrase_found == phrase_expected
    except AssertionError:
        LOG.error("url:      %s", url)
        LOG.error("expected: %s", repr(phrase_expected))
        LOG.error("found:    %s", repr(phrase_found))
        raise



def _test_dashboard_browser_redirect_canonical(
        base_url, selenium,
        build_url, parse_url_params, await_state, dashboard_resources,
        case,
):

    canonical = case.get("canonical_js", None) or case["canonical"]

    url_original = build_url(
        base_url, case["original"]["resource"], case["original"].get("params", None))
    url_canonical = build_url(
        base_url, canonical["resource"], canonical.get("params", None))

    selenium.get(url_original)

    if case["canonical"]["resource"] in dashboard_resources:
        await_state(selenium)

    params_current = parse_url_params(selenium.current_url)
    params_canonical = parse_url_params(url_canonical)

    path_current = urlparse(selenium.current_url).path
    path_canonical = urlparse(url_canonical).path

    try:
        assert params_current == params_canonical
        assert path_current == path_canonical
    except AssertionError:
        LOG.warning("")
        LOG.warning("original url:    %s", url_original)
        LOG.warning("current url:     %s", selenium.current_url)
        LOG.warning("canonical url:   %s", url_canonical)
        raise


def _test_dashboard_browser_title_phrase(
        build_url, await_state, title_phrase_selector, selenium, base_url, case,
        i18n=None, lang=None
):

    params = case.get("params", None) or {}

    if lang:
        params["lang"] = lang

    resource = case.get("resource", "/overview")

    url = build_url(base_url, resource, params=params)
    selenium.get(url)

    try:
        await_state(selenium)
    except:
        LOG.error("uri:      %s", repr(url))
        raise

    desc = case["desc"]

    fail = False
    for key, phrase_expected in desc.items():
        selector = title_phrase_selector[key]
        element = selenium.find(selector, wait=False)

        try:
            if phrase_expected:
                assert element
            else:
                assert not element
        except AssertionError:
            LOG.error("key:      %s", repr(key))
            LOG.error("selector: %s", repr(selector))
            LOG.error("found:    %s", repr(bool(element)))
            fail = True
            continue

        if not phrase_expected:
            continue

        if lang and i18n:
            phrase_orig = phrase_expected
            phrase_translated = i18n[lang].pgettext("filter-phrase-test", phrase_expected)
            if phrase_translated == phrase_expected:
                LOG.error("No translation in %s for phrase %s", lang, repr(phrase_expected))
                fail = True
                continue
            phrase_expected = phrase_translated

        phrase_expected = format_title_plain(phrase_expected)

        phrase_found = element.text
        try:
            assert phrase_found == phrase_expected
        except AssertionError:
            LOG.error("")
            LOG.error("key:      %s", repr(key))
            LOG.error("selector: %s", repr(selector))
            if lang and i18n:
                LOG.error("orig:     %s", repr(phrase_orig))
            LOG.error("found:    %s", bool(element))
            LOG.error("expected: %s", repr(phrase_expected))
            LOG.error("found:    %s", repr(phrase_found))
            fail = True

    if fail:
        LOG.error("")
        LOG.error("uri:      %s", url)
        if lang:
            LOG.error("lang:     %s", repr(lang))
        pytest.fail()



def pgettext_dummy(_context, msgtxt):
    return msgtxt



def _test_dashboard_api_rank(
        request, log_response_profile, build_resource, base_url, get_json,
        case,
        extra_test_data=None,
        extra_test_facet=None,
        surplus_keys_data=None,
):
    url = base_url + build_resource("/api" + case["resource"], case.get("params", None))
    data = get_json(url, headers={
        "Accept": "application/json"
    })
    log_response_profile(request, data)


    # This function is no designed to test pages with no results.
    assert data["result"]

    try:
        if extra_test_data:
            extra_test_data(data)

        rank_key_set = set(data["result"]) - (surplus_keys_data or set())

        assert rank_key_set == set(case["rank"])

        for facet, facet_data in case["rank"].items():
            assert data["result"][facet]["index"] == facet_data["index"]

            # This function is no designed to test pages with no results.
            assert data["result"][facet]["items"]

            if extra_test_facet:
                extra_test_facet(facet, data["result"][facet], facet_data)

    except AssertionError:
        LOG.error("url:      %s", url)
        raise




def _test_dashboard_api_rank_item_i18n(
        request, log_response_profile, build_resource, base_url, get_json,
        case
):
    """
    Translate all labels where appropriate, but not slugs or codes.
    If labels are used as filter values in the URL they should also
    not be translated.
    """

    url = base_url + build_resource("/api/overview", case.get("params", None))
    data = get_json(url, headers={
        "Accept": "application/json"
    })
    log_response_profile(request, data)


    fail = False
    for path, values in case["result"].items():
        (metric, i) = path

        item = data["result"][metric]["items"][i]

        for (key, expected) in values["api"].items():
            found = item.get(key, None)

            try:
                if expected:
                    assert found
                else:
                    assert not found
                    continue
            except AssertionError:
                LOG.error("")
                LOG.error("path:     %s", path)
                LOG.error("key:      %s", key)
                LOG.error("expected: %s", repr(expected))
                LOG.error("found:    %s", repr(found))
                fail = True
                continue

            if expected is True:
                continue

            try:
                assert found == expected
            except AssertionError:
                LOG.error("")
                LOG.error("path:     %s", path)
                LOG.error("key:      %s", key)
                LOG.error("expected: %s", repr(expected))
                LOG.error("found:    %s", repr(found))
                fail = True

    if fail:
        LOG.error("")
        LOG.error("url:      %s", url)
        pytest.fail()



def _test_dashboard_browser_rank(
        build_url, app_prefix, await_state, selenium, base_url, case,
        extra_test_facet=None,
):
    url = build_url(base_url, case["resource"], case.get("params", None))

    selenium.get(url)

    try:
        assert_no_errors(selenium, base_url)
    except AssertionError:
        LOG.error(url)
        raise

    await_state(selenium)

    tab_el = selenium.find(f"#{app_prefix}-nav-item-rank", wait=False, required=False)
    tab_expected = case.get("rank_tab_title", None)

    if tab_expected:
        assert tab_el.is_displayed()
        assert tab_el.text == tab_expected
    else:
        assert tab_el is None or not tab_el.is_displayed()


    widget_data = {}
    for widget_el in selenium.find_all(f"div.{app_prefix}-result-rank-widget"):
        class_text = widget_el.get_attribute("class")
        match = re.search(f"{app_prefix}-widget-rank-([^ ]+)", class_text)
        assert match
        facet = match.group(1)

        widget_data[facet] = {
            "metric": [],
        }

        sort_select = selenium.find(
            f"div.{app_prefix}-result-bar-sort-ctrl option[selected]",
            node=widget_el, required=False, wait=False)

        if not sort_select:
            sort_select = selenium.find(
                f"div.{app_prefix}-result-bar-sort-ctrl span[value]",
                node=widget_el, required=False, wait=False)

        assert sort_select

        first_bar_el = selenium.find(
            f"div.{app_prefix}-result-widget-bar-list div.{app_prefix}-result-bar",
            node=widget_el, wait=False)

        value_el_list = selenium.find_all(
            f"div.{app_prefix}-result-bar-value",
            node=first_bar_el, wait=False)

        for value_el in value_el_list:
            metric = value_el.get_attribute("exuk-metric")
            widget_data[facet]["metric"].append(metric)

        widget_data[facet]["index"] = sort_select.get_attribute("value")


    assert set(widget_data) == set(case["rank"])

    for facet, facet_data in case["rank"].items():
        assert widget_data[facet]["index"] == facet_data["index"]

        if extra_test_facet:
            extra_test_facet(facet, widget_data[facet], facet_data)



def _test_dashboard_browser_rank_item_i18n(
        build_url, app_prefix, await_state, selenium, base_url, case,
):
    """
    Check that all internal links on case pages include:
    -   the correct app base URL
    -   the correct language
    """

    url = build_url(base_url, "/overview", case.get("params", None))

    selenium.get(url)

    try:
        assert_no_errors(selenium, base_url)
    except AssertionError:
        LOG.error(url)
        raise

    await_state(selenium)


    fail = False
    for path, values in case["result"].items():
        (metric, i) = path

        bar = selenium.find_all(f"div.{app_prefix}-widget-rank-{metric} div.{app_prefix}-result-widget-bar-list div.{app_prefix}-result-bar-text")[i]

        found = bar.text
        expected = values["browser"]

        try:
            assert found == expected
        except AssertionError:
            LOG.error("")
            LOG.error("path:     %s", path)
            LOG.error("expected: %s", repr(expected))
            LOG.error("found:    %s", repr(found))
            fail = True

    if fail:
        LOG.error("")
        LOG.error("url:      %s", url)
        pytest.fail()



def _test_dashboard_browser_set_filter_i18n(
        build_url, app_prefix, await_state, selenium, base_url, lang, case
):

    params = {}
    if lang:
        params["lang"] = lang

    url = build_url(base_url, "/overview", params or None)

    selenium.get(url)

    try:
        assert_no_errors(selenium, base_url)
    except AssertionError:
        LOG.error(url)
        raise

    state = await_state(selenium)


    def get_filter_el(key):
        filter_div = filter_set_get_filter(
            selenium, app_prefix, key, wait=False)
        filter_input = filter_set_get_input(
            selenium, app_prefix, key, filter_div=filter_div, wait=False)

        return filter_div, filter_input


    fail = False
    for filter_key, filter_data in case.items():
        filter_div, filter_input = get_filter_el(filter_key)
        placeholder_found = filter_input.get_attribute("placeholder")

        if placeholder_found != filter_data["placeholder"]:
            LOG.error("")
            LOG.error("place exp:   %s", repr(filter_data["placeholder"]))
            LOG.error("place fnd:   %s", repr(placeholder_found))
            fail = True

        for item in filter_data["item"]:
            search = item.get("search", item["label"])
            match_li = filter_set_search(
                selenium, app_prefix, filter_key, search, label=item["label"])

            selenium.scroll_and_click(match_li)
            state = await_state(selenium, state)

            value_list = filter_set_get_value(
                selenium, app_prefix, filter_key, wait=False)

            try:
                value_item_el = value_list.get(item["label"], None)
            except KeyError:
                LOG.error("filter key:   %s", filter_key)
                LOG.error("label:        %s", item["label"])
                LOG.error("value:        %s", repr(list(value_list)))
                raise

            filter_set_remove_value(
                selenium, app_prefix, filter_key, label=item["label"],
                item_el=value_item_el,
                filter_div=filter_div, wait=False)


    if fail:
        LOG.error("")
        LOG.error("url:      %s", url)
        pytest.fail()
