"""Version 2 of statement-set clustering; LSH candidates are approximate.

Every pair in each bucket is eligible for exact verification. Identical sets and
whitespace equivalence are unioned in the same data structure, so a later merge
cannot split an existing component. LSH can still miss pairs across all buckets.
"""
from collections import defaultdict
from itertools import combinations

import numpy as np

VERSION = "minhash-all-pairs-v2"
N_PERM, BANDS = 128, 32
JACCARD = 0.8
P = (1 << 31) - 1  # products fit uint64 for the 32-bit statement vocabulary


def minhash(sets):
    rng = np.random.default_rng(12345)
    a = rng.integers(1, P, N_PERM, dtype=np.uint64)
    b = rng.integers(0, P, N_PERM, dtype=np.uint64)
    sig = np.full((len(sets), N_PERM), np.iinfo(np.uint64).max, dtype=np.uint64)
    for i, s in enumerate(sets):
        if s:
            x = np.fromiter(s, dtype=np.uint64)[:, None]
            if np.any(x >= P):
                raise ValueError("statement IDs must be below the MinHash prime")
            sig[i] = ((a * x + b) % np.uint64(P)).min(0)
    return sig


def near_dup_clusters(keys, sets, ws_hashes=None, signatures=None):
    if len(keys) != len(sets) or (ws_hashes is not None and len(ws_hashes) != len(keys)):
        raise ValueError("clustering inputs have different lengths")
    parent = list(range(len(keys)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        a, b = find(i), find(j)
        if a == b:
            return False
        parent[max(a, b)] = min(a, b)
        return True

    reps, ws_reps, active = {}, {}, []
    for i, s in enumerate(sets):
        if ws_hashes is not None:
            union(i, ws_reps.setdefault(ws_hashes[i], i))
        if s:  # unrelated empty graphs must not collapse into one component
            if s in reps:
                union(i, reps[s])
            else:
                reps[s] = i
                active.append(i)
    sig = minhash(sets) if signatures is None else np.asarray(signatures)
    rows = sig.shape[1] // BANDS
    if sig.shape != (len(keys), N_PERM):
        raise ValueError("invalid MinHash signature shape")
    seen, n_merges = set(), 0
    for band in range(BANDS):
        buckets = defaultdict(list)
        for i in active:
            buckets[sig[i, band * rows:(band + 1) * rows].tobytes()].append(i)
        for bucket in buckets.values():
            for i, j in combinations(bucket, 2):
                if find(i) == find(j):
                    continue
                pair = (min(i, j), max(i, j))
                if pair in seen:
                    continue
                seen.add(pair)
                s1, s2 = sets[i], sets[j]
                if min(len(s1), len(s2)) / max(len(s1), len(s2)) < JACCARD:
                    continue
                if len(s1 & s2) / len(s1 | s2) >= JACCARD:
                    n_merges += union(i, j)
    return np.array([find(i) for i in range(len(keys))]), n_merges
