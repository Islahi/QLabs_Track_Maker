"""Fit a pixel->world affine calibration for Cityscape/Townscape references.

Example with three or more known image/world anchor pairs::

    python tools/calibrate_workspace_reference.py \
        data/cityscape_reference.json \
        --anchor 434 331 0 0 \
        --anchor 500 331 10 0 \
        --anchor 434 265 0 10

Each anchor is: PIXEL_X PIXEL_Y WORLD_X WORLD_Y.
The script updates only the JSON calibration; it does not modify the PNG.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _solve_3x3(matrix, values):
    # Small dependency-free Gaussian elimination for the normal equations.
    augmented = [list(map(float, row)) + [float(value)] for row, value in zip(matrix, values)]
    n = 3
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-12:
            raise ValueError("Calibration anchors do not span a usable 2-D affine fit")
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        scale = augmented[col][col]
        augmented[col] = [value / scale for value in augmented[col]]
        for row in range(n):
            if row == col:
                continue
            factor = augmented[row][col]
            augmented[row] = [
                current - factor * pivot_value
                for current, pivot_value in zip(augmented[row], augmented[col])
            ]
    return [augmented[row][-1] for row in range(n)]


def _least_squares_coefficients(anchors, value_index):
    # Solve (A^T A)c = A^T b for c=[u,v,1].
    ata = [[0.0] * 3 for _ in range(3)]
    atb = [0.0] * 3
    for anchor in anchors:
        u, v = float(anchor[0]), float(anchor[1])
        row = [u, v, 1.0]
        target = float(anchor[value_index])
        for i in range(3):
            atb[i] += row[i] * target
            for j in range(3):
                ata[i][j] += row[i] * row[j]
    return _solve_3x3(ata, atb)


def _rms_error(anchors, x_coeff, y_coeff):
    total = 0.0
    maximum = 0.0
    for u, v, x, y in anchors:
        predicted_x = x_coeff[0] * u + x_coeff[1] * v + x_coeff[2]
        predicted_y = y_coeff[0] * u + y_coeff[1] * v + y_coeff[2]
        error = ((predicted_x - x) ** 2 + (predicted_y - y) ** 2) ** 0.5
        total += error * error
        maximum = max(maximum, error)
    return (total / len(anchors)) ** 0.5, maximum


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument(
        "--anchor",
        nargs=4,
        type=float,
        action="append",
        metavar=("PX", "PY", "X", "Y"),
        required=True,
    )
    args = parser.parse_args()

    if len(args.anchor) < 3:
        parser.error("At least three pixel/world anchors are required")

    data = json.loads(args.reference.read_text(encoding="utf-8"))
    x_coeff = _least_squares_coefficients(args.anchor, 2)
    y_coeff = _least_squares_coefficients(args.anchor, 3)
    rms, maximum = _rms_error(args.anchor, x_coeff, y_coeff)

    image = data.setdefault("image", {})
    image["pixel_to_world_affine"] = {
        "x": x_coeff,
        "y": y_coeff,
    }
    calibration = data.setdefault("calibration", {})
    calibration.update({
        "method": "Least-squares affine fit from user-supplied image pixel/world anchors.",
        "anchors": [
            {"pixel": [u, v], "world_xy": [x, y]}
            for u, v, x, y in args.anchor
        ],
        "anchor_rms_error_m": rms,
        "anchor_max_error_m": maximum,
        "status": "user_calibrated",
    })

    args.reference.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {args.reference}")
    print(f"RMS error: {rms:.4f} m")
    print(f"Max error: {maximum:.4f} m")
    print("x =", x_coeff)
    print("y =", y_coeff)


if __name__ == "__main__":
    main()
