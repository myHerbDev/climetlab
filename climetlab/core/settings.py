# (C) Copyright 2020 ECMWF.
#
# This software is licensed under the terms of the Apache Licence Version 2.0
# which can be obtained at http://www.apache.org/licenses/LICENSE-2.0.
# In applying this licence, ECMWF does not waive the privileges and immunities
# granted to it by virtue of its status as an intergovernmental organisation
# nor does it submit to any jurisdiction.
#

import getpass
import logging
import os
import re
import tempfile
from contextlib import contextmanager
from functools import wraps
from typing import Callable

import yaml

from climetlab.utils.html import css

LOG = logging.getLogger(__name__)

DOT_CLIMETLAB = os.path.expanduser("~/.climetlab")

SETTINGS_STACK = []


class Settings:
    def __init__(self, default, description, getter=None, none_ok=False, kind=None):
        self.default = default
        self.description = description
        self.getter = getter
        self.none_ok = none_ok
        self.kind = kind if kind is not None else type(default)

    def kind(self):
        return type(self.default)


_ = Settings

SETTINGS_AND_HELP = {
    "cache-directory": _(
        os.path.join(tempfile.gettempdir(), "climetlab-%s" % (getpass.getuser(),)),
        """Directory of where the dowloaded files are cached, with ``${USER}`` is the user id.
        See :ref:`caching` for more information.""",
    ),
    "styles-directories": _(
        [os.path.join(DOT_CLIMETLAB, "styles")],
        """List of directories where to search for styles definitions.
        See :ref:`styles` for more information.""",
    ),
    "projections-directories": _(
        [os.path.join(DOT_CLIMETLAB, "projections")],
        """List of directories where to search for projections definitions.
        See :ref:`projections` for more information.""",
    ),
    "layers-directories": _(
        [os.path.join(DOT_CLIMETLAB, "layers")],
        """List of directories where to search for layers definitions.
        See :ref:`layers` for more information.""",
    ),
    "datasets-directories": _(
        [os.path.join(DOT_CLIMETLAB, "datasets")],
        """List of directories where to search for datasets definitions.
        See :ref:`datasets` for more information.""",
    ),
    "plotting-options": _(
        {},
        """Dictionary of default plotting options.
        See :ref:`plotting` for more information.""",
    ),
    "number-of-download-threads": _(
        5,
        """Number of threads used to download data.""",
    ),
    "maximum-cache-size": _(
        None,
        """Maximum disk space used by the CliMetLab cache (ex: 100G or 2T).""",
        getter="_as_bytes",
        none_ok=True,
    ),
    "maximum-cache-disk-usage": _(
        "90%",
        """Disk usage threshold after which CliMetLab expires older cached entries (% of the full disk capacity).
        See :ref:`caching` for more information.""",
        getter="_as_percent",
    ),
    "url-download-timeout": _(
        "30s",
        """Timeout when downloading from an url.""",
        getter="_as_seconds",
    ),
    "download-updated-urls": _(
        False,
        "Re-download URLs when the remote version of a cached file as been changed",
    ),
}


NONE = object()
DEFAULTS = {}
for k, v in SETTINGS_AND_HELP.items():
    DEFAULTS[k] = v.default


@contextmanager
def new_settings(s):
    SETTINGS._stack.append(s)
    try:
        yield None
    finally:
        SETTINGS._stack.pop()
        SETTINGS._notify()


def forward(func):
    @wraps(func)
    def wrapped(self, *args, **kwargs):
        if self._stack:
            return func(self._stack[-1], *args, **kwargs)
        return func(self, *args, **kwargs)

    return wrapped


class Settings:
    def __init__(self, settings_yaml: str, defaults: dict, callbacks=[]):
        self._defaults = defaults
        self._settings = dict(**defaults)
        self._callbacks = [c for c in callbacks]
        self._settings_yaml = settings_yaml
        self._pytest = None
        self._stack = []

    @forward
    def get(self, name: str, default=NONE):
        """[summary]

        Args:
            name (str): [description]
            default ([type], optional): [description]. Defaults to NONE.

        Returns:
            [type]: [description]
        """

        if name not in SETTINGS_AND_HELP:
            raise KeyError("No setting name '%s'" % (name,))

        getter, none_ok = (
            SETTINGS_AND_HELP[name].getter,
            SETTINGS_AND_HELP[name].none_ok,
        )
        if getter is None:
            getter = lambda name, value, none_ok: value
        else:
            getter = getattr(self, getter)

        if default is NONE:
            return getter(name, self._settings[name], none_ok)

        return getter(name, self._settings.get(name, default), none_ok)

    @forward
    def set(self, name: str, *args, **kwargs):
        """[summary]

        Args:
            name (set): [description]
            value ([type]): [description]
        """

        if name not in SETTINGS_AND_HELP:
            raise KeyError("No setting name '%s'" % (name,))

        klass = SETTINGS_AND_HELP[name].kind

        if klass in (bool, int, float, str):
            # TODO: Proper exceptions
            assert len(args) == 1
            assert len(kwargs) == 0
            value = args[0]

        if klass is list:
            assert len(args) > 0
            assert len(kwargs) == 0
            value = list(args)
            if len(args) == 1 and isinstance(args[0], list):
                value = args[0]

        if klass is dict:
            assert len(args) <= 1
            if len(args) == 0:
                assert len(kwargs) > 0
                value = kwargs

            if len(args) == 1:
                assert len(kwargs) == 0
                value = args[0]

        getter, none_ok = (
            SETTINGS_AND_HELP[name].getter,
            SETTINGS_AND_HELP[name].none_ok,
        )
        if getter is not None:
            assert len(args) == 1
            assert len(kwargs) == 0
            value = args[0]
            # Check if value is properly formatted for getter
            getattr(self, getter)(name, value, none_ok)
        else:
            if not isinstance(value, klass):
                raise TypeError("Setting '%s' must be of type '%s'" % (name, klass))

        self._settings[name] = value
        self._changed()

    @forward
    def reset(self, name: str = None):
        """Reset setting(s) to default values.

        Args:
            name (str, optional): The name of the setting to reset to default. If the setting does not have a default,
            it is removed. If `None` is passed, all settings are reset to their default values. Defaults to None.
        """
        if name is None:
            self._settings = dict(**DEFAULTS)
        else:
            if name not in DEFAULTS:
                raise KeyError("No setting name '%s'" % (name,))

            self._settings.pop(name, None)
            if name in DEFAULTS:
                self._settings[name] = DEFAULTS[name]
        self._changed()

    @forward
    def _repr_html_(self):
        html = [css("table")]
        html.append("<table class='climetlab'>")
        for k, v in sorted(self._settings.items()):
            html.append(
                "<tr><td>%s</td><td>%r</td><td>%r</td></td>"
                % (k, v, SETTINGS_AND_HELP.get(k, (None, "..."))[0])
            )
        html.append("</table>")
        return "".join(html)

    def _changed(self):
        self._save()
        self._notify()

    def _notify(self):
        for cb in self._callbacks:
            cb()

    def on_change(self, callback: Callable[[], None]):
        self._callbacks.append(callback)

    def _save(self):

        if self._settings_yaml is None:
            return

        try:
            with open(self._settings_yaml, "w") as f:
                yaml.dump(self._settings, f, default_flow_style=False)
        except Exception:
            LOG.error(
                "Cannot save CliMetLab settings (%s)",
                self._settings_yaml,
                exc_info=True,
            )

    def _as_number(self, name, value, units, none_ok):
        if value is None and none_ok:
            return None

        value = str(value)
        # TODO: support floats
        m = re.search(r"^\s*(\d+)\s*([%\w]+)?\s*$", value)
        if m is None:
            raise ValueError(f"{name}: invalid number/unit {value}")
        value = int(m.group(1))
        if m.group(2) is None:
            return value
        unit = m.group(2)[0]
        if unit not in units:
            valid = ", ".join(units.keys())
            raise ValueError(f"{name}: invalid unit '{unit}', valid values are {valid}")
        return value * units[unit]

    def _as_seconds(self, name, value, none_ok):
        units = dict(s=1, m=60, h=3600, d=86400)
        return self._as_number(name, value, units, none_ok)

    def _as_percent(self, name, value, none_ok):
        units = {"%": 1}
        return self._as_number(name, value, units, none_ok)

    def _as_bytes(self, name, value, none_ok):
        units = {}
        n = 1
        for u in "KMGTP":
            n *= 1024
            units[u] = n
            units[u.lower()] = n

        return self._as_number(name, value, units, none_ok)

    @forward
    def temporary(self, name=None, *args, **kwargs):
        tmp = Settings(None, self._settings, self._callbacks)
        if name is not None:
            tmp.set(name, *args, **kwargs)
        return new_settings(tmp)


save = False
settings_yaml = os.path.expanduser("~/.climetlab/settings.yaml")

try:
    if not os.path.exists(DOT_CLIMETLAB):
        os.mkdir(DOT_CLIMETLAB, 0o700)
    if not os.path.exists(settings_yaml):
        with open(settings_yaml, "w") as f:
            yaml.dump(DEFAULTS, f, default_flow_style=False)
except Exception:
    LOG.error(
        "Cannot create CliMetLab settings directory, using defaults (%s)",
        settings_yaml,
        exc_info=True,
    )

settings = dict(**DEFAULTS)
try:
    with open(settings_yaml) as f:
        s = yaml.load(f, Loader=yaml.SafeLoader)
        settings.update(s)

    if s != settings:
        save = True

except Exception:
    LOG.error(
        "Cannot load CliMetLab settings (%s), reverting to defaults",
        settings_yaml,
        exc_info=True,
    )

SETTINGS = Settings(settings_yaml, settings)
if save:
    SETTINGS._save()
