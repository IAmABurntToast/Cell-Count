#!/usr/bin/env python

from pathlib import Path
import csv
import re
import argparse

import numpy as np
from cellpose import models, io
import matplotlib.pyplot as plt



def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run Cellpose CPSAM on all plate images in a folder, "
            "write colony_counts.csv, and export overlay images."
        )
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default="/Users/hanjiunke/Desktop/CFU App",
        help="Folder containing plate images (default: /Users/hanjiunke/Desktop/CFU App)",
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=None,
        help="Optional: Directory to save results. If invalid/empty, defaults to input folder.",
    )
    args = parser.parse_args()

    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        raise SystemExit(f"Folder does not exist: {folder}")

    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = folder

    # which files to treat as plates
    IMAGE_EXTS = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}
    images = sorted(
        p for p in folder.iterdir() 
        if p.suffix.lower() in IMAGE_EXTS and not p.name.startswith(".")
    )

    print(f"Found {len(images)} images in {folder}", flush=True)
    for i, img in enumerate(images):
        print(f"  [{i+1}] {img.name}", flush=True)
    
    if not images:
        return

    # subfolder for visualization outputs
    visuals_dir = output_dir / "cp_visuals"
    visuals_dir.mkdir(exist_ok=True)
    print(f"Saving overlay images to: {visuals_dir}", flush=True)

    import torch
    
    # Check for GPU (CUDA) or MPS (Mac)
    use_gpu = False
    if torch.cuda.is_available():
        use_gpu = True
        print("GPU detected (CUDA).")
    elif torch.backends.mps.is_available():
        use_gpu = True
        print("GPU detected (MPS/Mac).")
    else:
        print("No GPU detected. Using CPU.", flush=True)
        print("WARNING: Processing on CPU will be slow for large images!", flush=True)

    # load CPSAM model (same as 'run CPSAM' button)
    print(f"Loading CPSAM model (gpu={use_gpu})...")
    model = models.CellposeModel(pretrained_model="cpsam", gpu=use_gpu)

    out_path = output_dir / "colony_counts.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "File Name",
                "True Count",
            ]
        )

        for img_path in images:
            stem = img_path.stem

            try:
                print(f"\nProcessing {img_path.name} ...", flush=True)
                img = io.imread(str(img_path))

                # rescale=0.5 downsamples image by half (1/4 area).
                # Critical for Streamlit Cloud (CPU only, low RAM) to prevent OOM/Timeouts.
                print(f"  Shape before processing: {img.shape}", flush=True)
                
                masks, flows, styles = model.eval(
                    img,
                    channels=[0, 0],
                    diameter=None,   
                    rescale=0.5,     # <- CHANGED: downscale for Cloud stability
                )

                pred = int(masks.max())  # 0 = background, 1..N = colonies
                print(f"  -> predicted {pred} colonies", flush=True)

                # --------- save raw mask (label image, mainly for data use) ----------
                # io.save_masks(...)

                # --------- overlay: original plate + colored colonies ----------
                fig, ax = plt.subplots(figsize=(5, 5))

                # show original image in gray/RGB
                if img.ndim == 2:          # grayscale
                    ax.imshow(img, cmap="gray")
                else:                       # RGB
                    ax.imshow(img)

                # show masks as colored blobs with transparency
                masked_labels = np.ma.masked_where(masks == 0, masks)
                ax.imshow(masked_labels, alpha=0.5, cmap="tab20")
                ax.axis("off")

                overlay_path = visuals_dir / f"{stem}_overlay.png"
                fig.savefig(overlay_path, dpi=200, bbox_inches="tight")
                plt.close(fig)
                print(f"  saved overlay: {overlay_path.name}", flush=True)

                writer.writerow(
                    [
                        stem,
                        pred,
                    ]
                )
            except Exception as e:
                print(f"ERROR processing {img_path.name}: {e}", flush=True)
                # Optionally continue or log specifically
                continue

    print(f"\nDone. Wrote {out_path}", flush=True)
    print(f"Overlay + mask images saved in: {visuals_dir}")


if __name__ == "__main__":
    main()
