import scanpy as sc
import pandas as pd
import numpy as np
import json
import scipy.sparse as sp
from scipy.io import mmread
import gzip

# Load the scRNA-seq data
print("Loading scRNA-seq data...")
matrix = mmread('matrix.mtx.gz')
matrix = matrix.T.tocsr()  # Transpose to cells x genes

with gzip.open('barcodes.tsv.gz', 'rt') as f:
    barcodes = [line.strip() for line in f]

with gzip.open('features.tsv.gz', 'rt') as f:
    features = [line.strip().split('\t') for line in f]

gene_ids = [f[0] for f in features]
gene_names = [f[1] for f in features]

# Create AnnData object
adata = sc.AnnData(X=matrix)
adata.obs_names = barcodes
adata.var_names = gene_ids
adata.var['gene_symbols'] = gene_names

print(f"Data shape: {adata.shape}")
print(f"Number of cells: {adata.n_obs}")
print(f"Number of genes: {adata.n_vars}")

# Load drug target information
print("\nLoading drug target information...")
with open('pubchem_cid_5394_consolidatedcompoundtarget.json', 'r') as f:
    drug_targets = json.load(f)

# Extract target genes
target_genes = set()
for target in drug_targets:
    if 'genename' in target and target['genename']:
        target_genes.add(target['genename'])

print(f"Number of unique target genes: {len(target_genes)}")
print(f"Target genes: {sorted(target_genes)}")

# Map target genes to the dataset
gene_symbol_to_idx = {symbol: idx for idx, symbol in enumerate(gene_names)}
target_gene_indices = []
matched_targets = []

for gene in target_genes:
    if gene in gene_symbol_to_idx:
        target_gene_indices.append(gene_symbol_to_idx[gene])
        matched_targets.append(gene)

print(f"\nMatched {len(matched_targets)} target genes in the dataset:")
print(matched_targets)

# Normalize the data
print("\nNormalizing data...")
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)

# Save the original data
X_original = adata.X.copy()

# Model the effect of Temozolomide
print("\nModeling drug effects...")

# Temozolomide is an alkylating agent that damages DNA
# It primarily affects:
# 1. MGMT (DNA repair) - downregulation reduces repair capacity
# 2. Genes involved in DNA damage response (ATM, ATR, etc.) - typically upregulated
# 3. Apoptosis and cell cycle genes - changes based on DNA damage

# Convert to dense for easier manipulation
if sp.issparse(X_original):
    X_predicted = X_original.toarray()
else:
    X_predicted = X_original.copy()

# For each target gene, model the effect
for i, gene_idx in enumerate(target_gene_indices):
    gene = matched_targets[i]

    # Get the gene expression values
    gene_expr = X_predicted[:, gene_idx]

    # Model different effects based on biological knowledge
    # MGMT: Temozolomide effectiveness is higher when MGMT is low
    # For modeling purposes, we slightly reduce MGMT expression
    if gene == 'MGMT':
        # Reduce MGMT expression by ~30% (drug depletes MGMT)
        gene_expr = gene_expr * 0.7

    # DNA damage response genes (ATM, ATR, BRCA2, etc.)
    elif gene in ['ATM', 'ATR', 'BRCA2', 'H2AX', 'MSH6']:
        # Upregulate DNA damage response
        gene_expr = gene_expr * 1.4

    # Cell cycle checkpoint genes
    elif gene in ['CDKN2A']:
        # Upregulate cell cycle arrest
        gene_expr = gene_expr * 1.5

    # Apoptosis-related
    elif gene in ['MYC']:
        # Reduce oncogene expression
        gene_expr = gene_expr * 0.8

    # Drug efflux transporters
    elif gene in ['ABCB1', 'ABCG2']:
        # May be upregulated as resistance mechanism
        gene_expr = gene_expr * 1.2

    # Other targets - moderate general stress response
    else:
        gene_expr = gene_expr * 1.1

    # Update the matrix
    X_predicted[:, gene_idx] = gene_expr

# Add temporal effect (day 8 -> day 9)
# Model general transcriptional changes over time
# Add small random perturbations to simulate biological variation
np.random.seed(42)
temporal_noise = np.random.normal(1.0, 0.05, X_predicted.shape)
X_predicted = X_predicted * temporal_noise

# Convert back to sparse
X_predicted = sp.csr_matrix(X_predicted)

# Create output AnnData object
adata_predicted = sc.AnnData(X=X_predicted)
adata_predicted.obs_names = adata.obs_names
adata_predicted.var_names = adata.var_names
adata_predicted.var['gene_symbols'] = adata.var['gene_symbols']

# Save the predicted data in the same format as input
print("\nSaving predicted scRNA-seq data...")

# Convert back to sparse matrix and save
matrix_predicted = adata_predicted.X.T

# Exponentiate to reverse log transformation
matrix_predicted_exp = np.expm1(matrix_predicted)

# Convert to sparse format
if not sp.issparse(matrix_predicted_exp):
    matrix_predicted_exp = sp.csr_matrix(matrix_predicted_exp)

# Save as Matrix Market format
from scipy.io import mmwrite
mmwrite('predicted_matrix.mtx', matrix_predicted_exp)

# Gzip the matrix file
import os
os.system('gzip -f predicted_matrix.mtx')

# Copy barcodes and features
os.system('cp barcodes.tsv.gz predicted_barcodes.tsv.gz')
os.system('cp features.tsv.gz predicted_features.tsv.gz')

print("\nPrediction complete!")
print(f"Output files: predicted_matrix.mtx.gz, predicted_barcodes.tsv.gz, predicted_features.tsv.gz")

# Generate summary statistics
print("\n=== Summary Statistics ===")
print(f"Original data - Mean expression: {X_original.mean():.4f}")
print(f"Predicted data - Mean expression: {X_predicted.mean():.4f}")

# Save the path to the predicted matrix
with open('prediction_output.txt', 'w') as f:
    f.write('predicted_matrix.mtx.gz')

print("\nPrediction saved to: predicted_matrix.mtx.gz")
