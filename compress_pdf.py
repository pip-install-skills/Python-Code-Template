import os
import shutil
import fitz  # PyMuPDF (pip install pymupdf)

# -----------------------------
INPUT_PDF = "input.pdf"
OUTPUT_PDF = "output.pdf"
TARGET_KB = 450   # target size
# -----------------------------

TARGET_BYTES = TARGET_KB * 1024


def human_kb(b):
    return f"{b/1024:.1f} KB"


def lossless_optimize(inp, out):
    """Lossless cleanup: keeps text & vector content."""
    doc = fitz.open(inp)
    try:
        doc.save(
            out,
            garbage=4,   # maximum garbage collection
            deflate=True,
            clean=True,
        )
    finally:
        doc.close()
    return os.path.getsize(out)


def rasterize_compress(inp, out, target_bytes):
    """Rasterize each page to JPEG at lower DPI until small enough."""
    attempts = [150, 120, 96, 72, 60]  # from higher to lower quality

    original = fitz.open(inp)
    try:
        for dpi in attempts:
            print(f"\nTrying rasterization at {dpi} DPI...")
            new = fitz.open()

            for page in original:
                pix = page.get_pixmap(dpi=dpi)
                img = pix.tobytes("jpeg")

                # Page size in points
                w_pt = pix.width * 72 / dpi
                h_pt = pix.height * 72 / dpi

                p = new.new_page(width=w_pt, height=h_pt)
                rect = fitz.Rect(0, 0, w_pt, h_pt)
                p.insert_image(rect, stream=img)

            new.save(out, garbage=4, deflate=True, clean=True)
            new.close()

            size = os.path.getsize(out)
            print(f" → Size: {human_kb(size)}")

            if size <= target_bytes:
                print(" ✓ Target achieved")
                return size

        # Could not reach target
        return os.path.getsize(out)

    finally:
        original.close()


def compress_pdf():
    if not os.path.exists(INPUT_PDF):
        raise FileNotFoundError(INPUT_PDF)

    original_size = os.path.getsize(INPUT_PDF)
    print("Original size:", human_kb(original_size))
    print("Target:", human_kb(TARGET_BYTES))

    # Already under target?
    if original_size <= TARGET_BYTES:
        shutil.copyfile(INPUT_PDF, OUTPUT_PDF)
        print("Already under target, copied directly.")
        return

    print("\nStep 1: Lossless optimization…")
    size_lossless = lossless_optimize(INPUT_PDF, OUTPUT_PDF)
    print(" → After lossless:", human_kb(size_lossless))

    if size_lossless <= TARGET_BYTES:
        print(" ✓ Done (lossless successful)")
        return

    print("\nStep 2: Rasterization + compression…")
    final_size = rasterize_compress(INPUT_PDF, OUTPUT_PDF, TARGET_BYTES)

    print("\nFinal output size:", human_kb(final_size))
    if final_size > TARGET_BYTES:
        print("⚠️ Warning: Could not reach the target size.")


# Run it
compress_pdf()

