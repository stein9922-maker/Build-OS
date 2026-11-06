"""Stand-ins for Streamlit and Plotly so UI/figure code can run headlessly in tests.

IMPORTANT LIMITS: these only prove that OUR code executes and passes the values we expect.
They cannot prove that real Streamlit/Plotly accept those calls or how anything looks.
"""
from __future__ import annotations

import functools
import sys
import types
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MISSING = object()


# ----------------------------------------------------------------- module swapping helpers
@contextmanager
def swapped_modules(replacements: dict):
    """Temporarily replace entries in sys.modules, restoring them afterwards."""
    saved = {name: sys.modules.get(name, _MISSING) for name in replacements}
    sys.modules.update(replacements)
    try:
        yield
    finally:
        for name, original in saved.items():
            if original is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


# ----------------------------------------------------------------------------------- plotly
class Trace:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class Bar(Trace):
    pass


class Scatter(Trace):
    pass


class Figure:
    def __init__(self):
        self.traces, self.layout = [], {}

    def add_trace(self, trace):
        self.traces.append(trace)

    def update_layout(self, **kwargs):
        self.layout.update(kwargs)


def _fake_plotly_modules() -> dict:
    graph_objects = types.ModuleType("plotly.graph_objects")
    graph_objects.Figure, graph_objects.Bar, graph_objects.Scatter = Figure, Bar, Scatter
    root = types.ModuleType("plotly")
    root.graph_objects = graph_objects
    return {"plotly": root, "plotly.graph_objects": graph_objects}


@contextmanager
def fake_plotly():
    with swapped_modules(_fake_plotly_modules()):
        yield


@contextmanager
def missing_plotly():
    """Make `import plotly...` fail, as on a machine without Plotly."""
    with swapped_modules({"plotly": None, "plotly.graph_objects": None}):
        yield


# --------------------------------------------------------------------------------- streamlit
class RerunRequested(Exception):
    """Raised by the fake st.rerun(), like the real one interrupts the script."""


class FakeStreamlit(types.ModuleType):
    """A headless 'Streamlit': buttons are never pressed, inputs return their defaults,
    and every call is recorded in `self.calls` as (name, args, kwargs)."""

    _CONTEXT_METHODS = {"form", "expander", "container", "spinner", "tab"}

    def __init__(self):
        super().__init__("streamlit")
        self.calls: list[tuple] = []
        self.session_state: dict = {}
        self.sidebar = self  # st.sidebar.x(...) behaves like st.x(...)

    # context-manager support so `with st.form(...)`, `with tab:` etc. work
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self if name in self._CONTEXT_METHODS else None

        return record

    # ---- helpers for assertions ----
    def of(self, name: str) -> list[tuple]:
        return [(args, kwargs) for n, args, kwargs in self.calls if n == name]

    def texts(self, name: str) -> list[str]:
        return [str(args[0]) for args, _kw in self.of(name) if args]

    # ---- widgets that must return something sensible ----
    def cache_resource(self, func=None, **_kw):
        return functools.cache(func) if func is not None else functools.cache

    def selectbox(self, *args, **kwargs):
        self.calls.append(("selectbox", args, kwargs))
        options = list(kwargs.get("options", args[1] if len(args) > 1 else []))
        key = kwargs.get("key")
        if key is not None and key in self.session_state:
            return self.session_state[key]
        value = options[kwargs.get("index", 0)] if options else None
        if key is not None:
            self.session_state[key] = value
        return value

    def _value_widget(self, name, args, kwargs, default):
        self.calls.append((name, args, kwargs))
        return kwargs.get("value", default)

    def text_input(self, *args, **kwargs):
        return self._value_widget("text_input", args, kwargs, "")

    def text_area(self, *args, **kwargs):
        return self._value_widget("text_area", args, kwargs, "")

    def number_input(self, *args, **kwargs):
        return self._value_widget("number_input", args, kwargs, 0)

    def date_input(self, *args, **kwargs):
        return self._value_widget("date_input", args, kwargs, None)

    def checkbox(self, *args, **kwargs):
        self.calls.append(("checkbox", args, kwargs))
        return False

    def button(self, *args, **kwargs):
        self.calls.append(("button", args, kwargs))
        return False

    def form_submit_button(self, *args, **kwargs):
        self.calls.append(("form_submit_button", args, kwargs))
        return False

    def columns(self, spec, *args, **kwargs):
        self.calls.append(("columns", (spec, *args), kwargs))
        return tuple(self for _ in range(spec if isinstance(spec, int) else len(spec)))

    def tabs(self, labels, *args, **kwargs):
        self.calls.append(("tabs", (labels, *args), kwargs))
        return tuple(self for _ in labels)

    def rerun(self):
        self.calls.append(("rerun", (), {}))
        raise RerunRequested()


@contextmanager
def headless_streamlit(plotly: str = "fake"):
    """Run code that does `import streamlit` against FakeStreamlit.

    plotly: 'fake' (stand-in Plotly), 'missing' (import fails) or 'real' (leave untouched).
    Any `webui` modules imported inside the block are discarded afterwards so they never keep
    a reference to the fake.
    """
    fake = FakeStreamlit()
    replacements = {"streamlit": fake}
    if plotly == "fake":
        replacements.update(_fake_plotly_modules())
    elif plotly == "missing":
        replacements.update({"plotly": None, "plotly.graph_objects": None})

    def web_modules():
        return {n for n in sys.modules if n == "webui" or n.startswith("webui.")}

    before = web_modules()
    with swapped_modules(replacements):
        try:
            yield fake
        finally:
            for name in web_modules() - before:
                del sys.modules[name]
