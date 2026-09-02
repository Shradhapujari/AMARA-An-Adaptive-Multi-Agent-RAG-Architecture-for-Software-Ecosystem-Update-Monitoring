"""
Deployment entrypoint — renders the maintained demo in `app_1.py`.

This file used to be a second, older copy of the whole pipeline: its own
fetchers, its own evaluator, its own answer rendering. It had drifted badly
from `app_1.py`, and because Streamlit Community Cloud serves *this* file, the
drift was what the public URL showed -- a release whose name was an
`HTTPSConnectionPool ... Read timed out` exception, months after `app_1.py`
had been fixed. There is now one pipeline; importing `app_1` runs it, because
a Streamlit script *is* its module body.

The wrapper around that import is a deploy probe, and it is here because the
deployed app went blank while every environment it could be reproduced in ran
it fine: a clean venv on the pinned requirements with Streamlit 1.63.0 renders
this file correctly, and so does the developer's own machine. A blank page
means nothing reached the browser, so nothing said why. The probe makes the
deployment state its own failure:

  * the "Starting" marker paints before the import, so a page frozen on it
    means the import hung rather than raised -- a distinction the blank page
    destroys;
  * an exception is rendered into the page instead of only into logs that
    need a dashboard login to read.

`set_page_config` has to be the first Streamlit call, so it is made here and
neutralised for the duration of the import -- calling it twice is an error,
and `app_1` rightly calls it itself. The arguments are copied from `app_1`, so
the page is identical to the one it configures.

Remove the probe once the deployment is healthy: the import alone is the
supported behaviour, and `git log` holds this note if it is ever needed again.
"""

import traceback

import streamlit as st

st.set_page_config(
    page_title="Multi-Agent RAG System — Software Ecosystem Monitor",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

_boot = st.empty()
_boot.info("Starting — importing the pipeline…")

_set_page_config = st.set_page_config
st.set_page_config = lambda *a, **k: None      # app_1 calls it again; already done

try:
    import app_1  # noqa: F401  -- the import is the render
    _boot.empty()
except BaseException:                           # noqa: BLE001 - shown, not swallowed
    _boot.empty()
    st.error("The app failed to start. Traceback below.")
    st.code(traceback.format_exc(), language="text")
    raise
finally:
    st.set_page_config = _set_page_config
