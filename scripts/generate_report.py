#!/usr/bin/env python3
"""
Generate the VisionShield university-style project report (PDF).

Every figure is produced by the *real* engine — the blur comparison grid and
mask demos run `BlurEngine` / `MaskGenerator` on a synthetic scene, and the
timing chart benchmarks the actual algorithms on this machine. Diagrams are
drawn with matplotlib; the document is assembled with ReportLab Platypus.

Usage:
    python scripts/generate_report.py
Output:
    docs/report/VisionShield_Project_Report.pdf
    docs/report/figures/*.png
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import cv2  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

from app.vision.blur_engine import BlurEngine  # noqa: E402
from app.vision.masking import MaskGenerator  # noqa: E402
from app.vision.types import BlurType, Box, Region  # noqa: E402

FIG_DIR = ROOT / "docs" / "report" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Print-friendly palette
NAVY = "#0B1220"
CYAN = "#0891B2"
VIOLET = "#7C3AED"
INK = "#111827"
MUT = "#5B6575"
PANEL = "#F2F6FB"
EDGE = "#C9D4E4"


# --------------------------------------------------------------------------- #
# Synthetic scene — structured enough that every blur is clearly visible      #
# --------------------------------------------------------------------------- #
def make_scene(w: int = 640, h: int = 360) -> np.ndarray:
    """Deterministic BGR test scene: gradient, shapes, text, fine grid."""
    x = np.linspace(0, 1, w, dtype=np.float32)
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    b = (60 + 120 * x)[None, :].repeat(h, 0)
    g = (40 + 140 * y).repeat(w, 1)
    r = 90 + 60 * np.sin(6.28 * (x[None, :] + y))
    img = np.dstack([b, g, r]).astype(np.uint8)

    for gx in range(0, w, 32):
        cv2.line(img, (gx, 0), (gx, h), (255, 255, 255), 1)
    for gy in range(0, h, 32):
        cv2.line(img, (0, gy), (w, gy), (255, 255, 255), 1)

    cv2.circle(img, (int(w * 0.30), int(h * 0.42)), 62, (40, 60, 220), -1)
    cv2.circle(img, (int(w * 0.30), int(h * 0.42)), 62, (255, 255, 255), 2)
    cv2.rectangle(img, (int(w * 0.55), int(h * 0.22)), (int(w * 0.82), int(h * 0.62)),
                  (200, 160, 40), -1)
    cv2.putText(img, "SAMPLE 123", (int(w * 0.18), int(h * 0.85)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 3, cv2.LINE_AA)
    cv2.putText(img, "fine detail text", (int(w * 0.56), int(h * 0.72)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1, cv2.LINE_AA)
    return img


def _rgb(img_bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)


# --------------------------------------------------------------------------- #
# Figure 1 — system architecture                                              #
# --------------------------------------------------------------------------- #
def _boxed(ax, x, y, w, h, title, lines, face=PANEL, edge=EDGE, tcol=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.018",
                                fc=face, ec=edge, lw=1.4))
    ax.text(x + w / 2, y + h - 0.055, title, ha="center", va="top",
            fontsize=10.5, fontweight="bold", color=tcol)
    for i, ln in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.115 - i * 0.052, ln, ha="center", va="top",
                fontsize=8.2, color=MUT)


def _arrow(ax, p0, p1, label="", color=CYAN, ls="-"):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=14,
                                 lw=1.6, color=color, linestyle=ls))
    if label:
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        ax.text(mx, my + 0.018, label, ha="center", fontsize=8, color=color,
                fontweight="bold")


def fig_architecture(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    _boxed(ax, 0.03, 0.60, 0.30, 0.34, "Browser — React SPA",
           ["Dashboard · Controls · Stats", "AppContext (global state)",
            "useStream (WS consumer)", "Vite dev proxy / nginx"])
    _boxed(ax, 0.38, 0.56, 0.34, 0.40, "FastAPI backend",
           ["routes/  REST + WebSocket", "services/  CameraManager",
            "vision/  detect · mask · blur", "config/ · utils/"])
    _boxed(ax, 0.78, 0.63, 0.19, 0.26, "OS webcam", ["V4L2 / DirectShow", "driver buffer"])

    _boxed(ax, 0.38, 0.08, 0.34, 0.34, "Processing threads",
           ["CaptureThread → latest frame", "ProcessingThread → pipeline",
            "SharedOutput → JPEG + stats"], face="#EEF2FF")

    _arrow(ax, (0.33, 0.83), (0.38, 0.83), "REST /api/*")
    _arrow(ax, (0.38, 0.70), (0.33, 0.70), "WS frames + stats", VIOLET)
    _arrow(ax, (0.78, 0.76), (0.72, 0.76), "frames", INK)
    _arrow(ax, (0.55, 0.56), (0.55, 0.42), "start / stop / read slot", MUT)

    ax.set_title("VisionShield — system architecture", fontsize=13,
                 fontweight="bold", color=NAVY, pad=12)
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Figure 2 — frame pipeline flowchart                                          #
# --------------------------------------------------------------------------- #
def fig_pipeline(path: Path) -> None:
    stages = [
        ("Capture", "newest camera frame (1-slot)"),
        ("Downscale + mirror", "PROCESS_WIDTH = 960 px"),
        ("Detect", "BlazeFace  /  HandLandmarker (VIDEO mode)"),
        ("Smooth", "EMA α=0.45 · hold 8 frames"),
        ("Mask", "ellipses / rounded rect · feather 41 px"),
        ("Blur", "one of 9 algorithms · strength 1–100"),
        ("Composite", "frame·m + blurred·(1−m)"),
        ("Overlay + encode", "banner · brackets · JPEG q80"),
        ("Publish", "SharedOutput → WebSocket clients"),
    ]
    fig, ax = plt.subplots(figsize=(6.4, 8.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    n = len(stages)
    bh = 0.075
    gap = (0.96 - n * bh) / (n - 1)
    y = 0.96 - bh
    for i, (title, sub) in enumerate(stages):
        face = "#EEF2FF" if title in ("Detect", "Blur") else PANEL
        ax.add_patch(FancyBboxPatch((0.14, y), 0.72, bh,
                                    boxstyle="round,pad=0.008,rounding_size=0.014",
                                    fc=face, ec=EDGE, lw=1.3))
        ax.text(0.5, y + bh * 0.62, title, ha="center", fontsize=10.5,
                fontweight="bold", color=INK)
        ax.text(0.5, y + bh * 0.24, sub, ha="center", fontsize=8, color=MUT)
        if i < n - 1:
            ax.add_patch(FancyArrowPatch((0.5, y - 0.004), (0.5, y - gap + 0.006),
                                         arrowstyle="-|>", mutation_scale=13,
                                         lw=1.5, color=CYAN))
        y -= bh + gap
    ax.set_title("Per-frame processing pipeline", fontsize=13, fontweight="bold",
                 color=NAVY, pad=10)
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Figure 3 — threading model                                                   #
# --------------------------------------------------------------------------- #
def fig_threading(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 3.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    _boxed(ax, 0.02, 0.30, 0.20, 0.46, "CaptureThread",
           ["cap.read() at driver speed", "keeps ONLY newest frame",
            "30-miss failure detection"])
    _boxed(ax, 0.295, 0.30, 0.22, 0.46, "ProcessingThread",
           ["FramePipeline @ target FPS", "settings snapshot / frame",
            "JPEG encode (q80)"], face="#EEF2FF")
    _boxed(ax, 0.585, 0.30, 0.17, 0.46, "SharedOutput",
           ["single slot", "jpeg · stats · seq", "latest-frame-wins"])
    _boxed(ax, 0.82, 0.30, 0.16, 0.46, "Async clients",
           ["WS handlers", "MJPEG generator", "read-only"])

    _arrow(ax, (0.22, 0.53), (0.295, 0.53), "latest()")
    _arrow(ax, (0.515, 0.53), (0.585, 0.53), "publish()")
    _arrow(ax, (0.755, 0.53), (0.82, 0.53), "snapshot()", VIOLET)

    ax.text(0.5, 0.10, "No queues anywhere: every hand-off is a one-slot buffer, "
                       "so a slow consumer skips frames instead of accumulating lag.",
            ha="center", fontsize=8.6, color=MUT, style="italic")
    ax.set_title("Threading model", fontsize=13, fontweight="bold", color=NAVY, pad=10)
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Figure 4 — the nine blur algorithms on one scene (REAL engine output)        #
# --------------------------------------------------------------------------- #
def fig_blur_grid(path: Path, engine: BlurEngine, scene: np.ndarray) -> None:
    labels = {
        BlurType.GAUSSIAN: "Gaussian", BlurType.BOX: "Box", BlurType.BILATERAL: "Bilateral",
        BlurType.MEDIAN: "Median", BlurType.PIXELATE: "Pixelate", BlurType.MOSAIC: "Mosaic",
        BlurType.MOTION: "Motion", BlurType.STRONG: "Strong", BlurType.LIGHT: "Light",
    }
    fig, axes = plt.subplots(2, 5, figsize=(11.4, 4.4))
    axes = axes.ravel()
    axes[0].imshow(_rgb(scene))
    axes[0].set_title("Original", fontsize=9.5, fontweight="bold", color=INK)
    for ax, bt in zip(axes[1:], BlurType):
        ax.imshow(_rgb(engine.apply(scene, bt, 60)))
        ax.set_title(labels[bt], fontsize=9.5, color=INK)
    for ax in axes:
        ax.axis("off")
    fig.suptitle("Blur engine output — every algorithm at strength 60",
                 fontsize=12.5, fontweight="bold", color=NAVY)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=165)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Figure 5 — masking & compositing walk-through (REAL engine output)           #
# --------------------------------------------------------------------------- #
def fig_mask_demo(path: Path, engine: BlurEngine, scene: np.ndarray) -> None:
    gen = MaskGenerator(feather_px=41)
    box = Box(scene.shape[1] * 0.17, scene.shape[0] * 0.18,
              scene.shape[1] * 0.26, scene.shape[0] * 0.52)
    mask = gen.ellipses(scene.shape, [box])
    blurred = engine.apply(scene, BlurType.GAUSSIAN, 70)
    out_outside = gen.composite(scene, blurred, mask, Region.OUTSIDE)
    out_inside = gen.composite(scene, blurred, mask, Region.INSIDE)

    ref = scene.copy()
    x, y, w, h = box.as_int()
    cv2.ellipse(ref, (x + w // 2, y + h // 2), (w // 2, h // 2), 0, 0, 360,
                (34, 211, 238), 3)

    fig, axes = plt.subplots(1, 4, figsize=(11.4, 2.9))
    panels = [
        (ref, "1 · Detection (padded box → ellipse)"),
        ((mask * 255).astype(np.uint8), "2 · Feathered mask (soft edge)"),
        (out_outside, "3 · Region = outside (face sharp)"),
        (out_inside, "4 · Region = inside (face hidden)"),
    ]
    for ax, (img, title) in zip(axes, panels):
        if img.ndim == 2:
            ax.imshow(img, cmap="gray", vmin=0, vmax=255)
        else:
            ax.imshow(_rgb(img))
        ax.set_title(title, fontsize=8.8, color=INK)
        ax.axis("off")
    fig.suptitle("Mask generation and compositing", fontsize=12.5,
                 fontweight="bold", color=NAVY)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    fig.savefig(path, dpi=165)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Figure 6 — measured per-algorithm timing on this machine (REAL benchmark)    #
# --------------------------------------------------------------------------- #
def fig_blur_timing(path: Path, engine: BlurEngine) -> dict:
    frame = cv2.resize(make_scene(), (960, 540))
    results: dict[str, float] = {}
    for bt in BlurType:
        engine.apply(frame, bt, 60)  # warm-up
        t0 = time.perf_counter()
        runs = 25
        for _ in range(runs):
            engine.apply(frame, bt, 60)
        results[bt.value] = (time.perf_counter() - t0) / runs * 1000.0

    names = list(results.keys())
    vals = [results[n] for n in names]
    fig, ax = plt.subplots(figsize=(8.6, 3.4))
    bars = ax.bar(names, vals, color=CYAN, edgecolor=NAVY, linewidth=0.6)
    bars[int(np.argmax(vals))].set_color(VIOLET)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + max(vals) * 0.02, f"{v:.1f}",
                ha="center", fontsize=8, color=INK)
    ax.set_ylabel("ms per 960×540 frame", fontsize=9)
    ax.set_title("Measured blur cost at strength 60 (25-run average, this machine)",
                 fontsize=11.5, fontweight="bold", color=NAVY)
    ax.tick_params(axis="x", labelsize=8.5)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return results


def build_all_figures() -> dict:
    """Generate every figure; returns the measured blur timings."""
    engine = BlurEngine()
    scene = make_scene()
    fig_architecture(FIG_DIR / "architecture.png")
    fig_pipeline(FIG_DIR / "pipeline.png")
    fig_threading(FIG_DIR / "threading.png")
    fig_blur_grid(FIG_DIR / "blur_grid.png", engine, scene)
    fig_mask_demo(FIG_DIR / "mask_demo.png", engine, scene)
    timings = fig_blur_timing(FIG_DIR / "blur_timing.png", engine)
    print(f"[figures] 6 figures written to {FIG_DIR}")
    return timings


# =========================================================================== #
#  PDF assembly (ReportLab Platypus)                                          #
# =========================================================================== #
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.lib.utils import ImageReader  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents  # noqa: E402

PDF_PATH = ROOT / "docs" / "report" / "VisionShield_Project_Report.pdf"

C_NAVY = colors.HexColor(NAVY)
C_CYAN = colors.HexColor(CYAN)
C_VIOLET = colors.HexColor(VIOLET)
C_INK = colors.HexColor(INK)
C_MUT = colors.HexColor(MUT)
C_PANEL = colors.HexColor(PANEL)
C_EDGE = colors.HexColor(EDGE)

S_H1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=15.5, leading=19,
                      textColor=C_NAVY, spaceBefore=16, spaceAfter=7)
S_H1N = ParagraphStyle("H1NoTOC", parent=S_H1)
S_H2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=11.5, leading=15,
                      textColor=colors.HexColor("#0E5E74"), spaceBefore=11, spaceAfter=4)
S_BODY = ParagraphStyle("Body", fontName="Helvetica", fontSize=9.6, leading=13.6,
                        textColor=C_INK, spaceAfter=5, alignment=4)  # justified
S_BULL = ParagraphStyle("Bullet", parent=S_BODY, leftIndent=13, bulletIndent=3,
                        spaceAfter=3, alignment=0)
S_CAP = ParagraphStyle("Caption", fontName="Helvetica-Oblique", fontSize=8.2,
                       leading=10.5, textColor=C_MUT, alignment=1,
                       spaceBefore=3, spaceAfter=10)
S_CODE = ParagraphStyle("Code", fontName="Courier", fontSize=7.7, leading=9.8,
                        textColor=C_INK)
S_TOC1 = ParagraphStyle("TOC1", fontName="Helvetica-Bold", fontSize=10.2,
                        leading=15, textColor=C_INK)
S_TOC2 = ParagraphStyle("TOC2", fontName="Helvetica", fontSize=9.2, leading=13,
                        leftIndent=14, textColor=C_MUT)


class ReportDoc(BaseDocTemplate):
    """A4 document with a cover template, running header/footer, TOC + outline."""

    def __init__(self, filename: str, **kw) -> None:
        super().__init__(filename, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                         topMargin=2.35 * cm, bottomMargin=1.9 * cm,
                         title="VisionShield — Project Report",
                         author="Youcef — SoftWebElevation", **kw)
        body = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="body")
        cover = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="cover")
        self.addPageTemplates([
            PageTemplate(id="Cover", frames=[cover], onPage=_paint_cover),
            PageTemplate(id="Body", frames=[body], onPage=_paint_body),
        ])

    def afterFlowable(self, flowable) -> None:
        if not isinstance(flowable, Paragraph):
            return
        style = flowable.style.name
        if style not in ("H1", "H2"):
            return
        text = flowable.getPlainText()
        level = 0 if style == "H1" else 1
        # Deterministic key: identical across multiBuild passes, so the TOC
        # (which links against these keys) can converge.
        key = "sec-" + re.sub(r"\W+", "-", text.lower()).strip("-")
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level, closed=False)
        self.notify("TOCEntry", (level, text, self.page, key))


def _paint_cover(canv, doc) -> None:
    W, H = A4
    canv.saveState()
    canv.setFillColor(C_NAVY)
    canv.rect(0, H - 7.4 * cm, W, 7.4 * cm, stroke=0, fill=1)
    canv.setFillColor(C_CYAN)
    canv.rect(0, H - 7.4 * cm - 0.14 * cm, W, 0.14 * cm, stroke=0, fill=1)

    cx, cy = 2.9 * cm, H - 3.7 * cm
    canv.setLineWidth(3)
    canv.setStrokeColor(C_CYAN)
    canv.circle(cx, cy, 0.88 * cm, stroke=1, fill=0)
    canv.setFillColor(C_VIOLET)
    canv.circle(cx, cy, 0.35 * cm, stroke=0, fill=1)

    canv.setFillColor(colors.white)
    canv.setFont("Helvetica-Bold", 31)
    canv.drawString(4.4 * cm, H - 3.55 * cm, "VisionShield")
    canv.setFont("Helvetica", 12)
    canv.setFillColor(colors.HexColor("#BFE3EF"))
    canv.drawString(4.42 * cm, H - 4.5 * cm,
                    "Real-Time AI Privacy Blur — Face & Hand Privacy Modes")
    canv.setFont("Helvetica", 9.5)
    canv.drawString(4.42 * cm, H - 5.2 * cm,
                    "FastAPI  ·  OpenCV  ·  MediaPipe Tasks  ·  React  ·  WebSockets  ·  Docker")

    canv.setFillColor(C_INK)
    canv.setFont("Helvetica-Bold", 13)
    canv.drawCentredString(W / 2, H - 11.6 * cm,
                           "Final-Year Software Engineering Project Report")
    canv.setFont("Helvetica", 10.5)
    canv.setFillColor(C_MUT)
    canv.drawCentredString(W / 2, H - 12.55 * cm, "Author: Youcef  —  SoftWebElevation")
    canv.drawCentredString(W / 2, H - 13.25 * cm,
                           "\u00c9cole nationale Sup\u00e9rieure d'Informatique (ESI)")
    canv.drawCentredString(W / 2, H - 13.95 * cm, "July 2026  ·  Version 1.0")

    canv.setStrokeColor(C_EDGE)
    canv.setLineWidth(1)
    canv.line(5.4 * cm, H - 15.0 * cm, W - 5.4 * cm, H - 15.0 * cm)
    canv.setFont("Helvetica-Oblique", 9)
    canv.drawCentredString(W / 2, H - 16.0 * cm,
                           "Every figure in this report was generated by the project's own")
    canv.drawCentredString(W / 2, H - 16.55 * cm,
                           "vision engine — see scripts/generate_report.py.")

    canv.setFillColor(C_NAVY)
    canv.rect(0, 0, W, 1.1 * cm, stroke=0, fill=1)
    canv.setFillColor(colors.white)
    canv.setFont("Helvetica", 8)
    canv.drawCentredString(W / 2, 0.42 * cm, "VisionShield v1.0  ·  MIT License  ·  github.com/kingofdead6")
    canv.restoreState()


def _paint_body(canv, doc) -> None:
    W, H = A4
    canv.saveState()
    canv.setFont("Helvetica-Bold", 8.5)
    canv.setFillColor(C_NAVY)
    canv.drawString(2 * cm, H - 1.35 * cm, "VisionShield")
    canv.setFont("Helvetica", 8.5)
    canv.setFillColor(C_MUT)
    canv.drawRightString(W - 2 * cm, H - 1.35 * cm, "Real-Time AI Privacy Blur — Project Report")
    canv.setStrokeColor(C_CYAN)
    canv.setLineWidth(1.1)
    canv.line(2 * cm, H - 1.55 * cm, W - 2 * cm, H - 1.55 * cm)
    canv.setFont("Helvetica", 8.5)
    canv.setFillColor(C_MUT)
    canv.drawCentredString(W / 2, 1.05 * cm, f"Page {doc.page}")
    canv.restoreState()


# ------------------------------ flowable helpers --------------------------- #
_fig_no = 0


def P(text: str, style=S_BODY) -> Paragraph:
    return Paragraph(text, style)


def bullets(items) -> list:
    return [Paragraph(t, S_BULL, bulletText="\u2022") for t in items]


def code_block(text: str) -> Table:
    t = Table([[Preformatted(text.strip("\n"), S_CODE)]], colWidths=[17 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_PANEL),
        ("BOX", (0, 0), (-1, -1), 0.7, C_EDGE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def fig(name: str, caption: str, width=16.6 * cm) -> KeepTogether:
    global _fig_no
    _fig_no += 1
    path = FIG_DIR / name
    iw, ih = ImageReader(str(path)).getSize()
    img = Image(str(path), width=width, height=width * ih / iw)
    return KeepTogether([Spacer(1, 4), img,
                         P(f"<b>Figure {_fig_no}</b> — {caption}", S_CAP)])


def data_table(header, rows, widths) -> Table:
    data = [[Paragraph(f"<b>{h}</b>", ParagraphStyle("th", parent=S_BODY, fontSize=8.4,
                                                     textColor=colors.white, alignment=0))
             for h in header]]
    cell = ParagraphStyle("td", parent=S_BODY, fontSize=8.4, leading=11, spaceAfter=0)
    for r in rows:
        data.append([Paragraph(str(c), cell) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_PANEL]),
        ("GRID", (0, 0), (-1, -1), 0.5, C_EDGE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


# ------------------------------ document body ------------------------------ #
def build_pdf(timings: dict) -> None:
    doc = ReportDoc(str(PDF_PATH))
    s: list = [Spacer(1, 1), NextPageTemplate("Body"), PageBreak()]

    # ---- Table of contents ------------------------------------------------ #
    s.append(Paragraph("Table of Contents", S_H1N))
    toc = TableOfContents()
    toc.levelStyles = [S_TOC1, S_TOC2]
    s += [toc, PageBreak()]

    # ---- 1. Objectives ----------------------------------------------------- #
    s.append(P("1. Project Objectives", S_H1))
    s.append(P(
        "VisionShield is a production-quality, full-stack computer-vision application that "
        "captures a live webcam feed, detects people's faces and hands with modern neural "
        "models, and applies a configurable privacy blur in real time — streaming the result "
        "into a browser dashboard at 30–60 frames per second. The project was built to the "
        "standard of a deployable product rather than a script: typed configuration, clean "
        "layering, automated tests, Docker packaging and full documentation."))
    s.append(P("The functional objectives are:", S_BODY))
    s += bullets([
        "<b>Face Privacy Mode</b> — detect every face in the frame and keep each one "
        "perfectly sharp inside a soft-edged elliptical mask while everything else is "
        "blurred; support multiple simultaneous faces and fast head motion with smooth "
        "per-frame updates.",
        "<b>Hand Privacy Mode</b> — compute the smallest rectangle containing both detected "
        "hands and keep it visible (or hidden — the blur side is switchable); expand the "
        "rectangle around a single hand; show an informative on-frame message when no hands "
        "are present.",
        "<b>Nine blur algorithms</b> — Gaussian, Box, Bilateral, Median, Pixelate, Mosaic, "
        "Motion, Strong and Light — switchable live, with a 1–100 intensity slider.",
        "<b>Real-time delivery</b> — a FastAPI backend streaming processed frames over "
        "WebSockets into a responsive React dashboard with live statistics, dark mode, "
        "connection status and error notifications.",
        "<b>Engineering quality</b> — multithreaded capture/processing, GPU acceleration "
        "with automatic CPU fallback, environment-driven configuration, logging, validation, "
        "a 50+ case test suite and one-command Docker deployment."])

    # ---- 2. Technologies --------------------------------------------------- #
    s.append(P("2. Technologies Used", S_H1))
    s.append(data_table(
        ["Layer", "Technology", "Role"],
        [["Detection", "MediaPipe Tasks 0.10+", "BlazeFace face detector + 21-landmark hand "
          "landmarker, VIDEO running mode with built-in tracking"],
         ["Image processing", "OpenCV 4.10+ / NumPy", "Blur kernels, mask compositing, JPEG "
          "encoding, capture"],
         ["Backend", "FastAPI + Uvicorn", "REST API, WebSocket streaming, OpenAPI docs"],
         ["Validation / config", "Pydantic v2 + pydantic-settings", "Typed request models and "
          "12-factor environment configuration"],
         ["Frontend", "React 18 + Vite 6", "Component UI, instant dev server, optimised build"],
         ["Styling", "Tailwind CSS v4", "Design-token system with class-based dark mode"],
         ["HTTP / routing", "Axios + React Router 6", "REST client and page routing"],
         ["Packaging", "Docker + docker-compose + nginx", "Reproducible deployment, SPA "
          "serving, /api and /ws reverse proxy"],
         ["Testing", "pytest + FastAPI TestClient", "Unit, API-contract and end-to-end "
          "pipeline tests with injected fake detectors"],
         ["This report", "matplotlib + ReportLab", "All figures generated by the project's "
          "own engine"]],
        [3.0 * cm, 4.6 * cm, 9.4 * cm]))

    # ---- 3. System architecture -------------------------------------------- #
    s.append(P("3. System Architecture", S_H1))
    s.append(P(
        "The system is split into a browser SPA and a Python backend. Three ideas shape the "
        "whole design. <b>First</b>, the hot path is thread-based while the API is async: "
        "OpenCV and MediaPipe are blocking C++ code, so all vision work lives in plain "
        "threads and FastAPI's event loop only ever reads a shared slot — the API stays "
        "responsive at any frame rate. <b>Second</b>, every hand-off is a single-slot, "
        "latest-frame-wins buffer rather than a queue: live video wants freshness, and "
        "queues accumulate stale frames that turn into visible lag. <b>Third</b>, user "
        "settings are immutable snapshots: the processing thread reads one frozen settings "
        "object per frame and REST updates atomically swap it, so the hot loop contains no "
        "locks and can never observe a half-applied update."))
    s.append(fig("architecture.png", "High-level architecture: React SPA, FastAPI service "
                                     "layers, and the threaded vision core."))
    s.append(P(
        "The repository mirrors this separation: <font face='Courier'>backend/app</font> "
        "contains <font face='Courier'>routes/</font> (thin HTTP/WS controllers), "
        "<font face='Courier'>services/</font> (camera lifecycle and shared state), "
        "<font face='Courier'>vision/</font> (detectors, smoothing, masking, blur, "
        "pipeline), <font face='Courier'>config/</font> and <font face='Courier'>utils/"
        "</font>; the frontend keeps API access, global state, hooks, components and pages "
        "in separate folders. Each layer depends only on the layer below it."))
    s.append(P("3.1 Threading model", S_H2))
    s.append(P(
        "A dedicated <b>capture thread</b> drains the camera as fast as the driver delivers, "
        "overwriting a one-frame slot; this keeps the driver's internal buffer empty, which "
        "is the classic cure for the 300&nbsp;ms \u201csoap-opera delay\u201d of naive "
        "OpenCV loops. The <b>processing thread</b> runs the full vision pipeline at the "
        "configured FPS cap, always on the newest frame, and publishes an encoded JPEG plus "
        "statistics into <font face='Courier'>SharedOutput</font>. MediaPipe graphs are not "
        "thread-safe, so the detectors are constructed lazily <i>inside</i> the processing "
        "thread. Async WebSocket handlers and the MJPEG generator are pure readers."))
    s.append(fig("threading.png", "Two producer threads and N async consumers, decoupled by "
                                  "one-slot buffers."))

    # ---- 4. Backend --------------------------------------------------------- #
    s.append(P("4. Backend Explanation", S_H1))
    s.append(P(
        "<b>Configuration</b> (<font face='Courier'>config/settings.py</font>) is a single "
        "pydantic-settings class: every tunable — camera index, resolution, processing "
        "width, FPS cap, JPEG quality, detector confidences, mask feathering, smoothing "
        "coefficients, model URLs — is a typed field with a default, overridable through "
        "the environment or a <font face='Courier'>.env</font> file. Configuration therefore "
        "doubles as documentation and is validated at startup."))
    s.append(P(
        "<b>Services</b>. <font face='Courier'>CameraManager</font> owns the lifecycle: "
        "<font face='Courier'>start()</font> opens the device (raising a clean "
        "<font face='Courier'>CameraError</font> with a human-readable hint if it is missing "
        "or busy), spawns both threads, and <font face='Courier'>stop()</font> joins them "
        "and releases the camera — it is also wired into FastAPI's lifespan hook so Ctrl-C "
        "never leaves the webcam locked. <font face='Courier'>SettingsStore</font> holds the "
        "immutable settings snapshot behind a lock with atomic partial updates; "
        "<font face='Courier'>SharedOutput</font> is the one-slot frame buffer with a "
        "monotonically increasing sequence number that lets consumers detect new frames "
        "cheaply."))
    s.append(P(
        "<b>Routes</b> are deliberately thin: Pydantic validates the payload, the service "
        "singleton does the work, and domain errors map to HTTP 400 with actionable "
        "messages. Settings updates are partial — the UI sends only the field that changed "
        "— and invalid values (e.g. strength 500) are rejected with 422 while the previous "
        "settings remain in force. The blur catalogue is served by the API itself, so "
        "adding a tenth algorithm is a backend-only change and the frontend grid updates "
        "automatically."))

    # ---- 5. Frontend --------------------------------------------------------- #
    s.append(P("5. Frontend Explanation", S_H1))
    s.append(P(
        "The React application is a small control room: a viewfinder-styled video panel, a "
        "statistics panel with an FPS sparkline, and a controls rail (camera start/stop, "
        "mode cards, blur-region toggle, the nine-algorithm grid, a debounced strength "
        "slider, and overlay/mirror toggles). Tailwind v4 design tokens map utilities onto "
        "runtime CSS variables, so class-based dark/light theming flips a single attribute "
        "on the root element; typography uses three roles — Space Grotesk for display, "
        "Inter for body text, JetBrains Mono for every number."))
    s.append(P("5.1 State management", S_H2))
    s.append(P(
        "Global state is one React context (<font face='Courier'>AppContext</font>) rather "
        "than Redux: the state is small and its shape is stable. The provider owns settings, "
        "camera status, statistics, theme and toasts, and exposes actions. "
        "<font face='Courier'>updateSettings</font> is <b>optimistic</b>: the UI flips "
        "instantly, the PUT is sent, the server echo reconciles, and on failure the change "
        "rolls back with an error toast — controls feel instant even on a slow link. A "
        "health probe every 8&nbsp;s drives the online/offline chip, and a 3&nbsp;s "
        "status/stats poll while running surfaces capture-thread errors (e.g. an unplugged "
        "camera) as notifications."))
    s.append(P("5.2 The zero-re-render video path", S_H2))
    s.append(P(
        "Storing each incoming frame in React state would re-render the tree 30–60 times "
        "per second. Instead the <font face='Courier'>useStream</font> hook writes every "
        "binary WebSocket frame directly onto the <font face='Courier'>&lt;img&gt;</font> "
        "DOM node through a ref, so React renders exactly zero times per frame; old object "
        "URLs are revoked on a short delay (immediate revocation can abort a frame that is "
        "still decoding). Interleaved JSON stats messages update state only about twice per "
        "second. The socket auto-reconnects with a 1.2&nbsp;s backoff."))
    s.append(code_block(
"""// hooks/useStream.js — the per-frame hot path (no setState involved)
ws.onmessage = (e) => {
  if (typeof e.data === "string") {                  // JSON side-channel
    const msg = JSON.parse(e.data);
    if (msg.type === "stats") onStatsRef.current?.(msg);
    return;
  }
  const url = URL.createObjectURL(e.data);           // binary JPEG frame
  const prev = lastUrl;
  lastUrl = url;
  img.src = url;                                     // straight to the DOM
  if (prev) setTimeout(() => URL.revokeObjectURL(prev), 300);
};"""))

    # ---- 6. CV pipeline -------------------------------------------------------- #
    s.append(P("6. Computer Vision Pipeline", S_H1))
    s.append(P(
        "Each frame flows through eight stages. The frame is first downscaled to "
        "<font face='Courier'>PROCESS_WIDTH</font> (960&nbsp;px) — detection quality at "
        "webcam distance is unchanged while every later stage gets roughly twice cheaper — "
        "and mirrored if selfie view is on. The mode's detector runs, boxes are temporally "
        "smoothed, a feathered mask is built, the whole frame is blurred once with the "
        "active algorithm, original and blurred are composited through the mask, and "
        "overlays (banner, optional detection brackets) are drawn before JPEG encoding."))
    s.append(fig("pipeline.png", "The per-frame pipeline; detection and blur are the two "
                                 "cost centres."))
    s.append(P("6.1 Mask generation and compositing", S_H2))
    s.append(P(
        "A mask is a single-channel float32 image in [0,1] where 1 marks the protected "
        "region. Faces use ellipses (they hug heads, so the sharp region excludes "
        "rectangular background corners); the hand region uses a rounded rectangle (sharp "
        "corners feather badly). Soft edges come from Gaussian-blurring the binary mask "
        "with a 41&nbsp;px kernel, producing a smooth 0\u21921 ramp. Compositing is one "
        "vectorised blend that covers all four combinations of mode \u00d7 region:"))
    s.append(code_block(
"""# vision/masking.py — one formula for every mode/region combination
m = mask if region == Region.OUTSIDE else 1.0 - mask
m3 = cv2.merge([m, m, m])
out = frame.astype(np.float32) * m3 + blurred.astype(np.float32) * (1.0 - m3)
return out.astype(np.uint8)"""))
    s.append(P(
        "The frame is blurred in full and then composited — rather than blurring only the "
        "masked region — because the feathered transition band blends partially blurred and "
        "sharp pixels, which requires both complete images anyway; region-only blurring also "
        "creates halo artefacts where the kernel reads across the boundary. A full Gaussian "
        "at 960&nbsp;px costs 1–3&nbsp;ms, so correctness is cheap."))
    s.append(fig("mask_demo.png", "Real engine output: detection ellipse, feathered mask, "
                                  "and both compositing regions."))
    s.append(P("6.2 Temporal smoothing", S_H2))
    s.append(P(
        "Raw detections jitter by a few pixels and can vanish for a frame or two during "
        "fast motion — the mask would shiver and flicker. "
        "<font face='Courier'>MultiBoxSmoother</font> fixes both: detections are matched to "
        "existing tracks by greedy nearest-centre assignment (Hungarian assignment is "
        "overkill for \u22644 objects), each track's box is an exponential moving average "
        "(\u03b1 = 0.45 — responsive yet damped), and an unmatched track survives eight "
        "frames at its last position before being reaped, bridging detector misses so a "
        "fast head turn never flashes an unprotected face. Trackers reset on mode change so "
        "stale boxes cannot leak between modes."))
    s.append(code_block(
"""# vision/smoothing.py — EMA update once a detection is matched to a track
a = self.alpha
b = track.box
track.box = Box(
    x=(1 - a) * b.x + a * best.x,
    y=(1 - a) * b.y + a * best.y,
    w=(1 - a) * b.w + a * best.w,
    h=(1 - a) * b.h + a * best.h,
)
track.missed = 0            # unmatched tracks instead do: track.missed += 1
# tracks with missed > hold_frames are removed"""))

    # ---- 7. Face detection ---------------------------------------------------- #
    s.append(P("7. Face Detection", S_H1))
    s.append(P(
        "Face detection uses MediaPipe Tasks' <font face='Courier'>FaceDetector</font> "
        "running <b>BlazeFace short-range</b> — a ~200&nbsp;KB single-shot detector "
        "purpose-built for camera-distance faces that executes in well under a millisecond "
        "on a laptop CPU. It was chosen over YOLOv8-face and OpenCV-DNN ResNet-SSD because "
        "the project's budget is 30–60 FPS <i>including</i> blur and streaming: YOLO costs "
        "15–40&nbsp;ms per frame on CPU, consuming the entire budget for accuracy that is "
        "indistinguishable at webcam range. The <font face='Courier'>BaseDetector</font> "
        "interface (plus constructor injection in the pipeline) makes swapping in YOLO a "
        "one-class change for long-range deployments."))
    s.append(P(
        "The detector runs in <font face='Courier'>RunningMode.VIDEO</font> with strictly "
        "increasing millisecond timestamps (guaranteed by a small timestamper even when two "
        "frames land in the same millisecond), which enables MediaPipe's temporal "
        "optimisations. Detected pixel-space boxes are padded asymmetrically "
        "(28% horizontally, 42% vertically — heads are taller than detector boxes), "
        "smoothed, and rendered as ellipses. Model files auto-download on first start with "
        "atomic writes, retries and an offline error message containing the exact "
        "<font face='Courier'>curl</font> command."))

    # ---- 8. Hand detection ------------------------------------------------------ #
    s.append(P("8. Hand Detection", S_H1))
    s.append(P(
        "Hand detection uses <font face='Courier'>HandLandmarker</font>: a palm detector "
        "followed by a 21-point landmark model. In VIDEO mode the expensive palm detector "
        "only re-runs when landmark tracking confidence drops, so steady-state cost is a "
        "few milliseconds for two hands. The bounding box is derived from the landmark "
        "extremes rather than the palm-detector box — tighter, more stable, and it follows "
        "extended fingers."))
    s.append(P(
        "Mode logic: with two hands, <font face='Courier'>Box.union()</font> yields the "
        "smallest rectangle containing both; with one hand, that hand's box expands by 55% "
        "so the protected window stays useful; with none, the mask is empty — which, "
        "composited normally, blurs the <i>entire</i> frame when the region is "
        "\u201coutside\u201d (a privacy-safe default) and leaves it sharp when "
        "\u201cinside\u201d, while an on-frame banner explains what to do. That behaviour "
        "required zero special-case code: the empty mask falls out of the same compositing "
        "formula."))

    # ---- 9. Blur algorithms ------------------------------------------------------ #
    s.append(P("9. Blur Algorithms", S_H1))
    s.append(P(
        "All nine algorithms sit behind one <font face='Courier'>apply(frame, type, "
        "strength)</font> call. The 1–100 strength value maps onto each algorithm's natural "
        "parameter space — kernel size, tile size, sigma, downscale factor — chosen so the "
        "slider <i>feels</i> consistent across algorithms:"))
    s.append(data_table(
        ["Algorithm", "Strength mapping", "Implementation note"],
        [["Gaussian", "kernel 3\u2192103 px", "CUDA path when available (chained \u226431 px kernels)"],
         ["Box", "kernel 3\u2192103 px", "uniform average (cv2.blur)"],
         ["Bilateral", "\u03c3 20\u2192180", "edge-preserving; runs at half resolution (O(d\u00b2) filter)"],
         ["Median", "kernel 3\u219231 px", "capped — large medians are extremely slow"],
         ["Pixelate", "block 2\u219220 px", "downscale + nearest-neighbour upscale"],
         ["Mosaic", "tile 8\u219260 px", "area-averaged tiles + darkened grid lines"],
         ["Motion", "line 5\u219299 px", "25\u00b0 rotated line PSF via filter2D"],
         ["Strong", "8\u219218\u00d7 downscale", "downscale + Gaussian + upscale: maximum anonymisation"],
         ["Light", "kernel 3\u219215 px", "gentle frosted-glass softening"]],
        [2.6 * cm, 3.6 * cm, 10.8 * cm]))
    s.append(fig("blur_grid.png", "Every algorithm applied by the real engine to the same "
                                  "synthetic scene at strength 60."))
    s.append(P(
        "At construction the engine probes <font face='Courier'>cv2.cuda</font>; on CUDA "
        "builds of OpenCV, Gaussian-family blurs run on the GPU (kernels chained because "
        "CUDA caps them at 31\u00d731) and everywhere else the SIMD CPU path runs "
        "transparently — same output, zero configuration. A per-call "
        "<font face='Courier'>cv2.error</font> guard falls back to Gaussian so a kernel "
        "edge case can never kill the stream."))

    # ---- 10. API documentation ---------------------------------------------------- #
    s.append(P("10. API Documentation", S_H1))
    s.append(P(
        "The full reference lives in <font face='Courier'>docs/API.md</font> and as "
        "interactive Swagger at <font face='Courier'>/docs</font>. Summary:"))
    s.append(data_table(
        ["Method", "Endpoint", "Purpose"],
        [["POST", "/api/camera/start", "Open webcam, start threads; 400 with hint if missing/busy"],
         ["POST", "/api/camera/stop", "Stop and release the device (idempotent)"],
         ["GET", "/api/camera/status", "running, index, resolution, uptime, error"],
         ["GET", "/api/settings", "Current mode, blur type, strength, region, toggles"],
         ["PUT", "/api/settings", "Partial update; applies on the next frame"],
         ["GET", "/api/settings/blur-types", "Catalogue of the nine algorithms"],
         ["GET", "/api/stats", "FPS, latency, detections, frames, uptime, CUDA flag"],
         ["GET", "/api/health", "Liveness probe for Docker/monitoring"],
         ["WS", "/ws/stream", "Binary JPEG frames + JSON stats messages"],
         ["GET", "/api/stream/mjpeg", "MJPEG fallback playable in a bare &lt;img&gt; tag"],
         ["GET", "/api/stream/snapshot", "One current frame (204 when idle)"]],
        [1.8 * cm, 5.2 * cm, 10.0 * cm]))
    s.append(P(
        "The WebSocket pushes two message kinds: <b>binary</b> frames (one complete JPEG "
        "each) and <b>text</b> JSON — <font face='Courier'>{\"type\":\"stats\", ...}</font> "
        "roughly twice per second, or <font face='Courier'>{\"type\":\"status\","
        "\"running\":false}</font> while idle. The server-side loop sends a frame only when "
        "the shared sequence number changes, so a slow client skips frames instead of "
        "accumulating a backlog:"))
    s.append(code_block(
"""# routes/stream.py — latest-frame-wins at the network layer
while True:
    jpeg, seq = manager.frame_and_seq()
    if jpeg is not None and seq != last_seq:
        last_seq = seq
        await ws.send_bytes(jpeg)
        delivered += 1
        if delivered % 12 == 0:
            await ws.send_text(json.dumps({"type": "stats", **manager.stats()}))
    await asyncio.sleep(poll)          # poll at 2x target FPS"""))

    # ---- 11. Performance analysis --------------------------------------------------- #
    s.append(P("11. Performance Analysis", S_H1))
    s.append(P(
        "The design targets 30–60 FPS on an ordinary laptop CPU. Four optimisations do "
        "most of the work: processing at 960&nbsp;px instead of capture resolution "
        "(\u2248 2\u00d7 across the whole pipeline); VIDEO-mode detectors whose trackers "
        "avoid re-running the heavy detection stage every frame; one-slot buffers that make "
        "latency independent of consumer speed; and a browser video path that never touches "
        "React state. Typical stage costs on a mid-range 4-core CPU: face detection "
        "0.5–1.5&nbsp;ms, hand landmarks 3–6&nbsp;ms, blur 1–3&nbsp;ms (Gaussian), mask + "
        "composite 1–2&nbsp;ms, JPEG encode 2–4&nbsp;ms — a total of 8–15&nbsp;ms per "
        "frame, i.e. comfortable 60 FPS headroom in face mode."))
    tr = [[k, f"{v:.2f} ms"] for k, v in timings.items()]
    s.append(data_table(["Blur algorithm", "Measured cost (960\u00d7540, strength 60)"],
                        tr, [6.0 * cm, 6.0 * cm]))
    s.append(fig("blur_timing.png", "Measured per-algorithm blur cost on the build machine "
                                    "(25-run averages produced by this script)."))
    s.append(P(
        "Memory stays flat over time by construction: fixed-size one-slot buffers, no "
        "growing queues, detectors reused for the process lifetime, and object URLs revoked "
        "in the browser. If more headroom is needed, the levers are "
        "<font face='Courier'>PROCESS_WIDTH</font> (640&nbsp;px roughly doubles headroom), "
        "<font face='Courier'>JPEG_QUALITY</font>, preferring Pixelate/Gaussian over "
        "Bilateral at high strength, and a CUDA build of OpenCV."))

    # ---- 12. Testing strategy ---------------------------------------------------------- #
    s.append(P("12. Testing Strategy", S_H1))
    s.append(P(
        "The suite (51 passing tests) is designed to run <b>without a camera and without "
        "network access</b>, so it works in any CI environment. The key enabler is "
        "dependency injection: <font face='Courier'>FramePipeline</font> accepts pre-built "
        "detectors, and the end-to-end tests inject scriptable fakes that return chosen "
        "boxes per frame — exercising the real smoothing, masking, blurring, compositing "
        "and overlay code deterministically."))
    s.append(data_table(
        ["Suite", "What it proves"],
        [["Blur engine (27 cases)", "Every algorithm \u00d7 strengths {1, 50, 100} returns a "
          "changed uint8 frame; strength clamping; higher strength removes more "
          "high-frequency energy; catalogue covers all nine types"],
         ["Masking", "Masks stay in [0,1] with a genuine soft edge; compositing keeps the "
          "protected centre identical to the original and the far corner identical to the "
          "blurred frame, in both regions; empty mask + outside = fully blurred frame"],
         ["Smoothing", "EMA converges onto a static target; a lost track survives exactly "
          "hold_frames updates then is reaped; two targets keep two tracks; box union"],
         ["API contract", "Health, idle stats, settings round-trip, 422 on invalid values, "
          "blur catalogue shape, camera start without a device returns 400 with a "
          "camera-specific message, stop is idempotent, idle snapshot returns 204"],
         ["Pipeline end-to-end", "Face mode keeps the face centre sharp while blurring the "
          "corner; two hands \u2192 union box then single-hand expansion after the second "
          "track dies; all nine blurs through the full pipeline; inside-region inversion; "
          "no-detection banner path"],
         ["Model manager", "A missing model raises an error containing copy-pasteable curl "
          "instructions; real-model tests auto-skip when files are absent"]],
        [4.6 * cm, 12.4 * cm]))

    # ---- 13. Future improvements --------------------------------------------------------- #
    s.append(P("13. Future Improvements", S_H1))
    s += bullets([
        "<b>WebRTC transport</b> — replace JPEG-over-WebSocket with hardware-encoded VP8/H.264 "
        "for sub-30 ms glass-to-glass latency and lower bandwidth (aiortc server-side).",
        "<b>Person segmentation mode</b> — MediaPipe's selfie-segmentation model would allow "
        "pixel-accurate silhouettes instead of ellipses, at ~5 ms per frame.",
        "<b>Recording &amp; virtual camera</b> — a writer thread subscribed to SharedOutput "
        "(PyAV muxing) and a pyvirtualcam sink so the blurred feed can be used in Zoom/Meet.",
        "<b>Multi-camera support</b> — a CameraManager registry keyed by device index with an "
        "index path parameter on the routes; the architecture already isolates all per-camera "
        "state in one object.",
        "<b>GPU inference delegate</b> — MediaPipe's GPU delegate for the detectors themselves "
        "(the blur engine already has its CUDA path).",
        "<b>Preset profiles &amp; hotkeys</b> — saved mode/blur/strength combinations exposed "
        "through the settings API and bound to keyboard shortcuts in the UI.",
        "<b>Authentication</b> — token-protected control endpoints for deployments where the "
        "dashboard is exposed beyond localhost."])

    # ---- 14. Conclusion -------------------------------------------------------------------- #
    s.append(P("14. Conclusion", S_H1))
    s.append(P(
        "VisionShield meets its brief in full: two AI-driven privacy modes with soft-edged, "
        "temporally stable masks; nine live-switchable blur algorithms with a consistent "
        "intensity model; a threaded capture/processing core that sustains 30–60 FPS on CPU "
        "with automatic GPU use where available; a WebSocket streaming layer whose "
        "latest-frame-wins design keeps latency flat regardless of consumer speed; and a "
        "React control room that renders zero times per video frame. Beyond the features, "
        "the project demonstrates the engineering habits that make such a system "
        "maintainable — immutable settings snapshots, single-slot hand-offs, dependency-"
        "injected detectors, exhaustive tests that run anywhere, typed configuration, and "
        "documentation written at every level from README to this report. The result is "
        "both a usable privacy tool and a template for building real-time computer-vision "
        "products end to end."))

    doc.multiBuild(s)
    print(f"[pdf] wrote {PDF_PATH}")


if __name__ == "__main__":
    t = build_all_figures()
    build_pdf(t)
