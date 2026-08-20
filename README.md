# Cityscape + Townscape mapped workspace references — v2.4

This package preserves the corrected **Cityscape v2.2** reference and replaces the preliminary Townscape v2.3 two-anchor fit with a **four-marker validated Townscape/Townscape Lite calibration**.

## Townscape v2.4 correction

The previous Townscape reference was close but slightly misaligned because it inferred the documented road-parking coordinates from the visible parking-bay geometry. The new calibration uses the four temporary markers spawned by `tools/townscape_validate_reference.py`:

- Open World Origin: `(0.000, 0.000)`
- Car Spawn Spot: `(0.000, -1.300)`
- Road Parking 1: `(-13.093, -7.572)`
- Road Parking 2: `(-18.078, -2.879)`

The marker centers were measured directly in the supplied Townscape Lite top-down screenshot and fitted with a full 2-D affine transform.

Marker-fit residuals:

- RMS: **0.0168 m**
- maximum: **0.0240 m**

To keep the editor reference clean, the final raster is generated from the earlier top-down screenshot that contains **no calibration markers and no QCar**. That clean capture was registered to the marker capture using SIFT feature matching and a RANSAC homography:

- good feature matches: **137**
- RANSAC inliers: **102**
- median inlier reprojection error: **0.548 px**
- mean inlier reprojection error: **0.714 px**

The four calibrated marker positions were transferred onto the clean capture before the final clean-capture pixel-to-world affine was fitted.

## Files

- `data/cityscape_qlabs_rectified.png` — corrected Cityscape raster from v2.2.
- `data/cityscape_reference.json` — Cityscape reference/calibration metadata.
- `data/townscape_qlabs_rectified.png` — corrected, clean, world-aligned Townscape raster.
- `data/townscape_reference.json` — four-marker Townscape calibration and registration metadata.
- `docs/townscape_qlabs_rectified_validation.png` — Townscape raster with 5 m grid, world axes and the four exact reference points.
- `tools/townscape_validate_reference.py` — spawns the four temporary calibration markers.

## Editor use

Run:

```bash
python main.py
```

Select **Workspace → Townscape** or **Workspace → Townscape Lite**, then press **Fit Workspace**.

The raster is a locked placement guide only. It is not selectable and is never exported as QLabs road geometry.

## Accuracy note

The reported marker residual quantifies agreement at the four calibration points in the supplied top-down capture. It should not be interpreted as centimetre-level survey accuracy across every road edge. The reference remains a calibrated visual placement guide and should be revalidated after major QLabs workspace/camera changes.


## v2.5 workspace-fit / Z defaults

- Cityscape and Cityscape Lite now share the same calibrated Cityscape map.
- Townscape and Townscape Lite continue to share the validated Townscape map.
- Selecting any of those four compact mapped workspaces automatically sizes the editable canvas around the calibrated map and then fits the viewport to it.
- Saved JSON projects keep their explicitly saved canvas dimensions when reopened.
- Native track/spawn base Z defaults are workspace-specific: Plane/Custom = 0.20 m, Cityscape/Cityscape Lite = 0.50 m, Townscape/Townscape Lite = 0.50 m, Open Road = 1.20 m.  The toolbar value remains editable and saved per project.
