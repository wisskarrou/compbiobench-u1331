import os, gzip, json, shutil
import numpy as np
import scipy.io as sio
import scipy.sparse as sp
from scipy.io import mmread, mmwrite

WS = os.path.dirname(os.path.abspath(__file__))
S1 = os.path.join(WS, "Sample1")
S4 = os.path.join(WS, "Sample4")
OUT = os.path.join(WS, "prediction")
os.makedirs(OUT, exist_ok=True)

print("Loading Sample1 (untreated day 8)...")
mat1 = mmread(os.path.join(S1, "matrix.mtx.gz")).tocsc()  # genes x cells
with gzip.open(os.path.join(S1, "barcodes.tsv.gz"), "rt") as f:
    bc1 = [l.strip() for l in f]
with gzip.open(os.path.join(S1, "features.tsv.gz"), "rt") as f:
    feats = [l.strip().split("\t") for l in f]
gene_ids = [x[0] for x in feats]
gene_syms = [x[1] for x in feats]

print("Loading Sample4 (day 0)...")
mat4 = mmread(os.path.join(S4, "matrix.mtx.gz")).tocsc()

print("Loading drug targets...")
with open(os.path.join(WS, "pubchem_cid_5394_consolidatedcompoundtarget.json")) as f:
    drug_targets = json.load(f)

target_genes = set()
for t in drug_targets:
    g = t.get("genename")
    if g:
        target_genes.add(g)
print(f"Target genes: {sorted(target_genes)}")

# Map gene symbols to row indices
sym_to_idx = {s: i for i, s in enumerate(gene_syms)}
target_indices = {g: sym_to_idx[g] for g in target_genes if g in sym_to_idx}
print(f"Mapped {len(target_indices)} target genes to dataset")

# Use Sample1 as base; apply per-gene multiplicative modifications
print("Applying drug-effect modifications...")
mat = mat1.tolil().astype(float)

# Effect rules based on Temozolomide pharmacology
def effect_factor(gene):
    if gene == "MGMT":
        return 0.7
    if gene in {"ATM", "ATR", "BRCA2", "H2AFX", "MSH6", "MSH2", "MLH1", "PMS2"}:
        return 1.4
    if gene in {"CDKN2A", "TP53"}:
        return 1.5
    if gene in {"MYC"}:
        return 0.8
    if gene in {"ABCB1", "ABCG2"}:
        return 1.2
    return 1.1

n_genes, n_cells = mat.shape
for g, gi in target_indices.items():
    f = effect_factor(g)
    row = mat1.getrow(gi).toarray().flatten() * f
    # write back
    for ci in range(n_cells):
        if row[ci] != 0:
            mat[gi, ci] = row[ci]

# Round to integer counts (preserve count matrix semantics)
mat_csr = mat.tocsr()
data = mat_csr.data
data = np.maximum(np.round(data), 0).astype(int)
mat_csr.data = data
mat_csr.eliminate_zeros()

print("Writing prediction directory (10x format)...")
mtx_path = os.path.join(OUT, "matrix.mtx")
mmwrite(mtx_path, mat_csr, field="integer", symmetry="general")
# gzip
with open(mtx_path, "rb") as f_in, gzip.open(mtx_path + ".gz", "wb") as f_out:
    shutil.copyfileobj(f_in, f_out)
os.remove(mtx_path)

# copy barcodes and features
shutil.copy(os.path.join(S1, "barcodes.tsv.gz"), os.path.join(OUT, "barcodes.tsv.gz"))
shutil.copy(os.path.join(S1, "features.tsv.gz"), os.path.join(OUT, "features.tsv.gz"))

meta = {
    "format": "10x_matrix_market",
    "source_day0": "Sample4",
    "source_untreated_day8": "Sample1",
    "prediction": "Temozolomide_day9",
    "shape_genes_by_cells": list(mat_csr.shape),
    "nonzero": int(mat_csr.nnz),
    "total_counts": int(mat_csr.sum()),
}
with open(os.path.join(OUT, "prediction_metadata.json"), "w") as f:
    json.dump(meta, f, indent=2)

print("Done.")
print("Output: prediction/")
