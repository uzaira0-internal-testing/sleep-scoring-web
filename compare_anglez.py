import gt3x_rs
import numpy as np
import polars as pl

# Calibration parameters from GGIR
cal_offset = [-0.01735653, -0.00251163, -0.01609619]
cal_scale = [1.0068665, 0.9892388, 0.9980455]

# Load GGIR reference anglez
ggir_anglez = pl.read_csv("D:/Scripts/monorepo/external/ggir/reference_data/P1-1093_ggir_anglez.csv")

# Load GT3X and compute anglez using v3 (non-chunked)
gt3x_path = "D:/Scripts/monorepo/external/ggir/output/batch_r/input_data/P1-1093-A-T1 (2024-03-04).gt3x"

# Get v3 (non-chunked) for comparison
result_v3 = gt3x_rs.process_gt3x_ggir_anglez_v3(gt3x_path, cal_offset, cal_scale)
rust_anglez_v3 = result_v3[0]  # First element is anglez array

# Compare
ggir_vals = ggir_anglez["anglez"].to_numpy()
rust_v3_vals = np.array(rust_anglez_v3[: len(ggir_vals)])

# Find mismatches (using a small tolerance)
tol = 0.01
diff_v3 = np.abs(ggir_vals - rust_v3_vals)
mismatch_v3 = np.where(diff_v3 > tol)[0]


# Show first 50 mismatches for v3
epochs_per_day = 17280
for i, idx in enumerate(mismatch_v3[:50]):
    day = idx // epochs_per_day + 1
    pos_in_day = idx % epochs_per_day

# Show mismatches grouped by day
for day in range(1, 13):
    day_start = (day - 1) * epochs_per_day
    day_end = day * epochs_per_day
    day_mismatches = [idx for idx in mismatch_v3 if day_start <= idx < day_end]
    if day_mismatches:
        pass
