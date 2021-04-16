import re
import sys
import json
import gettext
import hashlib
import urllib.parse
from copy import deepcopy
from typing import Union, List, Set, Tuple
from pathlib import Path
from collections import defaultdict, namedtuple

import bleach
import markdown
import tornado.web
from tornado.log import app_log

from firma.web import \
    Application, \
    BaseHandler as FirmaBaseHandler



CACHE_TTL_SHORT = 7 * 24 * 60 * 60    # One week
CACHE_TTL_LONG = 30 * 24 * 60 * 60    # One month
MARKDOWN_DEFAULT_TAGS = [
    "a",
    "p",
    "ul",
    "ol",
    "li",
    "em",
    "img",
    "strong",
    "blockquote",
]
MARKDOWN_DEFAULT_ATTRIBUTES = [
    "href",
    "src",
    "alt",
]


FilterSetItemGroup = namedtuple("FilterSetItemGroup", "value label items")



class QueryRewriteContinueException(Exception):
    pass



class FiltersException(Exception):
    """
    To be used by the app for reporting problems with the filter dict
    """

    def __init__(self, errors, filter_dict):
        message = " ".join([v["message"] for v in errors])
        super().__init__(message)
        self.errors = errors
        self.filter_dict = filter_dict



class FilterValueException(Exception):
    """
    To be used by filter classes to report bad values
    """

    def __init__(self, *args, **kwargs):
        self.keys = kwargs.pop("keys", None)
        super().__init__(*args, **kwargs)



class I18nDummy(Exception):
    @staticmethod
    def pgettext(context, message):
        return message



def prune(d):
    if hasattr(d, "items"):
        d = {k: prune(v) for k, v in d.items()}
        d = {k: v for k, v in d.items() if v is not None}

    if hasattr(d, "__len__"):
        if not d:
            return None

    return d



def cache_join(items):
    """
    Join a list of strings for a cache key parameter.

    Even though some country names may contain the delimiter (a comma) there is no
    danger of a collision or requirement to be able to reverse the process.
    """

    if not items:
        return ""

    return ",".join(sorted([str(v) for v in items]))



def post_limit_items(f):
    def wrapper(_self, filter_dict, **kwargs):
        post_limit = kwargs.pop("post_limit", None)
        result = f(_self, filter_dict, **kwargs)

        if result["items"] and post_limit is not None:
            result["items"] = result["items"][:post_limit]

        return result

    return wrapper



# Format functions



def format_title_plain(title):
    """
    Remove square brackets from text, used to mark up bold title text.

    `"the [UK]'s list of “[Countries of Concern]”"`
    becomes:
    `"the UK's list of “Countries of Concern”"`

    """
    return re.sub(r"[\[\]]", "", title)



def format_title_bold_only(title):
    """
    Extract and concatenate bold title text.

    `"the [UK]'s list of “[Countries of Concern]”"`
    becomes:
    `"UK Countries of Concern"`
    """
    return " ".join(re.findall(r"\[(.+?)\]", title))



def format_markdown_safe(text, tags=None, attributes=None, single=None):
    """
    `single`:
      Process a single phrase; Remove outer paragraph tags,
      so only inner markup is processed.
    """

    if tags is None:
        tags = MARKDOWN_DEFAULT_TAGS
    if attributes is None:
        attributes = MARKDOWN_DEFAULT_ATTRIBUTES

    html = markdown.Markdown().convert(text)
    clean = bleach.clean(html, tags=tags, attributes=attributes)

    if clean and single:
        try:
            assert "\n" not in clean
            assert clean.startswith("<p>")
            assert clean.endswith("</p>")
        except AssertionError:
            sys.stderr.write(repr(clean))
            sys.stderr.flush()
            raise
        clean = clean[3:-4]

    return clean



def format_i18n(template, values):
    template = template.replace("<{", "{")
    template = template.replace("}>", "}")
    return template.format(**values)



# Dependency building



def hash_data(data):
    hasher = hashlib.sha1()
    hasher.update(json.dumps(data).encode())
    return hasher.hexdigest()[:7]



def less_header(target, deps, static_path, variables):
    target_path = static_path / target

    source_lines = []

    if variables:
        for k, v in variables:
            source_lines.append(f"@{k}: ~{repr(v)};")

    for dep in deps:
        rel_path = Path("static") / dep
        source_lines.append(f"@import {repr(str(rel_path))};")

    source_text = "\n".join(source_lines) + "\n"

    with target_path.open("w") as fp:
        fp.write(source_text)



def less_cmd(target, deps, node_path):
    target_full = str(Path("static") / target)
    target_map = target_full + ".map"

    return [
        f"{node_path}/less/bin/lessc",
        f"--source-map={target_map}",
        # Do not quote sub-arguments (though note that they
        # must be quoted if running the command in the shell):
        "--clean-css=--s1 --advanced",
    ] + [
        str(Path("static") / v) for v in deps
    ] + [
        target_full
    ]



def uglifyjs_cmd(target, deps, node_path, beautify=None):
    target = Path(target)
    target_map = target.name + ".map"
    target = str(Path("static") / target)

    return [
        f"{node_path}/uglify-js/bin/uglifyjs",
    ] + [
        str(Path("static") / v) for v in deps
    ] + [
        "--source-map",
        f"url={target_map}",
        ("-b" if beautify else "-cm"),
        "-o",
        target
    ]



def json2js(target, deps, variable_name, static_path: Path):
    target_path = static_path / target
    deps_paths = [static_path / v for v in deps]
    json_data = {}

    for path in deps_paths:
        json_data[path.stem] = json.loads(path.read_text())

    js_text = f"window.{variable_name} = {json.dumps(json_data)};"
    target_path.write_text(js_text)



def template2json(target, deps, static_path: Path):
    target_path = static_path / target
    deps_paths = [static_path / v for v in deps]

    json_data = {}
    for path in deps_paths:
        json_data[path.name] = path.read_text()

    json_text = json.dumps(json_data)
    target_path.write_text(json_text)



# Decorators



class cache_and_profile():  # pylint: disable=invalid-name
    def __init__(self, key, hook=None):
        self.key = key
        self.hook = hook

    def __call__(self, f):
        def wrapper(handler, filter_dict, **kwargs):
            """\
The cache returns `None` if no record is present, but we would like to
be able to store values of `None`. We do not need to store values of `False`
in the cache. So we'll let `False` in the cache stand for a value of `None`.

-   Store a value of `None` as `False` in the cache.
-   Retrieve `False` in the cache as a value of `None`.
"""

            kwargs2 = deepcopy(kwargs)
            kwargs2.pop("post_limit", None)
            cache_key = handler.cache_key_filtered(
                self.key, filter_dict, **kwargs2)

            if self.hook:
                cache_key = self.hook(handler, filter_dict, cache_key)

            if handler.get_argument_boolean("cache") is not False:
                data = handler.cache_get_json(cache_key)
                if data is not None:
                    return None if data is False else data

                if hasattr(handler, "request_cache_hook"):
                    handler.request_cache_hook(True)
            else:
                if hasattr(handler, "request_cache_hook"):
                    handler.request_cache_hook(False)

            handler.profile_start(self.key)

            data = f(handler, filter_dict, **kwargs)

            handler.profile_end(self.key)
            handler.cache_set_json(cache_key, False if data is None else data)

            return data

        return wrapper



class Filter:
    def __init__(self, spec):
        self.key = spec["key"]
        self.text = spec.get("text", None)
        self.codec_plus = spec.get("codecPlus", None)

    def keys(self):
        return set(self.default_request_args.keys())

    @property
    def default_request_args(self):
        return {
            self.key: None
        }

    def filter_dict(self, request_args, handler=None):
        filter_dict = {}
        request_labels = {}
        errors = []

        filter_dict[self.key] = request_args[self.key]

        return filter_dict, request_labels, errors


    def query_params(self, request_args) -> List[str]:
        """
        Return URL-encoded query string value
        """

        value = request_args[self.key]

        if not value:
            return []

        key = urllib.parse.quote_plus(str(self.key).encode("utf-8"))
        value = urllib.parse.quote_plus(str(value).encode("utf-8"))

        return ["%s=%s" % (key, value)]



class FilterText(Filter):
    def request_args(self, raw_params, **_kwargs) -> Tuple[dict, bool]:
        args = {
            self.key: None,
        }
        redirect = False

        value = raw_params.get(self.key, None)
        if value:
            # `value` is a list. Accept only the last supplied value.
            value = value[-1]

            if value and self.codec_plus:
                value = value.replace("+", " ")
            value.strip() or None

            if value:
                args[self.key] = value

        return (args, redirect)




class FilterGroupedSet(Filter):
    re_search_text = re.compile('^\"(.*)\"$')

    def __init__(self, spec):
        super().__init__(spec)

        self.items = spec.get("items", None)
        self.groups = spec.get("groups", None)
        self.groups_expand = spec.get("groups_expand", None)
        self.groups_extra_keys = spec.get("groups_extra_keys", None)
        self.allow_search_text = spec.get("allowSearchText", None)
        self.null_value = spec.get("nullValue", None)
        self.extra = spec.get("extra", None)

        self.items_full = set()
        if self.items:
            if None in self.items:
                app_log.error("`None` in `FilterGroupedSet.items` (`%s`).", self.key)
                app_log.error(repr(self.items))
            self.items_full.update(self.items)

        if self.groups:
            assert not self.items_full & set(self.groups)
            if None in self.groups:
                app_log.error("`None` in `FilterGroupedSet.groups` (`%s`).", self.key)
                app_log.error(repr(self.groups))
            self.items_full.update(self.groups)

        if self.groups_extra_keys:
            assert not self.items_full & self.groups_extra_keys
            if None in self.groups_extra_keys:
                app_log.error("`None` in `FilterGroupedSet.groups_extra_keys` (`%s`).", self.key)
                app_log.error(repr(self.groups_extra_keys))
            self.items_full.update(self.groups_extra_keys)

        if self.null_value:
            assert self.null_value not in self.items_full
            if self.null_value is None:
                app_log.error("`FilterGroupedSet.null_value` is `None` (`%s`).", self.key)
                app_log.error(repr(self.null_value))
            self.items_full.add(self.null_value)

        if "placeholderNames" in spec and self.items:
            placeholder_name_set = spec["placeholderNames"]
            option_name_set = set([v["name"] for v in self.items["items"]])
            not_found = placeholder_name_set - option_name_set
            if not_found:
                raise Exception(
                    "Placeholder names %s not found in `%s` item names.",
                    ", ".join([f"`{v}`" for v in not_found]),
                    spec["key"]
                )

        self.preverify = spec.get("preverify", None)


    @staticmethod
    def verify_set_values(key, values, recognised):
        if not (values and recognised):
            return

        values = set(values)
        recognised = set(recognised)

        unrecognised = values - recognised
        if unrecognised:
            raise FilterValueException(
                f"Unrecognised values for filter `{key}`: `{repr(unrecognised)}`")


    @staticmethod
    def values_exact_search(
            values: Set[str]
    ) -> Tuple[Set[str], Set[str]]:

        exact = set()
        search = set()

        for value in values:
            if match := FilterGroupedSet.re_search_text.match(value):
                search.add(match.group(1))
            else:
                exact.add(value)

        return (exact, search)


    def request_args(self, raw_params, **_kwargs) -> Tuple[dict, bool]:
        args = {}
        redirect = False

        args[self.key] = BaseHandler.set_values(raw_params, self.key)

        if self.preverify:
            preverify_redirect = self.preverify(args, raw_params)
            redirect |= preverify_redirect

        if args[self.key] and self.items_full:
            values = args[self.key]
            if self.allow_search_text:
                values, _search = self.values_exact_search(values)

            self.verify_set_values(self.key, values, self.items_full)

        return (args, redirect)


    def filter_dict(self, request_args, handler=None):
        filter_dict = {}
        request_labels = {}
        errors = []

        value_set = set()
        label_set = set()

        for value in request_args[self.key] or []:
            group = None

            if self.groups_expand:
                group = self.groups_expand(value, handler)
            if group is None and self.groups:
                group = self.groups.get(value)

            if group:
                value_set.update(group["items"])
                title = group.get("title", None)
                if title:
                    if callable(title):
                        title = title(handler.i18n)
                    label_set.add(FilterSetItemGroup(value, title, tuple(group["items"])))
            elif self.null_value and value == self.null_value:
                value_set.add(None)
            else:
                value_set.add(value)

        filter_dict[self.key] = value_set

        if label_set:
            request_labels[self.key] = label_set

        return filter_dict, request_labels, errors


    def query_params(self, request_args) -> List[str]:
        """
        Return URL-encoded query string value
        """

        value = request_args[self.key]

        if not value:
            return []

        key = urllib.parse.quote_plus(str(self.key).encode("utf-8"))
        value = ",".join(
            [urllib.parse.quote_plus(str(v).encode("utf-8"))
             for v in value])

        return ["%s=%s" % (key, value)]


class FilterPartition(Filter):
    def __init__(self, spec):
        super().__init__(spec)

        self.items = spec["items"]

        assert "all" not in self.items

        self.all_value = {v["key"] for v in self.items}
        self.default_value = {v["key"] for v in self.items if v["defaultValue"]}


    @staticmethod
    def partition_values(raw_params, key):
        values = set()
        for value in raw_params.get(key, []):
            value = urllib.parse.unquote_plus(value)
            for v in value.split(","):
                v = v.strip()
                if not v:
                    continue
                values.add(v)

        return values or set()


    @property
    def default_request_args(self):
        return {
            self.key: self.default_value
        }


    def request_args(self, raw_params, default_all=None, **_kwargs) -> Tuple[dict, bool]:
        args = {}
        redirect = False

        if default_all is None:
            default_all = False

        values = self.partition_values(raw_params, self.key)

        if "all" in values:
            values = set()

        elif not values:
            if default_all:
                values = set()
            elif len(self.default_value) == len(self.all_value):
                values = set()
            else:
                values = deepcopy(self.default_value)
        else:
            values = values & self.all_value

        args[self.key] = values or None

        return (args, redirect)


    def query_params(self, request_args) -> List[str]:
        """
        Convert `request_args` URL-encoded query string value

        For a partition, filtering is only applied if the `request_args` value
        is truthy. So a `request_args` value of `None` is effectively the
        `all_value` for the filter.
        """

        value = request_args[self.key]

        if value is None:
            value = self.all_value

        if value == self.default_value:
            return []


        if value == self.all_value:
            value = ["all"]

        key = urllib.parse.quote_plus(str(self.key).encode("utf-8"))
        value = ",".join(
            [urllib.parse.quote_plus(str(v).encode("utf-8"))
             for v in value if v])

        return ["%s=%s" % (key, value)]



class CaatDashApplication(Application):
    def __init__(self, handlers, options, **settings):
        self.cache = None

        self.faq = None
        self.faq_mtime = None

        self.i18n = None
        self.i18n_options = None

        self.filters = {}

        super().__init__(handlers, options, **settings)


    # Cache & Serialization

    def dump_json(self, obj, **kwargs):
        kwargs = dict({
            "indent": 2,
            "separators": (", ", ": ")
        }, **kwargs)
        serializer = self.json_serializer if hasattr(self, "json_serializer") else None
        s = json.dumps(obj, default=serializer, **kwargs)
        return s


    def cache_get_json(self, key, accept_old=False):
        value = self.settings.cache.get_item(key, accept_old=accept_old)
        return value and json.loads(value)


    def cache_set_json(
            self, key, value, valuable=False, expired=False):

        ttl = CACHE_TTL_LONG if valuable else CACHE_TTL_SHORT

        if value is None:
            value = False

        value = self.dump_json(value, indent=None, separators=(",", ":"),)
        status = self.settings.cache.set_item(key, value, ttl=ttl, expired=expired)

        return status


    # FAQ

    def load_faq(self):
        path = self.path / "static/json/faq.json"
        mtime = path.stat().st_mtime

        if self.faq_mtime != mtime:
            self.faq = []
            for key, value in json.loads(path.read_text()).items():
                value["key"] = key
                self.faq.append(value)

            self.faq_mtime = mtime
            app_log.warning("Loaded `%s`", path)


    # I18n

    def init_i18n(self, lang_labels, lang_default):
        domain = self.app_prefix
        i18n_path = self.path / "static/i18n"

        self.i18n = {}
        self.i18n_options = []
        fail = False
        for lang_path in i18n_path.glob(f"*/LC_MESSAGES/{domain}.mo"):
            lang = lang_path.parent.parent.name

            try:
                label = lang_labels[lang]
            except:
                app_log.info(
                    f"Translation found but not enabled: `{lang}`: `{lang_path.absolute()}`.")
                continue

            self.i18n[lang] = gettext.translation(domain, i18n_path, languages=[lang])
            self.i18n_options.append({
                "slug": lang,
                "label": label,
            })
            if lang == lang_default:
                self.i18n_options[-1]["default"] = True

        if fail:
            sys.exit(1)

        self.i18n_options.sort(key=lambda x: x["label"])

        self.add_stat("Loaded translations", ", ".join(sorted(list(self.i18n))))




class BaseHandler(FirmaBaseHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start = None
        self.profile = None
        self.raw_params = self.get_raw_params(self.request.uri)


    @property
    def cache_get_json(self):
        return self.application.cache_get_json

    @property
    def cache_set_json(self):
        return self.application.cache_set_json

    @property
    def json_serializer(self):
        return self.application.json_serializer

    @property
    def dump_json(self):
        return self.application.dump_json


    # Query parameter handling

    def query_rewrite(
            self,
            path: Union[str, None] = None,
            query: Union[dict, None] = None,
            replace_query: Union[bool, None] = None
    ):
        """
        If `path` is `None`, the current resource path will be preserved
        `path` may not contain a query string

        `query` appends to the current query string by default.
        If `query` is `None`, the current query string will be preserved

        if `replace_query` is truthy the current query will be ignored.
        """

        query_string_altered = None

        fragment = None
        if path:
            parts = urllib.parse.urlparse(path)
            assert not parts.scheme
            assert not parts.netloc
            assert not parts.params

            path = parts.path
            # query_s = parts.query
            fragment = parts.fragment


        def quote_key_value(key, value):
            key = urllib.parse.quote_plus(str(key).encode("utf-8"))
            value = ",".join(
                [urllib.parse.quote_plus(str(v).encode("utf-8"))
                 for v in value])
            return "%s=%s" % (key, value)


        args = {}
        if replace_query:
            args = self.get_request_args_default()
        else:
            args = self.request_args.copy()


        query_parts = []

        if query:
            # `args` is guaranteed to have all permissable keys.
            for key in args:
                if key in query:
                    args[key] = query[key]

        # Set filters & Partition Filters & Date filters

        all_keys = set()
        for key, filter_ in self.filters.items():
            query_parts += filter_.query_params(args)
            all_keys |= filter_.keys()


        for key, value in list(args.items()):
            if key in all_keys:
                continue

            if hasattr(value, "pop") and not value:
                # Empty iterable
                continue

            if value is None:
                continue

            if not hasattr(value, "pop"):
                # Make all values iterable
                value = [value]

            try:
                value = self.query_rewrite_key(key, value)
            except AttributeError:
                pass

            if not value:
                continue

            query_parts.append(quote_key_value(key, value))

        url = self.url_root

        if path is None:
            path = self.request.path
        elif "?" in path:
            raise Exception("Path may not contain a query string, '%s'." % repr(path))

        if not path.startswith("/"):
            raise Exception("Path must start with /, '%s'." % repr(path))

        url += path
        if len(url) > 1 and url.endswith("/"):
            url = url[:-1]

        if query_parts:
            url += "?" + "&".join(query_parts)

        if not url and "?" in self.request.uri:
            url += "?"

        if fragment:
            url += "#" + fragment

        return url


    def href_url_root(self, text):
        """
        Filter for Mako.
        Accepts Markdown HTML output and updates `a` `href` URLs.
        """
        return re.sub(r'href="/', f'href="{self.url_root}/', text)


    @staticmethod
    def get_raw_params(uri):
        """
        Get query string parameters with unencoded keys but still encoded values.

        Returns either `None` or a list of strings, one for each time the key
        appears in the query string.
        """

        params = defaultdict(list)

        query_string = urllib.parse.urlsplit(uri)[3]
        parts = re.compile(r"[&;]").split(query_string)
        for part in parts:
            part = urllib.parse.unquote(part)
            e = part.split("=")
            if len(e) == 2:
                (key, value) = e
            else:
                (key, ) = e
                value = None
            key = urllib.parse.unquote_plus(key)
            params[key].append(value)

        return params


    @staticmethod
    def set_values(raw_params, key):
        # Only split on commas if they are followed by
        # alphanumeric or quote characters
        #
        # See ExUK: `sql_item_core.py:item_verify`.
        # This should be moved outside CAAT Dash and handled by
        # functions or patterns supplied by individual apps

        re_split_items = re.compile(r"(?:,)(?=[\w\"])")

        values = set()
        for instance_value in raw_params.get(key, []):
            for v in re_split_items.split(instance_value):
                v = urllib.parse.unquote_plus(v)
                v = v.strip()
                if not v:
                    continue
                values.add(v)

        return values or None


    @staticmethod
    def verify_argument_set(name, values, items):
        if values and items and (values - items):
            raise tornado.web.HTTPError(
                404,
                "Values for argument `%s` (`%s`) are not valid items."
                % (name, ",".join(values - items)))


    def get_argument_uint(self, name, default=None):
        value = self.get_argument(name, default=default)
        if value:
            try:
                value = int(value)
            except ValueError:
                raise tornado.web.HTTPError(
                    404,
                    "Value for argument `%s` (`%s`) cannot be converted "
                    "to an integer." % (name, value))
            if value < 0:
                raise tornado.web.HTTPError(
                    404, "Value for argument `%s` (`%d`) must greater "
                    "than or equal to zero." % (name, value))

        return value


    def get_argument_option(self, name, option_list, default=None) -> Union[str, None]:
        args = self.get_arguments(name)

        if args:
            value = args[-1]
            if value in option_list:
                return value

            raise tornado.web.HTTPError(
                404,
                "Value for argument `%s` (`%s`) not in options (`%s`)" % (
                    name, value, repr(set(option_list))))

        return default


    def get_argument_boolean(self, name) -> Union[bool, None]:
        value = self.get_argument_option(name, ("0", "1", "false", "true"))

        if value == "false":
            return False
        if value == "true":
            return True

        return bool(int(value)) if value else None


    def get_argument_set(self, name, items=None) -> Union[set, None]:
        values = self.set_values(self.raw_params, name)

        if items is not None:
            self.verify_argument_set(name, values, items=items)

        return values or None


    def get_argument_order(self):
        return self.get_argument_option("order", ("asc", "desc"))
