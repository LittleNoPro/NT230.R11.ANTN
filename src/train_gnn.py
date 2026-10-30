"""Train/evaluate one GlareShell configuration (paper §3.3, §4.3-4.4).

Node attribute = [statement embedding (D) | one-hot risk level (3)]  (risk part dropped when variant != nw)
  variant none : raw statements, no risk weights
  variant n    : normalised statements, no risk weights
  variant nw   : normalised statements + risk weights (full GlareShell)
Graph embedding = mean of final node states (Eq. 6) -> MLP -> {benign, webshell}.
Model selection: epoch with best validation F1; test metrics reported at that epoch.
"""
import argparse
import json
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader
from torch_geometric.nn import GCNConv, GATConv, GINConv, global_mean_pool
from torch_geometric.utils import to_undirected

from common import RUNS, SPLITS, metrics, set_seed, dump_json
from embeddings import build_table, load_graphs

_GRAPHS = None


def graphs():
    global _GRAPHS
    if _GRAPHS is None:
        _GRAPHS = load_graphs()
    return _GRAPHS


def make_data(g, field, y):
    sid = torch.from_numpy(g[field].astype(np.int64) + 1)
    risk = torch.from_numpy(g["risk"].astype(np.int64))
    if len(sid) == 0:                      # empty ICFG (parse failure / all statements pruned)
        sid, risk = torch.zeros(1, dtype=torch.long), torch.zeros(1, dtype=torch.long)
    ei = torch.from_numpy(g["edges"].astype(np.int64))
    ei = to_undirected(ei, num_nodes=len(sid)) if ei.numel() else ei.reshape(2, 0)
    return Data(sid=sid, risk=risk, edge_index=ei, y=torch.tensor([y]), num_nodes=len(sid))


class GlareNet(nn.Module):
    def __init__(self, table, use_risk, gnn, hidden, layers, heads):
        super().__init__()
        self.register_buffer("table", torch.as_tensor(np.asarray(table)))
        self.use_risk = use_risk
        d = self.table.shape[1] + (3 if use_risk else 0)
        self.convs = nn.ModuleList()
        for _ in range(layers):
            if gnn == "gcn":
                self.convs.append(GCNConv(d, hidden)); d = hidden
            elif gnn == "gat":
                self.convs.append(GATConv(d, hidden, heads=heads)); d = hidden * heads
            elif gnn == "gin":
                self.convs.append(GINConv(nn.Sequential(nn.Linear(d, hidden), nn.ReLU(), nn.Linear(hidden, hidden)),
                                          train_eps=True)); d = hidden
        self.gnn = gnn
        self.mlp = nn.Sequential(nn.Linear(d, d), nn.ReLU(), nn.Linear(d, 2))

    def forward(self, b):
        x = self.table[b.sid]
        if self.use_risk:
            x = torch.cat([x, F.one_hot(b.risk, 3).float()], 1)
        for conv in self.convs:
            x = conv(x, b.edge_index)
            x = F.elu(x) if self.gnn == "gat" else F.relu(x)
        return self.mlp(global_mean_pool(x, b.batch))


@torch.no_grad()
def predict(model, loader, dev):
    model.eval()
    ys, ps = [], []
    for b in loader:
        b = b.to(dev)
        ps.append(torch.softmax(model(b), 1)[:, 1].cpu())
        ys.append(b.y.cpu())
    return torch.cat(ys).numpy(), torch.cat(ps).numpy()


def run(cfg):
    set_seed(cfg["seed"])
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    G = graphs()
    split = json.load(open(SPLITS / f"{cfg['split']}_s{cfg['seed']}.json"))
    field = "raw" if cfg["variant"] == "none" else "norm"
    vocab = G["vocab_raw"] if field == "raw" else G["vocab_norm"]
    import pandas as pd
    from common import DATA
    lab = pd.read_csv(DATA / "manifests/manifest_all.csv", usecols=["sha256", "label"]).drop_duplicates("sha256")
    ymap = dict(zip(lab.sha256, (lab.label == "webshell").astype(int)))
    t0 = time.time()
    emb_split = cfg.get("emb_split", cfg["split"])
    emb_keys = json.load(open(SPLITS / f"{emb_split}_s{cfg['seed']}.json"))["train"]
    table = build_table(G["graphs"], vocab, emb_keys, field, cfg["emb"], cfg["dim"], cfg["window"], cfg["seed"])
    t_emb = time.time() - t0
    ds = {k: [make_data(G["graphs"][s], field, ymap[s]) for s in split[k]] for k in ("train", "val", "test")}
    gen = torch.Generator().manual_seed(cfg["seed"])
    tl = DataLoader(ds["train"], batch_size=cfg["batch"], shuffle=True, generator=gen)
    vl = DataLoader(ds["val"], batch_size=256)
    te = DataLoader(ds["test"], batch_size=256)
    model = GlareNet(table, cfg["variant"] == "nw", cfg["gnn"], cfg["hidden"], cfg["layers"], cfg["heads"]).to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=cfg["lr"])
    best, best_state, bad, hist = -1, None, 0, []
    t1 = time.time()
    for ep in range(cfg["epochs"]):
        model.train()
        tot = 0.0
        for b in tl:
            b = b.to(dev)
            loss = F.cross_entropy(model(b), b.y)
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item() * b.num_graphs
        yv, pv = predict(model, vl, dev)
        f1 = metrics(yv, pv >= 0.5)["f1"]
        hist.append((ep, tot / len(ds["train"]), f1))
        if f1 > best:
            best, bad = f1, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items() if k != "table"}
        else:
            bad += 1
            if bad >= cfg["patience"]:
                break
    model.load_state_dict(best_state, strict=False)
    yt, pt = predict(model, te, dev)
    t_inf = (time.time() - t1)
    res = dict(cfg=cfg, test=metrics(yt, pt >= 0.5), val_f1=best, epochs_run=len(hist), history=hist,
               secs_embedding=t_emb, secs_train=t_inf, n=dict((k, len(v)) for k, v in ds.items()),
               pred=dict(sha=split["test"], y=yt.tolist(), p=[round(float(x), 5) for x in pt]))
    dump_json(res, RUNS / f"{cfg['name']}.json")
    return res


def parse(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--split", default="paper_random")
    ap.add_argument("--emb_split", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--emb", default="fasttext")
    ap.add_argument("--dim", type=int, default=100)
    ap.add_argument("--window", type=int, default=5)
    ap.add_argument("--variant", default="nw", choices=["none", "n", "nw"])
    ap.add_argument("--gnn", default="gcn", choices=["gcn", "gat", "gin"])
    ap.add_argument("--layers", type=int, default=2)
    ap.add_argument("--hidden", type=int, default=10)
    ap.add_argument("--heads", type=int, default=8)
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--patience", type=int, default=10)
    a = vars(ap.parse_args(argv))
    if a["emb_split"] is None:
        a.pop("emb_split")
    return a


if __name__ == "__main__":
    r = run(parse())
    print(json.dumps(r["test"]), "val_f1", round(r["val_f1"], 4), "epochs", r["epochs_run"],
          "emb_s", round(r["secs_embedding"], 1), "train_s", round(r["secs_train"], 1))
