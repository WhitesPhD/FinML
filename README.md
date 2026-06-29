# Big Data in Finance — Financial Machine Learning

Open course materials for a Master's-level module on **machine learning methods for finance**, taught by Dr Daniele Bianchi. The course applies state-of-the-art ML methods to two core financial problems: **return prediction** (factor investing and market timing) and **credit risk assessment** (default prediction and credit scoring).

Each week pairs theoretical foundations with practical, Python-based financial applications.

## Contents

| Folder | Description |
|--------|-------------|
| `Misc/` | Course syllabus |
| `Lectures/` | 7 Beamer slide decks (one per week) |
| `Lectures/Figures/` | Figures used in the slides (SHAP plots, cumulative returns, trees, PDP/ICE) |
| `Notes/` | 7 sets of lecture notes (one per week) |
| `Quizzes/` | Quizzes, in versions with and without solutions |
| `Codes/` | One Jupyter tutorial notebook per week (see `Codes/README.md`) |

## Topics

1. **Week 1** — Foundations of machine learning (loss functions, bias–variance, cross-validation for time series, multiple testing)
2. **Weeks 2–3** — Regression methods (Ridge/Lasso/Elastic Net, trees, Random Forests, gradient boosting / XGBoost)
3. **Week 4** — Classification methods (logistic regression, LDA/QDA, evaluation metrics, class imbalance, calibration)
4. **Week 5** — Unsupervised learning (PCA, instrumented PCA, clustering)
5. **Week 6** — Model interpretability (SHAP, LIME, partial dependence, walk-forward validation)
6. **Week 7** — Neural networks (MLPs, backpropagation, regularization)

## Building the documents

All materials are LaTeX source and compile with **pdfLaTeX**.

```bash
# Slides (compile from within the Lectures/ directory so figure paths resolve)
cd Lectures
pdflatex "Week 1 Slides.tex"

# Notes
cd Notes
pdflatex "Week 1 Notes.tex"
```

Slides use the `beamer` class with `tikz`; notes and quizzes use the `article` class. A standard TeX distribution (TeX Live or MiKTeX) covers all dependencies.

## Data

The datasets are **not** included in this repository. They are public and can be downloaded from:

- **Market timing** (Goyal–Welch–Zafirov equity-premium predictors): [Amit Goyal's website](https://docs.google.com/spreadsheets/d/10_nkOkJPvq4eZgNl-1ys63PzhbnM3S2y/edit?gid=1922816101#gid=1922816101)
- **Credit risk** (LendingClub loans): [Kaggle](https://www.kaggle.com/datasets/wordsforthewise/lending-club)

See [`Codes/README.md`](Codes/README.md) for the expected filenames, column conventions, and setup notes.

## Course chat (AI companion)

A lightweight, static **retrieval-augmented chat** over the course material lives in [`chat/`](chat/) (one self-contained `index.html`), with a landing page at [`index.html`](index.html), designed to be served via **GitHub Pages**. It is **bring-your-own-key**: visitors paste their own Anthropic or OpenAI API key, which is kept in the browser's `sessionStorage` and sent only to the chosen provider — no secrets are stored in the repo and there is no backend.

The chat retrieves from `course-chunks.json`, a keyword index built from the slides, notes, and tutorial notebooks. Rebuild it whenever the material changes:

```bash
python3 scripts/build_chunks.py   # writes course-chunks.json
```

Requires Python 3.9+. Optionally install `pdftotext` (Poppler or MacTeX) so each chunk also carries the compiled-PDF text; without it the index uses the LaTeX/notebook text only. To publish, push to GitHub and enable Pages (serve from the repo root) — the chat will be at `/chat/`.

## Author

Dr Daniele Bianchi — <https://whitesphd.com>

## License

© 2026 Daniele Bianchi.

These materials are licensed under the
[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/).
You are free to share and adapt the material for **non-commercial** purposes, provided you give appropriate
credit and distribute any derivatives under the same license. Full terms in [LICENSE](LICENSE).
