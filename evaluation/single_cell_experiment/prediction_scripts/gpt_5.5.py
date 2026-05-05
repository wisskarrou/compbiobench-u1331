import gzip
import json
import os
import shutil

import numpy as np
from scipy import io, sparse


WORKDIR = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(WORKDIR, "prediction")


def read_features(sample):
    path = os.path.join(WORKDIR, sample, "features.tsv.gz")
    ids, names, rows = [], [], []
    with gzip.open(path, "rt") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            ids.append(parts[0])
            names.append(parts[1] if len(parts) > 1 else parts[0])
            rows.append(parts)
    return ids, names, rows


def read_matrix(sample):
    path = os.path.join(WORKDIR, sample, "matrix.mtx.gz")
    with gzip.open(path, "rb") as handle:
        return io.mmread(handle).tocsr().astype(np.float32)


def build_gene_scale(gene_names, untreated_scale):
    scale = untreated_scale.copy()
    name_to_idx = {g: i for i, g in enumerate(gene_names)}

    with open(os.path.join(WORKDIR, "pubchem_cid_5394_consolidatedcompoundtarget.json")) as handle:
        records = json.load(handle)
    target_genes = {r.get("genename", "") for r in records if r.get("taxname", "").startswith("Homo sapiens")}

    repair_response = {
        "MGMT": 1.25,
        "MSH6": 1.15,
        "ATM": 1.30,
        "ATR": 1.25,
        "TP53": 1.20,
        "CDKN2A": 1.35,
        "PTEN": 1.10,
        "BRCA2": 1.15,
        "GSTP1": 1.15,
        "H2AFX": 1.25,
        "ABCB1": 1.20,
        "ABCG2": 1.20,
    }
    growth_axis = {
        "MYC": 0.85,
        "ALK": 0.90,
        "PIK3CA": 0.92,
        "PRL": 0.95,
        "CSF2": 0.95,
    }
    stress = {
        "CDKN1A": 1.35,
        "GADD45A": 1.25,
        "GADD45B": 1.20,
        "DDIT3": 1.20,
        "ATF3": 1.18,
        "JUN": 1.12,
        "FOS": 1.12,
        "BBC3": 1.20,
        "PMAIP1": 1.20,
        "BAX": 1.12,
    }
    proliferation = {
        "MKI67", "TOP2A", "PCNA", "TYMS", "MCM2", "MCM3", "MCM4", "MCM5",
        "MCM6", "MCM7", "CDK1", "CCNA2", "CCNB1", "CCNB2", "BIRC5",
        "UBE2C", "AURKA", "AURKB", "PLK1", "CDC20", "CENPF", "NUSAP1",
    }

    drug_factor = np.ones(len(gene_names), dtype=np.float32)
    for gene in target_genes:
        if gene in name_to_idx:
            drug_factor[name_to_idx[gene]] *= 1.10
    for table in (repair_response, growth_axis, stress):
        for gene, factor in table.items():
            if gene in name_to_idx:
                drug_factor[name_to_idx[gene]] *= factor
    for gene in proliferation:
        if gene in name_to_idx:
            drug_factor[name_to_idx[gene]] *= 0.82

    return np.clip(scale * drug_factor, 0.35, 2.75)


def deterministic_round(data):
    floored = np.floor(data)
    frac = data - floored
    # Deterministic fractional rounding avoids run-to-run noise while preserving totals better than floor.
    idx = np.arange(data.size, dtype=np.float32)
    threshold = ((idx * 0.61803398875) % 1.0).astype(np.float32)
    return floored + (frac > threshold)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    gene_ids, gene_names, _ = read_features("Sample1")
    x0 = read_matrix("Sample4")
    x1 = read_matrix("Sample1")

    mean0 = np.asarray(x0.mean(axis=1)).ravel()
    mean1 = np.asarray(x1.mean(axis=1)).ravel()
    untreated = np.power((mean1 + 0.05) / (mean0 + 0.05), 1.0 / 8.0).astype(np.float32)
    untreated = np.clip(untreated, 0.70, 1.35)
    scale = build_gene_scale(gene_names, untreated)

    pred = x1.tocoo(copy=True)
    pred.data *= scale[pred.row]
    pred.data = deterministic_round(pred.data).astype(np.int32)
    keep = pred.data > 0
    pred = sparse.coo_matrix((pred.data[keep], (pred.row[keep], pred.col[keep])), shape=pred.shape)
    pred.sum_duplicates()
    pred = pred.tocsr()

    tmp_mtx = os.path.join(OUTDIR, "matrix.mtx")
    io.mmwrite(tmp_mtx, pred, field="integer")
    with open(tmp_mtx, "rb") as src, gzip.open(tmp_mtx + ".gz", "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst)
    os.remove(tmp_mtx)

    shutil.copyfile(os.path.join(WORKDIR, "Sample1", "features.tsv.gz"), os.path.join(OUTDIR, "features.tsv.gz"))
    shutil.copyfile(os.path.join(WORKDIR, "Sample1", "barcodes.tsv.gz"), os.path.join(OUTDIR, "barcodes.tsv.gz"))

    summary = {
        "format": "10x_matrix_market",
        "source_day0": "Sample4",
        "source_untreated_day8": "Sample1",
        "prediction": "Temozolomide_day9",
        "shape_genes_by_cells": list(pred.shape),
        "nonzero": int(pred.nnz),
        "total_counts": int(pred.sum()),
    }
    with open(os.path.join(OUTDIR, "prediction_metadata.json"), "w") as handle:
        json.dump(summary, handle, indent=2)


if __name__ == "__main__":
    main()
