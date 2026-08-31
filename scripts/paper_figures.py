#!/usr/bin/env python3
"""
Regenerate the paper's retrieval figures from the run artifacts.

Every number is read from results/<run_id>/per_query.jsonl rather than typed in,
so a figure cannot drift from the table it sits beside. Run ids are the same ones
results/PROVENANCE.md records.

    ./venv311/bin/python scripts/paper_figures.py

Writes paper/Figures/inversion-per-query.pdf and paper/Figures/localization.pdf
as vector PDFs. Both are designed to survive grayscale printing: series are
separated by hatch and marker shape as well as hue, and every bar is directly
labelled, so no claim in either figure rests on colour alone.
"""

from __future__ import annotations

import json
import os
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIGDIR = os.path.join(ROOT, "paper", "Figures")

# Validated categorical slots 1 and 2 (dataviz reference palette, light surface):
# CVD separation dE 24.7 protan, normal-vision 33.6, both >= 3:1 on the surface.
BLUE, ORANGE = "#2a78d6", "#eb6834"

# acmsmall's text block is 5.478in. Drawing at 6.6in means \includegraphics
# scales by 0.83 at \columnwidth, so the 9.5pt figure title renders near 7.9pt
# and the 8pt labels near 6.6pt -- quieter than the 9pt body, which is what a
# figure's own furniture should be. Drawing at the text width instead scales the
# art UP and makes every label louder than the prose around it. Note the fonts
# are NOT enlarged to compensate: doing both cancels out.
FIG_W = 6.6
INK, MUTED, GRID = "#1a1a19", "#5c5c5a", "#d8d8d5"

INVERSION_RUN = "run_1788128243_237950e265eb"

# The ablation rows, in the order the paper's table presents them. Each is the
# run that produced it; panel (a) retrieves the rewritten phrasing only, panel
# (b) issues both phrasings and unions the pools.
ABLATION = [
    ("a", "Substring\nboost",      "run_1788128243_237950e265eb"),
    ("a", "Okapi\nBM25",           "run_1788128704_237950e265eb"),
    ("a", "Embedding\ncosine",     "run_1788129232_237950e265eb"),
    ("b", "Substring\nboost",      "run_1788147304_237950e265eb"),
    ("b", "Substring\norig. rank", "run_1788148035_237950e265eb"),
    ("b", "Embedding\ncosine",     "run_1788133873_237950e265eb"),
]


# results/ is gitignored, so a fresh clone has no run directories. The rows the
# figures need are shipped under eval_harness/sample_results/paper_runs/ and used
# as a fallback, which is what makes these figures regenerable from the
# repository alone rather than only on the machine that produced the runs.
SEARCH = (
    os.path.join(ROOT, "results"),
    os.path.join(ROOT, "eval_harness", "sample_results", "paper_runs"),
)


def per_query_path(run_id: str) -> str:
    for base in SEARCH:
        cand = os.path.join(base, run_id, "per_query.jsonl")
        if os.path.exists(cand):
            return cand
    raise SystemExit(
        f"{run_id}: per_query.jsonl not found in results/ or "
        f"eval_harness/sample_results/paper_runs/")


def load(run_id: str) -> dict[str, dict[str, dict]]:
    """{system: {query_id: ir_dict}} for one run."""
    path = per_query_path(run_id)
    by: dict[str, dict[str, dict]] = {}
    with open(path) as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                name = row.get("system") or row.get("generator")
                by.setdefault(name, {})[row["query_id"]] = row.get("ir") or {}
    return by


def arm_mean(run_id: str, system: str, metric: str) -> float:
    vals = [ir[metric] for ir in load(run_id)[system].values() if ir.get(metric) is not None]
    return st.mean(vals)


def style(ax) -> None:
    """Recessive axes: no box, thin muted grid behind the marks."""
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, length=0, labelsize=8)
    ax.set_axisbelow(True)


def figure_inversion() -> str:
    """Per-question paired differences behind the inversion table.

    The job is polarity, one value per question, so the form is a sorted
    lollipop against a zero rule rather than a bar chart: the sign, and the
    absence of any positive value, are the whole claim. Ties are drawn as open
    squares at zero rather than omitted -- they are why the exact test has seven
    usable pairs instead of ten, which is what sets the p-value floor.
    """
    by = load(INVERSION_RUN)
    qs = sorted(set(by["marag"]) & set(by["single_agent"]))
    # Descending, so the ties land at the bottom next to their own label and the
    # deficits read top-down in increasing severity.
    diffs = sorted((by["marag"][q]["ndcg@3"] - by["single_agent"][q]["ndcg@3"]
                    for q in qs), reverse=True)
    mean = st.mean(diffs)
    n_ties = sum(1 for d in diffs if abs(d) < 1e-12)

    fig, ax = plt.subplots(figsize=(FIG_W, 3.3))
    for y, d in enumerate(diffs):
        tied = abs(d) < 1e-12
        if not tied:
            ax.plot([0, d], [y, y], color=BLUE, lw=2, solid_capstyle="round", zorder=2)
            ax.plot([d], [y], marker="o", ms=7, color=BLUE,
                    markeredgecolor="#fcfcfb", markeredgewidth=1.2, zorder=3)
        else:
            ax.plot([0], [y], marker="s", ms=6, color="#fcfcfb",
                    markeredgecolor=MUTED, markeredgewidth=1.4, zorder=3)

    ax.axvline(0, color=INK, lw=1.2, zorder=1)
    ax.axvline(mean, color=ORANGE, lw=2, ls=(0, (4, 2)), zorder=1)
    ax.annotate(f"mean {mean:+.3f}", xy=(mean, -0.45), xytext=(mean - 0.03, -0.45),
                color=ORANGE, fontsize=8, ha="right", va="center")
    ax.annotate(f"{n_ties} tied questions", xy=(0, n_ties / 2 - 0.5),
                xytext=(0.04, n_ties / 2 - 0.5), color=MUTED, fontsize=8,
                ha="left", va="center")

    ax.set_xlim(-1.12, 0.42)
    ax.set_ylim(-0.9, len(diffs) - 0.4)
    ax.set_yticks([])
    ax.set_xticks([-1.0, -0.75, -0.5, -0.25, 0.0])
    ax.set_xlabel("nDCG@3, multi-agent minus single-agent baseline, one mark per question",
                  color=MUTED, fontsize=8)
    ax.xaxis.grid(True, color=GRID, lw=0.6)
    style(ax)
    ax.set_title("No question favours the multi-agent pipeline",
                 color=INK, fontsize=9.5, loc="left", pad=6)

    out = os.path.join(FIGDIR, "inversion-per-query.pdf")
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def figure_localization() -> str:
    """MRR against nDCG@3 across the ranking and retrieval ablation.

    Small multiples rather than one six-group chart: the panel split IS the
    experimental variable (which phrasing was retrieved), so it belongs in the
    layout instead of in a divider line. Both measures share one 0-1 axis --
    never two scales -- so the divergence inside panel (a) and the joint jump in
    panel (b) are directly comparable.
    """
    rows = []
    for panel, label, run in ABLATION:
        rows.append((panel, label,
                     arm_mean(run, "marag", "mrr"),
                     arm_mean(run, "marag", "ndcg@3")))

    fig, axes = plt.subplots(1, 2, figsize=(FIG_W, 3.4), sharey=True)
    titles = {"a": "(a) rewritten phrasing only",
              "b": "(b) both phrasings, pools unioned"}
    w = 0.34
    for ax, panel in zip(axes, ("a", "b")):
        sub = [r for r in rows if r[0] == panel]
        x = list(range(len(sub)))
        b1 = ax.bar([i - w / 2 - 0.012 for i in x], [r[2] for r in sub], w,
                    color=ORANGE, edgecolor="#fcfcfb", linewidth=1.5, zorder=2)
        b2 = ax.bar([i + w / 2 + 0.012 for i in x], [r[3] for r in sub], w,
                    color=BLUE, edgecolor="#fcfcfb", linewidth=1.5,
                    hatch="///", zorder=2)
        for bars in (b1, b2):
            for b in bars:
                ax.annotate(f"{b.get_height():.2f}",
                            xy=(b.get_x() + b.get_width() / 2, b.get_height()),
                            xytext=(0, 2), textcoords="offset points",
                            ha="center", va="bottom", fontsize=7, color=MUTED)
        ax.set_xticks(x)
        ax.set_xticklabels([r[1] for r in sub], fontsize=7, color=MUTED,
                           linespacing=1.25)
        ax.set_title(titles[panel], fontsize=8, color=INK, pad=4)
        ax.set_ylim(0, 1.14)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.yaxis.grid(True, color=GRID, lw=0.6)
        style(ax)

    axes[0].legend(handles=[Patch(facecolor=ORANGE, label="MRR"),
                            Patch(facecolor=BLUE, hatch="///", label="nDCG@3")],
                   frameon=False, fontsize=8, labelcolor=MUTED,
                   loc="upper left", bbox_to_anchor=(0.0, 1.02), ncol=2,
                   handlelength=1.1, columnspacing=1.2)

    out = os.path.join(FIGDIR, "localization.pdf")
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    os.makedirs(FIGDIR, exist_ok=True)
    for fn in (figure_inversion, figure_localization):
        print("wrote", os.path.relpath(fn(), ROOT))


if __name__ == "__main__":
    main()
