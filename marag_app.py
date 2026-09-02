"""
Deployment entrypoint — runs the maintained demo in `app_1.py`.

This file used to be a second, older copy of the whole pipeline; that is
recorded in git history and in the commit that replaced it. This note is
about a second bug the replacement introduced.

Streamlit reruns the entrypoint *script* on every page load and every widget
interaction -- rebuilding the page from scratch is the framework's whole
model, so nothing persists between runs except what an app explicitly caches.
A plain `import app_1` looks like it does that, but only its first execution
does real work: Python imports the module once and caches it in
`sys.modules`, so every rerun after the first finds `app_1` already imported
and does nothing -- none of its `st.*` calls fire again. Streamlit still
reports the run as CONNECTED / notRunning, because nothing raised; the page
is simply never rebuilt. Confirmed by reloading a running local instance:
first load -- layout "wide", 8 elements, 482 characters of text; reload of
the same process -- layout "narrow" (app_1's set_page_config never re-ran),
zero elements, still CONNECTED. That is the same state the deployed URL was
in, and it explains why a brand-new process always looked fine to every local
test and probe run here -- each one only ever observed a first run.

`runpy.run_path` re-executes the target file as `__main__` on every call, so
every rerun does real work again, the same as if `app_1.py` were the
configured entrypoint directly. This file exists at all only because
Streamlit Cloud is configured to serve this filename; if that setting is ever
repointed to `app_1.py`, this file can go.
"""

import runpy
from pathlib import Path

# Resolved against this file rather than the working directory, so the
# entrypoint does not depend on where the server was started from.
runpy.run_path(str(Path(__file__).with_name("app_1.py")), run_name="__main__")
