"""
Deployment entrypoint — renders the maintained demo in `app_1.py`.

This file used to be a second, older copy of the whole pipeline: its own
fetchers, its own evaluator, its own answer rendering. It had drifted badly
from `app_1.py`, and because Streamlit Community Cloud serves *this* file, the
drift was what the public URL showed. The reviewed demo answered

    Any critical Linux updates today?
    -> 1 release(s) found:
       • Error: HTTPSConnectionPool(host='releasetrain.io', port=443):
         Read timed out. (read timeout=10) v ()

from this file's copy of the fetchers, which returned a row whose product name
was the exception text -- while `app_1.py` had already been fixed to ground the
question, exclude advisories from release answers, and present a cited
paragraph. Nobody was going to keep two pipelines honest, and the one on the
public URL was the one nobody was editing.

So there is now one pipeline. Importing `app_1` runs it: a Streamlit script
*is* its module body, so the import renders the page.

The previous contents are in git (`git log --follow marag_app.py`) if the
smaller demo is ever wanted back -- but it should be restored as a thin view
over `app_1`'s functions, not as a second implementation of them.
"""

import app_1  # noqa: F401  -- the import is the render
