"""
The deployment entrypoint must do real work on *every* rerun, not just the first.

Streamlit re-executes the entrypoint script on every page load and every
widget interaction; rebuilding the page from scratch is the framework's model.
A one-line `import app_1` satisfies that only once -- Python caches the module
in `sys.modules`, so the second and later runs bind an already-imported name
and execute none of its `st.*` calls. Nothing raises, so Streamlit reports the
run CONNECTED / notRunning and simply shows an empty page.

That is exactly what the deployed app was doing. Measured against a running
local instance: first load rendered layout "wide", 8 blocks, 482 characters;
reloading the same process gave layout "narrow" (app_1's set_page_config had
not re-run), 0 blocks. Every fresh process looked healthy, which is why it
survived local testing -- a new process only ever shows a first run.

The test runs the entrypoint twice in one process against a stand-in target
and asserts the target's body executed both times.
"""

import os
import runpy
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

ENTRYPOINT = os.path.join(ROOT, "marag_app.py")


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """The real entrypoint beside a stand-in `app_1.py` that counts its runs."""
    shutil.copy(ENTRYPOINT, tmp_path / "marag_app.py")
    (tmp_path / "app_1.py").write_text(
        "import pathlib\n"
        "p = pathlib.Path(__file__).with_name('runs.txt')\n"
        "p.write_text(str(int(p.read_text()) + 1) if p.exists() else '1')\n",
        encoding="utf-8")
    (tmp_path / "runs.txt").write_text("0", encoding="utf-8")
    # Run from elsewhere, so a CWD-relative lookup would fail to find the target.
    monkeypatch.chdir(tmp_path.parent)
    return tmp_path


def _run(sandbox):
    runpy.run_path(str(sandbox / "marag_app.py"), run_name="__main__")


def _count(sandbox):
    return int((sandbox / "runs.txt").read_text())


def test_first_run_executes_the_app(sandbox):
    _run(sandbox)
    assert _count(sandbox) == 1


def test_every_rerun_executes_the_app_again(sandbox):
    # The regression: with `import app_1`, this stays at 1 forever and the
    # page goes blank from the second page load onward.
    for expected in (1, 2, 3, 4):
        _run(sandbox)
        assert _count(sandbox) == expected, (
            f"rerun {expected} did not execute the app: the entrypoint is "
            "import-cached, so Streamlit rebuilds nothing and the page is blank")


def test_target_is_resolved_relative_to_the_entrypoint_not_the_cwd(sandbox):
    # Already guaranteed by the chdir in the fixture; asserted explicitly so a
    # future edit back to a bare relative path fails here with the reason.
    assert os.getcwd() != str(sandbox)
    _run(sandbox)
    assert _count(sandbox) == 1


def test_entrypoint_does_not_rely_on_a_plain_import(sandbox):
    src = open(ENTRYPOINT, encoding="utf-8").read()
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    # The docstring names `import app_1` when explaining the bug; the check is
    # that it is not what the module actually executes.
    body = code.split('"""')[-1]
    assert "import app_1" not in body
    assert "run_path" in body
