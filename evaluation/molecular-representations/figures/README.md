# Optional activity-model comparison figure

The RF reference line plus four alternatives cover all five model variants. Two axes separately show paired MAE and measured top-ten-recall differences. The random-network versus RF comparison is descriptive post-score analysis. Original GP, frozen-feature and fine-tuned intervals are checked to 1e-12 by the script. This is not a claim of better prospective drug discovery.

To regenerate, copy this directory to a NEW location, install NumPy and Matplotlib, then run `python -B plot.py` there. The script overwrites rendered files in its own directory, so do not run it inside the sealed archive. Captured versions: NumPy 2.5.3, Matplotlib 3.11.2. Rendering is optional; standard package verification and numeric recalculation do not require Matplotlib.

`input.json` carries source-relative paths and hashes. All three referenced scored source files are included in the package. The rendering receipt pins the supplied PNG/SVG/PDF; numeric recomputation is separate from timestamp-dependent image metadata.
