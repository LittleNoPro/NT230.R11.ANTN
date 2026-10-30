"""Shortcut probe: score small hand-written *benign* standalone scripts (tests/probe_benign) with the
TF-IDF + LR baseline trained on the clean_group split (seed 0). The GNN side of the probe is
`python detect.py ../tests/probe_benign` (final demo model). Output: results/probe_tfidf.json"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import vstack as sp_vstack
from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer
from sklearn.linear_model import LogisticRegression

from baselines import TOKEN, file_text
from common import DATA, RESULTS, ROOT, SPLITS


def main():
    man = pd.read_csv(DATA / "manifests/manifest_all.csv")
    man = man[man.keep_exact == 1].drop_duplicates("sha256").set_index("sha256")
    tr = json.load(open(SPLITS / "clean_group_s0.json"))["train"]
    y = (man.loc[tr, "label"] == "webshell").astype(int).values
    hv = HashingVectorizer(token_pattern=TOKEN, lowercase=False, ngram_range=(1, 2), n_features=1 << 18,
                           alternate_sign=False, norm=None, dtype=np.float32)
    tf = TfidfTransformer(sublinear_tf=True)
    X = tf.fit_transform(sp_vstack([hv.transform([file_text(man.loc[s]) for s in tr[i:i + 500]])
                                    for i in range(0, len(tr), 500)]).tocsr())
    lr = LogisticRegression(C=10, max_iter=3000).fit(X, y)
    files = sorted((ROOT / "tests/probe_benign").glob("*.php"))
    p = lr.predict_proba(tf.transform(hv.transform([f.read_bytes().decode("latin-1") for f in files])))[:, 1]
    out = {f.name: round(float(v), 4) for f, v in zip(files, p)}
    for k, v in out.items():
        print(f"{'WEBSHELL' if v >= 0.5 else 'benign':8s} p={v:.3f} {k}")
    (RESULTS / "probe_tfidf.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
