"""Shared paths, metrics and statistics helpers."""
import json
import random
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROC = DATA / "processed"
SPLITS = DATA / "splits"
RESULTS = ROOT / "results"
RUNS = RESULTS / "runs"

METRICS = ["precision", "recall", "tnr", "fpr", "acc", "f1"]


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def metrics(y_true, y_pred) -> dict:
    """Paper Eq. (7)-(11) + FPR. Positive class = webshell (1)."""
    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    div = lambda a, b: a / b if b else float("nan")
    p, r = div(tp, tp + fp), div(tp, tp + fn)
    return dict(tp=tp, tn=tn, fp=fp, fn=fn, precision=p, recall=r, tnr=div(tn, tn + fp), fpr=div(fp, fp + tn),
                acc=div(tp + tn, tp + tn + fp + fn), f1=div(2 * p * r, p + r) if p == p and r == r and p + r else 0.0)


def mean_ci(xs, conf=0.95):
    """Mean and half-width of a Student-t confidence interval over seeds."""
    from scipy import stats
    xs = np.asarray([x for x in xs if x == x], dtype=float)
    if len(xs) < 2:
        return (float(xs.mean()) if len(xs) else float("nan")), float("nan")
    h = stats.t.ppf((1 + conf) / 2, len(xs) - 1) * xs.std(ddof=1) / np.sqrt(len(xs))
    return float(xs.mean()), float(h)


def wilson(k, n, z=1.96):
    """Wilson score interval for a proportion k/n."""
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def dump_json(obj, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=float))
