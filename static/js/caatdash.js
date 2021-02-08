/*global window, $, _, URI */

(function () {
  "use strict";

  // Allow running on sites that already use `$`.
  var $ = jQuery;

  if (window.CaatDash) {
    throw "CaatDash already defined.";
  }

  // Logging AJAX Buffer

  var AjaxBufferCaatDash = function (options) {
    this.processRequest = options.processRequest;
    this.processResponse = options.processResponse;
    AjaxBuffer.call(this, options);
  };

  AjaxBufferCaatDash.prototype = Object.create(AjaxBuffer.prototype);

  // Filter Base Class

  function CaatDashFilter (app, control, filterSpec, setCallback) {
    var filter = this;

    // Constant properties

    filter.key = filterSpec.key;
    filter.text = filterSpec.text;
    filter.hidden = filterSpec.hidden;

    // Upstream properties

    filter.app = app;
    filter.control = control;
    filter.setCallback = setCallback;

    // Variable properties

    filter.value = undefined;
  }

  _.extend(CaatDashFilter.prototype, {
    register: {},

    create: function (app, control, filterSpec, setCallback) {
      var constructor = CaatDashFilter.prototype.register[filterSpec.type];
      return new constructor(app, control, filterSpec, setCallback);
    },

    initFilterFolding: function (options) {
      var filter = this;
      var app = filter.app;

      var $open, $clear, $header, $options;
      var slideDuration = 100;
      var open, clear;
      var filterOptions = options;

      var openHint, clearHint;

      if (filter.text.hint) {
        openHint = app.i18n.pgettext("filter-label", "Filter by <{facet}>")
          .replace("<{facet}>", app.i18n.pgettext("filter-label", filter.text.hint));
        clearHint = app.i18n.pgettext("filter-label", "Clear <{facet}> filters")
          .replace("<{facet}>", app.i18n.pgettext("filter-label", filter.text.hint));

      }

      $header = filter.el.$filter.find(app.selector(
        ".<%= prefix %>-filter-header"));
      $open = filter.el.$filter.find(app.selector(
        ".<%= prefix %>-filter-header .<%= prefix %>-filter-open"));
      $clear = filter.el.$filter.find(app.selector(
        ".<%= prefix %>-filter-header .<%= prefix %>-filter-clear"));
      $options = filter.el.$filter.find(app.selector(
        ".<%= prefix %>-filter-option-list"));

      filter.clearEnabled = function (value) {
        $clear.toggleClass(app.selector("<%= prefix %>-disabled"), !value);
      };

      if (options.alwaysOpen) {
        $open.hide();
        $clear.show();

        if (openHint) {
          $header.attr("title", openHint);
        }

        if (clearHint) {
          $clear.attr("title", clearHint);
        }

        filter.clear = function (options) {
          if (!_.isNil(options) && _.isFunction(options.clearCallback)) {
            options.clearCallback();
          }
        };
      } else {
        filter.open = function (options) {
          options = _.extend({
            duration: 0
          }, options);

          if (!filter.el.$filter.hasClass(app.selector(
            "<%= prefix %>-closed-style"))) {
            return;
          }

          filter.el.$filter.removeClass(app.selector(
            "<%= prefix %>-closed-style"));

          $open.hide();
          $clear.show();
          $options.slideDown(options.duration, options.callback);

          $header.attr("title", null);
          if (clearHint) {
            $clear.attr("title", clearHint);
          }
        };

        filter.clear = function (options) {
          options = _.extend({
            duration: 0
          }, options);

          filter.el.$filter.addClass(app.selector(
            "<%= prefix %>-closed-style"));

          $options.slideUp(options.duration, function () {
            if (_.isFunction(options.clearCallback)) {
              options.clearCallback();
            }
            if (_.isFunction(options.closeCallback)) {
              options.closeCallback();
            }
          });
          $clear.hide();
          if (!filter.alwaysOpen) {
            $open.show();
          }

          $clear.attr("title", null);
          if (openHint) {
            $header.attr("title", openHint);
          }
        };

        $header.on("click", function (event) {
          if (filter.el.$filter.hasClass(app.selector(
            "<%= prefix %>-disabled"))) {
            return;
          }

          filter.open({
            duration: slideDuration,
            callback: options.openCallback,
            interactive: true
          });
        });
      }

      $clear.on("click", function (event) {
        filter.clear({
          duration: slideDuration,
          clearCallback: options.clearCallback,
          closeCallback: options.closeCallback,
          interactive: true
        });
        event.preventDefault();
        event.stopPropagation();
      });

      filter.clear();
    }
  });

  // Filter Value Class

  function CaatDashFilterText (app, control, filterSpec, setCallback) {
    var filter = this;
    var placeholder;

    CaatDashFilter.call(this, app, control, filterSpec, setCallback);

    filter.alwaysOpen = filterSpec.alwaysOpen;

    if (!_.isNil(_.get(filter, "text.placeholderNames"))) {
      placeholder = _.map(filter.text.placeholderNames, function (v) {
        if (_.get(filterSpec, "i18nContext.label")) {
          return app.i18n.pgettext(filterSpec.i18nContext.label, v);
        }
        return v;
      }).join(", ");
    }

    if (!filterSpec.hidden) {
      var $filter = $(app.render("filter-text.html", {
        label: filter.text.label,
        key: filter.key,
        placeholder: placeholder,
      }));

      filter.el = {
        $filter: $filter,
        $options:  $filter.find(app.selector(
          ".<%= prefix %>-filter-option-list")),
        $input:  $filter.find(app.selector(
          ".<%= prefix %>-filter-option-search input")),
        $loading:  $filter.find(app.selector(
          "span.<%= prefix %>-filter-loading"))
      };
    }

    filter.init(app);
  }

  CaatDashFilter.prototype.register.text = CaatDashFilterText;

  CaatDashFilterText.prototype = _.extend(Object.create(CaatDashFilter.prototype), {
    paramsToFilters: function (params) {
      var filter = this;
      var filters = {};

      if (!_.isNil(params[filter.key])) {
        filters[filter.key] = params[filter.key];
      } else {
        filters[filter.key] = null;
      }

      return filters;
    },

    filtersToParams: function (filters) {
      var filter = this;
      var params = {};

      if (!_.isNil(filters[filter.key])) {
        params[filter.key] = filters[filter.key];
      }

      return params;
    },

    upstreamSet: function (text) {
      this.setCallback(this.key, this.value, text);
    },

    init: function (app, options) {
      var filter = this;

      if (filter.el) {
        this.initFilterFolding({
          alwaysOpen: filter.alwaysOpen,
          openCallback: function (options) {
            options = _.extend({
              interactive: true
            }, options);

            filter.el.$input.prop("disabled", false);
            if (options.interactive) {
              filter.el.$input.focus();
            }
          },
          closeCallback: function () {
            filter.el.$input.prop("disabled", true);
          },
          clearCallback: function () {
            filter.value = null;
            filter.el.$input.val("");
            filter.setCallback(filter.key, null, "clearcallback 1");
          }
        });

        filter.el.$input.on("change", function (event) {
          filter.set(filter.el.$input.val());
        });

        // Only disable inputs after events are bound, to avoid
        // users entering text while page is initializing:
        filter.el.$input.prop("disabled", false);
      }
    },

    set: function (value) {
      // The `value` of the filter is either `null` or a non-zero length string.

      var filter = this;

      if (_.isEqual(value, filter.value)) {
        return;
      }

      filter.value = value;

      if (filter.el) {
        if (filter.value) {
          filter.el.$input.val(filter.value);
          if (_.isFunction(filter.open)) {
            filter.open();
          }
        }

        if (_.isFunction(filter.clearEnabled)) {
          filter.clearEnabled(!!filter.value);
        }
      }

      filter.upstreamSet("update");
    },

    enable: function (value) {
      var filter = this;
      var app = filter.app;

      if (filter.el) {
        var $control = filter.el.$filter.find(app.selector(
          "div.<%= prefix %>-filter-control"));

        filter.el.$filter.toggleClass(app.selector("<%= prefix %>-disabled"), !value);
        $control.toggle(value);
      }
    }

  });

  // Filter Set Class

  function CaatDashFilterSet (app, control, filterSpec, setCallback) {
    var filter = this;
    var placeholder;

    CaatDashFilter.call(this, app, control, filterSpec, setCallback);

    filter.alwaysOpen = filterSpec.alwaysOpen;

    filter.expandFilters = filterSpec.expandFilters;
    filter.allowSearchText = filterSpec.allowSearchText;

    filter.autocompleteInit = filterSpec.autocompleteInit;
    filter.autocompleteClear = filterSpec.autocompleteClear;

    if (_.isFunction(filterSpec.staticSource)) {
      filter.staticSource = filterSpec.staticSource(app, filterSpec);
      filter.itemLabel = this.itemLabelStatic;
      filter.autocompleteSource = this.autocompleteSourceStatic;
    } else {
      filter.itemLabel = filterSpec.itemLabel;
      filter.autocompleteSource = function (request, callback) {
        filterSpec.search(request.term, request.value, app, control, filter, callback);
      };
    }

    if (!_.isNil(_.get(filter, "text.placeholderNames"))) {
      placeholder = _.map(filter.text.placeholderNames, function (v) {
        if (_.get(filterSpec, "i18nContext.label")) {
          return app.i18n.pgettext(filterSpec.i18nContext.label, v);
        }
        return v;
      }).join(", ");
    }

    var $filter = $(app.render("caatdash-filter-set.html", {
      label: filter.text.label,
      key: filter.key,
      placeholder: placeholder,
    }));

    filter.el = {
      $filter: $filter,
      $options:  $filter.find(app.selector(
        ".<%= prefix %>-filter-option-list")),
      $input:  $filter.find(app.selector(
        ".<%= prefix %>-filter-option-search input")),
      $loading:  $filter.find(app.selector(
        "span.<%= prefix %>-filter-loading"))
    };

    filter.init(app);
  }

  CaatDashFilter.prototype.register.set = CaatDashFilterSet;

  CaatDashFilterSet.prototype = _.extend(Object.create(CaatDashFilter.prototype), {
    paramSplitComma: function (text) {
      // Split on a comma unless it comes before a space.
      // This is to preserve country names containing a comma,
      // Eg. "Palestine, State of" in comma-separated lists.

      var parts = text.split(",");
      var parts2 = [];
      _.each(parts, function (v, i) {
        if (v[0] == " ") {
          parts2[parts2.length - 1] += "," + v;
        } else {
          parts2.push(v);
        }
      });

      return parts2;
    },

    paramsToFilters: function (params) {
      var filter = this;
      var filters = {};

      if (!_.isNil(params[filter.key])) {
        var parts = filter.paramSplitComma(params[filter.key]);
        filters[filter.key] = _(parts).map(function (v, i) {
          return {
            "value": v.trim()
          };
        }).filter().value();
      } else {
        filters[filter.key] = null;
      }

      return filters;
    },

    filtersToParams: function (filters) {
      var filter = this;
      var params = {};

      if (!_.isNil(filters[filter.key])) {
        var valueList = _.map(filters[filter.key], "value");
        params[filter.key] = valueList.join(",");
      }

      return params;
    },

    itemLabelStatic: function (item) {
      var source = this.staticSource;
      var match = _.find(source, function (v) {
        return v.slug == item.value;
      });
      if (_.isNil(match)) {
        console.error("`item` has no `label`:", item);
        throw "";
      }

      return match.label;
    },

    autocompleteSourceStatic: function (request, callback) {
      var source = _.map(this.staticSource, function (v, i) {
        return {
          label: v.label,
          value: v.slug,
        };
      });

      var result = CaatDash.prototype.filterSearch(source, request.term, {
        exclude: request.value,
        limit: 16
      });

      callback(result);
    },

    addItem: function (item) {
      var filter = this;

      var selected = _.map(filter.value, function (v, i) {
        return v.value;
      });
      if (_.includes(selected, item.value)) {
        return;
      }
      if (_.isNil(filter.value)) {
        filter.value = [];
      }
      filter.value.push(item);
      filter.renderItem(item);
      filter.clearEnabled(true);
      filter.upstreamSet("add item");
    },

    removeItem: function (item) {
      var filter = this;

      var index = _.findIndex(filter.value, function (item2) {
        return item2.value == item.value;
      });
      if (index === -1) {
        return;
      }
      filter.value.splice(index, 1);
      if (_.isEmpty(filter.value)) {
        filter.value = null;
        filter.clearEnabled(false);
      }
      filter.upstreamSet("remove item");
    },

    renderItem: function (item) {
      var filter = this;
      var app = filter.app;

      var label = item.label;

      if (_.isNil(label) &&_.isFunction(filter.itemLabel)) {
        label = filter.itemLabel(item);
      }
      if (_.isNil(label)) {
        label = item.value;
      }

      var $option = $(app.render("caatdash-filter-set-item.html", {
        label: label
      }));
      var $remove = $option.find(app.selector(
        ".<%= prefix %>-filter-remove"));
      $remove.on("click", function (event) {
        $option.remove();
        filter.removeItem(item);
      });
      filter.el.$options.children().last().before($option);
    },

    emptyItems: function () {
      var app = this.app;
      this.el.$options.children(app.selector(
        ":not(.<%= prefix %>-filter-option-search)")).remove();
    },

    styleLoading: function () {
      this.el.$loading.css("visibility", "visible");
    },

    styleLoaded: function () {
      this.el.$loading.css("visibility", "hidden");
    },

    upstreamSet: function (text) {
      this.setCallback(this.key, this.value, text);
    },

    init: function (app, options) {
      var filter = this;
      var searchRegex = new RegExp('^"(.+)"$');

      if (filter.autocompleteInit) {
        filter.autocompleteInit(filter.app, filter);
      }

      if (filter.autocompleteSource) {
        filter.el.$input.autocomplete({
          minLength: 0,
          delay: 0,
          source: function (request, callback) {
            // Fix autocomplete binding bug
            // https://bugs.jqueryui.com/ticket/10050
            filter.el.$input.data("ui-autocomplete").menu.bindings = $();
            request.value = _.cloneDeep(filter.value);
            filter.styleLoading();
            filter.autocompleteSource(request, function (source) {
              if (filter.allowSearchText) {
                var hasSearch = false;
                if (request.value) {
                  hasSearch = _.some(request.value, function (value) {
                    return searchRegex.test(value.value);
                  });
                }
                if (request.term && !hasSearch) {
                  source.unshift('"' + request.term + '"');
                }
              }
              callback(source);
              filter.styleLoaded();
            });
          },
          select: function (event, ui) {
            event.preventDefault();
          }
        }).prop(
          "disabled", false
        ).on({
          "input": filter.app.autoFocusOnInput,
          "focus": filter.app.openOnFocus,
          "autocompleteclose": function (event, ui) {
            if (_.isFunction(filter.autocompleteClear)) {
              filter.autocompleteClear(filter);
            }
          },
          "autocompleteselect autocompletechange": function (event, ui) {
            // `ui.item` is `null` if value is not in source.
            var value = ui.item ? ui.item.value : null;
            filter.el.$input.val("");

            if (!_.isNil(value)) {
              if (event.type == "autocompletechange") {
                // autocompletechange is only required if we're clearing the input.
                return;
              }
              filter.addItem(ui.item);
              filter.el.$input.focus().trigger("input");
            }

            return false;         // Do not set input to selected value;
          }
        });
      }

      this.initFilterFolding({
        alwaysOpen: filter.alwaysOpen,
        openCallback: function (options) {
          options = _.extend({
            interactive: true
          }, options);

          filter.el.$input.prop("disabled", false);
          if (options.interactive) {
            filter.el.$input.focus();
          }
        },
        closeCallback: function () {
          filter.el.$input.prop("disabled", true);
        },
        clearCallback: function () {
          filter.value = [];
          filter.emptyItems();
          filter.el.$input.val("");
          filter.setCallback(filter.key, null, "clearcallback 1");
        }
      });
    },

    set: function (value) {
      // The `value` of the filter is either `null` or
      // an array of objects containing `value` and optionally, `label`.

      var filter = this;

      if (_.isEqual(value, filter.value)) {
        return;
      }

      filter.emptyItems();
      filter.value = value;
      if (filter.value) {
        _.each(filter.value, function (item, i) {
          filter.renderItem(item);
        });
        if (_.isFunction(filter.open)) {
          filter.open();
        }
      }

      if (_.isFunction(filter.clearEnabled)) {
        filter.clearEnabled(!!filter.value);
      }

      filter.upstreamSet("update");
    },

    enable: function (value) {
      var filter = this;
      var app = filter.app;

      var $control = filter.el.$filter.find(app.selector(
        "div.<%= prefix %>-filter-control"));

      filter.el.$filter.toggleClass(app.selector("<%= prefix %>-disabled"), !value);
      $control.toggle(value);
    }
  });

  function CaatDashFilterPartition (app, control, filterSpec, setCallback) {
    var filter = this;

    CaatDashFilter.call(this, app, control, filterSpec, setCallback);

    filter.defaultValue = undefined;
    filter.items = filterSpec.items;
    filter.allValue = filterSpec.allValue;
    filter.defaultValue = filterSpec.defaultValue;

    var $filter = $(app.render("caatdash-filter-partition.html", {
      label: filter.text.label,
      key: filter.key
    }));

    filter.el = {
      $filter: $filter,
      $options: $filter.find(app.selector(".<%= prefix %>-filter-option-list")),
      $header: $filter.find(app.selector(".<%= prefix %>-filter-header")),
      $icon: $filter.find(app.selector(".<%= prefix %>-filter-header i")),
      $desc: undefined
    };

    filter.init(app);
  }

  CaatDashFilter.prototype.register.partition = CaatDashFilterPartition;

  CaatDashFilterPartition.prototype = _.extend(Object.create(CaatDashFilter.prototype), {
    valueString: function (filters) {
      if (_.every(filters, Boolean)) {
        return "all";
      }

      return _(filters).pickBy().keys().value().join(",");
    },

    init: function (app, options) {
      var filter = this;

      var $header;
      var defaultValue = filter.valueString(_(filter.items).map(function (v, i) {
        return [v.key, v.selected];
      }).fromPairs().value());

      _.each(filter.items, function (item, i) {
        var $item = $(app.render("caatdash-field-partition-item.html", item));
        var $input = $item.find("input");
        var defaultState = item.selected;
        $input.prop("checked", defaultState);
        filter.el.$options.append($item);
      });
      filter.el.$inputs = filter.el.$filter.find("input");
      filter.el.$desc = filter.el.$filter.find(app.selector(
        ".<%= prefix %>-filter-option-desc"));

      filter.el.$inputs.on("input", function (event) {
        var $input = $(event.target);
        var value = _(filter.el.$inputs).filter(function (v, i) {
          return $(v).prop("checked");
        }).map(function (v, i) {
          return $(v).val();
        }).value();

        if (_.isEmpty(value)) {
          value = null;
        } else {
          filter.set(value);
        }

        filter.el.$filter.toggleClass(app.selector(
          "<%= prefix %>-style-invalid"), _.isNull(value));

      });

      filter.el.$header.on("click", function (event) {
        filter.el.$filter.toggleClass(app.selector(
          "<%= prefix %>-style-highlight"));
        filter.el.$desc.slideToggle("fast");
        if (filter.el.$filter.hasClass(app.selector(
          "<%= prefix %>-style-highlight"))) {
          filter.el.$icon.removeClass("fa-question-circle");
          filter.el.$icon.addClass("fa-minus-circle");
        } else {
          filter.el.$icon.addClass("fa-question-circle");
          filter.el.$icon.removeClass("fa-minus-circle");
        }

      });

    },

    paramsToFilters: function (params) {
      var filter = this;
      var filters = {};
      var value = null;

      if (!_.isNil(params[filter.key])) {
        if (params[filter.key] === "all") {
          value = filter.allValue;
        } else {
          var parts = params[filter.key].split(",");
          value = [];
          _.each(filter.items, function (item) {
            if (_.includes(parts, item.key)) {
              value.push(item.key);
            }
          });
        }
      } else {
        value = filter.defaultValue;
      }

      filters[filter.key] = value;

      return filters;
    },

    filtersToParams: function (filters) {
      var filter = this;
      var params = {};

      if (_.isNil(filters[filter.key])) {
        console.error("Partition is empty: " + filter.key);
        throw "";
      }

      _.forEach(filters[filter.key], function (value) {
        if (!_.includes(filter.allValue, value)) {
          console.error(
            "Unrecognised value " + value + " for partition " + filter.key +
              ". Acceptable values are " + filter.allValue.join(","));
          throw "";
        }
      });

      if (!_.isEqual(_.sortBy(filters[filter.key]), _.sortBy(filter.defaultValue))) {
        if (_.isEqual(_.sortBy(filters[filter.key]), _.sortBy(filter.allValue))) {
          params[filter.key] = "all";
        } else {
          params[filter.key] = filters[filter.key].join(",");
        }
      }

      return params;
    },

    set: function (value, options) {
      var filter = this;

      options = _.extend({
        trigger: true
      }, options);

      value = _.cloneDeep(value);

      if (_.isEqual(value, filter.value)) {
        return;
      }

      filter.value = value;

      _.each(filter.items, function (item, i) {
        var $input = filter.el.$options.children().eq(i).find("input");
        $input.prop("checked", _.includes(filter.value, item.key));
      });

      if (options.trigger) {
        filter.setCallback(
          filter.key, _.cloneDeep(filter.value),
          "update partition " + filter.key);
      }

    },

    enable: function (value) {
      var filter = this;
      var app = filter.app;

      var $control = filter.el.$header.find(app.selector(
        "div.<%= prefix %>-filter-control"));

      filter.el.$filter.toggleClass(app.selector(
        "<%= prefix %>-disabled"), !value);
      $control.toggle(value);

      _.each(filter.items, function (item, i) {
        var $input = filter.el.$options.children().eq(i).find("input");
        $input.prop("disabled", !value);
      });
    }
  });

  // CAAT Dashboard Application

  function CaatDash (options) {
    var self = this;

    options = options || {};

    // Internal

    self.profile = null;
    self.completeState = null;
    self.completeResult = {};

    // Required parameters

    self.uri = options.uri;
    self.prefix = options.prefix;
    self.data = options.data;

    // Options

    self.cache = true;
    self.lang = null;
    self.sleep = null;
    self.debug = {
      ajax: false,
      scroll: false,
      pageState: false,
      auxState: false,
      dashboardState: false,
    };
    self.pageScrollMaxDuration = 300;
    self.pageScrollMaxDurationDistance = 1000;

    if (!_.isUndefined(options.cache)) {
      if (!(
        _.isNil(options.cache) ||
          _.isBoolean(options.cache)
      )) {
        console.error("CaatDash: Value of `cache` must be boolean, null or undefined.");
        throw null;
      } else {
        self.cache = options.cache;
      }
    }

    if (!_.isUndefined(options.sleep)) {
      if (!(
        _.isNil(options.sleep) ||
          _.isInteger(options.sleep)
      )) {
        console.error("CaatDash: Value of `sleep` must be integer, null or undefined.");
        throw null;
      } else {
        self.sleep = options.sleep;
      }
    }

    if (!_.isUndefined(options.debug)) {
      self.debug = options.debug;
    }

    this.setLanguage();
  }

  _.extend(CaatDash.prototype, {
    // Debug functions

    log: function (name) {
      var self = this;

      if (!self.debug[name]) {
        return;
      }
      console.log.apply(console, Array.prototype.slice.call(arguments, 1));
    },

    // Format functions

    formatTitleStrong: function (text) {
      if (_.isNil(text)) {
        return text;
      }
      return text
        .replace(/\[/g, "<strong>")
        .replace(/\]/g, "</strong>")
      ;
    },

    formatTitleClean: function (text) {
      if (_.isNil(text)) {
        return text;
      }
      return text
        .replace(/\[/g, "")
        .replace(/\]/g, "")
      ;
    },

    formatLabel: function (name, description) {
      if (description) {
        return name + " ‒ " + description;
      }
      return name;
    },

    formatCommas: function (n) {
      var s = "" + n;
      var o = "";

      if (n === null) {
        return null;
      }

      while (s.length > 3) {
        o = "," + s.substring(s.length - 3, s.length) + o;
        s = s.substring(0, s.length - 3);
      }
      return s + o;
    },

    formatAbbreviate: function (n) {
      var s = "" + n;
      var o = "";
      var p = null;
      var levels = [
        ["bn", 9],
        ["m", 6],
        ["k", 3]
      ];

      if (n === null) {
        return null;
      }

      _.each(levels, function (level, i) {
        var suffix = level[0];
        var v = level[1];

        if (n >= Math.pow(10, v + 1)) {
          p = n / Math.pow(10, v);
        } else if (n + 5 * Math.pow(10, v - 2) >= Math.pow(10, v + 1)) {
          p = (n + 5 * Math.pow(10, v - 2)) / Math.pow(10, v);
        }

        if (p) {
          p = p.toFixed(0) + suffix;
          return false;
        }

        if (n >= Math.pow(10, v)) {
          p = n / Math.pow(10, v);
        } else if (n + 5 * Math.pow(10, v - 4) >= Math.pow(10, v)) {
          p = (n + 5 * Math.pow(10, v - 4)) / Math.pow(10, v);
        }

        if (p) {
          p = p.toFixed(1) + suffix;
          return false;
        }
      });

      return p || ("" + n);
    },

    // Search functions

    filterSearch: function (data, searchText, options) {
      var searchParts = latinize(searchText).toLowerCase().split(/\s+/);
      var hits = [];
      var reBoundary = "(?:^|\\s)"; // https://stackoverflow.com/a/10590516/201665

      options = _.extend({
        exclude: null,
        limit: null
      }, options);

      _.each(data, function (v, i) {
        var score = 0;
        var text = (!_.isNil(v.label)) ? v.label : v.value;

        text = latinize(text).toLowerCase();

        _.each(searchParts, function (part) {
          var match = text.match(new RegExp(reBoundary + part, "i"));
          if (match) {
            score += 2 * match.length;
          } else {
            match = text.match(new RegExp(part, "i"));
            if (match) {
              score += 1 * match.length;
            }
          }
        });

        if (score) {
          hits.push({
            "score": score,
            "item": v
          });
        }
      });

      hits = _(hits);

      if (options.exclude) {
        var excludeValue = _.map(options.exclude, "value");
        // Remove exclude and move above.
        hits = hits.filter(function (v, i) {
          return !_.includes(excludeValue, v.item.value);
        });
      }

      hits = hits.orderBy(
        [
          "score",
          function (v) {
            return v.item.sort;
          }
        ], ["desc", "asc"]
      ).map("item");

      if (options.limit) {
        hits = hits.slice(0, options.limit);
      }

      hits = hits.value();

      return hits;
    },

    // Autocomplete functions

    autoFocusOnInput: function (event) {
      var $input = $(event.target);
      $input.autocomplete("option", "autoFocus", !!$input.val());
    },

    openOnFocus: function (event) {
      var $input = $(event.target);
      $input.autocomplete("search");
    },

    initAcChange: function ($input, callback) {
      $input.on("autocompleteselect autocompletechange", function (event, ui) {
        // `ui.item` is `null` if value is not in source.
        var value = ui.item ? ui.item.value : null;
        if (event.type == "autocompletechange" && value) {
          // `autocompletechange` is only required to clear input.
          return;
        }
        callback(value);
      });
    },

    updateWithValue: function ($input, value, name) {
      // returns `true` if value was updated.

      if (_.isNil(value)) {
        return false;
      }

      if (!_.includes($input.autocomplete("option", "source"), value)) {
        return false;
      }

      $input.val(value);

      return true;
    },

    // Select functions

    sortSelectInit: function ($parent, sortOptions, set, setter) {
      var app = this;

      if (sortOptions && sortOptions.length > 1) {
        var $sortTitle = $parent.find(app.selector(
          ".<%= prefix %>-result-bar-sort-title"));
        var $sortSelect = $parent.find(app.selector(
          ".<%= prefix %>-result-bar-sort-ctrl select"));

        $sortTitle.on("click", function (event) {
          $sortSelect.focus();
        });

        $sortSelect.on("change", function (event) {
          set("index", this.value, setter + " select");
        });
      }
    },

    // URI functions

    uriToResource: function (uri, options) {
      return firma.uriToResource(this.uri.root, uri, options);
    },

    resourceToUri: function (resource) {
      return firma.resourceToUri(this.uri.root, resource);
    },

    uriToParams: function (uri) {
      var params;

      if (_.isNil(uri)) {
        uri = window.location;
      }

      params = _(URI(uri).search(true)).mapValues(function (v, k) {
        return v.trim();
      }).pickBy().value();

      params = _.isEmpty(params) ? null : params;

      return params;
    },

    paramsToResource: function (params, path) {
      var app = this;

      var resource;
      if (_.isNil(path)) {
        path = firma.urlRemoveRoot(app.uri.root, URI(window.location).resource());
      }

      resource = URI(path).search(params).resource();
      resource = resource.replace(new RegExp("%2C", "gi"), ",");
      resource = resource.replace(new RegExp("%20", "gi"), "+");

      return resource;
    },

    faqResourceUpdate: function (resource) {
      var app = this;
      var params = app.uriToParams();
      params = _.pick(params, ["lang"]);
      return app.resourceToUri(app.paramsToResource(params, resource));
    },

    // i18n functions

    setLanguage: function (lang, domain) {
      if (_.isNil(this.data.i18n)) {
        console.error("I18n data at `data.i18n` is not defined.");
      }

      var data;

      if (lang === this.lang) {
        return;
      }

      if (_.isNil(lang)) {
        this.i18n = {
          pgettext: function (context, message) {
            if (_.isNil(message)) {
              console.error("pgettext message is nil.");
            }
            return message;
          }
        };
      } else {
        data = this.data.i18n[lang];
        if (_.isNil(data)) {
          console.error("No translation data for language `" + lang + "`.");
          throw "";
        }
        if (_.isNil(domain)) {
          console.error("Domain is null");
          throw "";
        }
        this.i18n = new Jed({
          locale_data: data,
          domain: domain
        });
      }

      this.lang = lang;
    },

    i18nFilter: function (context, start) {
      return _(this.i18n.options.locale_data[this.prefix]).pickBy(function (v, k) {
        return _.startsWith(k, context + "\u0004" + (start || ""));
      }).value();
    },

    // AJAX functions

    ajaxBuffer: function (options) {
      // Create an Ajax Buffer with logging.

      var self = this;

      _.extend(options, {
        processRequest: function (data) {
          if (
            self.cache &&
              _.isNull(self.sleep)
          ) {
            return data;
          }

          if (!_.isObject(data)) {
            data = {};
          }
          if (!self.cache) {
            data.cache = self.cache;
          }
          if (!_.isNull(self.sleep)) {
            data.sleep = self.sleep;
          }

          self.log("ajaxBuffer", "processRequest", data);
          return data;
        },

        processResponse: function (data) {
          if (_.isObject(data) && !_.isNil(data.profile)) {
            self.log("ajaxBuffer", "processResponse", data);
            self.profile = data.profile;
            delete data.profile;
          }
          return data;
        }
      });

      return new AjaxBufferCaatDash(options);
    },

    // Cookie functions

    setCookie: function (key, value, expiresDays) {
      var path = "/";
      var expires = "";
      if (!_.isNil(expiresDays)) {
        expires = new Date();
        expires.setTime(expires.getTime() + (expiresDays * 24 * 60 * 60 * 1000));
        expires = "expires=" + expires + "; ";
      }
      var s = encodeURIComponent(key) + "=" +
          encodeURIComponent(value) + "; " + expires + "path=" + path;
      document.cookie = s;
    },

    getCookie: function (key) {
      var allValue = document.cookie;
      var value;
      _.each(document.cookie.split("; "), function (cookie) {
        cookie = cookie.split("=");
        if (decodeURIComponent(cookie[0]) == key) {
          value = decodeURIComponent(cookie[1]);
          return false;
        }
      });
      return value;
    },

    deleteCookie: function (key) {
      // Expire in the past.
      this.setCookie(key, "", -1);
    },

    // State functions

    simpleHashSum: function (item) {
      var sum = 0;
      _.each(JSON.stringify(item), function (character) {
        sum += character.charCodeAt(0);
      });
      return sum;
    },

    setCompleteResult: function (key, value) {
      if (_.isUndefined(value)) {
        delete this.completeResult.key;
      } else {
        this.completeResult[key] = this.simpleHashSum(value);
      }
    },

    clearState: function () {
      // Clear the state
      // Should be called whenever new content is requested
      this.completeState = null;
    },

    setCompleteState: function (state, replace) {
      // `replace` should be `true` only when finished building from a history state,
      // It should be `false` when receiving AJAX results, even if they're
      // a further pagination result.

      if (replace) {
        this.restoreScroll(state.scroll);
        this.completeState = window.history.state;
        this.log("pageState", "replace", this.completeState, _.cloneDeep(state));
      } else {
        this.completeState = firma.setCompleteState(state);
        this.log("pageState", "set", this.completeState, _.cloneDeep(state));
      }
      this.setAuxState();
    },

    setAuxState: function () {
      var aux = {
        scroll: {
          x: window.scrollX,
          y: window.scrollY
        }
      };
      this.log("auxState", "set", aux);
      firma.setAuxState(aux);
    },

    // Template functions

    selector: function (text) {
      // Render a CSS selector template using prefix variable.

      return _.template(text)({
        prefix: this.prefix
      });
    },

    render: function (name, data, options) {
      var app = this;
      var templateText = app.data.template[name];

      if (_.isUndefined(templateText)) {
        console.error("Template is not defined", name);
        throw "";
      }

      var f = _.template(templateText);

      data = _.extend(data || {}, {
        prefix: app.prefix,
        i18n: app.i18n
      });

      return firma.template.process(name, f, data, options);
    },

    // Scroll functions

    initScrollEvent: function () {
      var self = this;
      var timeoutId = null;

      var handler = function (event) {
        if (_.isNil(window.history.state)) {
          self.log("scroll", "history nil");
          return;
        }
        if (_.isNil(self.completeState)) {
          self.log("scroll", "state nil");
          return;
        }

        self.log("scroll", "set");
        self.setAuxState();
      };

      var delayHandler = function (event) {
        if (timeoutId) {
          clearTimeout(timeoutId);
        }

        timeoutId = setTimeout(handler, 200);
      };

      window.history.scrollRestoration = "manual";
      window.addEventListener("scroll", delayHandler);
    },

    scrollToTop: function (callback) {
      // Note that the length of the page may be shortened
      // if content is changed during transition.

      var bodyY = $("body").scrollTop();
      var htmlY = $("html").scrollTop();

      callback = _.isFunction(callback) ? callback : _.noop();

      if (bodyY == 0 && htmlY == 0) {
        callback();
        return;
      }

      var $el = bodyY > 0 ? $("body") : $("html");
      var y = $el.scrollTop();
      var duration = self.pageScrollMaxDuration * Math.min(
        1, y / self.pageScrollMaxDurationDistance);

      $el.animate({
        scrollTop: 0
      }, {
        duration: duration,
        complete: callback
      });
    },

    restoreScroll: function (scroll) {
      if (_.isNil(scroll)) {
        this.log("scroll", "scroll nil");
        return;
      }

      if (window.scrollX || window.scrollY) {
        this.log("scroll", "scroll expired");
        return;
      }

      this.log("scroll", "restore", scroll.x, scroll.y);
      window.scrollTo(scroll.x, scroll.y);
    },

    // Filter functions

    createFilterControls: function (control, setCallback) {
      var app = this;

      control.el.$filterContainer.empty();

      _.each(app.filterControlOrder, function (key, i) {
        var filter;

        if (_.isNil(key)) {
          control.el.$filterContainer.append(
            $(app.selector("<div class='<%= prefix %>-dashboard-filter-separator'>"))
          );
          return;
        }

        if (_.isNil(app.filterManifest[key])) {
          console.error("No filter manifest for key `" + key  + "` in `filterControlOrder`.");
          throw "";
        }

        filter = CaatDashFilter.prototype.create(
          app, control, app.filterManifest[key], setCallback);

        if (!_.isNil(filter.el)) {
          control.el.$filterContainer.append(filter.el.$filter);
        }
        control.children.push(filter);
      });
    },

    // Page component functions

    insertHomeFaq: function () {
      var app = this;
      var $faq = $(app.selector("#<%= prefix %>-home-faq"));
      var $faqWidget = $(app.render("caatdash-widget-faq.html", {
        faq: app.faqItem(),
        resourceUpdate: _.bind(app.faqResourceUpdate, app)
      }));
      $faq.replaceWith($faqWidget);
    },

    // Initialization functions

    run: function () {
      var self = this;

      $(function () {
        var contentState;

        // $("#title-block").hide();

        if (window.performance && performance.navigation.type == 2) {
          // On back or forward navigation.
          contentState = window.history.state;
        }

        self.initScrollEvent();
        self.route(firma.getState(contentState));
      });
    }
  });

  window.CaatDashFilter = CaatDashFilter;
  window.CaatDash = CaatDash;

})();
