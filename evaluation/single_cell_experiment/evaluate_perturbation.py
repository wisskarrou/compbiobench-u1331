"""
evaluate_perturbation.py
========================
Evaluate scRNA-seq perturbation prediction quality against ground truth.

Metrics and plots follow best practices from:
  - GEARS (Roohani et al., Nature Biotechnology 2024)
  - scGen (Lotfollahi et al., Nature Methods 2019)
  - CPA (Lotfollahi et al., Molecular Systems Biology 2023)
  - scREPA (ScienceDirect 2025)
  - scArchon (bioRxiv 2025) benchmarking suite
  - Systema (Nature Biotechnology 2025)
  - "Optimal distance metrics for scRNA-seq" (bioRxiv 2023)
  - "Diversity by Design" / DEG-aware metrics (arXiv 2025)

Usage
-----
    python evaluate_perturbation.py \
        --ground_truth  ground_truth.mtx.gz  \
        --predicted     predicted.mtx.gz     \
        [--gt_barcodes  gt_barcodes.tsv]     \
        [--gt_features  gt_features.tsv]     \
        [--pred_barcodes pred_barcodes.tsv]  \
        [--pred_features pred_features.tsv]  \
        [--n_top_deg    20]                  \
        [--outdir       results/]

If barcode / feature files are not provided, the script auto-generates
integer indices so it can still run without them.

Outputs (saved to --outdir)
---------------------------
metrics_summary.csv          – All scalar metrics in one table
01_umap_ground_truth.png     – UMAP of GT cells coloured by cluster (Leiden)
02_umap_predicted.png        – UMAP of predicted cells with GT cluster colours
03_umap_combined.png         – GT vs Predicted overlaid (coloured by source)
04_mean_expression_scatter.png – Mean expression scatter (all genes)  [scGen Fig 2b]
05_delta_scatter.png         – Δ-expression scatter (pred-ctrl vs gt-ctrl) [GEARS / CPA]
06_top_deg_scatter.png       – Mean expression scatter (top DEGs only)  [CPA / PerturbNet]
07_volcano.png               – Volcano plot: GT log-FC vs significance    [standard]
08_deg_overlap_bar.png       – DEG recall @ top-k thresholds              [scArchon]
09_violin_top_genes.png      – Per-gene violin: ctrl / gt / predicted      [scGen Fig 2e / scREPA]
10_deg_rank_comparison.png   – DEG rank comparison bubble chart            [scREPA Fig 2e]
11_pearson_delta_histogram.png – Distribution of per-gene Pearson(Δ)     [DEG-aware paper]
12_wasserstein_per_gene.png  – Wasserstein distance per gene (top DEGs)   [CPA benchmark]
"""

import argparse, os, warnings
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
import seaborn as sns

warnings.filterwarnings("ignore")

# ── colour palette (consistent across figures) ────────────────────────────────
PALETTE = {
    "ground_truth": "#2196F3",   # blue
    "predicted":    "#FF5722",   # deep orange
    "control":      "#9E9E9E",   # grey
}

# ═══════════════════════════════════════════════════════════════════════════════
# I/O helpers
# ═══════════════════════════════════════════════════════════════════════════════

def load_mtx(mtx_path, barcodes_path=None, features_path=None):
    """Load a (possibly gzipped) .mtx / .mtx.gz file into a dense numpy array.

    Returns
    -------
    X : np.ndarray  (cells × genes)
    barcodes : list[str]
    features : list[str]
    """
    import gzip, shutil, tempfile, pathlib

    path = pathlib.Path(mtx_path)

    # decompress if needed
    if path.suffix == ".gz":
        tmp = tempfile.NamedTemporaryFile(suffix=".mtx", delete=False)
        with gzip.open(path, "rb") as f_in, open(tmp.name, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        mat = sio.mmread(tmp.name)
        os.unlink(tmp.name)
    else:
        mat = sio.mmread(str(path))

    # mmread returns COO; convert to CSC then dense
    if sp.issparse(mat):
        mat = mat.tocsr()
    X = np.asarray(mat.todense(), dtype=np.float32)

    # MTX from 10x is (genes × cells); transpose if needed
    # Heuristic: if more rows than columns assume genes × cells
    if X.shape[0] > X.shape[1] and X.shape[1] < 50_000:
        X = X.T   # → cells × genes

    n_cells, n_genes = X.shape

    # barcodes
    if barcodes_path and os.path.exists(barcodes_path):
        barcodes = pd.read_csv(barcodes_path, header=None, sep="\t")[0].tolist()
    else:
        barcodes = [f"cell_{i}" for i in range(n_cells)]

    # features / genes
    if features_path and os.path.exists(features_path):
        feat = pd.read_csv(features_path, header=None, sep="\t")
        features = feat.iloc[:, 0].tolist()
    else:
        features = [f"gene_{i}" for i in range(n_genes)]

    # If transposed, lengths should match
    if len(features) == X.shape[1] or len(barcodes) == X.shape[0]:
        pass
    else:
        # swap if mismatched
        if len(features) == X.shape[0] and len(barcodes) == X.shape[1]:
            X = X.T
            barcodes, features = features[:X.shape[0]], barcodes[:X.shape[1]]

    return X, barcodes[:X.shape[0]], features[:X.shape[1]]


def normalise_log1p(X):
    """Library-size normalise (10 000 counts / cell) then log1p."""
    lib = X.sum(axis=1, keepdims=True)
    lib[lib == 0] = 1
    return np.log1p(X / lib * 10_000)


# ═══════════════════════════════════════════════════════════════════════════════
# Metric helpers
# ═══════════════════════════════════════════════════════════════════════════════

def pearson_r(a, b):
    r, _ = stats.pearsonr(a, b)
    return float(r)

def spearman_r(a, b):
    r, _ = stats.spearmanr(a, b)
    return float(r)

def r2_score(true, pred):
    ss_res = np.sum((true - pred) ** 2)
    ss_tot = np.sum((true - np.mean(true)) ** 2)
    return 1 - ss_res / (ss_tot + 1e-12)

def wasserstein_distance_1d(u, v):
    """Earth-mover's (Wasserstein-1) distance between two 1-D samples."""
    return float(stats.wasserstein_distance(u, v))

def mmd_rbf(X, Y, gamma=1.0):
    """Maximum Mean Discrepancy with RBF kernel (unbiased estimator)."""
    n, m = len(X), len(Y)
    XX = np.dot(X, X.T)
    YY = np.dot(Y, Y.T)
    XY = np.dot(X, Y.T)
    diag_X = np.diag(XX)
    diag_Y = np.diag(YY)
    K_XX = np.exp(-gamma * (diag_X[:, None] + diag_X[None, :] - 2 * XX))
    K_YY = np.exp(-gamma * (diag_Y[:, None] + diag_Y[None, :] - 2 * YY))
    K_XY = np.exp(-gamma * (diag_X[:, None] + diag_Y[None, :] - 2 * XY))
    mmd = K_XX.mean() + K_YY.mean() - 2 * K_XY.mean()
    return float(mmd)

def deg_overlap(true_degs, pred_degs, top_k):
    """Fraction of the top-k ground-truth DEGs recovered in predicted top-k."""
    t = set(true_degs[:top_k])
    p = set(pred_degs[:top_k])
    return len(t & p) / max(len(t), 1)


# ═══════════════════════════════════════════════════════════════════════════════
# UMAP helper (requires umap-learn & scanpy)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_umap(X, n_pcs=30, n_neighbors=15, seed=42):
    """PCA → UMAP; returns (n_cells, 2) embedding."""
    try:
        from sklearn.decomposition import PCA
        import umap as umap_lib
        n_pcs = min(n_pcs, X.shape[0] - 1, X.shape[1] - 1)
        pca = PCA(n_components=n_pcs, random_state=seed)
        emb_pca = pca.fit_transform(X)
        reducer = umap_lib.UMAP(n_neighbors=n_neighbors, min_dist=0.3,
                                random_state=seed, n_components=2)
        return reducer.fit_transform(emb_pca)
    except Exception as e:
        print(f"  [UMAP] Falling back to PCA 2D: {e}")
        from sklearn.decomposition import PCA
        return PCA(n_components=2, random_state=seed).fit_transform(X)


def leiden_clusters(X, n_neighbors=15, resolution=0.5):
    """Leiden clustering; falls back to KMeans if leidenalg unavailable."""
    try:
        import scanpy as sc
        import anndata as ad
        adata = ad.AnnData(X.astype(np.float32))
        sc.pp.neighbors(adata, n_neighbors=n_neighbors, use_rep="X")
        sc.tl.leiden(adata, resolution=resolution)
        return adata.obs["leiden"].astype(int).values
    except Exception:
        from sklearn.cluster import KMeans
        k = max(2, min(10, X.shape[0] // 30))
        return KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(X)


# ═══════════════════════════════════════════════════════════════════════════════
# Differential expression (simple t-test / Wilcoxon)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_deg(X_ctrl, X_perturbed, feature_names, method="ttest"):
    """Return a DataFrame ranked by |log2FC| with p-values."""
    mu_ctrl = X_ctrl.mean(axis=0)
    mu_pert = X_perturbed.mean(axis=0)
    log2fc = np.log2(mu_pert + 1) - np.log2(mu_ctrl + 1)

    pvals = []
    for g in range(X_ctrl.shape[1]):
        if method == "wilcoxon":
            _, p = stats.mannwhitneyu(X_ctrl[:, g], X_perturbed[:, g],
                                      alternative="two-sided")
        else:
            _, p = stats.ttest_ind(X_ctrl[:, g], X_perturbed[:, g],
                                   equal_var=False)
        pvals.append(p)

    pvals = np.array(pvals)
    # Benjamini-Hochberg FDR
    from statsmodels.stats.multitest import multipletests
    try:
        _, padj, _, _ = multipletests(pvals, method="fdr_bh")
    except Exception:
        padj = pvals

    df = pd.DataFrame({
        "gene":    feature_names,
        "log2FC":  log2fc,
        "pval":    pvals,
        "padj":    padj,
        "mu_ctrl": mu_ctrl,
        "mu_pert": mu_pert,
    })
    df["absFC"] = df["log2FC"].abs()
    df = df.sort_values("absFC", ascending=False).reset_index(drop=True)
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# Figure helpers
# ═══════════════════════════════════════════════════════════════════════════════

FIG_DPI = 150

def savefig(fig, path):
    fig.savefig(path, dpi=FIG_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → {path}")


def style_ax(ax, title="", xlabel="", ylabel=""):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_title(title, fontsize=11, fontweight="bold", pad=6)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.tick_params(labelsize=8)


# ═══════════════════════════════════════════════════════════════════════════════
# Individual plot functions
# ═══════════════════════════════════════════════════════════════════════════════

# ── 01 / 02  UMAP ground truth + predicted (separate) ─────────────────────────
def plot_umap_separate(emb_gt, labels_gt, emb_pred, outdir):
    """
    Reproduce GEARS Fig 3 / scGen Fig 2a:
    Left:  GT cells coloured by Leiden cluster.
    Right: Predicted cells coloured by the *same* GT cluster labels
           (ARI / NMI evaluate how well clusters are preserved).
    """
    cmap = plt.get_cmap("tab20")
    unique = np.unique(labels_gt)
    colour_map = {c: cmap(i / max(len(unique), 1)) for i, c in enumerate(unique)}
    colours_gt = [colour_map[l] for l in labels_gt]

    # --- figure 01: GT UMAP ---
    fig, ax = plt.subplots(figsize=(5, 4))
    scatter = ax.scatter(emb_gt[:, 0], emb_gt[:, 1], c=colours_gt, s=4, alpha=0.6)
    handles = [plt.Line2D([0], [0], marker="o", color="w",
                          markerfacecolor=colour_map[c], markersize=6, label=str(c))
               for c in unique]
    ax.legend(handles=handles, title="Cluster", fontsize=7, markerscale=1.2,
              loc="upper right", frameon=False)
    style_ax(ax, "UMAP – Ground Truth", "UMAP 1", "UMAP 2")
    savefig(fig, os.path.join(outdir, "01_umap_ground_truth.png"))

    # --- figure 02: Predicted UMAP with GT colours ---
    # Assign each predicted cell the nearest GT cluster via NN in UMAP space
    if len(emb_pred) == len(emb_gt):
        labels_pred_mapped = labels_gt  # same order
    else:
        dists = cdist(emb_pred, emb_gt)
        nn_idx = dists.argmin(axis=1)
        labels_pred_mapped = labels_gt[nn_idx]

    colours_pred = [colour_map.get(l, (0.5, 0.5, 0.5, 1)) for l in labels_pred_mapped]
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.scatter(emb_pred[:, 0], emb_pred[:, 1], c=colours_pred, s=4, alpha=0.6)
    ax.legend(handles=handles, title="GT Cluster", fontsize=7, markerscale=1.2,
              loc="upper right", frameon=False)
    style_ax(ax, "UMAP – Predicted (GT cluster colours)", "UMAP 1", "UMAP 2")
    savefig(fig, os.path.join(outdir, "02_umap_predicted.png"))


# ── 03  UMAP combined (GT vs Predicted) ───────────────────────────────────────
def plot_umap_combined(emb_gt, emb_pred, outdir):
    """
    scGen Fig 2a / Nature Biotechnology style:
    Overlay GT and Predicted embeddings in a shared UMAP space,
    coloured by source (blue = GT, orange = Predicted).
    """
    X_all = np.vstack([emb_gt, emb_pred])
    labels = (["Ground Truth"] * len(emb_gt) + ["Predicted"] * len(emb_pred))

    fig, ax = plt.subplots(figsize=(5.5, 4))
    for src, col in [("Ground Truth", PALETTE["ground_truth"]),
                     ("Predicted",    PALETTE["predicted"])]:
        mask = np.array(labels) == src
        ax.scatter(X_all[mask, 0], X_all[mask, 1],
                   c=col, s=4, alpha=0.5, label=src)
    ax.legend(fontsize=8, frameon=False, markerscale=2)
    style_ax(ax, "UMAP – Ground Truth vs Predicted", "UMAP 1", "UMAP 2")
    savefig(fig, os.path.join(outdir, "03_umap_combined.png"))


# ── 04  Mean-expression scatter (all genes) ────────────────────────────────────
def plot_mean_expression_scatter(mu_gt, mu_pred, r2, pearson, outdir):
    """
    scGen Fig 2b / CPA Fig 2:
    x = mean gene expression in GT, y = mean gene expression in Predicted.
    Each dot = one gene.
    """
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.scatter(mu_gt, mu_pred, s=5, alpha=0.4, color="#455A64", rasterized=True)
    lims = [min(mu_gt.min(), mu_pred.min()), max(mu_gt.max(), mu_pred.max())]
    ax.plot(lims, lims, "k--", lw=1, label="y = x")
    ax.text(0.05, 0.92,
            f"R² = {r2:.3f}\nPearson r = {pearson:.3f}",
            transform=ax.transAxes, fontsize=9,
            bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))
    ax.set_xlim(lims); ax.set_ylim(lims)
    ax.legend(fontsize=8, frameon=False)
    style_ax(ax, "Mean Gene Expression (All Genes)",
             "Ground Truth (mean log-norm)", "Predicted (mean log-norm)")
    savefig(fig, os.path.join(outdir, "04_mean_expression_scatter.png"))


# ── 05  Δ-expression scatter ──────────────────────────────────────────────────
def plot_delta_scatter(delta_gt, delta_pred, pearson_delta, r2_delta, outdir):
    """
    GEARS Fig 2b / "Diversity by Design" Fig:
    x = Δ_gt  = μ_perturbed_gt − μ_control
    y = Δ_pred = μ_perturbed_pred − μ_control
    The key metric used across the field: Pearson(Δ).
    """
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.scatter(delta_gt, delta_pred, s=5, alpha=0.4,
               color="#6A1B9A", rasterized=True)
    lims = [min(delta_gt.min(), delta_pred.min()),
            max(delta_gt.max(), delta_pred.max())]
    ax.plot(lims, lims, "k--", lw=1, label="y = x")
    ax.axhline(0, color="grey", lw=0.5, ls=":")
    ax.axvline(0, color="grey", lw=0.5, ls=":")
    ax.text(0.05, 0.92,
            f"Pearson(Δ) = {pearson_delta:.3f}\nR²(Δ) = {r2_delta:.3f}",
            transform=ax.transAxes, fontsize=9,
            bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))
    ax.set_xlim(lims); ax.set_ylim(lims)
    ax.legend(fontsize=8, frameon=False)
    style_ax(ax, "Δ-Expression Scatter (Perturbed − Control)",
             "Δ Ground Truth", "Δ Predicted")
    savefig(fig, os.path.join(outdir, "05_delta_scatter.png"))


# ── 06  Top-DEG mean expression scatter ───────────────────────────────────────
def plot_top_deg_scatter(mu_gt, mu_pred, deg_df, n_top, pearson_deg, r2_deg, outdir):
    """
    CPA / PerturbNet style: same as Fig 04 but restricted to top-N DEGs.
    Highlighted genes are labelled (adjustText if available).
    """
    top_genes = deg_df["gene"].values[:n_top]
    gene_list  = list(deg_df["gene"])  # full list (ordered by |FC|)
    idx = [gene_list.index(g) for g in top_genes if g in gene_list]

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(mu_gt, mu_pred, s=4, alpha=0.2, color="#B0BEC5", rasterized=True,
               label="all genes")
    ax.scatter(mu_gt[idx], mu_pred[idx], s=20, alpha=0.9,
               color=PALETTE["ground_truth"], zorder=3, label=f"top {n_top} DEGs")

    lims = [min(mu_gt.min(), mu_pred.min()), max(mu_gt.max(), mu_pred.max())]
    ax.plot(lims, lims, "k--", lw=1)
    ax.set_xlim(lims); ax.set_ylim(lims)

    # label top 10
    texts = []
    for i in idx[:10]:
        texts.append(ax.text(mu_gt[i], mu_pred[i], deg_df["gene"].iloc[
            deg_df[deg_df["gene"] == list(top_genes)[idx.index(i)]].index[0]
            if i < len(top_genes) else i], fontsize=7))
    try:
        from adjustText import adjust_text
        adjust_text(texts, ax=ax, arrowprops=dict(arrowstyle="-", color="grey", lw=0.5))
    except ImportError:
        pass

    ax.text(0.05, 0.92,
            f"Pearson r = {pearson_deg:.3f}\nR² = {r2_deg:.3f}",
            transform=ax.transAxes, fontsize=9,
            bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"))
    ax.legend(fontsize=8, frameon=False)
    style_ax(ax, f"Mean Expression – Top {n_top} DEGs",
             "Ground Truth (mean log-norm)", "Predicted (mean log-norm)")
    savefig(fig, os.path.join(outdir, "06_top_deg_scatter.png"))


# ── 07  Volcano plot ───────────────────────────────────────────────────────────
def plot_volcano(deg_df, n_label, outdir):
    """
    Standard volcano: x = log2FC (GT), y = −log10(padj).
    Highlights top-N most significant DEGs.
    """
    df = deg_df.copy()
    df["-log10padj"] = -np.log10(df["padj"].clip(lower=1e-300))

    sig = df[(df["padj"] < 0.05) & (df["absFC"] > 1)]
    up  = sig[sig["log2FC"] > 0]
    dn  = sig[sig["log2FC"] < 0]

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(df["log2FC"], df["-log10padj"],
               s=5, alpha=0.4, color="#90A4AE", rasterized=True, label="non-sig")
    ax.scatter(up["log2FC"], up["-log10padj"],
               s=8, alpha=0.8, color="#E53935", label=f"Up ({len(up)})")
    ax.scatter(dn["log2FC"], dn["-log10padj"],
               s=8, alpha=0.8, color="#1E88E5", label=f"Down ({len(dn)})")

    ax.axhline(-np.log10(0.05), color="grey", lw=0.8, ls="--")
    ax.axvline(1,  color="grey", lw=0.8, ls="--")
    ax.axvline(-1, color="grey", lw=0.8, ls="--")

    # label top-N
    top = df.nsmallest(n_label, "padj")
    texts = [ax.text(row["log2FC"], row["-log10padj"], row["gene"], fontsize=7)
             for _, row in top.iterrows()]
    try:
        from adjustText import adjust_text
        adjust_text(texts, ax=ax, arrowprops=dict(arrowstyle="-", color="grey", lw=0.5))
    except ImportError:
        pass

    ax.legend(fontsize=8, frameon=False)
    style_ax(ax, "Volcano Plot – Ground Truth DEGs",
             "log₂ Fold Change (Perturbed vs Control)", "−log₁₀(adjusted p-value)")
    savefig(fig, os.path.join(outdir, "07_volcano.png"))


# ── 08  DEG overlap / recall bar chart ────────────────────────────────────────
def plot_deg_overlap(gt_deg_genes, pred_deg_genes, ks, outdir):
    """
    scArchon / benchmarking papers: fraction of top-k GT DEGs recovered.
    Shows DEG recall at multiple k thresholds.
    """
    overlaps = [deg_overlap(gt_deg_genes, pred_deg_genes, k) for k in ks]
    fig, ax = plt.subplots(figsize=(5, 3.5))
    bars = ax.bar([str(k) for k in ks], overlaps,
                  color=PALETTE["ground_truth"], edgecolor="white", width=0.6)
    for bar, val in zip(bars, overlaps):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                f"{val:.2f}", ha="center", va="bottom", fontsize=8)
    ax.set_ylim(0, 1.12)
    style_ax(ax, "DEG Recall @ Top-k", "Top-k Threshold", "Fraction Recovered")
    savefig(fig, os.path.join(outdir, "08_deg_overlap_bar.png"))


# ── 09  Violin plot of selected genes ─────────────────────────────────────────
def plot_violins(X_ctrl, X_gt, X_pred, gene_indices, gene_names, outdir):
    """
    scGen Fig 2e / scREPA Fig 2c:
    Per-gene violin for control, GT perturbed, predicted.
    Shows the expression distribution rather than just the mean.
    """
    n = len(gene_indices)
    fig, axes = plt.subplots(1, n, figsize=(2.5 * n, 4), sharey=False)
    if n == 1:
        axes = [axes]

    for ax, gi, gn in zip(axes, gene_indices, gene_names):
        data = {
            "Control":       X_ctrl[:, gi].flatten(),
            "GT Perturbed":  X_gt[:, gi].flatten(),
            "Predicted":     X_pred[:, gi].flatten(),
        }
        colours = [PALETTE["control"],
                   PALETTE["ground_truth"],
                   PALETTE["predicted"]]
        parts = ax.violinplot(list(data.values()),
                              showmedians=True, showextrema=False)
        for pc, col in zip(parts["bodies"], colours):
            pc.set_facecolor(col)
            pc.set_alpha(0.7)
        parts["cmedians"].set_color("black")
        ax.set_xticks([1, 2, 3])
        ax.set_xticklabels(["Ctrl", "GT\nPert", "Pred"], fontsize=8)
        ax.set_title(gn, fontsize=9, fontweight="bold")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(labelsize=7)

    fig.suptitle("Expression Distribution – Top DEGs", fontsize=11, y=1.02)
    fig.tight_layout()
    savefig(fig, os.path.join(outdir, "09_violin_top_genes.png"))


# ── 10  DEG rank comparison bubble chart ──────────────────────────────────────
def plot_deg_rank_comparison(deg_gt, deg_pred_vs_ctrl, n_show, outdir):
    """
    scREPA Fig 2e:
    Bubble chart: x = GT DEG rank, y = Predicted DEG rank.
    Bubble size ∝ |log2FC| in GT; colour = direction.
    """
    gt_genes  = deg_gt["gene"].values[:n_show]
    gt_fc     = deg_gt["log2FC"].values[:n_show]
    gt_rank   = np.arange(1, n_show + 1)

    pred_gene_list = list(deg_pred_vs_ctrl["gene"])
    pred_rank_map  = {g: i + 1 for i, g in enumerate(pred_gene_list)}
    pred_ranks = np.array([pred_rank_map.get(g, n_show + 10) for g in gt_genes])

    sizes  = (np.abs(gt_fc) * 30).clip(20, 300)
    colours = ["#E53935" if fc > 0 else "#1E88E5" for fc in gt_fc]

    fig, ax = plt.subplots(figsize=(5, 5))
    sc = ax.scatter(gt_rank, pred_ranks, s=sizes, c=colours, alpha=0.7, edgecolors="white")
    ax.plot([1, n_show + 10], [1, n_show + 10], "k--", lw=1)
    ax.set_xlim(0, n_show + 5)
    ax.set_ylim(0, n_show + 5)

    # legend
    from matplotlib.lines import Line2D
    leg = [Line2D([0], [0], marker="o", color="w",
                  markerfacecolor="#E53935", markersize=8, label="Up-regulated"),
           Line2D([0], [0], marker="o", color="w",
                  markerfacecolor="#1E88E5", markersize=8, label="Down-regulated")]
    ax.legend(handles=leg, fontsize=8, frameon=False)
    style_ax(ax, "DEG Rank: GT vs Predicted",
             "GT DEG Rank", "Predicted DEG Rank")
    savefig(fig, os.path.join(outdir, "10_deg_rank_comparison.png"))


# ── 11  Per-gene Pearson(Δ) histogram ─────────────────────────────────────────
def plot_pearson_delta_hist(delta_gt_genes, delta_pred_genes, gene_names, outdir):
    """
    "Diversity by Design" / DEG-aware metrics paper:
    For each gene compute Pearson correlation between its Δ in GT vs Predicted
    across a set of pseudo-replicates (bootstrap samples).
    Here we compute it across all genes in one condition pair (single value per gene
    if we have only one condition) — or show the full distribution per gene.
    Fall back to showing the per-gene |Δ| residual distribution.
    """
    residuals = delta_pred_genes - delta_gt_genes

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))

    # left: distribution of Δ residuals (pred - gt)
    ax = axes[0]
    ax.hist(residuals, bins=60, color=PALETTE["predicted"], alpha=0.75,
            edgecolor="white")
    ax.axvline(0, color="black", lw=1, ls="--")
    ax.axvline(residuals.mean(), color="red", lw=1.2, ls="-",
               label=f"mean={residuals.mean():.3f}")
    ax.legend(fontsize=8, frameon=False)
    style_ax(ax, "Δ Residuals Distribution\n(Predicted Δ − GT Δ)",
             "Δ Residual", "# Genes")

    # right: cumulative Δ recovery (fraction of genes with |residual| < ε)
    ax2 = axes[1]
    eps_range = np.linspace(0, np.abs(residuals).max(), 200)
    frac = [(np.abs(residuals) < e).mean() for e in eps_range]
    ax2.plot(eps_range, frac, color=PALETTE["ground_truth"], lw=2)
    ax2.axhline(0.9, color="grey", lw=0.8, ls="--", label="90% recall")
    ax2.legend(fontsize=8, frameon=False)
    style_ax(ax2, "Cumulative Δ Recovery",
             "|Δ Residual| threshold (ε)", "Fraction of genes")

    fig.suptitle("Δ-Expression Residual Analysis", fontsize=11, y=1.01)
    fig.tight_layout()
    savefig(fig, os.path.join(outdir, "11_pearson_delta_histogram.png"))


# ── 12  Wasserstein distance per gene (top DEGs) ──────────────────────────────
def plot_wasserstein_per_gene(X_gt, X_pred, gene_indices, gene_names, outdir):
    """
    CPA benchmark:
    Per-gene Wasserstein distance between GT and Predicted distributions.
    Lower = better distributional match.
    """
    wdists = [wasserstein_distance_1d(X_gt[:, gi].flatten(),
                                      X_pred[:, gi].flatten())
              for gi in gene_indices]

    df_w = pd.DataFrame({"gene": gene_names, "wasserstein": wdists})
    df_w = df_w.sort_values("wasserstein", ascending=False)

    fig, ax = plt.subplots(figsize=(max(6, len(gene_indices) * 0.45), 4))
    colours = [PALETTE["ground_truth"] if w < df_w["wasserstein"].median()
               else PALETTE["predicted"] for w in df_w["wasserstein"]]
    ax.bar(df_w["gene"], df_w["wasserstein"],
           color=colours, edgecolor="white", width=0.7)
    ax.axhline(df_w["wasserstein"].median(), color="black", lw=1, ls="--",
               label=f"median={df_w['wasserstein'].median():.3f}")
    ax.set_xticklabels(df_w["gene"], rotation=45, ha="right", fontsize=8)
    ax.legend(fontsize=8, frameon=False)
    style_ax(ax, "Wasserstein Distance per Gene (Top DEGs)",
             "Gene", "Wasserstein Distance")
    savefig(fig, os.path.join(outdir, "12_wasserstein_per_gene.png"))


# ═══════════════════════════════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def main(args):
    os.makedirs(args.outdir, exist_ok=True)
    print("=" * 60)
    print("scRNA-seq Perturbation Prediction Evaluation")
    print("=" * 60)

    # ── 1. Load data ──────────────────────────────────────────────────────────
    print("\n[1/6] Loading data …")
    X_gt,   bc_gt,   feat_gt   = load_mtx(args.ground_truth,
                                           args.gt_barcodes,   args.gt_features)
    X_pred, bc_pred, feat_pred = load_mtx(args.predicted,
                                           args.pred_barcodes, args.pred_features)
    print(f"  Ground truth  : {X_gt.shape[0]} cells × {X_gt.shape[1]} genes")
    print(f"  Predicted     : {X_pred.shape[0]} cells × {X_pred.shape[1]} genes")

    # Align genes
    common = sorted(set(feat_gt) & set(feat_pred))
    if not common:
        # fall back: assume same gene order up to min
        n_genes = min(X_gt.shape[1], X_pred.shape[1])
        X_gt   = X_gt[:, :n_genes]
        X_pred = X_pred[:, :n_genes]
        common = feat_gt[:n_genes]
        print(f"  ⚠  No common gene names – using first {n_genes} genes.")
    else:
        gi_gt   = [feat_gt.index(g)   for g in common]
        gi_pred = [feat_pred.index(g) for g in common]
        X_gt    = X_gt[:, gi_gt]
        X_pred  = X_pred[:, gi_pred]
        print(f"  Aligned to {len(common)} common genes.")

    gene_names = list(common)

    # ── 2. Normalise ──────────────────────────────────────────────────────────
    print("\n[2/6] Normalising (library-size + log1p) …")
    X_gt_norm   = normalise_log1p(X_gt)
    X_pred_norm = normalise_log1p(X_pred)

    # Pseudobulk means (main unit of analysis in the literature)
    mu_gt   = X_gt_norm.mean(axis=0)
    mu_pred = X_pred_norm.mean(axis=0)

    # Synthetic control = mean of GT cells (simulate "before perturbation")
    # In practice you'd pass a separate control matrix; here we use a 20%
    # random subsample of GT as a proxy control for DEG computation.
    rng = np.random.default_rng(42)
    ctrl_idx = rng.choice(len(X_gt_norm),
                          size=max(10, len(X_gt_norm) // 5), replace=False)
    X_ctrl_norm = X_gt_norm[ctrl_idx]
    mu_ctrl     = X_ctrl_norm.mean(axis=0)

    delta_gt   = mu_gt   - mu_ctrl
    delta_pred = mu_pred - mu_ctrl

    # ── 3. Metrics ────────────────────────────────────────────────────────────
    print("\n[3/6] Computing metrics …")
    metrics = {}

    # Pearson / Spearman on mean expression (all genes) [scGen, CPA]
    metrics["Pearson_r_all"]     = pearson_r(mu_gt, mu_pred)
    metrics["Spearman_r_all"]    = spearman_r(mu_gt, mu_pred)
    metrics["R2_all"]            = r2_score(mu_gt, mu_pred)

    # MSE / MAE on mean expression [GEARS, PerturbNet]
    metrics["MSE_all"]           = float(np.mean((mu_gt - mu_pred) ** 2))
    metrics["MAE_all"]           = float(np.mean(np.abs(mu_gt - mu_pred)))

    # Pearson(Δ) and R²(Δ) [GEARS, CPA, "Diversity by Design"]
    metrics["Pearson_delta"]     = pearson_r(delta_gt, delta_pred)
    metrics["Spearman_delta"]    = spearman_r(delta_gt, delta_pred)
    metrics["R2_delta"]          = r2_score(delta_gt, delta_pred)
    metrics["MSE_delta"]         = float(np.mean((delta_gt - delta_pred) ** 2))

    # DEG analysis
    deg_gt = compute_deg(X_ctrl_norm, X_gt_norm, gene_names)
    # Predicted DEG (same control; compare predicted distribution to control)
    deg_pred_vs_ctrl = compute_deg(X_ctrl_norm, X_pred_norm, gene_names)

    n_top = args.n_top_deg
    top_gt_genes   = deg_gt["gene"].values[:n_top]
    top_pred_genes = deg_pred_vs_ctrl["gene"].values[:n_top]

    # Mean expression on top DEGs only [CPA, PerturbNet]
    top_idx = [gene_names.index(g) for g in top_gt_genes
               if g in gene_names][:n_top]
    metrics["Pearson_r_topDEG"]  = pearson_r(mu_gt[top_idx], mu_pred[top_idx])
    metrics["R2_topDEG"]         = r2_score(mu_gt[top_idx], mu_pred[top_idx])
    metrics["MSE_topDEG"]        = float(np.mean((mu_gt[top_idx] - mu_pred[top_idx]) ** 2))

    # DEG recall / overlap [scArchon]
    ks = [10, 20, 50, 100, 200]
    ks = [k for k in ks if k <= n_top]
    if n_top not in ks:
        ks.append(n_top)
    for k in ks:
        metrics[f"DEG_recall@{k}"] = deg_overlap(top_gt_genes, top_pred_genes, k)

    # Wasserstein distance (mean across all genes) [CPA]
    # Computing full per-gene Wasserstein is slow; sample 200 genes
    sample_genes = rng.choice(len(gene_names),
                              size=min(200, len(gene_names)), replace=False)
    wdists = [wasserstein_distance_1d(X_gt_norm[:, g].flatten(),
                                      X_pred_norm[:, g].flatten())
              for g in sample_genes]
    metrics["Wasserstein_mean"] = float(np.mean(wdists))

    # MMD (embedding space) [optimal distance metrics paper]
    # Use PCA-reduced representations for speed
    from sklearn.decomposition import PCA
    n_pc = min(30, X_gt_norm.shape[0] - 1, X_gt_norm.shape[1] - 1,
               X_pred_norm.shape[0] - 1)
    pca = PCA(n_components=n_pc, random_state=42)
    pca.fit(np.vstack([X_gt_norm, X_pred_norm]))
    emb_gt_pca   = pca.transform(X_gt_norm)
    emb_pred_pca = pca.transform(X_pred_norm)
    metrics["MMD_RBF"] = mmd_rbf(emb_gt_pca, emb_pred_pca, gamma=1.0 / n_pc)

    # ARI / NMI on cluster labels [GEARS]
    try:
        from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
        labels_gt   = leiden_clusters(X_gt_norm)
        if len(X_pred_norm) == len(X_gt_norm):
            labels_pred = leiden_clusters(X_pred_norm)
            metrics["ARI"]  = float(adjusted_rand_score(labels_gt, labels_pred))
            metrics["NMI"]  = float(normalized_mutual_info_score(labels_gt, labels_pred))
        else:
            metrics["ARI"] = float("nan")
            metrics["NMI"] = float("nan")
    except Exception as e:
        print(f"  [cluster metrics] skipped: {e}")
        labels_gt = np.zeros(len(X_gt_norm), dtype=int)
        metrics["ARI"] = float("nan")
        metrics["NMI"] = float("nan")

    # AUC-PR for DEG identification [AUC-PR paper, bioRxiv 2025]
    try:
        from sklearn.metrics import average_precision_score
        true_deg_binary  = (deg_gt["padj"] < 0.05).astype(int).values
        # Score = predicted |log2FC| (ordered by GT gene order)
        gt_order = list(deg_gt["gene"])
        pred_fc_ordered = np.array([
            deg_pred_vs_ctrl.loc[
                deg_pred_vs_ctrl["gene"] == g, "absFC"
            ].values[0] if g in deg_pred_vs_ctrl["gene"].values else 0.0
            for g in gt_order
        ])
        metrics["AUC_PR_DEG"] = float(average_precision_score(
            true_deg_binary, pred_fc_ordered))
    except Exception as e:
        print(f"  [AUC-PR] skipped: {e}")
        metrics["AUC_PR_DEG"] = float("nan")

    # Print metrics table
    print("\n  ┌─ Metrics Summary ─────────────────────────────────")
    for k, v in metrics.items():
        print(f"  │  {k:<28s}  {v:+.4f}")
    print("  └────────────────────────────────────────────────────")

    # Save metrics CSV
    pd.DataFrame(metrics, index=["value"]).T.reset_index().rename(
        columns={"index": "metric", "value": "value"}
    ).to_csv(os.path.join(args.outdir, "metrics_summary.csv"), index=False)

    # ── 4. UMAP embeddings ────────────────────────────────────────────────────
    print("\n[4/6] Computing UMAP embeddings …")
    print("  GT cells …")
    emb_gt   = compute_umap(X_gt_norm)
    print("  Predicted cells …")
    emb_pred = compute_umap(X_pred_norm)

    # combined UMAP
    X_all_norm = np.vstack([X_gt_norm, X_pred_norm])
    print("  Combined …")
    emb_all = compute_umap(X_all_norm)
    emb_gt_in_all   = emb_all[:len(X_gt_norm)]
    emb_pred_in_all = emb_all[len(X_gt_norm):]

    # ── 5. Plots ──────────────────────────────────────────────────────────────
    print("\n[5/6] Generating plots …")
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.linewidth": 0.8,
        "figure.dpi": FIG_DPI,
    })
    sns.set_style("whitegrid", {"grid.linestyle": ":"})

    plot_umap_separate(emb_gt, labels_gt, emb_pred, args.outdir)
    plot_umap_combined(emb_gt_in_all, emb_pred_in_all, args.outdir)
    plot_mean_expression_scatter(mu_gt, mu_pred,
                                 metrics["R2_all"], metrics["Pearson_r_all"], args.outdir)
    plot_delta_scatter(delta_gt, delta_pred,
                       metrics["Pearson_delta"], metrics["R2_delta"], args.outdir)
    plot_top_deg_scatter(mu_gt, mu_pred, deg_gt, n_top,
                         metrics["Pearson_r_topDEG"], metrics["R2_topDEG"], args.outdir)
    plot_volcano(deg_gt, n_label=10, outdir=args.outdir)
    plot_deg_overlap(top_gt_genes, top_pred_genes, ks, args.outdir)

    # Violin: top-5 DEGs
    violin_n = min(5, len(top_idx))
    violin_idx   = top_idx[:violin_n]
    violin_names = [gene_names[i] for i in violin_idx]
    plot_violins(X_ctrl_norm, X_gt_norm, X_pred_norm,
                 violin_idx, violin_names, args.outdir)

    plot_deg_rank_comparison(deg_gt, deg_pred_vs_ctrl, n_show=n_top, outdir=args.outdir)
    plot_pearson_delta_hist(delta_gt, delta_pred, gene_names, args.outdir)

    # Wasserstein per gene – top DEGs
    wass_n    = min(30, len(top_idx))
    wass_idx  = top_idx[:wass_n]
    wass_names = [gene_names[i] for i in wass_idx]
    plot_wasserstein_per_gene(X_gt_norm, X_pred_norm, wass_idx, wass_names, args.outdir)

    # ── 6. Done ───────────────────────────────────────────────────────────────
    print(f"\n[6/6] All outputs saved to: {os.path.abspath(args.outdir)}/")
    print("  Files:")
    for f in sorted(os.listdir(args.outdir)):
        print(f"    {f}")
    print("\n✓ Evaluation complete.")


# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate scRNA-seq perturbation prediction vs ground truth",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--ground_truth",  required=True,
                        help="Ground-truth expression matrix (.mtx or .mtx.gz)")
    parser.add_argument("--predicted",     required=True,
                        help="Predicted expression matrix (.mtx or .mtx.gz)")
    parser.add_argument("--gt_barcodes",   default=None,
                        help="Ground-truth barcodes file (TSV, one per line)")
    parser.add_argument("--gt_features",   default=None,
                        help="Ground-truth features/genes file (TSV)")
    parser.add_argument("--pred_barcodes", default=None,
                        help="Predicted barcodes file (TSV)")
    parser.add_argument("--pred_features", default=None,
                        help="Predicted features/genes file (TSV)")
    parser.add_argument("--n_top_deg",     type=int, default=50,
                        help="Number of top DEGs for focused metrics/plots (default 50)")
    parser.add_argument("--outdir",        default="perturbation_eval_results",
                        help="Output directory (created if absent)")
    args = parser.parse_args()
    main(args)
