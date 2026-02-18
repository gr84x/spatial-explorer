# Spatial Explorer

[![CI](https://github.com/gr84x/spatial-explorer/actions/workflows/ci.yml/badge.svg)](https://github.com/gr84x/spatial-explorer/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/gr84x/spatial-explorer/branch/main/graph/badge.svg)](https://codecov.io/gh/gr84x/spatial-explorer)
[![License: MIT](https://img.shields.io/github/license/gr84x/spatial-explorer)](LICENSE)

**Spatial Explorer** is an open-source, browser-based visualization tool for exploring spatial biology data. It enables interactive visualization of cell locations, gene expression, and phenotype queries directly in your browser—no installation required.

## Overview

Spatial transcriptomics and proteomics platforms (CosMx, Xenium, MERFISH, etc.) generate rich datasets mapping thousands of cells with their spatial coordinates and molecular profiles. Spatial Explorer provides a fast, intuitive interface for:

- **Visualizing tissue architecture**: Plot cells colored by type or gene expression
- **Querying marker genes**: Search and color cells by any gene in your dataset
- **Boolean gating**: Build complex phenotype queries (e.g., `CD8A+ AND CD3E+ AND NOT CD4+`)
- **Interactive exploration**: Pan, zoom, click cells to inspect expression profiles
- **Shareable analysis**: Export publication-ready figures (PNG/SVG) and share interactive URLs

## Features (V1.0 Core)

### Data Loading
- **CSV/TSV support**: Drag-and-drop or browse to load standard tabular data
- **Native format parsers**: Python utilities for CosMx and Xenium exports (see [Parsers](#native-format-parsers))
- **Flexible column mapping**: Automatically detects `cell_id`, `x`, `y`, `cell_type`, and gene expression columns

### Visualization
- **Interactive spatial plot**: Smooth pan/zoom with optimized rendering for 10,000+ cells
- **Gene expression coloring**: Type any gene symbol to color cells by expression level
- **Cell type legend**: Toggle visibility of individual cell types
- **Scale bar**: Configurable µm/pixel calibration for accurate distance measurement

### Analysis
- **Boolean phenotype gating**: Build multi-condition queries with AND/OR/NOT logic
- **Expression profile inspection**: Click any cell to view top expressed genes
- **Cell selection**: Navigate and inspect individual cells with detailed metadata

### Export & Sharing
- **PNG export**: High-resolution raster images (1x, 2x, 4x scaling)
- **SVG export**: Scalable vector graphics for publications
- **Shareable URLs**: Share your exact view (zoom, pan, gene query, cell selection) via link

### Performance
- **Spatial indexing**: Fast hover/click selection using uniform grid acceleration
- **Optimized rendering**: RequestAnimationFrame throttling, cached gene ranges
- **Tested at scale**: Smooth performance with 10K+ cells (see [Performance Notes](#performance-notes))

---

## Getting Started

### Quick Start (Demo)

The easiest way to try Spatial Explorer is with the built-in synthetic demo dataset:

1. **Open the demo**: Open `web/index.html` in your browser (or serve `web/` via a local web server)
2. **Explore**: The demo includes 12,000 synthetic cells across 7 cell types with realistic marker genes
3. **Try gene queries**: Type `EPCAM`, `CD3E`, `CD19`, `LST1`, or `COL1A1` in the gene search box
4. **Load your data**: Click "Load CSV/TSV" to import your own dataset

### Loading Your Own Data

Spatial Explorer accepts CSV or TSV files with a simple tabular format.

**Minimal working example:**

```csv
cell_id,x,y,cell_type,EPCAM,CD3E,CD19
cell_001,12.34,56.78,Tumor,2.45,0.12,0.03
cell_002,13.45,57.89,T cell,0.08,3.21,0.05
cell_003,14.56,58.90,B cell,0.02,0.15,2.87
```

**How to load:**
1. Click **"Load CSV/TSV"** in the toolbar, or
2. Drag and drop your file onto the plot canvas

---

## Data Format Specifications

### CSV/TSV Format (Standard Input)

Spatial Explorer expects tabular data with the following columns:

#### Required Columns

| Column Name | Type | Description |
|-------------|------|-------------|
| `cell_id` | string | Unique identifier for each cell |
| `x` | numeric | X-coordinate (microns, pixels, or arbitrary units) |
| `y` | numeric | Y-coordinate (same units as x) |

#### Optional Columns

| Column Name | Type | Description |
|-------------|------|-------------|
| `cell_type` | string | Cell type annotation (e.g., "T cell", "Tumor") |
| *gene names* | numeric | Any remaining columns are treated as gene expression values |

#### Notes

- **Column names are case-insensitive** and trimmed; a leading UTF-8 BOM is ignored.
- **Required headers** (in the browser app): `cell_id`, `x`, `y` (optional: `cell_type`).
- **Gene columns**: Any column not named `cell_id`, `x`, `y`, or `cell_type` is treated as a gene.
- **Missing values**: Empty gene-expression cells default to `0`.
- **Delimiters**: Auto-detected (comma or tab) from the header line.
- **CSV parsing limitation (browser)**: Quoted fields are **not** supported. Avoid commas/tabs inside values.
- If you need **flexible column mapping** (e.g., `barcode`, `centerx/centery`) use the **Python** `parsers.universal.load_spatial()` loader and export a standardized CSV.

#### Example: Minimal Dataset

```csv
cell_id,x,y
C1,100.5,200.3
C2,101.2,199.8
C3,102.0,201.5
```

#### Example: Full Dataset with Cell Types and Genes

```csv
cell_id,x,y,cell_type,EPCAM,CD3E,CD8A,CD4,CD19,COL1A1
tumor_1,1234.5,5678.9,Tumor,8.45,0.12,0.05,0.03,0.01,0.23
tcell_1,1235.2,5677.3,T cell,0.08,7.23,4.56,2.31,0.02,0.15
bcell_1,1233.8,5679.4,B cell,0.03,0.18,0.09,0.11,6.78,0.08
fibro_1,1236.1,5676.5,Fibroblast,0.15,0.22,0.08,0.12,0.05,9.12
```

#### Phenotype Gate JSON (Copy/Paste)

The **Phenotype gate** UI supports copy/paste via a small JSON document.

**Schema (version = 1):**

```json
{
  "version": 1,
  "enabled": true,
  "advanced": false,
  "expr": "A AND (B OR C) AND NOT D",
  "conditions": [
    {"gene": "CD3E", "sense": "pos", "cutoff": 0.5, "join": "AND"},
    {"gene": "EPCAM", "sense": "pos", "cutoff": 0.5, "join": "OR"}
  ]
}
```

**Notes:**
- Condition labels `A`, `B`, `C`… are derived from the **array order** in `conditions`.
- `sense` is `"pos"` (gene+) or `"neg"` (gene-).
- `expr` supports `AND` / `OR` / `NOT` and parentheses.
- When `advanced=false`, the app treats `expr` as **derived** from the builder (it may be overwritten).

#### Standardized Python Parser Output (Contract)

All Python parsers (and `parsers.universal.load_spatial`) return a dictionary with the same shape:

```python
{
  "platform": str,                 # e.g. "xenium" | "visium" | "cosmx" | ...
  "transcript_data": DataFrame,    # columns: x, y, gene, cell_id
  "cell_metadata": DataFrame,      # columns: cell_id, x, y, cell_type
  "expression_matrix": DataFrame,  # index: cell_id, columns: genes
  "metadata": dict,
}
```

This contract is what you should target when adding new parsers or building conversion scripts.

### CosMx Native Format (NanoString/Bruker)

For **CosMx** data, use the Python parser to convert native exports to CSV:

```python
from parsers.cosmx import parse_cosmx

# Parse a directory containing CosMx native output files
result = parse_cosmx("path/to/cosmx_output/")

# Result contains:
# - transcript_data: DataFrame (x, y, gene, cell_id)
# - cell_metadata: DataFrame (cell_id, x, y, cell_type)
# - expression_matrix: DataFrame (cells x genes)
# - metadata: dict
```

#### Expected CosMx Files

The parser looks for these files in the input directory:

| File Pattern | Description | Required |
|--------------|-------------|----------|
| `tx_file.csv` or `transcripts.csv` | Transcript coordinates and gene labels | ✅ Yes |
| `cell_metadata.csv` | Cell centroids and annotations | ✅ Yes |
| `exprMat_file.csv` | Expression matrix (cells × genes) | Optional |
| `*.json` | Experiment/run metadata | Optional |

#### CosMx Column Mapping

**Transcript table** (`tx_file.csv`):
- X coordinate: `x`, `x_global_px`, `x_global`, `x_position`, `globalx`, `centerx`
- Y coordinate: `y`, `y_global_px`, `y_global`, `y_position`, `globaly`, `centery`
- Gene: `gene`, `target`, `targetname`, `target_name`, `feature_name`
- Cell ID: `cell_id`, `cellid`, `cell`

**Cell metadata** (`cell_metadata.csv`):
- Cell ID: `cell_id`, `cellid`, `cell`
- X centroid: `x`, `centerx`, `centroid_x`, `centroidx`
- Y centroid: `y`, `centery`, `centroid_y`, `centroidy`
- Cell type: `cell_type`, `celltype`, `cell_class`, `classification`, `cluster`, `annotation`

**Expression matrix** (`exprMat_file.csv`):
- Supports **wide format** (first column = cell_id, remaining columns = genes)
- Supports **long format** (columns: `cell_id`, `gene`, `count`)

#### Exporting for Spatial Explorer

After parsing with `parse_cosmx()`, convert to CSV:

```python
import pandas as pd

# Merge cell metadata with expression matrix
cells = result['cell_metadata']
expr = result['expression_matrix']

# Join expression data to cells (assumes cell_id as index)
df = cells.set_index('cell_id').join(expr, how='inner')
df = df.reset_index()

# Save to CSV
df.to_csv('cosmx_for_spatial_explorer.csv', index=False)
```

Your CSV will have columns: `cell_id`, `x`, `y`, `cell_type`, *gene1*, *gene2*, …

### Visium Native Format (10x Genomics / Space Ranger)

For **Visium** (Space Ranger) data, use the Python parser:

```python
from parsers.visium import parse_visium

# Parse a directory containing a Space Ranger output (e.g. outs/)
result = parse_visium("path/to/spaceranger_outs/")

# Result contains:
# - transcript_data: empty DataFrame (Visium has no per-transcript coordinates)
# - cell_metadata: DataFrame (cell_id, x, y, cell_type) for spots/barcodes
# - expression_matrix: DataFrame (spots x genes)
# - metadata: dict
```

#### Expected Visium Files

The parser looks for these files under the input directory:

| Path / Pattern | Description | Required |
|---|---|---|
| `spatial/tissue_positions.csv` or `spatial/tissue_positions_list.csv` | Spot positions (barcodes + pixel coords) | ✅ Yes |
| `filtered_feature_bc_matrix/` | Expression matrix MEX directory | Optional |
| `filtered_feature_bc_matrix.h5` | Expression matrix HDF5 | Optional |
| `spatial/scalefactors_json.json` | Image scaling factors | Optional |

**Note**: If `scipy` is not installed, large Visium matrices may be too large to load densely. In that case, install `scipy` or export a smaller gene panel.

---

### Xenium Native Format (10x Genomics)

For **Xenium** data, use the Python parser:

```python
from parsers.xenium import parse_xenium

# Parse a directory containing Xenium native output files
result = parse_xenium("path/to/xenium_output/")

# Result contains:
# - transcript_data: DataFrame (x, y, gene, cell_id)
# - cell_metadata: DataFrame (cell_id, x, y, cell_type)
# - expression_matrix: DataFrame (cells x genes, may be sparse)
# - metadata: dict
```

#### Expected Xenium Files

The parser looks for these files in the input directory:

| File Pattern | Description | Required |
|--------------|-------------|----------|
| `transcripts.parquet` or `transcripts.csv.gz` | Transcript coordinates and gene labels | ✅ Yes |
| `cells.parquet` or `cells.csv.gz` | Cell centroids (and optional metrics) | ✅ Yes |
| `cell_feature_matrix.h5` or `cell_feature_matrix/` | Expression matrix (HDF5 or MEX directory) | Optional |
| `experiment.xenium` or `*.json` | Run/experiment metadata | Optional |

#### Xenium Column Mapping

**Transcript table** (`transcripts.parquet`):
- X coordinate: `x`, `x_location`, `x_um`, `xcoord`
- Y coordinate: `y`, `y_location`, `y_um`, `ycoord`
- Gene: `gene`, `feature_name`, `feature`, `target`, `symbol`
- Cell ID: `cell_id`, `cellid`, `cell`

**Cell metadata** (`cells.parquet`):
- Cell ID: `cell_id`, `cellid`, `cell`, `barcode`
- X centroid: `x`, `x_centroid`, `centroid_x`, `centerx`
- Y centroid: `y`, `y_centroid`, `centroid_y`, `centery`
- Cell type: `cell_type`, `celltype`, `annotation`, `cluster`, `graphclust`, `kmeans`, `label`

**Expression matrix**:
- **HDF5 format** (`cell_feature_matrix.h5`): 10x Cell Ranger-style sparse matrix
- **MEX directory** (`cell_feature_matrix/`): Contains `matrix.mtx.gz`, `barcodes.tsv.gz`, `features.tsv.gz`
- Requires optional dependency: `h5py`
- `scipy` is recommended for efficient sparse loading; if missing, the parser will fall back to a dense load for small matrices (guarded to avoid huge allocations).

#### Exporting for Spatial Explorer

```python
# Merge cell metadata with expression matrix
cells = result['cell_metadata']
expr = result['expression_matrix']

# If expression is sparse, convert to dense (caution: memory-intensive for large gene panels)
if hasattr(expr, 'sparse'):
    expr = expr.sparse.to_dense()

# Join and save
df = cells.set_index('cell_id').join(expr, how='inner').reset_index()
df.to_csv('xenium_for_spatial_explorer.csv', index=False)
```

**Note**: For large Xenium datasets (100K+ cells, 500+ genes), consider filtering to top expressed genes before export to reduce file size.

## Usage Guide

### Navigation

- **Pan**: Click and drag the canvas
- **Zoom**: Mouse wheel or trackpad pinch
- **Reset view**: Click the "Reset view" button to refit the plot

### Gene Expression Queries

1. Type a gene symbol in the **"Gene"** search box
2. Cells will be colored by expression level:
   - **Gray/blue**: Low or no expression
   - **Bright blue**: Medium expression
   - **Green**: High expression
3. Clear the gene box to return to cell-type coloring

**Tip**: The autocomplete dropdown shows all available genes in your dataset.

### Cell Type Filters

- In the **"Cell types"** panel, toggle checkboxes to show/hide specific cell types
- The plot updates instantly
- The status line shows visible/total cell counts

### Phenotype Gating (Boolean Queries)

Build complex cell selection queries using boolean logic:

1. Click **"Add condition"** in the **"Phenotype gate"** panel
2. For each condition:
   - **Gene**: Select a gene from the dropdown
   - **Sense**: Choose `+` (positive) or `-` (negative)
   - **Cutoff**: Set expression threshold (default: 0)
   - The condition gets a label: **A**, **B**, **C**, etc.
3. Write a boolean expression in the **"Expression"** box:
   - Example: `A AND B` (cells positive for both A and B)
   - Example: `A AND (B OR C) AND NOT D` (complex logic)
4. Matching cells are highlighted on the plot

**Example**: To find CD8+ T cells:
- Condition A: `CD8A` +, cutoff 0
- Condition B: `CD3E` +, cutoff 0
- Expression: `A AND B`

**Advanced**: Check "Advanced expression" to manually edit the expression without using the UI-generated labels.

**Copy/Paste Gates**: Use "Copy gate JSON" and "Paste gate JSON" to save and share phenotype definitions.

### Cell Selection & Inspection

- **Click any cell** on the plot to select it
- The **"Selected cell"** panel displays:
  - Cell ID and type
  - Coordinates (x, y)
  - Neighborhood zone (core/mid/rim based on distance from origin)
  - **Top 10 expressed genes** (bar chart)
- Click elsewhere to deselect

### Scale Calibration

Use the **µm/px** field to set the microns-per-pixel ratio:
- Default: `1.0` (treat x/y coordinates as pixels)
- CosMx: Typically `~0.12–0.18` µm/px
- Xenium: Coordinates are already in microns, so set to `1.0` or calibrate based on your export

The scale bar on the canvas updates automatically.

---

## Export Functionality

### PNG Export (Raster)

1. Click **"Export PNG"**
2. Select resolution from the **"Export"** dropdown:
   - **1x**: Current canvas resolution
   - **2x**: Double resolution (recommended for publications)
   - **4x**: Quad resolution (very high quality, larger file)
3. Your browser will download a PNG file with the current view

**Filename format**: `spatial-explorer_YYYYMMDD_HHMMSSZ.png`

### SVG Export (Vector)

1. Click **"Export SVG"**
2. Downloads a scalable vector graphics file
3. Ideal for:
   - Illustrations and figures
   - Further editing in Adobe Illustrator, Inkscape, etc.
   - Publications requiring vector formats

**Filename format**: `spatial-explorer_YYYYMMDD_HHMMSSZ.svg`

**Note**: SVG export captures cell positions, colors, and types as vector circles. The **scale bar is included** when µm/px calibration is set, but other UI elements (e.g., legend panels) are not (use PNG for full UI capture).

---

## Shareable URLs

Spatial Explorer automatically saves your view state to the browser URL. Share the link to reproduce your exact analysis:

**What's saved in the URL:**
- Zoom level (`z`)
- Pan position (`x`, `y`)
- Gene query (`g`)
- Selected cell ID (`c`)
- µm/pixel calibration (`u`)

**Example URL:**
```
https://example.com/spatial-explorer/#v=1&z=320&x=612&y=487&g=CD3E&c=4523&u=0.18
```

**How to share:**
1. Set up your desired view (zoom, gene, selection)
2. Copy the URL from your browser's address bar
3. Send to collaborators—they'll see exactly what you see

**Privacy note**: Data is **not** uploaded to any server. The URL only contains view parameters, not your dataset.

---

## Performance Notes

Spatial Explorer is optimized for datasets with **10,000+ cells**. Key performance features:

### Spatial Indexing
- **Uniform grid acceleration structure** for fast cell picking
- Hover/click selection is **O(k)** (local density) instead of O(n) (all cells)
- Typical pick time: **<1ms** even at 10K+ cells

### Render Optimization
- **RequestAnimationFrame throttling**: Prevents redundant redraws during fast pan/zoom
- **Cached gene ranges**: Percentile calculations (for gene coloring) are cached and invalidated only when filters change
- **Reduced allocations**: Minimal per-frame object creation

### Benchmarks (12,000 Cells, Synthetic Dataset)

| Operation | Time (typical) |
|-----------|----------------|
| Full canvas render | ~8–15ms |
| Hover pick (dense region) | ~0.5–2ms |
| Gene query color switch | <10ms |

**Testing methodology**: Built-in synthetic dataset, measured via EMA (exponential moving average) telemetry displayed in the status line.

### Recommendations
- ✅ **10K–20K cells**: Excellent performance on modern hardware
- ⚠️ **20K–50K cells**: Acceptable; consider filtering genes to reduce memory
- ❌ **50K+ cells**: Requires further optimization (WebGL rendering, server-side pre-processing)

---

## Installation & Deployment

### Local Development

No build step required—this is a **vanilla JavaScript ES module** application.

1. Clone the repository
2. Serve the `web/` directory:
   ```bash
   # Using Python
   python3 -m http.server 8000 --directory web
   
   # Using Node.js (npx)
   npx serve web
   ```
3. Open `http://localhost:8000` in your browser

### Production Deployment

Spatial Explorer is a **static web application**. Deploy to any static hosting service:

- **GitHub Pages**: Push to `gh-pages` branch
- **Netlify / Vercel**: Drag and drop the directory
- **AWS S3 + CloudFront**: Upload as static site
- **Any web server**: Serve as static HTML/JS/CSS

**Requirements:**
- Modern browser with ES6 module support (Chrome 61+, Firefox 60+, Safari 11+, Edge 16+)
- Canvas API support
- No server-side processing required

---

## Native Format Parsers

Python utilities are provided for CosMx, Xenium, and MERSCOPE native outputs.

### Installation

Parsers require Python 3.9+ and pandas:

```bash
pip install pandas pyarrow  # For Parquet support (Xenium)
pip install h5py scipy      # Optional: for Xenium HDF5/MEX matrices
```

### Usage

**Universal loader (auto-detects input format):**
```python
from parsers.universal import load_spatial

# Works with:
# - CosMx native output directories
# - Visium (Space Ranger) output directories
# - Xenium native output directories
# - MERSCOPE native output directories
# - Standard cell-level CSV/TSV files (cell_id, x, y, ...)
result = load_spatial("path/to/input")
```

**CosMx:**
```python
from parsers.cosmx import parse_cosmx

result = parse_cosmx("path/to/cosmx_output/")
# Produces standardized structure with transcript_data, cell_metadata, expression_matrix
```

**MERSCOPE:**
```python
from parsers.merscope import parse_merscope

result = parse_merscope("path/to/merscope_output/")
# Produces standardized structure with transcript_data, cell_metadata, expression_matrix
```

**Visium (Space Ranger):**
```python
from parsers.visium import parse_visium

result = parse_visium("path/to/spaceranger_outs/")
# Produces standardized structure with transcript_data (empty), cell_metadata (spots), expression_matrix
```

**Visium HD (Space Ranger binned outputs):**
```python
from parsers.visium_hd import parse_visium_hd

result = parse_visium_hd("path/to/spaceranger_outs/")
# Selects the highest-resolution bin under binned_outputs/ and returns bins as cell_metadata + expression_matrix
```

**Xenium:**
```python
from parsers.xenium import parse_xenium

result = parse_xenium("path/to/xenium_output/")
# Produces standardized structure with transcript_data, cell_metadata, expression_matrix
```

**Convert to CSV:**
```python
cells = result['cell_metadata']
expr = result['expression_matrix']
df = cells.set_index('cell_id').join(expr, how='inner').reset_index()
df.to_csv('output_for_spatial_explorer.csv', index=False)
```

### Parser Features

- ✅ **Defensive**: Tolerates missing files (logs warnings, returns empty DataFrames)
- ✅ **Flexible column mapping**: Automatically detects common column name variants
- ✅ **Format detection**: Handles wide/long expression matrices, Parquet, gzipped CSV, HDF5, MEX
- ✅ **Validation**: Checks for required columns and warns about data quality issues (NaN coordinates, etc.)

### Extending Parsers

To add support for a new platform (MERSCOPE, STARmap, etc.):

1. Create `parsers/yourplatform.py`
2. Implement `parse_yourplatform(input_dir)` returning:
   ```python
   {
       'platform': 'yourplatform',
       'transcript_data': DataFrame,   # columns: x, y, gene, cell_id
       'cell_metadata': DataFrame,     # columns: cell_id, x, y, cell_type
       'expression_matrix': DataFrame, # index: cell_id, columns: genes
       'metadata': dict
   }
   ```
3. Follow the defensive parsing pattern from `cosmx.py` and `xenium.py`

---

## Project Structure

```
.
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── PERF_NOTES.md
├── web/                            # Static browser app (no build step)
│   ├── index.html
│   ├── app.js
│   ├── data.js
│   ├── render.js
│   ├── ui.js
│   └── tests/                      # Node unit tests (node:test)
├── parsers/                        # Python parsers for native formats
└── tests/                          # Python tests for parsers
```

---

## Browser Compatibility

| Browser | Minimum Version | Notes |
|---------|-----------------|-------|
| Chrome | 61+ | ✅ Recommended |
| Firefox | 60+ | ✅ Recommended |
| Safari | 11+ | ✅ Works well |
| Edge | 16+ | ✅ Chromium-based versions recommended |
| Mobile Safari | iOS 11+ | ⚠️ Touch gestures supported, large datasets may lag |
| Mobile Chrome | Android 61+ | ⚠️ Works, but performance varies by device |

**Required browser features:**
- ES6 modules (`import`/`export`)
- Canvas 2D API
- `requestAnimationFrame`
- URLSearchParams
- Typed arrays (Float32Array, Uint8Array)

---

## Troubleshooting

### "Missing required columns" error when loading CSV

**Cause**: Your CSV is missing `cell_id`, `x`, or `y` columns.

**Solution**: Ensure your CSV has headers exactly named (case-insensitive):
- `cell_id`
- `x`
- `y`

**Example fix:**
```csv
# ❌ Wrong:
id,x_coord,y_coord

# ✅ Correct:
cell_id,x,y
```

### Cells not appearing on the plot

**Possible causes:**
1. **All cell types are hidden**: Check the "Cell types" panel—ensure at least one type is checked
2. **Coordinates out of view**: Click "Reset view" to refit
3. **Invalid coordinates**: Ensure x/y columns contain numeric values (not text)

### Gene query returns no results

**Cause**: Gene name doesn't match any column in your dataset.

**Solution**: 
- Check spelling and capitalization
- Use the autocomplete dropdown to see available genes
- Gene names must match column headers exactly

### Performance is slow with my dataset

**Possible causes:**
1. **Too many cells**: If >50K cells, consider downsampling
2. **Too many genes**: Filter to top 50–100 expressed genes before export
3. **Browser limitations**: Try Chrome (fastest Canvas performance)

**Optimization tips:**
- Close other browser tabs
- Use 2x export resolution instead of 4x
- Disable browser extensions temporarily

### Phenotype gate not highlighting cells

**Possible causes:**
1. **Gate is disabled**: Ensure "Highlight gate" checkbox is checked
2. **Invalid expression**: Check the expression syntax (use `A AND B`, not `A & B`)
3. **Cutoff too high**: Try lowering the cutoff values
4. **Missing genes**: Check the gate status for "Missing genes" errors

---

## Contributing

Contributions are welcome! Spatial Explorer is designed to be modular and extensible.

### Areas for Contribution

- **New native format parsers** (MERSCOPE, STARmap, seqFISH, IMC, etc.)
- **Additional export formats** (PDF, EPS, interactive HTML)
- **UI improvements** (dark mode, keyboard shortcuts, improved mobile UX)
- **Performance enhancements** (WebGL rendering, WebAssembly acceleration)
- **Analysis features** (clustering visualization, spatial statistics, neighborhood analysis)
- **Accessibility** (screen reader support, high-contrast mode, keyboard navigation)

### Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes
4. Test thoroughly:
   - Load synthetic demo dataset
   - Load real CosMx/Xenium data
   - Test in Chrome, Firefox, Safari
   - Check mobile responsiveness
5. Submit a pull request with:
   - Clear description of changes
   - Screenshots/GIFs for UI changes
   - Any new dependencies documented

### Code Style

- **JavaScript**: ES6 modules, no bundler required
- **Python**: PEP 8, type hints encouraged
- **Comments**: Explain *why*, not *what* (code should be self-documenting)
- **Naming**: Descriptive names over abbreviations

---

## License

**MIT License**

Copyright (c) 2025 Spatial Explorer Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## Acknowledgments

Spatial Explorer was designed for the spatial biology community to enable fast, accessible exploration of complex tissue datasets.

**Technologies:**
- **Canvas 2D API** for high-performance rendering
- **ES6 Modules** for modern, dependency-free JavaScript
- **Pandas** for robust Python data parsing

**Inspiration:**
- 10x Genomics Xenium Explorer
- Seurat and Scanpy (for expression visualization patterns)
- D3.js (for interactive data visualization principles)

---

## Citation

If you use Spatial Explorer in your research, please cite:

```bibtex
@software{spatial_explorer_2025,
  author = {Spatial Explorer Contributors},
  title = {Spatial Explorer: Browser-based spatial biology visualization},
  year = {2025},
  url = {https://github.com/yourusername/spatial-explorer},
  version = {1.0.0}
}
```

---

## Contact & Support

- **Issues**: Report bugs and request features via [GitHub Issues](https://github.com/yourusername/spatial-explorer/issues)
- **Discussions**: Community Q&A and ideas via [GitHub Discussions](https://github.com/yourusername/spatial-explorer/discussions)
- **Email**: contact@spatial-explorer.example (for sensitive inquiries)

---

**Happy exploring!**
