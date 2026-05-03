"""
evaluate_perturbation.py
========================
Evaluate scRNA-seq perturbation prediction quality against ground truth,
supporting **multiple models** simultaneously.

Metrics and plots follow best practices from:
  - GEARS (Roohani et al., Nature Biotechnology 2024)
  - scGen (Lotfollahi et al., Nature Methods 2019)
  - CPA  (Lotfollahi et al., Molecular Systems Biology 2023)
  - scREPA (ScienceDirect 2025)
  - scArchon (bioRxiv 2025) benchmarking suite
  - Systema (Nature Biotechnology 2025)
  - "Optimal distance metrics for scRNA-seq" (bioRxiv 2023)
  - "Diversity by Design" / DEG-aware metrics (arXiv 2025)

Folder convention expected for predictions
------------------------------------------
    predictions/
        model_A/
            barcodes.tsv.gz
            features.tsv.gz
            matrix.mtx.gz
        model_B/
            barcodes.tsv.gz
            features.tsv.gz
            matrix.mtx.gz
        ...

Usage
-----
    # Multi-model mode  (auto-discovers subfolders)
    python evaluate_perturbation.py \
        --ground_truth  ground_truth/matrix.mtx.gz    \
        --gt_barcodes   ground_truth/barcodes.tsv.gz  \
        --gt_features   ground_truth/features.tsv.gz  \
        --predictions_dir  predictions/               \
        [--n_top_deg    50]                           \
        [--outdir       results/]

    # Legacy single-model mode (still works)
    python evaluate_perturbation.py \
        --ground_truth  gt.mtx.gz  \
        --predicted     pred.mtx.gz \
        [--outdir       results/]

Outputs (saved to --outdir)
---------------------------
Per-model sub-folder:
    {model}/metrics_summary.csv
    {model}/01_umap_gt_vs_model.png
    {model}/02_mean_expression_scatter.png
    {model}/03_delta_scatter.png
    {model}/04_top_deg_scatter.png
    {model}/05_violin_top_genes.png
    {model}/06_wasserstein_per_gene.png

Shared comparison plots (root outdir):
    00_volcano_gt.png               – Volcano on GT DEGs (reference, once)
    C01_metrics_heatmap.png         – All metrics × all models heatmap
    C02_metrics_radar.png           – Radar/spider chart per model
    C03_umap_all_models.png         – One UMAP panel per model + GT
    C04_delta_scatter_grid.png      – Δ-scatter grid (one panel per model)
    C05_mean_expr_scatter_grid.png  – Mean-expression scatter grid
    C06_deg_recall_grouped_bar.png  – DEG recall@k grouped bar chart
    C07_metric_bar_comparison.png   – Side-by-side bar chart (key metrics)
    C08_wasserstein_boxplot.png     – Per-gene Wasserstein distribution per model
    C09_deg_rank_heatmap.png        – DEG rank agreement heatmap (models × top-k genes)
    C10_violin_grid.png             – Violin grid: ctrl / GT / model1 / model2 / …
    metrics_all_models.csv          – Combined metrics table
"""

import argparse, os, warnings, glob
import numpy as np
import pandas as pd
import scipy.io as sio
import scipy.sparse as sp
import scipy.stats as stats
from scipy.spatial.distance import cdist

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyArrowPatch
import seaborn as sns

warnings.filterwarnings("ignore")

# ── colour helpers ────────────────────────────────────────────────────────────
GT_COLOR   = "#2B2D42"   # dark slate  – ground truth
CTRL_COLOR = "#8D99AE"   # steel grey  – control

def model_palette(n):
    """Return n visually distinct colours for models."""
    base = ["#E63946", "#2196F3", "#4CAF50", "#FF9800",
            "#9C27B0", "#00BCD4", "#F44336", "#8BC34A",
            "#3F51B5", "#FF5722"]
    if n <= len(base):
        return base[:n]
    cmap = plt.get_cmap("tab20")
    return [cmap(i / n) for i in range(n)]

FIG_DPI = 150

# ═══════════════════════════════════════════════════════════════════════════════
# I/O
# ═══════════════════════════════════════════════════════════════════════════════

def _open_maybe_gz(path):
    import gzip
    p = str(path)
    if p.endswith(".gz"):
        return gzip.open(p, "rb")
    return open(p, "rb")

def load_mtx(mtx_path, barcodes_path=None, features_path=None):
    """Load .mtx or .mtx.gz → (cells × genes) float32 ndarray + metadata."""
    import gzip, shutil, tempfile, pathlib

    path = pathlib.Path(mtx_path)
    if path.suffix == ".gz":
        tmp = tempfile.NamedTemporaryFile(suffix=".mtx", delete=False)
        with gzip.open(path, "rb") as fi, open(tmp.name, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        mat = sio.mmread(tmp.name)
        os.unlink(tmp.name)
    else:
        mat = sio.mmread(str(path))

    if sp.issparse(mat):
        mat = mat.tocsr()
    X = np.asarray(mat.todense(), dtype=np.float32)

    # 10x convention: rows = genes, cols = cells → transpose
    if X.shape[0] > X.shape[1] and X.shape[1] < 50_000:
        X = X.T

    n_cells, n_genes = X.shape

    def read_tsv_gz(p):
        if p is None or not os.path.exists(str(p)):
            return None
        return pd.read_csv(p, header=None, sep="\t", compression="infer")

    bc_df  = read_tsv_gz(barcodes_path)
    ft_df  = read_tsv_gz(features_path)

    barcodes = bc_df[0].tolist() if bc_df is not None else [f"cell_{i}" for i in range(n_cells)]
    features = ft_df.iloc[:, 0].tolist() if ft_df is not None else [f"gene_{i}" for i in range(n_genes)]

    # swap if shapes mismatch
    if len(features) == X.shape[0] and len(barcodes) == X.shape[1]:
        X = X.T
        barcodes, features = features, barcodes

    return X[:, :len(features)], barcodes[:X.shape[0]], features[:X.shape[1]]


def discover_models(predictions_dir):
    """Return {model_name: (mtx, barcodes, features)} paths."""
    models = {}
    for d in sorted(os.scandir(predictions_dir), key=lambda e: e.name):
        if not d.is_dir():
            continue
        mtx = os.path.join(d.path, "matrix.mtx.gz")
        bc  = os.path.join(d.path, "barcodes.tsv.gz")
        ft  = os.path.join(d.path, "features.tsv.gz")
        if os.path.exists(mtx):
            models[d.name] = (mtx,
                              bc  if os.path.exists(bc)  else None,
                              ft  if os.path.exists(ft)  else None)
    return models


def align_genes(feat_gt, X_gt, *model_data):
    """Intersect gene sets across GT and all models, return aligned arrays."""
    common = set(feat_gt)
    for _, feat in model_data:
        common &= set(feat)
    common = sorted(common)
    if not common:
        # fallback: use positional alignment
        n = min(len(feat_gt), *(len(f) for _, f in model_data))
        common = feat_gt[:n]
        X_gt_al = X_gt[:, :n]
        models_al = [X[:, :n] for X, _ in model_data]
        return common, X_gt_al, models_al

    gi_gt = [feat_gt.index(g) for g in common]
    X_gt_al = X_gt[:, gi_gt]
    models_al = []
    for X, feat in model_data:
        gi = [feat.index(g) for g in common]
        models_al.append(X[:, gi])
    return common, X_gt_al, models_al


# ═══════════════════════════════════════════════════════════════════════════════
# Normalisation
# ═══════════════════════════════════════════════════════════════════════════════

def normalise_log1p(X):
    lib = X.sum(axis=1, keepdims=True)
    lib[lib == 0] = 1
    return np.log1p(X / lib * 10_000)


# ═══════════════════════════════════════════════════════════════════════════════
# Metrics
# ═══════════════════════════════════════════════════════════════════════════════

def pearson_r(a, b):
    if np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return float("nan")
    r, _ = stats.pearsonr(a, b)
    return float(r)

def spearman_r(a, b):
    r, _ = stats.spearmanr(a, b)
    return float(r)

def r2_score(true, pred):
    ss_res = np.sum((true - pred) ** 2)
    ss_tot = np.sum((true - np.mean(true)) ** 2)
    return float(1 - ss_res / (ss_tot + 1e-12))

def mmd_rbf(X, Y, gamma=None):
    if gamma is None:
        gamma = 1.0 / X.shape[1]
    XX = np.dot(X, X.T); YY = np.dot(Y, Y.T); XY = np.dot(X, Y.T)
    dX = np.diag(XX); dY = np.diag(YY)
    K_XX = np.exp(-gamma * (dX[:, None] + dX[None, :] - 2 * XX))
    K_YY = np.exp(-gamma * (dY[:, None] + dY[None, :] - 2 * YY))
    K_XY = np.exp(-gamma * (dX[:, None] + dY[None, :] - 2 * XY))
    return float(K_XX.mean() + K_YY.mean() - 2 * K_XY.mean())

def deg_overlap(gt_genes, pred_genes, k):
    return len(set(gt_genes[:k]) & set(pred_genes[:k])) / max(k, 1)


def compute_deg(X_ctrl, X_pert, feature_names):
    mu_c = X_ctrl.mean(0); mu_p = X_pert.mean(0)
    log2fc = np.log2(mu_p + 1) - np.log2(mu_c + 1)
    pvals = np.array([
        stats.ttest_ind(X_ctrl[:, g], X_pert[:, g], equal_var=False)[1]
        for g in range(X_ctrl.shape[1])
    ])
    try:
        from statsmodels.stats.multitest import multipletests
        _, padj, _, _ = multipletests(pvals, method="fdr_bh")
    except Exception:
        padj = pvals
    df = pd.DataFrame({"gene": feature_names, "log2FC": log2fc,
                        "pval": pvals, "padj": padj,
                        "mu_ctrl": mu_c, "mu_pert": mu_p})
    df["absFC"] = df["log2FC"].abs()
    return df.sort_values("absFC", ascending=False).reset_index(drop=True)


def compute_metrics(mu_gt, mu_pred, delta_gt, delta_pred,
                    X_gt_norm, X_pred_norm, X_ctrl_norm,
                    gene_names, deg_gt, n_top, rng):
    m = {}
    m["Pearson_r_all"]   = pearson_r(mu_gt, mu_pred)
    m["Spearman_r_all"]  = spearman_r(mu_gt, mu_pred)
    m["R2_all"]          = r2_score(mu_gt, mu_pred)
    m["MSE_all"]         = float(np.mean((mu_gt - mu_pred) ** 2))
    m["MAE_all"]         = float(np.mean(np.abs(mu_gt - mu_pred)))
    m["Pearson_delta"]   = pearson_r(delta_gt, delta_pred)
    m["Spearman_delta"]  = spearman_r(delta_gt, delta_pred)
    m["R2_delta"]        = r2_score(delta_gt, delta_pred)
    m["MSE_delta"]       = float(np.mean((delta_gt - delta_pred) ** 2))

    deg_pred = compute_deg(X_ctrl_norm, X_pred_norm, gene_names)
    top_gt   = deg_gt["gene"].values[:n_top]
    top_pred = deg_pred["gene"].values[:n_top]

    top_idx = [list(gene_names).index(g) for g in top_gt if g in gene_names][:n_top]
    if top_idx:
        m["Pearson_r_topDEG"] = pearson_r(mu_gt[top_idx], mu_pred[top_idx])
        m["R2_topDEG"]        = r2_score(mu_gt[top_idx], mu_pred[top_idx])
        m["MSE_topDEG"]       = float(np.mean((mu_gt[top_idx] - mu_pred[top_idx]) ** 2))
    else:
        m["Pearson_r_topDEG"] = float("nan")
        m["R2_topDEG"]        = float("nan")
        m["MSE_topDEG"]       = float("nan")

    for k in [10, 20, 50, 100]:
        if k <= n_top:
            m[f"DEG_recall@{k}"] = deg_overlap(top_gt, top_pred, k)

    sg = rng.choice(len(gene_names), size=min(200, len(gene_names)), replace=False)
    m["Wasserstein_mean"] = float(np.mean([
        stats.wasserstein_distance(X_gt_norm[:, g].flatten(),
                                   X_pred_norm[:, g].flatten()) for g in sg]))

    from sklearn.decomposition import PCA
    n_pc = min(30, X_gt_norm.shape[0]-1, X_gt_norm.shape[1]-1, X_pred_norm.shape[0]-1)
    pca = PCA(n_components=n_pc, random_state=42)
    pca.fit(np.vstack([X_gt_norm, X_pred_norm]))
    m["MMD_RBF"] = mmd_rbf(pca.transform(X_gt_norm), pca.transform(X_pred_norm))

    try:
        from sklearn.metrics import average_precision_score
        true_bin = (deg_gt["padj"] < 0.05).astype(int).values
        score = np.array([
            deg_pred.loc[deg_pred["gene"]==g, "absFC"].values[0]
            if g in deg_pred["gene"].values else 0.
            for g in deg_gt["gene"]
        ])
        m["AUC_PR_DEG"] = float(average_precision_score(true_bin, score))
    except Exception:
        m["AUC_PR_DEG"] = float("nan")

    return m, deg_pred, top_idx, top_gt, top_pred


# ═══════════════════════════════════════════════════════════════════════════════
# Embedding helpers
# ═══════════════════════════════════════════════════════════════════════════════

def compute_umap(X, n_pcs=30, n_neighbors=15, seed=42):
    from sklearn.decomposition import PCA
    n_pcs = min(n_pcs, X.shape[0]-1, X.shape[1]-1)
    emb = PCA(n_components=n_pcs, random_state=seed).fit_transform(X)
    try:
        import umap as umap_lib
        return umap_lib.UMAP(n_neighbors=n_neighbors, min_dist=0.3,
                             random_state=seed).fit_transform(emb)
    except Exception:
        return PCA(n_components=2, random_state=seed).fit_transform(X)

def leiden_clusters(X, resolution=0.5):
    try:
        import scanpy as sc, anndata as ad
        adata = ad.AnnData(X.astype(np.float32))
        sc.pp.neighbors(adata, use_rep="X")
        sc.tl.leiden(adata, resolution=resolution)
        return adata.obs["leiden"].astype(int).values
    except Exception:
        from sklearn.cluster import KMeans
        k = max(2, min(10, X.shape[0]//30))
        return KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(X)


# ═══════════════════════════════════════════════════════════════════════════════
# Shared styling
# ═══════════════════════════════════════════════════════════════════════════════

def style_ax(ax, title="", xlabel="", ylabel=""):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if title:  ax.set_title(title, fontsize=10, fontweight="bold", pad=5)
    if xlabel: ax.set_xlabel(xlabel, fontsize=8)
    if ylabel: ax.set_ylabel(ylabel, fontsize=8)
    ax.tick_params(labelsize=7)

def savefig(fig, path):
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# Per-model plots (saved in per-model subfolder)
# ═══════════════════════════════════════════════════════════════════════════════

def plot_umap_gt_vs_model(emb_gt, emb_model, labels_gt, model_name, color, outdir):
    """GT cells (dark) + model cells (colour) in same UMAP space."""
    X_all = np.vstack([emb_gt, emb_model])
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.scatter(X_all[:len(emb_gt), 0], X_all[:len(emb_gt), 1],
               c=GT_COLOR, s=5, alpha=0.5, label="Ground Truth", rasterized=True)
    ax.scatter(X_all[len(emb_gt):, 0], X_all[len(emb_gt):, 1],
               c=color, s=5, alpha=0.5, label=model_name, rasterized=True)
    ax.legend(fontsize=8, frameon=False, markerscale=2)
    style_ax(ax, f"UMAP – GT vs {model_name}", "UMAP 1", "UMAP 2")
    savefig(fig, os.path.join(outdir, "01_umap_gt_vs_model.png"))


def plot_mean_scatter_single(mu_gt, mu_pred, r2, pearson, model_name, color, outdir):
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.scatter(mu_gt, mu_pred, s=4, alpha=0.35, c=color, rasterized=True)
    lims = [min(mu_gt.min(), mu_pred.min()), max(mu_gt.max(), mu_pred.max())]
    ax.plot(lims, lims, "k--", lw=0.8)
    ax.text(0.05, 0.92, f"R²={r2:.3f}\nr={pearson:.3f}",
            transform=ax.transAxes, fontsize=8,
            bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))
    ax.set_xlim(lims); ax.set_ylim(lims)
    style_ax(ax, f"Mean Expression – {model_name}",
             "GT (mean log-norm)", "Predicted (mean log-norm)")
    savefig(fig, os.path.join(outdir, "02_mean_expression_scatter.png"))


def plot_delta_scatter_single(dgt, dpred, pearson_d, r2_d, model_name, color, outdir):
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.scatter(dgt, dpred, s=4, alpha=0.35, c=color, rasterized=True)
    lims = [min(dgt.min(), dpred.min()), max(dgt.max(), dpred.max())]
    ax.plot(lims, lims, "k--", lw=0.8)
    ax.axhline(0, c="grey", lw=0.4, ls=":"); ax.axvline(0, c="grey", lw=0.4, ls=":")
    ax.text(0.05, 0.92, f"Pearson(Δ)={pearson_d:.3f}\nR²(Δ)={r2_d:.3f}",
            transform=ax.transAxes, fontsize=8,
            bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))
    ax.set_xlim(lims); ax.set_ylim(lims)
    style_ax(ax, f"Δ-Expression – {model_name}", "Δ GT", "Δ Predicted")
    savefig(fig, os.path.join(outdir, "03_delta_scatter.png"))


def plot_top_deg_scatter_single(mu_gt, mu_pred, top_idx, gene_names,
                                 pearson_d, r2_d, n_top, model_name, color, outdir):
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.scatter(mu_gt, mu_pred, s=3, alpha=0.2, c="#B0BEC5", rasterized=True)
    ax.scatter(mu_gt[top_idx], mu_pred[top_idx], s=18, alpha=0.85, c=color, zorder=3,
               label=f"top {n_top} DEGs")
    lims = [min(mu_gt.min(), mu_pred.min()), max(mu_gt.max(), mu_pred.max())]
    ax.plot(lims, lims, "k--", lw=0.8)
    ax.set_xlim(lims); ax.set_ylim(lims)
    ax.text(0.05, 0.92, f"r={pearson_d:.3f}\nR²={r2_d:.3f}",
            transform=ax.transAxes, fontsize=8,
            bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))
    for i in top_idx[:8]:
        ax.text(mu_gt[i], mu_pred[i], gene_names[i], fontsize=6)
    ax.legend(fontsize=8, frameon=False)
    style_ax(ax, f"Top-DEG Expression – {model_name}",
             "GT (mean log-norm)", "Predicted (mean log-norm)")
    savefig(fig, os.path.join(outdir, "04_top_deg_scatter.png"))


def plot_violin_single(X_ctrl, X_gt, X_pred, top_idx, gene_names, model_name, color, outdir):
    n = min(5, len(top_idx))
    if n == 0:
        return
    fig, axes = plt.subplots(1, n, figsize=(2.4*n, 4), sharey=False)
    if n == 1: axes = [axes]
    for ax, gi in zip(axes, top_idx[:n]):
        gname = gene_names[gi]
        parts = ax.violinplot(
            [X_ctrl[:, gi].flatten(), X_gt[:, gi].flatten(), X_pred[:, gi].flatten()],
            showmedians=True, showextrema=False)
        colours = [CTRL_COLOR, GT_COLOR, color]
        for pc, c in zip(parts["bodies"], colours):
            pc.set_facecolor(c); pc.set_alpha(0.75)
        parts["cmedians"].set_color("black")
        ax.set_xticks([1, 2, 3])
        ax.set_xticklabels(["Ctrl", "GT", "Pred"], fontsize=7)
        ax.set_title(gname, fontsize=8, fontweight="bold")
        ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    fig.suptitle(f"Expression Distributions – {model_name}", fontsize=10, y=1.02)
    fig.tight_layout()
    savefig(fig, os.path.join(outdir, "05_violin_top_genes.png"))


def plot_wasserstein_single(X_gt, X_pred, top_idx, gene_names, color, outdir):
    idx = top_idx[:30]
    wdists = [stats.wasserstein_distance(X_gt[:, i].flatten(), X_pred[:, i].flatten())
              for i in idx]
    names = [gene_names[i] for i in idx]
    order = np.argsort(wdists)[::-1]
    fig, ax = plt.subplots(figsize=(max(6, len(idx)*0.45), 3.5))
    ax.bar([names[i] for i in order], [wdists[i] for i in order],
           color=color, edgecolor="white", alpha=0.85)
    ax.axhline(np.median(wdists), c="black", lw=1, ls="--",
               label=f"median={np.median(wdists):.3f}")
    ax.set_xticklabels([names[i] for i in order], rotation=45, ha="right", fontsize=7)
    ax.legend(fontsize=8, frameon=False)
    style_ax(ax, "Wasserstein Distance – Top DEGs", "Gene", "Wasserstein Distance")
    savefig(fig, os.path.join(outdir, "06_wasserstein_per_gene.png"))


# ═══════════════════════════════════════════════════════════════════════════════
# Ground-truth reference plot (once)
# ═══════════════════════════════════════════════════════════════════════════════

def plot_volcano_gt(deg_gt, outdir, n_label=12):
    df = deg_gt.copy()
    df["-log10padj"] = -np.log10(df["padj"].clip(lower=1e-300))
    sig = df[(df["padj"] < 0.05) & (df["absFC"] > 1)]
    up  = sig[sig["log2FC"] > 0]; dn = sig[sig["log2FC"] < 0]
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(df["log2FC"], df["-log10padj"], s=4, alpha=0.3, c="#90A4AE", rasterized=True)
    ax.scatter(up["log2FC"], up["-log10padj"], s=8, alpha=0.85, c="#E53935",
               label=f"Up ({len(up)})")
    ax.scatter(dn["log2FC"], dn["-log10padj"], s=8, alpha=0.85, c="#1E88E5",
               label=f"Down ({len(dn)})")
    ax.axhline(-np.log10(0.05), c="grey", lw=0.8, ls="--")
    ax.axvline(1, c="grey", lw=0.8, ls="--"); ax.axvline(-1, c="grey", lw=0.8, ls="--")
    top = df.nsmallest(n_label, "padj")
    texts = [ax.text(r["log2FC"], r["-log10padj"], r["gene"], fontsize=6)
             for _, r in top.iterrows()]
    try:
        from adjustText import adjust_text
        adjust_text(texts, ax=ax, arrowprops=dict(arrowstyle="-", color="grey", lw=0.4))
    except ImportError:
        pass
    ax.legend(fontsize=8, frameon=False)
    style_ax(ax, "Volcano – Ground Truth DEGs",
             "log₂ Fold Change (Perturbed vs Control)", "−log₁₀(adj. p-value)")
    savefig(fig, os.path.join(outdir, "00_volcano_gt.png"))


# ═══════════════════════════════════════════════════════════════════════════════
# Multi-model comparison plots
# ═══════════════════════════════════════════════════════════════════════════════

def plot_metrics_heatmap(metrics_df, outdir):
    """
    Nature-benchmarking style: metrics × models heatmap with colour normalised
    per metric (so higher = always better after sign flip for error metrics).
    """
    # Columns to show and whether higher = better
    show_cols = {
        "Pearson_r_all":    True,
        "R2_all":           True,
        "MSE_all":          False,
        "MAE_all":          False,
        "Pearson_delta":    True,
        "R2_delta":         True,
        "MSE_delta":        False,
        "Pearson_r_topDEG": True,
        "R2_topDEG":        True,
        "MSE_topDEG":       False,
        "DEG_recall@10":    True,
        "DEG_recall@20":    True,
        "DEG_recall@50":    True,
        "Wasserstein_mean": False,
        "MMD_RBF":          False,
        "AUC_PR_DEG":       True,
    }
    cols = [c for c in show_cols if c in metrics_df.columns]
    higher_better = {c: show_cols[c] for c in cols}

    sub = metrics_df.set_index("model")[cols].copy().astype(float)

    # Normalise each column 0-1, flipping error metrics
    normed = sub.copy()
    for c in cols:
        col = sub[c].values.astype(float)
        rng = col.max() - col.min()
        if rng < 1e-12:
            normed[c] = 0.5
        else:
            n = (col - col.min()) / rng
            normed[c] = n if higher_better[c] else 1 - n

    fig, ax = plt.subplots(figsize=(max(10, len(cols)*0.75), max(4, len(sub)*0.55)))
    im = ax.imshow(normed.values, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")

    ax.set_xticks(range(len(cols))); ax.set_xticklabels(cols, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(sub)));  ax.set_yticklabels(sub.index, fontsize=9)

    # annotate with raw values
    for i in range(len(sub)):
        for j, c in enumerate(cols):
            val = sub.iloc[i, j]
            ax.text(j, i, f"{val:.3f}" if not np.isnan(val) else "—",
                    ha="center", va="center", fontsize=7,
                    color="black" if 0.3 < normed.iloc[i, j] < 0.8 else "white")

    cb = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    cb.set_label("Normalised score\n(green = best)", fontsize=8)
    ax.set_title("Metric Comparison Across Models", fontsize=12, fontweight="bold", pad=10)
    fig.tight_layout()
    savefig(fig, os.path.join(outdir, "C01_metrics_heatmap.png"))


def plot_metrics_radar(metrics_df, colors, outdir):
    """Spider/radar chart — classic benchmarking figure (scArchon, Systema style)."""
    radar_metrics = ["Pearson_r_all", "R2_all", "Pearson_delta",
                     "Pearson_r_topDEG", "DEG_recall@20", "AUC_PR_DEG"]
    radar_metrics = [m for m in radar_metrics if m in metrics_df.columns]
    if len(radar_metrics) < 3:
        return

    sub = metrics_df.set_index("model")[radar_metrics].astype(float)
    # Normalise each metric 0-1
    for c in radar_metrics:
        mn, mx = sub[c].min(), sub[c].max()
        sub[c] = (sub[c] - mn) / (mx - mn + 1e-12)

    N = len(radar_metrics)
    angles = np.linspace(0, 2*np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    for (model, row), color in zip(sub.iterrows(), colors):
        vals = row.tolist() + row.tolist()[:1]
        ax.plot(angles, vals, color=color, lw=2, label=model)
        ax.fill(angles, vals, color=color, alpha=0.08)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([m.replace("_", "\n") for m in radar_metrics], fontsize=8)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=6)
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.15), fontsize=8, frameon=False)
    ax.set_title("Model Comparison – Radar Chart\n(normalised per metric)",
                 fontsize=10, fontweight="bold", pad=20)
    savefig(fig, os.path.join(outdir, "C02_metrics_radar.png"))


def plot_umap_all_models(emb_gt, model_embs, model_names, colors, labels_gt, outdir):
    """
    One panel per model + one GT-only panel.
    GT cells in dark background; model cells overlaid in model colour.
    Mimics GEARS Fig 3 / Systema supplementary panels.
    """
    n = len(model_names) + 1
    ncols = min(4, n)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols,
                             figsize=(ncols * 3.5, nrows * 3.2))
    axes = np.array(axes).flatten()

    # panel 0: GT only, coloured by cluster
    cmap = plt.get_cmap("tab20")
    unique = np.unique(labels_gt)
    cmap_map = {c: cmap(i / max(len(unique), 1)) for i, c in enumerate(unique)}
    col_gt = [cmap_map[l] for l in labels_gt]
    axes[0].scatter(emb_gt[:, 0], emb_gt[:, 1], c=col_gt, s=5, alpha=0.6, rasterized=True)
    axes[0].set_title("Ground Truth\n(Leiden clusters)", fontsize=9, fontweight="bold")

    # remaining panels: GT (grey) + model (colour)
    for i, (name, emb_m, col) in enumerate(zip(model_names, model_embs, colors), start=1):
        ax = axes[i]
        ax.scatter(emb_gt[:, 0], emb_gt[:, 1], c=GT_COLOR, s=3, alpha=0.3,
                   rasterized=True, label="GT")
        ax.scatter(emb_m[:, 0], emb_m[:, 1], c=col, s=3, alpha=0.5,
                   rasterized=True, label=name)
        ax.set_title(name, fontsize=9, fontweight="bold")
        ax.legend(fontsize=6, frameon=False, markerscale=2, loc="lower right")

    for ax in axes[n:]:
        ax.set_visible(False)
    for ax in axes[:n]:
        ax.set_xticks([]); ax.set_yticks([])
        ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)

    fig.suptitle("UMAP: Ground Truth vs Each Model", fontsize=12, fontweight="bold", y=1.01)
    fig.tight_layout()
    savefig(fig, os.path.join(outdir, "C03_umap_all_models.png"))


def plot_delta_scatter_grid(model_deltas, gt_delta, model_names, colors, outdir):
    """Δ-expression scatter grid – one panel per model. GEARS / CPA style."""
    n = len(model_names)
    ncols = min(4, n); nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 3.5, nrows * 3.5))
    axes = np.array(axes).flatten()

    for i, (name, delta_pred, color) in enumerate(zip(model_names, model_deltas, colors)):
        ax = axes[i]
        ax.scatter(gt_delta, delta_pred, s=3, alpha=0.3, c=color, rasterized=True)
        lims = [min(gt_delta.min(), delta_pred.min()),
                max(gt_delta.max(), delta_pred.max())]
        ax.plot(lims, lims, "k--", lw=0.8)
        ax.axhline(0, c="grey", lw=0.3, ls=":"); ax.axvline(0, c="grey", lw=0.3, ls=":")
        r = pearson_r(gt_delta, delta_pred)
        ax.text(0.05, 0.92, f"Pearson(Δ)={r:.3f}",
                transform=ax.transAxes, fontsize=7,
                bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))
        ax.set_xlim(lims); ax.set_ylim(lims)
        style_ax(ax, name, "Δ GT", "Δ Predicted")

    for ax in axes[n:]:
        ax.set_visible(False)
    fig.suptitle("Δ-Expression Scatter (Perturbed − Control)", fontsize=12,
                 fontweight="bold", y=1.01)
    fig.tight_layout()
    savefig(fig, os.path.join(outdir, "C04_delta_scatter_grid.png"))


def plot_mean_expr_scatter_grid(mu_gt, model_means, model_names, colors, outdir):
    """Mean expression scatter grid. scGen / CPA style."""
    n = len(model_names)
    ncols = min(4, n); nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 3.5, nrows * 3.5))
    axes = np.array(axes).flatten()

    for i, (name, mu_pred, color) in enumerate(zip(model_names, model_means, colors)):
        ax = axes[i]
        ax.scatter(mu_gt, mu_pred, s=3, alpha=0.3, c=color, rasterized=True)
        lims = [min(mu_gt.min(), mu_pred.min()), max(mu_gt.max(), mu_pred.max())]
        ax.plot(lims, lims, "k--", lw=0.8)
        ax.set_xlim(lims); ax.set_ylim(lims)
        r  = pearson_r(mu_gt, mu_pred)
        r2 = r2_score(mu_gt, mu_pred)
        ax.text(0.05, 0.92, f"r={r:.3f}\nR²={r2:.3f}",
                transform=ax.transAxes, fontsize=7,
                bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))
        style_ax(ax, name, "GT mean", "Predicted mean")

    for ax in axes[n:]:
        ax.set_visible(False)
    fig.suptitle("Mean Gene Expression (All Genes)", fontsize=12, fontweight="bold", y=1.01)
    fig.tight_layout()
    savefig(fig, os.path.join(outdir, "C05_mean_expr_scatter_grid.png"))


def plot_deg_recall_grouped_bar(metrics_df, colors, outdir):
    """
    Grouped bar chart: DEG recall@k for each model at each k threshold.
    scArchon / benchmarking paper style.
    """
    ks = [k for k in [10, 20, 50, 100] if f"DEG_recall@{k}" in metrics_df.columns]
    if not ks:
        return
    models = metrics_df["model"].tolist()
    x = np.arange(len(ks))
    width = 0.8 / max(len(models), 1)

    fig, ax = plt.subplots(figsize=(max(6, len(ks)*2), 4))
    for i, (model, color) in enumerate(zip(models, colors)):
        row = metrics_df[metrics_df["model"] == model].iloc[0]
        vals = [row.get(f"DEG_recall@{k}", np.nan) for k in ks]
        bars = ax.bar(x + i * width - (len(models)-1)*width/2, vals,
                      width=width*0.9, label=model, color=color, alpha=0.85)
        for bar, v in zip(bars, vals):
            if not np.isnan(v):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                        f"{v:.2f}", ha="center", va="bottom", fontsize=6, rotation=90)

    ax.set_xticks(x); ax.set_xticklabels([f"Top-{k}" for k in ks], fontsize=9)
    ax.set_ylim(0, 1.25)
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    style_ax(ax, "DEG Recall @ Top-k", "Threshold", "Fraction of GT DEGs Recovered")
    savefig(fig, os.path.join(outdir, "C06_deg_recall_grouped_bar.png"))


def plot_metric_bar_comparison(metrics_df, colors, outdir):
    """
    Key metrics as side-by-side horizontal bar charts.
    One subplot per metric, models on y-axis.  Systema / scArchon style.
    """
    key = ["Pearson_delta", "R2_delta", "Pearson_r_topDEG",
           "Wasserstein_mean", "MMD_RBF", "AUC_PR_DEG"]
    key = [m for m in key if m in metrics_df.columns]
    lower_better = {"Wasserstein_mean", "MMD_RBF", "MSE_all", "MSE_delta"}

    ncols = min(3, len(key)); nrows = int(np.ceil(len(key) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols*4, nrows*2.5))
    axes = np.array(axes).flatten()

    models = metrics_df["model"].tolist()

    for ai, metric in enumerate(key):
        ax = axes[ai]
        vals = metrics_df.set_index("model")[metric].astype(float)
        best = vals.idxmin() if metric in lower_better else vals.idxmax()
        bar_cols = [colors[i] if m != best else "#FFD600"
                    for i, m in enumerate(models)]
        ax.barh(models, vals[models], color=bar_cols, edgecolor="white", height=0.6)
        ax.set_xlabel(metric.replace("_", " "), fontsize=8)
        for j, (model, v) in enumerate(zip(models, vals[models])):
            ax.text(v + abs(v)*0.01, j, f"{v:.3f}", va="center", fontsize=7)
        ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
        ax.tick_params(labelsize=8)
        arrow = "↓ better" if metric in lower_better else "↑ better"
        ax.set_title(f"{metric.replace('_',' ')}\n({arrow})", fontsize=8, fontweight="bold")

    for ax in axes[len(key):]:
        ax.set_visible(False)
    fig.suptitle("Key Metric Comparison (gold = best)", fontsize=12, fontweight="bold", y=1.02)
    fig.tight_layout()
    savefig(fig, os.path.join(outdir, "C07_metric_bar_comparison.png"))


def plot_wasserstein_boxplot(all_wdists, model_names, colors, outdir):
    """
    Box/violin plot of per-gene Wasserstein distances across all models.
    CPA benchmark style.
    """
    fig, ax = plt.subplots(figsize=(max(5, len(model_names)*1.2), 4))
    parts = ax.violinplot(all_wdists, showmedians=True, showextrema=True)
    for pc, col in zip(parts["bodies"], colors):
        pc.set_facecolor(col); pc.set_alpha(0.7)
    parts["cmedians"].set_color("black")
    parts["cmaxes"].set_color("grey"); parts["cmins"].set_color("grey")
    parts["cbars"].set_color("grey")
    ax.set_xticks(range(1, len(model_names)+1))
    ax.set_xticklabels(model_names, rotation=20, ha="right", fontsize=9)
    style_ax(ax, "Per-Gene Wasserstein Distance (sampled genes)",
             "Model", "Wasserstein Distance")
    savefig(fig, os.path.join(outdir, "C08_wasserstein_boxplot.png"))


def plot_deg_rank_heatmap(deg_gt, model_deg_dfs, model_names, n_top, outdir):
    """
    Heatmap: rows = top-N GT DEGs, columns = models.
    Cell value = predicted rank of that gene (lower = better).
    scREPA / benchmarking paper style.
    """
    top_genes = deg_gt["gene"].values[:n_top]
    data = {}
    for name, deg_pred in zip(model_names, model_deg_dfs):
        rank_map = {g: i+1 for i, g in enumerate(deg_pred["gene"])}
        data[name] = [rank_map.get(g, n_top*3) for g in top_genes]

    df_hm = pd.DataFrame(data, index=top_genes)

    fig, ax = plt.subplots(figsize=(max(6, len(model_names)*1.2), max(6, n_top*0.3)))
    sns.heatmap(df_hm, ax=ax, cmap="YlOrRd_r", annot=False,
                xticklabels=True, yticklabels=True,
                cbar_kws={"label": "Predicted DEG rank (lower=better)", "shrink": 0.5})
    ax.set_xticklabels(ax.get_xticklabels(), fontsize=9, rotation=25, ha="right")
    ax.set_yticklabels(ax.get_yticklabels(), fontsize=7)
    ax.set_title(f"DEG Rank Heatmap – Top-{n_top} GT DEGs", fontsize=11, fontweight="bold")
    fig.tight_layout()
    savefig(fig, os.path.join(outdir, "C09_deg_rank_heatmap.png"))


def plot_violin_grid(X_ctrl, X_gt, model_Xs, model_names, colors,
                     top_idx, gene_names, n_genes, outdir):
    """
    Violin grid: rows = top-N genes, columns = ctrl / GT / model1 / model2 / …
    scREPA Fig 2c extended to multiple models.
    """
    n_genes = min(n_genes, len(top_idx))
    if n_genes == 0:
        return
    n_sources = 2 + len(model_names)  # ctrl + GT + models
    fig, axes = plt.subplots(n_genes, n_sources,
                             figsize=(n_sources * 2.0, n_genes * 2.0),
                             sharey="row")
    if n_genes == 1:
        axes = axes[np.newaxis, :]
    if n_sources == 1:
        axes = axes[:, np.newaxis]

    source_labels = ["Ctrl", "GT"] + model_names
    source_colors = [CTRL_COLOR, GT_COLOR] + colors
    source_Xs     = [X_ctrl, X_gt] + list(model_Xs)

    for row, gi in enumerate(top_idx[:n_genes]):
        gname = gene_names[gi]
        for col, (src_X, src_col, src_label) in enumerate(
                zip(source_Xs, source_colors, source_labels)):
            ax = axes[row, col]
            vals = src_X[:, gi].flatten()
            parts = ax.violinplot([vals], showmedians=True, showextrema=False)
            parts["bodies"][0].set_facecolor(src_col)
            parts["bodies"][0].set_alpha(0.75)
            parts["cmedians"].set_color("black")
            ax.set_xticks([]); ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["bottom"].set_visible(False)
            ax.tick_params(labelsize=6)
            if row == 0:
                ax.set_title(src_label, fontsize=8, fontweight="bold", color=src_col)
            if col == 0:
                ax.set_ylabel(gname, fontsize=8, rotation=0, ha="right", labelpad=40)

    fig.suptitle("Expression Distributions: Control / GT / Each Model",
                 fontsize=11, fontweight="bold", y=1.01)
    fig.tight_layout()
    savefig(fig, os.path.join(outdir, "C10_violin_grid.png"))


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main(args):
    os.makedirs(args.outdir, exist_ok=True)
    rng = np.random.default_rng(42)

    plt.rcParams.update({"font.family": "DejaVu Sans",
                         "axes.linewidth": 0.8, "figure.dpi": FIG_DPI})
    sns.set_style("whitegrid", {"grid.linestyle": ":"})

    # ── Resolve models ────────────────────────────────────────────────────────
    if args.predictions_dir:
        model_paths = discover_models(args.predictions_dir)
        if not model_paths:
            raise RuntimeError(f"No model subfolders found in {args.predictions_dir}")
        print(f"Found {len(model_paths)} models: {list(model_paths.keys())}")
    elif args.predicted:
        # legacy single-model
        model_paths = {"predicted": (args.predicted, args.pred_barcodes, args.pred_features)}
    else:
        raise ValueError("Provide either --predictions_dir or --predicted")

    model_names = list(model_paths.keys())
    colors = model_palette(len(model_names))

    # ── Load ground truth ─────────────────────────────────────────────────────
    print("\n[1] Loading ground truth …")
    gt_bc  = os.path.join(args.ground_truth, "barcodes.tsv.gz")
    gt_ft  = os.path.join(args.ground_truth, "features.tsv.gz")
    gt_mat = os.path.join(args.ground_truth, "matrix.mtx.gz")
    X_gt_raw, bc_gt, feat_gt = load_mtx(gt_mat, gt_bc, gt_ft)
    print(f"  GT: {X_gt_raw.shape[0]} cells × {X_gt_raw.shape[1]} genes")

    # ── Load all models ───────────────────────────────────────────────────────
    print("\n[2] Loading model predictions …")
    model_raws = {}
    model_feats = {}
    for name, (mtx, bc, ft) in model_paths.items():
        X, bc_m, ft_m = load_mtx(mtx, bc, ft)
        model_raws[name]  = X
        model_feats[name] = ft_m
        print(f"  {name}: {X.shape[0]} cells × {X.shape[1]} genes")

    # ── Align genes ───────────────────────────────────────────────────────────
    print("\n[3] Aligning genes across GT and all models …")
    model_data_for_align = [(model_raws[n], model_feats[n]) for n in model_names]
    gene_names, X_gt_al, model_als = align_genes(feat_gt, X_gt_raw, *model_data_for_align)
    print(f"  Common genes: {len(gene_names)}")
    model_aligned = {n: X for n, X in zip(model_names, model_als)}

    # ── Normalise ─────────────────────────────────────────────────────────────
    print("\n[4] Normalising …")
    X_gt_norm = normalise_log1p(X_gt_al)
    model_norms = {n: normalise_log1p(model_aligned[n]) for n in model_names}

    # Synthetic control (20% of GT cells used as proxy unperturbed state)
    ctrl_idx  = rng.choice(len(X_gt_norm), size=max(10, len(X_gt_norm)//5), replace=False)
    X_ctrl_norm = X_gt_norm[ctrl_idx]
    mu_ctrl     = X_ctrl_norm.mean(0)
    mu_gt       = X_gt_norm.mean(0)
    delta_gt    = mu_gt - mu_ctrl

    # ── GT DEG (computed once) ────────────────────────────────────────────────
    print("\n[5] Computing GT DEGs …")
    deg_gt = compute_deg(X_ctrl_norm, X_gt_norm, gene_names)
    n_top  = min(args.n_top_deg, len(gene_names))

    # ── Per-model metrics & per-model plots ───────────────────────────────────
    print("\n[6] Computing per-model metrics and plots …")
    all_metrics  = []
    model_means  = []
    model_deltas = []
    model_deg_dfs = []
    model_top_idxs = []
    model_wdist_samples = []

    for name, color in zip(model_names, colors):
        print(f"\n  ── {name} ──")
        X_pred_norm = model_norms[name]
        mu_pred     = X_pred_norm.mean(0)
        delta_pred  = mu_pred - mu_ctrl

        m, deg_pred, top_idx, top_gt, top_pred = compute_metrics(
            mu_gt, mu_pred, delta_gt, delta_pred,
            X_gt_norm, X_pred_norm, X_ctrl_norm,
            gene_names, deg_gt, n_top, rng)

        m["model"] = name
        all_metrics.append(m)
        model_means.append(mu_pred)
        model_deltas.append(delta_pred)
        model_deg_dfs.append(deg_pred)
        model_top_idxs.append(top_idx)

        # per-gene Wasserstein sample for boxplot
        sg = rng.choice(len(gene_names), size=min(200, len(gene_names)), replace=False)
        wdists = [stats.wasserstein_distance(
                      X_gt_norm[:, g].flatten(), X_pred_norm[:, g].flatten())
                  for g in sg]
        model_wdist_samples.append(wdists)

        print(f"    Pearson_delta={m['Pearson_delta']:.4f}  "
              f"R2_delta={m['R2_delta']:.4f}  "
              f"Wasserstein_mean={m['Wasserstein_mean']:.4f}")

        # Per-model output folder
        mdir = os.path.join(args.outdir, name)
        os.makedirs(mdir, exist_ok=True)

        # ── UMAP for this model (computed in combined space) ──────────────────
        X_comb = np.vstack([X_gt_norm, X_pred_norm])
        emb_comb = compute_umap(X_comb)
        emb_gt_m  = emb_comb[:len(X_gt_norm)]
        emb_m     = emb_comb[len(X_gt_norm):]
        labels_gt_m = leiden_clusters(X_gt_norm)

        plot_umap_gt_vs_model(emb_gt_m, emb_m, labels_gt_m, name, color, mdir)
        plot_mean_scatter_single(mu_gt, mu_pred, m["R2_all"], m["Pearson_r_all"],
                                 name, color, mdir)
        plot_delta_scatter_single(delta_gt, delta_pred, m["Pearson_delta"],
                                  m["R2_delta"], name, color, mdir)
        if top_idx:
            plot_top_deg_scatter_single(mu_gt, mu_pred, top_idx, gene_names,
                                        m["Pearson_r_topDEG"], m["R2_topDEG"],
                                        n_top, name, color, mdir)
        plot_violin_single(X_ctrl_norm, X_gt_norm, X_pred_norm,
                           top_idx, gene_names, name, color, mdir)
        if top_idx:
            plot_wasserstein_single(X_gt_norm, X_pred_norm, top_idx, gene_names,
                                    color, mdir)

        # Save per-model metrics
        pd.DataFrame([m]).to_csv(os.path.join(mdir, "metrics_summary.csv"), index=False)

    # ── GT reference plots (once) ─────────────────────────────────────────────
    print("\n[7] Plotting GT reference …")
    plot_volcano_gt(deg_gt, args.outdir)

    # ── Combined metrics table ────────────────────────────────────────────────
    metrics_df = pd.DataFrame(all_metrics)
    cols = ["model"] + [c for c in metrics_df.columns if c != "model"]
    metrics_df = metrics_df[cols]
    metrics_df.to_csv(os.path.join(args.outdir, "metrics_all_models.csv"), index=False)

    print("\n[8] Generating multi-model comparison plots …")

    # C01: Heatmap
    plot_metrics_heatmap(metrics_df, args.outdir)

    # C02: Radar
    plot_metrics_radar(metrics_df, colors, args.outdir)

    # C03: UMAP all models (compute shared embedding)
    print("  Computing shared UMAP for all models …")
    X_all = np.vstack([X_gt_norm] + [model_norms[n] for n in model_names])
    emb_all = compute_umap(X_all)
    emb_gt_shared = emb_all[:len(X_gt_norm)]
    split = len(X_gt_norm)
    emb_models = []
    for n in model_names:
        sz = len(model_norms[n])
        emb_models.append(emb_all[split:split+sz])
        split += sz
    labels_gt_shared = leiden_clusters(X_gt_norm)
    plot_umap_all_models(emb_gt_shared, emb_models, model_names, colors,
                         labels_gt_shared, args.outdir)

    # C04: Δ scatter grid
    plot_delta_scatter_grid(model_deltas, delta_gt, model_names, colors, args.outdir)

    # C05: Mean expression scatter grid
    plot_mean_expr_scatter_grid(mu_gt, model_means, model_names, colors, args.outdir)

    # C06: DEG recall grouped bar
    plot_deg_recall_grouped_bar(metrics_df, colors, args.outdir)

    # C07: Key metric bars
    plot_metric_bar_comparison(metrics_df, colors, args.outdir)

    # C08: Wasserstein boxplot
    plot_wasserstein_boxplot(model_wdist_samples, model_names, colors, args.outdir)

    # C09: DEG rank heatmap
    plot_deg_rank_heatmap(deg_gt, model_deg_dfs, model_names, n_top, args.outdir)

    # C10: Violin grid (top 5 genes across all models)
    shared_top_idx = model_top_idxs[0] if model_top_idxs else []
    plot_violin_grid(X_ctrl_norm, X_gt_norm,
                     [model_norms[n] for n in model_names],
                     model_names, colors, shared_top_idx, gene_names,
                     n_genes=5, outdir=args.outdir)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("METRICS SUMMARY")
    print(f"{'='*60}")
    display_cols = ["model", "Pearson_delta", "R2_delta",
                    "Pearson_r_topDEG", "DEG_recall@20",
                    "Wasserstein_mean", "AUC_PR_DEG"]
    display_cols = [c for c in display_cols if c in metrics_df.columns]
    print(metrics_df[display_cols].to_string(index=False, float_format="{:.4f}".format))
    print(f"\n✓ All outputs saved to: {os.path.abspath(args.outdir)}/")
    print("  Per-model subfolders:", model_names)
    print("  Comparison plots:    C01–C10_*.png")


# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate scRNA-seq perturbation predictions (multi-model)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # Ground truth
    parser.add_argument("--ground_truth",    required=True,
                        help="Folder whose subfolders each contain "
                             "matrix.mtx.gz / barcodes.tsv.gz / features.tsv.gz")

    # Multi-model (primary)
    parser.add_argument("--predictions_dir", default=None,
                        help="Folder whose subfolders each contain "
                             "matrix.mtx.gz / barcodes.tsv.gz / features.tsv.gz")

    # Legacy single-model
    parser.add_argument("--predicted",       default=None,
                        help="Single predicted matrix (legacy mode)")
    parser.add_argument("--pred_barcodes",   default=None)
    parser.add_argument("--pred_features",   default=None)

    parser.add_argument("--n_top_deg",       type=int, default=50)
    parser.add_argument("--outdir",          default="perturbation_eval_results")

    args = parser.parse_args()
    main(args)