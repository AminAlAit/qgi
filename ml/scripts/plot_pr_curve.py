#!/usr/bin/env python3
"""
plot_pr_curve.py — V1.9.1 diagnostic chart generator for methodology page (#380).

Reads backtest_v19_results.json and emits four PNG charts into --outdir:
  1. pr_operating_points.png — partial PR curve (3 operating points/tier, test)
  2. per_tier_f1_bars.png    — grouped bars, val/test F1 + prec/recall
  3. bss_bars.png             — validation vs test Brier Skill Score per tier
  4. margin_trajectory.png   — V1.8 -> V1.8.1 -> V1.9 margin-over-persistence

Standalone. Uses matplotlib Agg backend. Chart footer watermarks every PNG.

CLI:
  python plot_pr_curve.py --input backtest_v19_results.json --outdir .tmp/charts/
"""

import argparse
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


TIERS = ['S', 'M', 'L', 'XL']
TIER_COLORS = {'S': '#1f77b4', 'M': '#2ca02c', 'L': '#ff7f0e', 'XL': '#d62728'}

FOOTER = ("QGI — V1.9 backtest (cutoff val=2015, test=2020). "
          "Chart generated 2026-04-22.")


def add_footer(fig):
    fig.text(0.5, 0.01, FOOTER, ha='center', va='bottom',
             fontsize=7, color='#666666', style='italic')


def safe_get(d, *keys, default=0):
    cur = d
    for k in keys:
        if cur is None or not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur is not None else default


def plot_pr_operating_points(data, outpath):
    """3-point PR curve per tier (k=10, 50, 100) from test phase."""
    test_metrics = safe_get(data, 'test', 'metrics', default={})

    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    axes = axes.flatten()

    for idx, tier in enumerate(TIERS):
        ax = axes[idx]
        m = test_metrics.get(tier) or {}
        n_gt = m.get('n_ground_truth', 0) or 0

        ks = [10, 50, 100]
        xs, ys = [], []
        for k in ks:
            p = m.get(f'precision_at_{k}', 0) or 0
            if n_gt > 0:
                r = min((k * p) / n_gt, 1.0)
            else:
                r = 0.0
            xs.append(r)
            ys.append(p)

        ax.plot(xs, ys, marker='o', linewidth=2, color=TIER_COLORS[tier])
        for k, x, y in zip(ks, xs, ys):
            ax.annotate(f'k={k}', xy=(x, y), xytext=(5, 5),
                        textcoords='offset points', fontsize=9)

        ax.set_xlim(0, max(0.05, max(xs) * 1.2) if xs else 1)
        ax.set_ylim(0, 1.05)
        ax.set_xlabel('Recall (approx, k*P@k / n_gt)')
        ax.set_ylabel('Precision@k')
        ax.set_title(f'Tier {tier} (n_gt={n_gt})')
        ax.grid(True, alpha=0.3)

    fig.suptitle(
        "V1.9 Precision-Recall operating points (test phase, 2020)\n"
        "Partial — 3 operating points per tier. "
        "Full 50-threshold curve deferred to V1.9.2 rerun.",
        fontsize=11,
    )
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])
    add_footer(fig)
    fig.savefig(outpath, dpi=150)
    plt.close(fig)


def plot_per_tier_f1_bars(data, outpath):
    """Grouped bar: val F1 / test F1 / test precision / test recall per tier."""
    val_m = safe_get(data, 'validation', 'metrics', default={})
    test_m = safe_get(data, 'test', 'metrics', default={})
    persist_f1 = safe_get(data, 'test', 'persistence', 'f1', default=0)

    groups = ['Val F1', 'Test F1', 'Test Precision', 'Test Recall']
    x = np.arange(len(TIERS))
    width = 0.2

    fig, ax = plt.subplots(figsize=(11, 6))

    val_f1 = [safe_get(val_m, t, 'f1') for t in TIERS]
    test_f1 = [safe_get(test_m, t, 'f1') for t in TIERS]
    test_p = [safe_get(test_m, t, 'precision') for t in TIERS]
    test_r = [safe_get(test_m, t, 'recall') for t in TIERS]

    ax.bar(x - 1.5 * width, val_f1, width, label='Val F1', color='#4C72B0')
    ax.bar(x - 0.5 * width, test_f1, width, label='Test F1', color='#DD8452')
    ax.bar(x + 0.5 * width, test_p, width, label='Test Precision', color='#55A868')
    ax.bar(x + 1.5 * width, test_r, width, label='Test Recall', color='#C44E52')

    ax.axhline(y=persist_f1, linestyle='--', color='gray',
               label=f'Persistence F1 ({persist_f1:.3f})')

    ax.set_xticks(x)
    ax.set_xticklabels(TIERS)
    ax.set_xlabel('Tier')
    ax.set_ylabel('Score')
    ax.set_ylim(0, 1.05)
    ax.set_title('V1.9 per-tier F1/precision/recall '
                 '(validation 2015 locked -> test 2020)')
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3, axis='y')

    fig.tight_layout(rect=[0, 0.03, 1, 1])
    add_footer(fig)
    fig.savefig(outpath, dpi=150)
    plt.close(fig)


def plot_bss_bars(data, outpath):
    """Val vs Test BSS per tier."""
    val_m = safe_get(data, 'validation', 'metrics', default={})
    test_m = safe_get(data, 'test', 'metrics', default={})

    x = np.arange(len(TIERS))
    width = 0.35
    val_bss = [safe_get(val_m, t, 'brier_skill_score') for t in TIERS]
    test_bss = [safe_get(test_m, t, 'brier_skill_score') for t in TIERS]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(x - width / 2, val_bss, width, label='Validation BSS',
           color='#4C72B0')
    ax.bar(x + width / 2, test_bss, width, label='Test BSS',
           color='#C44E52')
    ax.axhline(y=0, color='black', linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(TIERS)
    ax.set_xlabel('Tier')
    ax.set_ylabel('Brier Skill Score')
    ax.set_title('V1.9 Brier Skill Score per tier — validation positive on '
                 'S/M, test negative across all tiers (calibration ceiling).')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    for i, v in enumerate(val_bss):
        ax.text(i - width / 2, v + (0.005 if v >= 0 else -0.02),
                f'{v:.3f}', ha='center', fontsize=8)
    for i, v in enumerate(test_bss):
        ax.text(i + width / 2, v + (0.005 if v >= 0 else -0.02),
                f'{v:.3f}', ha='center', fontsize=8)

    fig.tight_layout(rect=[0, 0.03, 1, 1])
    add_footer(fig)
    fig.savefig(outpath, dpi=150)
    plt.close(fig)


def plot_margin_trajectory(outpath):
    """Hardcoded: V1.8 -> V1.8.1 -> V1.9 margin-over-persistence."""
    versions = ['V1.8\n(2026-04-12)', 'V1.8.1\n(2026-04-12)', 'V1.9\n(2026-04-21)']
    model_f1 = [0.506, 0.480, 0.481]
    persist_f1 = [0.438, 0.336, 0.292]
    margin = [0.067, 0.143, 0.189]

    fig, ax1 = plt.subplots(figsize=(11, 6))
    x = np.arange(len(versions))

    ax1.plot(x, model_f1, marker='o', linewidth=2, label='Model F1',
             color='#4C72B0')
    ax1.plot(x, persist_f1, marker='s', linewidth=2,
             label='Persistence F1', color='#C44E52')
    ax1.set_xticks(x)
    ax1.set_xticklabels(versions)
    ax1.set_ylabel('F1')
    ax1.set_ylim(0, 0.6)
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(x, margin, marker='^', linewidth=2, linestyle='--',
             label='Margin (model - persistence)', color='#55A868')
    ax2.set_ylabel('Margin')
    ax2.set_ylim(0, 0.25)

    for xi, mg in zip(x, margin):
        ax2.annotate(f'+{mg:.3f}', xy=(xi, mg), xytext=(5, 5),
                     textcoords='offset points', fontsize=9,
                     color='#2d7a3f')

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='center left')

    ax1.set_title(
        "Margin-over-persistence trajectory.\n"
        "V1.9.1 shipped 2026-04-22 but does not re-measure "
        "(tier-labeling change only; backtest metrics identical to V1.9).",
        fontsize=10,
    )

    fig.tight_layout(rect=[0, 0.03, 1, 1])
    add_footer(fig)
    fig.savefig(outpath, dpi=150)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--outdir', required=True)
    args = ap.parse_args()

    with open(args.input, 'r') as f:
        data = json.load(f)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    outputs = {
        'pr_operating_points.png': lambda p: plot_pr_operating_points(data, p),
        'per_tier_f1_bars.png':    lambda p: plot_per_tier_f1_bars(data, p),
        'bss_bars.png':            lambda p: plot_bss_bars(data, p),
        'margin_trajectory.png':   lambda p: plot_margin_trajectory(p),
    }

    for name, fn in outputs.items():
        path = outdir / name
        fn(str(path))
        print(f"wrote {path} ({os.path.getsize(path)} bytes)")


if __name__ == '__main__':
    main()
