import time
import logging
import collections
from typing import Iterable, Union



LOG = logging.getLogger("caatdash_test")
logging.getLogger('pytest_selenium.pytest_selenium').setLevel(logging.WARNING)



FILTER_SET_SEARCH_PAUSE = 0.2
JAVASCRIPT_ERROR_URL_IGNORE = {
    "twitter",
    "twimg",
    "facebook",
    "civi-int",
}



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



def filter_set_search_prefix(
        selenium,
        prefix: str,
        key: str,
        term: str,
        state_key: Union[str, None] = None
) -> list:
    """
    Enter search text in a filter set search input then await and return results.
    """

    selector = f"div.{prefix}-filter-set-{key} div.{prefix}-filter-option-search input"
    input_el = selenium.find(selector, wait=False, required=True)

    input_el.send_keys(term)

    # When no AJAX query is made results should be very fast.
    assert state_key is None
    time.sleep(FILTER_SET_SEARCH_PAUSE)

    results = []

    xpath = (
        "//ul["
        "contains(concat(' ', @class, ' '), ' ui-autocomplete ')"
        " and "
        "not(contains(@style, 'display: none'))"
        "]"
    )

    result_el = selenium.find(xpath, method="xpath", wait=False)

    if result_el:
        for item in selenium.find_all(
                "ul.ui-autocomplete li.ui-menu-item div.ui-menu-item-wrapper"):
            results.append(item.text)

    return results




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
