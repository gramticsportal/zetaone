#!/usr/bin/env python3
"""Render the one-page technical summary to PDF and PNG.

No LaTeX toolchain is needed: matplotlib's mathtext renders the equations. The LaTeX
source alongside this file is kept in step for anyone compiling with a real engine.

Vertical placement is done with a cursor per block rather than hand-chosen offsets, so
adding a line pushes what follows instead of drawing on top of it.

Usage:
  python docs/onepager/build_onepager.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent

INK, MUTED, RULE = "#12181f", "#5b6672", "#c9d2da"
DET, MOD, CAS, BAD = "#1f5fa8", "#b8690f", "#1d7a4f", "#a32b2b"
PANEL, PANEL_EDGE = "#f4f7fa", "#dbe3ea"


class Cursor:
    """Top-down text placer. Every write returns the space it consumed."""

    def __init__(self, fig, x, top, width):
        self.fig, self.x, self.y, self.width = fig, x, top, width

    def write(self, s, size=5.9, color=INK, weight="normal", style="normal", gap=0.004):
        n = s.count("\n") + 1
        self.fig.text(self.x, self.y, s, fontsize=size, color=color, fontweight=weight,
                      style=style, ha="left", va="top", zorder=4, linespacing=1.5)
        self.y -= n * (size * 0.00196) + gap
        return self.y

    def skip(self, amount=0.006):
        self.y -= amount
        return self.y


def box(fig, x, y, w, h, fc=PANEL, ec=PANEL_EDGE, lw=0.8, r=0.008, z=1):
    fig.patches.append(FancyBboxPatch(
        (x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
        transform=fig.transFigure, facecolor=fc, edgecolor=ec, linewidth=lw, zorder=z))


def txt(fig, x, y, s, size=6.0, color=INK, weight="normal", ha="left", va="top",
        style="normal", z=4):
    fig.text(x, y, s, fontsize=size, color=color, fontweight=weight, ha=ha, va=va,
             style=style, zorder=z, linespacing=1.5)


def arrow(fig, p1, p2, color=MUTED, lw=1.0, cs=None, z=3):
    fig.patches.append(FancyArrowPatch(
        p1, p2, transform=fig.transFigure, arrowstyle="-|>", mutation_scale=6,
        color=color, linewidth=lw, zorder=z, shrinkA=0, shrinkB=0,
        connectionstyle=cs or "arc3,rad=0"))


def node(fig, x, y, w, h, label, sub=None, fc="#ffffff", ec=MUTED, tc=INK, size=6.2):
    box(fig, x, y, w, h, fc=fc, ec=ec, lw=0.9, r=0.005, z=2)
    fig.text(x + w / 2, y + h / 2 + (0.006 if sub else 0), label, fontsize=size, color=tc,
             ha="center", va="center", fontweight="bold", zorder=4)
    if sub:
        fig.text(x + w / 2, y + h / 2 - 0.008, sub, fontsize=5.2, color=MUTED,
                 ha="center", va="center", zorder=4)


def rule(fig, x1, x2, y, color=RULE, lw=0.8):
    fig.add_artist(plt.Line2D([x1, x2], [y, y], transform=fig.transFigure,
                              color=color, linewidth=lw, zorder=2))


L, R = 0.055, 0.945
W = R - L


def build() -> plt.Figure:
    fig = plt.figure(figsize=(8.27, 11.69), dpi=200)
    fig.patch.set_facecolor("white")

    # ------------------------------------------------------------- header
    txt(fig, L, 0.988, "ZetaOne", size=20, weight="bold")
    txt(fig, L + 0.182, 0.9835, "deterministic policy engine  +  learned sensor",
        size=9.2, color=MUTED)
    rule(fig, L, R, 0.9575, color=INK, lw=1.6)
    txt(fig, L, 0.9525,
        "Ad Corpus v0.12   ·   172 clauses · 137 rules · 54 canonical · 28 sources   ·   "
        "1,588 precedents   ·   every figure below is the held-out $\\mathit{test}$ split",
        size=6.4, color=MUTED)

    # ------------------------------------------------------- architecture
    txt(fig, L, 0.937, "ARCHITECTURE", size=7.2, weight="bold", color=MUTED)
    ab, at = 0.716, 0.928
    box(fig, L, ab, W, at - ab, fc="#fbfcfd")

    ry, rh = 0.868, 0.040
    node(fig, 0.070, ry, 0.100, rh, "Asset", "text · image · A/V")
    node(fig, 0.190, ry, 0.120, rh, "Sensors", "VLM · OCR · ASR")
    node(fig, 0.330, ry, 0.120, rh, "Document", "normalised + spans")
    arrow(fig, (0.170, ry + rh / 2), (0.190, ry + rh / 2))
    arrow(fig, (0.310, ry + rh / 2), (0.330, ry + rh / 2))

    t1b, t1h = 0.762, 0.084
    box(fig, 0.070, t1b, 0.545, t1h, fc="#eef4fb", ec=DET, lw=1.1)
    txt(fig, 0.079, t1b + t1h - 0.006, "TIER 1 — DETERMINISTIC", size=6.2,
        weight="bold", color=DET)
    steps = [("Fold", "homoglyph·leet"), ("Packs", "54 · 1,298"), ("Gate", "23 licences"),
             ("Predicates", "APR · age"), ("Negation", "6 packs")]
    nx, nw, ngap = 0.079, 0.098, 0.011
    for i, (lab, sub) in enumerate(steps):
        x = nx + i * (nw + ngap)
        node(fig, x, t1b + 0.010, nw, 0.042, lab, sub, ec=DET, tc=DET, size=5.9)
        if i:
            arrow(fig, (x - ngap, t1b + 0.031), (x, t1b + 0.031), color=DET)
    # elbow from Document down and left into the tier-1 chain
    arrow(fig, (0.390, ry), (0.128, t1b + t1h), color=DET,
          cs="angle,angleA=-90,angleB=0,rad=4")

    node(fig, 0.640, t1b + 0.010, 0.112, 0.042, "Violations", "+ evidence", ec=DET, tc=DET)
    arrow(fig, (0.615, t1b + 0.031), (0.640, t1b + 0.031), color=DET)
    node(fig, 0.778, t1b + 0.010, 0.112, 0.042, "Verdict", "risk · audit", ec=INK)
    arrow(fig, (0.752, t1b + 0.031), (0.778, t1b + 0.031))

    box(fig, 0.640, ry - 0.004, 0.300, rh + 0.008, fc="#fdf5ea", ec=MOD, lw=1.1)
    txt(fig, 0.650, ry + rh + 0.000, "TIER 2 — LEARNED SENSOR", size=6.0,
        weight="bold", color=MOD)
    txt(fig, 0.650, ry + rh - 0.014,
        "runs only where Tier 1 is silent — 50% of traffic\n"
        "recommends HUMAN REVIEW, never a violation",
        size=5.4, color=MOD)
    arrow(fig, (0.618, t1b + t1h - 0.004), (0.660, ry - 0.004), color=MOD)
    txt(fig, 0.628, ry - 0.012, "silent", size=5.0, color=MOD, style="italic")

    node(fig, 0.778, 0.722, 0.162, 0.034, "Review queue", "human decides",
         ec=MOD, tc=MOD, size=6.0)
    arrow(fig, (0.912, ry - 0.004), (0.912, 0.756), color=MOD)

    txt(fig, 0.079, 0.7495,
        "Models are sensors: they extract signals and never decide a verdict.",
        size=6.0, color=MUTED, style="italic")

    # -------------------------------------------------- three configurations
    txt(fig, L, 0.705, "THE THREE CONFIGURATIONS", size=7.2, weight="bold", color=MUTED)
    pb, pt = 0.452, 0.696
    pw, pgap = 0.286, 0.016
    xs = [L, L + pw + pgap, L + 2 * (pw + pgap)]

    def panel(x, colour, face, title, tagline, body, headline, sub):
        box(fig, x, pb, pw, pt - pb, fc=face, ec=colour, lw=1.1)
        c = Cursor(fig, x + 0.013, pt - 0.011, pw - 0.026)
        c.write(title, size=8.0, weight="bold", color=colour, gap=0.005)
        c.write(tagline, size=6.0, color=MUTED, style="italic", gap=0.008)
        for s, kw in body:
            c.write(s, **kw)
        rule(fig, x + 0.013, x + pw - 0.013, pb + 0.042)
        txt(fig, x + 0.013, pb + 0.034, headline, size=7.2, weight="bold", color=colour)
        txt(fig, x + 0.013, pb + 0.016, sub, size=6.0, color=MUTED)

    panel(
        xs[0], DET, "#f6f9fd", "DETERMINISTIC", "Guarded licensing, not classification.",
        [("$V(d,p)=T(d,p)\\wedge\\neg E(d)\\wedge C(d)$\n"
          "$\\qquad\\wedge\\ \\neg\\exists c\\in Q(p):L_c(W(d))$",
          dict(size=6.6, gap=0.005)),
         ("monotone in triggers, antitone in licences",
          dict(size=5.5, color=MUTED, style="italic", gap=0.009)),
         ("825 terms · 287 phrases · 186 regex\n"
          "23 licence classes · 146 patterns\n"
          "window $W=240$ chars around the trigger\n"
          "36 packs licensable · 18 absolute",
          dict(size=6.0, gap=0.010)),
         ("Risk   $R=\\min(100,\\ \\sum_i \\pi(s_i)\\,\\mu(c_i))$",
          dict(size=6.4, gap=0.004)),
         ("$\\pi$: 100/50/20/5    $\\mu$: 1.0/0.7/0.3",
          dict(size=5.5, color=MUTED, gap=0.004))],
        "P 0.826    R 0.593    F1 0.690", "specificity 0.704   ·   ~5 ms/row")

    panel(
        xs[1], MOD, "#fdf8f1", "LANGUAGE MODEL", "Linear, inspectable, reproducible.",
        [("$x=[\\,\\hat{n}(d)\\ ;\\ \\phi(d)\\,]\\in\\mathbb{R}^{20010}$\n"
          "$p=\\sigma(w^{\\top}x+b)$", dict(size=6.6, gap=0.005)),
         ("$\\hat{n}$: L2-normalised 1–2gram + char-4gram\n$\\phi$: 10 structural flags",
          dict(size=5.5, color=MUTED, gap=0.009)),
         ("$J=-\\sum_i\\alpha_i[\\,y_i\\log p_i+(1-y_i)\\log(1-p_i)\\,]$\n"
          "$\\qquad\\qquad+\\ \\frac{\\lambda}{2}\\|w\\|^2$", dict(size=6.2, gap=0.007)),
         ("$w^{(0)}=0$ · full batch · $\\eta_t=\\eta/(1+t/100)$ · 400 it",
          dict(size=5.7, gap=0.004)),
         ("convex ⇒ path-independent ⇒ bit-identical weights",
          dict(size=5.5, color=MUTED, style="italic", gap=0.007)),
         ("242 KB .npz · numpy only · no torch · offline",
          dict(size=5.7, color=MUTED, gap=0.004))],
        "P 0.828    R 0.869    F1 0.848", "specificity 0.571   ·   dev AUC 0.837")

    panel(
        xs[2], CAS, "#f2faf6", "BOTH (CASCADE)", "Tier 2 asked only where Tier 1 is silent.",
        [("$d\\vee(s\\wedge\\neg d)\\ \\equiv\\ d\\vee s$", dict(size=6.6, gap=0.004)),
         ("the same predicate — a cascade earns its name\non cost, not on the decision",
          dict(size=5.5, color=MUTED, style="italic", gap=0.010)),
         ("$\\mathbb{E}[T]=\\sum_i \\left(\\prod_{j<i}e_j\\right) t_i$",
          dict(size=6.6, gap=0.004)),
         ("escalation rate $e$ dominates, not tier speed",
          dict(size=5.5, color=MUTED, style="italic", gap=0.010)),
         ("Where Tier 1 is silent (339 of 684 rows):\n"
          "   recovers 86% of the violations it missed\n"
          "   false-alarms on 38% of the clean copy",
          dict(size=6.0, gap=0.009)),
         ("confirmed $(d\\wedge s)$:   P 0.883 · spec 0.837",
          dict(size=5.9, color=CAS, gap=0.004))],
        "P 0.799    R 0.942    F2 0.909", "specificity 0.438   ·   recall +58%")

    # ------------------------------------------------------------- maths
    txt(fig, L, 0.4455, "THE MATHEMATICS THAT DECIDES WHAT THESE NUMBERS MEAN",
        size=7.2, weight="bold", color=MUTED)
    mb, mt = 0.224, 0.436
    box(fig, L, mb, W, mt - mb, fc="#fbfcfd")
    cw, cgap = 0.286, 0.016
    cxs = [L + 0.014, L + 0.014 + cw + cgap, L + 0.014 + 2 * (cw + cgap)]
    row_tops = [mt - 0.012, mt - 0.142]

    cells = [
        (0, 0, "1 · Why this is not a classifier", INK,
         [("$I(\\mathrm{words}\\,;\\,y)\\approx 0$", dict(size=6.4, gap=0.006)),
          ("85% of compliant minimal pairs carry the same\n"
           "trigger as the violation they pair with, by\n"
           "construction. Vocabulary cannot separate them;\n"
           "the licence gate can. The information is in the\n"
           "structure, not in the words.",
           dict(size=5.7, color=MUTED))]),
        (1, 0, "3 · Variance is clustered", BAD,
         [("$\\mathrm{SE}=\\sqrt{p(1-p)/G},\\qquad G=128$", dict(size=6.4, gap=0.006)),
          ("Rows inside one enforcement case are not\n"
           "independent — they restate one claim. Effective\n"
           "$n$ is 128 cases, not 347 rows.",
           dict(size=5.7, color=MUTED, gap=0.006)),
          ("$P=0.824\\pm0.066$,  not  $\\pm0.040$",
           dict(size=6.2, color=BAD, weight="bold", gap=0.005)),
          ("design effect $1.65\\times$ — compare engines with a\n"
           "cluster bootstrap over cases, or manufacture\n"
           "significance from correlated rows.",
           dict(size=5.7, color=MUTED))]),
        (2, 0, "5 · Evidence is double-counted", BAD,
         [("now:   $R=\\sum_i \\pi_i\\mu_i$   (assumes independence)",
           dict(size=5.9, gap=0.006)),
          ("\"cure for cancer\" — three words, one span —\n"
           "fires 8 packs and scores 100 out of 100. That\n"
           "measures how densely the pack library covers a\n"
           "phrase, not how bad the ad is.",
           dict(size=5.7, color=MUTED, gap=0.006)),
          ("fix:   $P=1-\\prod_i(1-p_i)$   over distinct spans",
           dict(size=6.2, color=CAS, weight="bold", gap=0.005)),
          ("bounded, order-independent, and immune to\nadding redundant packs.",
           dict(size=5.7, color=MUTED))]),
        (0, 1, "2 · Calibration is empirical Bayes", INK,
         [("$\\hat{c}=\\frac{k+m\\pi}{n+m},\\qquad m=8$", dict(size=6.4, gap=0.007)),
          ("Beta-Binomial posterior mean. Every regex shipped\n"
           "at 0.88; measured, they range 0.19 to 0.64.",
           dict(size=5.7, color=MUTED))]),
        (1, 1, "4 · The loss is asymmetric", INK,
         [("$L=c_{FN}\\cdot FN + c_{FP}\\cdot FP,\\quad c_{FN}>c_{FP}$",
           dict(size=5.9, gap=0.006)),
          ("A missed violation costs more than a flagged ad,\n"
           "so report $F_2=\\frac{5PR}{4P+R}$ rather than $F_1$.",
           dict(size=5.7, color=MUTED))]),
        (2, 1, "6 · The split unit is the case", INK,
         [("1,589 rows  ←  827 cases  ⇒  split by case",
           dict(size=5.9, gap=0.006)),
          ("578 / 121 / 128 groups. 13 north-star cases are\n"
           "locked to test, so a harvested sibling can never\n"
           "leak into training.",
           dict(size=5.7, color=MUTED))]),
    ]
    for col, row, title, colour, body in cells:
        c = Cursor(fig, cxs[col], row_tops[row], cw)
        c.write(title, size=6.6, weight="bold", color=colour, gap=0.006)
        for s, kw in body:
            c.write(s, **kw)

    # ------------------------------------------- honesty + results (bottom)
    bb, bt = 0.068, 0.205
    txt(fig, L, 0.214, "WHAT THE NUMBERS DO NOT SAY", size=7.2, weight="bold", color=BAD)
    txt(fig, 0.523, 0.214, "HELD-OUT RESULTS", size=7.2, weight="bold", color=INK)

    hw = 0.440
    box(fig, L, bb, hw, bt - bb, fc="#fdf4f4", ec="#e8c9c9", lw=1.0)
    c = Cursor(fig, L + 0.014, bt - 0.011, hw - 0.028)
    c.write("The model did not learn the rule.", size=7.0, weight="bold", color=BAD, gap=0.006)
    c.write("Recall by source on the held-out split.   * in-sample: the miner\n"
            "tokenised those rows straight into pack terms.",
            size=5.6, color=MUTED, gap=0.007)
    ty = c.y
    txt(fig, L + 0.014, ty, "source", size=5.6, color=MUTED, weight="bold")
    txt(fig, L + 0.330, ty, "det", size=5.6, color=DET, weight="bold", ha="right")
    txt(fig, L + 0.420, ty, "model", size=5.6, color=MOD, weight="bold", ha="right")
    rows = [("harvested — enforcement wording", "0.490", "0.908", INK),
            ("precedents — expert, north star", "0.932*", "0.864", INK),
            ("seed — expert, third register", "0.732", "0.772", INK),
            ("compliant pairs — specificity", "—", "0.564", BAD)]
    for i, (lab, d, m, col) in enumerate(rows):
        yy = ty - 0.012 - i * 0.0125
        txt(fig, L + 0.014, yy, lab, size=5.7, color=col)
        txt(fig, L + 0.330, yy, d, size=5.7, color=col, ha="right")
        txt(fig, L + 0.420, yy, m, size=5.7, color=col, ha="right", weight="bold")
    c2 = Cursor(fig, L + 0.014, ty - 0.012 - len(rows) * 0.0125 - 0.006, hw - 0.028)
    c2.write("0.564 on minimal pairs is a coin flip. It learned that enforcement-quoted\n"
             "copy reads differently from a rewrite — not the rule. Its own explain()\n"
             "agrees: top features on escalated copy are \"c: the\" and \"w:the\".",
             size=5.7, gap=0.006)

    rx = 0.523
    rw = R - rx
    box(fig, rx, bb, rw, bt - bb, fc="#fbfcfd")
    c = Cursor(fig, rx + 0.014, bt - 0.011, rw - 0.028)
    c.write("684 rows · 128 enforcement cases · test split", size=5.8, color=MUTED, gap=0.008)
    ty = c.y
    cols = [rx + 0.014, rx + 0.212, rx + 0.264, rx + 0.316, rx + 0.368, rx + 0.418]
    for i, h in enumerate(["configuration", "P", "R", "F1", "F2", "spec"]):
        txt(fig, cols[i], ty, h, size=5.7, weight="bold", color=MUTED,
            ha="left" if i == 0 else "right")
    rule(fig, rx + 0.014, rx + 0.418, ty - 0.005)
    data = [("deterministic", "0.826", "0.593", "0.690", "0.628", "0.704", DET, False),
            ("language model", "0.828", "0.869", "0.848", "0.860", "0.571", MOD, False),
            ("cascade  $(d\\vee s)$", "0.799", "0.942", "0.865", "0.909", "0.438", CAS, True),
            ("confirmed  $(d\\wedge s)$", "0.883", "0.520", "0.654", "0.566", "0.837", INK, False)]
    for i, (lab, *vals, col, bold) in enumerate(data):
        yy = ty - 0.016 - i * 0.0135
        txt(fig, cols[0], yy, lab, size=6.0, color=col, weight="bold")
        for cx, v in zip(cols[1:], vals):
            txt(fig, cx, yy, v, size=6.0, color=col, ha="right",
                weight="bold" if bold else "normal")
    c3 = Cursor(fig, rx + 0.014, ty - 0.016 - len(data) * 0.0135 - 0.007, rw - 0.028)
    c3.write("Recall $0.593\\!\\rightarrow\\!0.942$ and $F_2\\ 0.628\\!\\rightarrow\\!0.909$ are real.\n"
             "Specificity $0.704\\!\\rightarrow\\!0.438$ is the price, and in a review queue that\n"
             "price is reviewer time — so the learned tier ships behind a flag, off.",
             size=5.7)

    # -------------------------------------------------------------- footer
    rule(fig, L, R, 0.060, color=INK, lw=1.2)
    txt(fig, L, 0.0515,
        "Reproduce:   build_eval_splits.py  ·  calibrate_pack_confidence.py  ·  "
        "train_semantic_classifier.py  ·  scripts/eval_cascade.py",
        size=5.7, color=MUTED)
    txt(fig, L, 0.0385,
        "Training is deterministic — same split, same weights, bit for bit. "
        "Mining reads $\\mathit{train}$ only; $\\mathit{test}$ is reporting-only.",
        size=5.7, color=MUTED)
    txt(fig, R, 0.0515, "2026-08-23", size=5.7, color=MUTED, ha="right")
    return fig


def main() -> int:
    fig = build()
    fig.savefig(OUT / "zetaone_onepager.pdf", format="pdf", facecolor="white")
    fig.savefig(OUT / "zetaone_onepager.png", format="png", dpi=170, facecolor="white")
    plt.close(fig)
    print("wrote zetaone_onepager.pdf and .png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
