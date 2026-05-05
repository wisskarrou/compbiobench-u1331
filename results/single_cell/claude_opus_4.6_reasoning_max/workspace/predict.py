import numpy as np
import scipy.sparse as sp
import scipy.io as sio
import gzip
import json
import os
import shutil

np.random.seed(42)

print("=== Loading Sample1 (untreated day 8) ===")
mat1 = sio.mmread('Sample1/matrix.mtx.gz')
if sp.issparse(mat1):
    mat1 = mat1.tocsc()
# 10x format: genes x cells
print(f"  Raw matrix shape: {mat1.shape}")
# Transpose to cells x genes for computation
X1 = mat1.T.tocsr()
n_cells, n_genes = X1.shape
print(f"  Cells x Genes: {X1.shape}")

with gzip.open('Sample1/barcodes.tsv.gz', 'rt') as f:
    barcodes1 = [l.strip() for l in f]
with gzip.open('Sample1/features.tsv.gz', 'rt') as f:
    features1 = [l.strip().split('\t') for l in f]
gene_names1 = [ft[1] for ft in features1]

print("\n=== Loading Sample4 (day 0) ===")
mat4 = sio.mmread('Sample4/matrix.mtx.gz')
if sp.issparse(mat4):
    mat4 = mat4.tocsc()
X4 = mat4.T.tocsr()
print(f"  Cells x Genes: {X4.shape}")

print("\n=== Loading drug targets ===")
with open('pubchem_cid_5394_consolidatedcompoundtarget.json') as f:
    drug_targets = json.load(f)

target_genes = set()
for entry in drug_targets:
    gn = entry.get('genename', '')
    if gn:
        target_genes.add(gn)

gene_to_idx = {g: i for i, g in enumerate(gene_names1)}
matched = {g: gene_to_idx[g] for g in target_genes if g in gene_to_idx}
print(f"  Matched target genes: {len(matched)} - {sorted(matched.keys())}")

# Compute per-gene scale factors from temporal trend (day 0 -> day 8)
# Use pseudocount-based ratio to avoid division by zero
def gene_means_sparse(X):
    return np.asarray(X.mean(axis=0)).flatten()

mu_day0 = gene_means_sparse(X4)
mu_day8 = gene_means_sparse(X1)

# Temporal scale: ratio of day8/day0 means, extrapolated 1 more day
# day8_to_day9_ratio = (mu_day8/mu_day0)^(1/8) for one-day progression
pseudo = 0.01
ratio_8_over_0 = (mu_day8 + pseudo) / (mu_day0 + pseudo)
# Per-day multiplicative factor
per_day_factor = np.power(np.clip(ratio_8_over_0, 0.5, 2.0), 1.0/8.0)

print(f"  Temporal factor range: [{per_day_factor.min():.4f}, {per_day_factor.max():.4f}]")

# Drug effect multipliers for target genes
drug_effects = {}
for gene, idx in matched.items():
    if gene == 'MGMT':
        drug_effects[idx] = 0.65
    elif gene in ['ATM', 'ATR']:
        drug_effects[idx] = 1.45
    elif gene == 'H2AX':
        drug_effects[idx] = 1.6
    elif gene in ['BRCA2', 'MSH6']:
        drug_effects[idx] = 1.35
    elif gene == 'TP53':
        drug_effects[idx] = 1.5
    elif gene == 'CDKN2A':
        drug_effects[idx] = 1.45
    elif gene == 'PTEN':
        drug_effects[idx] = 1.2
    elif gene == 'MYC':
        drug_effects[idx] = 0.75
    elif gene in ['ABCB1', 'ABCG2']:
        drug_effects[idx] = 1.25
    elif gene == 'GSTP1':
        drug_effects[idx] = 1.3
    elif gene == 'SLFN11':
        drug_effects[idx] = 1.3
    elif gene == 'IDH1':
        drug_effects[idx] = 0.9
    elif gene == 'ATRX':
        drug_effects[idx] = 1.15
    elif gene == 'ARID1A':
        drug_effects[idx] = 1.1
    elif gene == 'PIK3CA':
        drug_effects[idx] = 0.9
    elif gene == 'HDAC4':
        drug_effects[idx] = 1.2
    elif gene == 'ALK':
        drug_effects[idx] = 0.95
    elif gene in ['ALB', 'ORM1', 'PRL', 'CSF2']:
        drug_effects[idx] = 1.05
    else:
        drug_effects[idx] = 1.1

# Build combined per-gene multiplier (temporal + drug)
combined_factor = per_day_factor.copy()
for idx, drug_mult in drug_effects.items():
    combined_factor[idx] *= drug_mult

# Apply to sparse matrix - multiply each column (gene) by its factor
# This preserves sparsity perfectly
X_pred = X1.copy().astype(np.float64)

# Multiply columns by factors using diagonal matrix
diag = sp.diags(combined_factor, format='csc')
X_pred = X_pred.dot(diag).tocsr()

# Add small stochastic noise to non-zero entries only
X_pred = X_pred.tocoo()
noise = np.random.normal(1.0, 0.02, len(X_pred.data))
X_pred.data = X_pred.data * noise
X_pred.data = np.maximum(X_pred.data, 0)

# Round to integers (count data)
X_pred.data = np.round(X_pred.data).astype(np.float64)

# Remove zeros created by rounding
X_pred = X_pred.tocsr()
X_pred.eliminate_zeros()

# Convert back to genes x cells (10x convention)
X_out = X_pred.T.tocsc()

print(f"\n=== Saving prediction ===")
print(f"  Output shape (genes x cells): {X_out.shape}")
print(f"  Non-zeros: {X_out.nnz} ({100*X_out.nnz/(X_out.shape[0]*X_out.shape[1]):.2f}%)")

outdir = 'prediction'
os.makedirs(outdir, exist_ok=True)

# Save matrix in COO format for Matrix Market
X_out_coo = X_out.tocoo()
sio.mmwrite(os.path.join(outdir, 'matrix.mtx'), X_out_coo)
os.system(f'gzip -f {outdir}/matrix.mtx')

shutil.copy('Sample1/features.tsv.gz', os.path.join(outdir, 'features.tsv.gz'))
shutil.copy('Sample1/barcodes.tsv.gz', os.path.join(outdir, 'barcodes.tsv.gz'))

metadata = {
    "description": "Predicted scRNA-seq for patient treated with Temozolomide at day 9",
    "method": "Temporal extrapolation + pharmacological perturbation model",
    "base_sample": "Sample1 (untreated day 8)",
    "reference_sample": "Sample4 (day 0)",
    "drug": "Temozolomide",
    "target_genes_modeled": sorted(matched.keys()),
    "n_cells": n_cells,
    "n_genes": n_genes,
}
with open(os.path.join(outdir, 'prediction_metadata.json'), 'w') as f:
    json.dump(metadata, f, indent=2)

print("Done!")
