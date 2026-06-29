# Tutorials (Code)

One Jupyter notebook per week, used in the hands-on tutorial sessions. Each notebook pairs with that week's slides and notes, and includes guided exercises (🔧) and AI-assisted prompting practice (🤖).

| Notebook | Topic | Data file |
|---|---|---|
| `Week_1_Tutorial.ipynb` | Python & data basics | `Data_GWZ.csv` |
| `Week_2_Tutorial.ipynb` | Train/test splits & regularized regression | `Data_GWZ.csv` |
| `Week_3_Tutorial.ipynb` | Tree-based methods | `Data_GWZ.csv` |
| `Week_4_Tutorial.ipynb` | Classification & credit risk | `lending_club_tutorial.csv` |
| `Week_5_Tutorial.ipynb` | Unsupervised learning (PCA, clustering) | `Data_GWZ.csv` |
| `Week_6_Tutorial.ipynb` | Model interpretability | `lending_club_tutorial.csv` |
| `Week_7_Tutorial.ipynb` | Neural networks | `Data_GWZ.csv` |

## Data is not included

The datasets are **not** distributed with this repository (the LendingClub file in particular is large). Download them from the public sources below and place the files in this `Codes/` folder (or update the path at the top of the notebook).

### 1. Market-timing data — `Data_GWZ.csv`

Goyal, Welch & Zafirov equity-premium predictor dataset, from Amit Goyal's website:

- <https://docs.google.com/spreadsheets/d/10_nkOkJPvq4eZgNl-1ys63PzhbnM3S2y/edit?gid=1922816101#gid=1922816101>

Export the sheet to CSV and save it as `Data_GWZ.csv`. The notebooks expect:

- a `DATE` column (monthly; some notebooks parse it with format `%Y%m`),
- a target column `MktRf` (market excess return), and
- predictor columns such as `d_p, d_y, e_p, b_m, tbl, lty, tms, dfy, svar, infl` (Weeks 2–3 use this subset; Weeks 5 and 7 use the broader predictor set).

You may need to rename columns to match these names.

### 2. Credit-risk data — `lending_club_tutorial.csv`

LendingClub loan data, from Kaggle:

- <https://www.kaggle.com/datasets/wordsforthewise/lending-club>

The notebooks expect a preprocessed subset saved as `lending_club_tutorial.csv` with a binary target column `default` (1 = defaulted, 0 = repaid) plus borrower/loan features (e.g. `loan_amnt`, `int_rate`, `annual_inc`, `dti`, `grade`, `home_ownership`, `purpose`, …). The raw Kaggle download requires cleaning/feature selection to reach this form.

> ⚠️ **Avoid label leakage** when preparing the LendingClub data: drop post-outcome fields (e.g. `recoveries`, `total_pymnt`, `last_pymnt_*`, the raw `loan_status`) — keep only information known at loan origination.

## Environment

```bash
pip install numpy pandas scikit-learn matplotlib seaborn xgboost shap
```

Python 3.9+ recommended. The notebooks are written for recent `pandas`/`scikit-learn`.

## A note on scope

These tutorials use **simplified protocols** for teaching within a one-hour session (e.g. a single chronological train/test split, a reduced set of predictors, and fixed hyperparameters), so their printed numbers will not exactly reproduce the full walk-forward results reported in the slides and notes.
