"""Train the deployable demo model: FastText + GAT (Table-3 setting) on the leakage-controlled
clean_group split (seed 0). Saves models/fasttext.kv and models/gat.pt for detect.py."""
import argparse

import numpy as np

from common import ROOT, SPLITS
from embeddings import _sentences, train_fasttext
from train_gnn import graphs, parse, run

MODELS = ROOT / "models"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", default="120")
    a = ap.parse_args()
    import json
    MODELS.mkdir(exist_ok=True)
    G = graphs()
    vocab = G["vocab_norm"]
    train = json.load(open(SPLITS / "clean_group_s0.json"))["train"]
    wv = train_fasttext(_sentences(G["graphs"], vocab, train, "norm"), 100, 5, 0)
    wv.save(str(MODELS / "fasttext.kv"))
    table = np.zeros((len(vocab) + 1, 100), np.float32)
    for i, w in enumerate(vocab):
        table[i + 1] = wv[w]
    cfg = parse(["--name", "final_demo_gat", "--split", "clean_group", "--emb", "fasttext", "--gnn", "gat",
                 "--hidden", "8", "--heads", "8", "--layers", "3", "--batch", "256", "--lr", "0.001",
                 "--epochs", a.epochs, "--patience", "30", "--seed", "0"])
    r = run(cfg, table=table, save=MODELS / "gat.pt")
    print("saved", MODELS, "test", {k: round(r["test"][k], 4) for k in ("precision", "recall", "f1", "fpr")})


if __name__ == "__main__":
    main()
