# Measurement validation protocol

Status: SDK extraction is validated against a real Matrice 4T original; agreement with DJI Thermal Analysis Tool 3 (DTAT3) is not yet recorded.

## Controlled comparison

1. Copy the exact original file and record its SHA-256 checksum.
2. Open it in DTAT3 and this application without saving or re-exporting it.
3. Record image/default emissivity, target distance, relative humidity, atmospheric temperature, and reflected temperature. Apply identical explicit values in both tools.
4. Compare at least ten pixels distributed across the frame, including the app-reported extrema. Coordinates are zero-based in this app; account for any one-based DJI UI convention.
5. Draw identical axis-aligned regions using native pixel boundaries and compare valid count, minimum, maximum, and arithmetic mean.
6. Repeat in each camera gain/range mode present in the sample set and near both ends of the observed range.
7. Save screenshots/exported values, SDK version, DTAT version, OS/architecture, checksum, parameters, and analysis version.

Do not choose an agreement tolerance before examining DJI's documented numeric output and rounding behavior. Record raw float differences separately from one-decimal display differences, justify the chosen software-agreement tolerance, and investigate systematic bias. Agreement between two programs does not establish the camera's physical measurement accuracy.

## Known validated sample

- SDK archive: `dji_thermal_sdk_v1.8_20250829.zip`
- Platform: Windows x64
- SDK API log: API version `0x14`, R-JPEG version `0x300`, header `0x1`, curve `0x1`
- File: `DJI_20260728125706_0001_T.JPG`
- Matrix: 640 × 512 float32 °C
- Defaults reported range: distance 1–300 m, humidity 1–100%, emissivity 0.1–1.0, ambient −40–80 °C, reflection −40–100 °C
- Result: min 21.3940067 °C at (435,340), max 30.4042301 °C at (639,120), mean 22.3346043 °C

