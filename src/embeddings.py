"""Statement embeddings (paper §3.2.1): Word2Vec CBOW/Skip-gram, FastText, GloVe, Doc2Vec PV-DM/PV-DBOW.

Each PHP statement (normalised or raw text) is one "word"; each file's statements in
emission order (≈ execution order of the ICFG lowering) form one "sentence".
Embeddings are trained on the TRAINING files of a split only and cached per configuration.
Returns a float32 table indexed by (global vocab id + 1); row 0 = zero vector (empty graph / OOV).
"""
import hashlib
import os
import pickle

import numpy as np

from common import PROC

CACHE = PROC / "emb_cache"
METHODS = ["glove", "w2v_c", "w2v_s", "d2v_m", "d2v_w", "fasttext"]


def _sentences(G, vocab, keys, field):
    return [[vocab[i] for i in G[k][field]] for k in keys if len(G[k][field])]


def train_glove(sents, dim, window, seed, epochs=25, x_max=100.0, alpha=0.75, lr=0.05):
    """GloVe (Pennington et al. 2014) with 1/d-weighted symmetric co-occurrence and AdaGrad."""
    import torch
    words = sorted({w for s in sents for w in s})
    wid = {w: i for i, w in enumerate(words)}
    co = {}
    for s in sents:
        ids = [wid[w] for w in s]
        for i, a in enumerate(ids):
            for d in range(1, window + 1):
                if i + d >= len(ids):
                    break
                b = ids[i + d]
                co[(a, b)] = co.get((a, b), 0.0) + 1.0 / d
                co[(b, a)] = co.get((b, a), 0.0) + 1.0 / d
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    pairs = torch.tensor(list(co.keys()), dtype=torch.long, device=dev)
    x = torch.tensor(list(co.values()), dtype=torch.float32, device=dev)
    del co
    g = torch.Generator(device="cpu").manual_seed(seed)
    n = len(words)
    W = ((torch.rand(n, dim, generator=g) - 0.5) / dim).to(dev).requires_grad_()
    C = ((torch.rand(n, dim, generator=g) - 0.5) / dim).to(dev).requires_grad_()
    bw = torch.zeros(n, device=dev, requires_grad=True)
    bc = torch.zeros(n, device=dev, requires_grad=True)
    opt = torch.optim.Adagrad([W, C, bw, bc], lr=lr)
    f = torch.clamp(x / x_max, max=1.0) ** alpha
    logx = torch.log(x)
    bs = 1 << 18
    for _ in range(epochs):
        perm = torch.randperm(len(x), device=dev)
        for i in range(0, len(x), bs):
            j = perm[i:i + bs]
            a, b = pairs[j, 0], pairs[j, 1]
            pred = (W[a] * C[b]).sum(1) + bw[a] + bc[b]
            loss = (f[j] * (pred - logx[j]) ** 2).sum()
            opt.zero_grad()
            loss.backward()
            opt.step()
    vec = (W + C).detach().cpu().numpy()
    return {w: vec[i] for w, i in wid.items()}


def train_fasttext(sents, dim=100, window=5, seed=0):
    from gensim.models import FastText
    # bucket reduced from 2M to 200k to fit in this machine's RAM (documented deviation)
    return FastText(sents, bucket=200_000, vector_size=dim, window=window, min_count=1, workers=8, seed=seed).wv


def build_table(G, vocab, train_keys, field, method, dim=100, window=5, seed=0, tag=""):
    """Train `method` on the training files and return the lookup table for the whole vocab."""
    h = hashlib.md5(("|".join(sorted(train_keys)) + f"{field}{method}{dim}{window}{seed}{tag}").encode()).hexdigest()[:16]
    path = CACHE / f"{method}_{field}_d{dim}_w{window}_s{seed}_{h}.npy"
    if path.exists() and np.load(path, mmap_mode="r").shape[0] != len(vocab) + 1:
        # same training files but an extended vocabulary (graphs_aug.pkl): separate cache entry
        path = path.with_name(path.stem + f"_v{len(vocab)}.npy")
    if path.exists():
        return np.load(path, mmap_mode="r")
    from gensim.models import Word2Vec, FastText
    from gensim.models.doc2vec import Doc2Vec, TaggedDocument
    sents = _sentences(G, vocab, train_keys, field)
    common = dict(vector_size=dim, window=window, min_count=1, workers=8, seed=seed)
    if method in ("w2v_c", "w2v_s"):
        m = Word2Vec(sents, sg=int(method == "w2v_s"), **common)
        lookup = m.wv
    elif method == "fasttext":
        lookup = train_fasttext(sents, dim, window, seed)
    elif method in ("d2v_m", "d2v_w"):
        docs = [TaggedDocument(s, [i]) for i, s in enumerate(sents)]
        # PV-DBOW does not train word vectors by default; dbow_words=1 is needed to embed statements
        m = Doc2Vec(docs, dm=int(method == "d2v_m"), dbow_words=int(method == "d2v_w"), **common)
        lookup = m.wv
    elif method == "glove":
        lookup = train_glove(sents, dim, window, seed)
    else:
        raise ValueError(method)
    table = np.zeros((len(vocab) + 1, dim), np.float32)
    has = (lambda w: w in lookup) if isinstance(lookup, dict) else (lambda w: w in lookup.key_to_index)
    for i, w in enumerate(vocab):
        if has(w):
            table[i + 1] = lookup[w]
        elif method == "fasttext":
            table[i + 1] = lookup[w]           # OOV statement composed from char n-grams
    CACHE.mkdir(parents=True, exist_ok=True)
    np.save(path, table)
    return table


def load_graphs():
    # GLARESHELL_GRAPHS=graphs_aug.pkl selects the corpus extended with the hard-benign track (hard_benign.py)
    with open(PROC / os.environ.get("GLARESHELL_GRAPHS", "graphs.pkl"), "rb") as f:
        return pickle.load(f)
