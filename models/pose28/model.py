"""
model.py
--------
Two-phase SketchPadModel:
  Phase 1: User uploads their sketch    → saves keypoints + overlay to disk
  Phase 2: User uploads reference sketch → compares keypoints, returns
                                           similarity score + per-limb feedback

Session state is persisted to disk so it survives the subprocess-per-call
execution model used by runner.py.
"""

import logging
import math
import os
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw
from typing import Optional

# ── Logging (never touches stdout — runner.py owns that) ─────────────────────
logging.basicConfig(
    filename=os.path.join(tempfile.gettempdir(), "sketchpad.log"),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)
logging.getLogger("PIL").setLevel(logging.WARNING)
_log = logging.getLogger("sketchpad")

# ── Model paths ───────────────────────────────────────────────────────────────
BASE       = os.path.dirname(__file__)
MODELS_DIR = os.path.join(BASE, "sketch2pose_models")
HRNET_PATH = os.path.join(MODELS_DIR, "hrn_w48_384x288.onnx")

# ── Session storage directory ─────────────────────────────────────────────────
SESSION_DIR = os.path.join(tempfile.gettempdir(), "sketchpad_sessions")
os.makedirs(SESSION_DIR, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────────────
HRNET_IMG_SIZE = (288, 384)
HRNET_MEAN     = np.array([0.485, 0.456, 0.406], dtype=np.float32)
HRNET_STD      = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# KPS index reference:
# 0=Head,  1=Neck,
# 2=RShoulder, 3=RArm, 4=RHand,
# 5=LShoulder, 6=LArm, 7=LHand,
# 8=Spine, 9=Hips,
# 10=RUpperLeg, 11=RLeg, 12=RFoot,
# 13=LUpperLeg, 14=LLeg, 15=LFoot,
# 16=LToe, 17=RToe
KPS = (
    "Head", "Neck",
    "Right Shoulder", "Right Arm", "Right Hand",
    "Left Shoulder",  "Left Arm",  "Left Hand",
    "Spine", "Hips",
    "Right Upper Leg", "Right Leg", "Right Foot",
    "Left Upper Leg",  "Left Leg",  "Left Foot",
    "Left Toe", "Right Toe",
)

SKELETON = (
    (0,1),(1,8),(8,9),(9,10),(9,13),
    (10,11),(11,12),(13,14),(14,15),
    (1,2),(2,3),(3,4),(1,5),(5,6),(6,7),
    (15,16),(12,17),
)

# Limb groups: name → joint indices (root to tip)
LIMB_GROUPS = {
    "right arm":  [2, 3, 4],    # RShoulder → RArm → RHand
    "left arm":   [5, 6, 7],    # LShoulder → LArm → LHand
    "right leg":  [10, 11, 12], # RUpperLeg → RLeg → RFoot
    "left leg":   [13, 14, 15], # LUpperLeg → LLeg → LFoot
    "torso":      [9, 8, 1],    # Hips → Spine → Neck
    "head":       [1, 0],       # Neck → Head
}


# ════════════════════════════════════════════════════════════════════════════
# Session state — fixed file paths, no session IDs needed
# Phase 1 saves to these files; Phase 2 loads, compares, then deletes them.
# ════════════════════════════════════════════════════════════════════════════

SKETCH_KPS     = os.path.join(SESSION_DIR, "sketch_kps.npy")
SKETCH_OVERLAY = os.path.join(SESSION_DIR, "sketch_overlay.png")


def _has_sketch() -> bool:
    return os.path.exists(SKETCH_KPS)


def _save_sketch(kps: np.ndarray, overlay: Image.Image):
    np.save(SKETCH_KPS, kps)
    overlay.save(SKETCH_OVERLAY)


def _load_sketch() -> tuple:
    kps     = np.load(SKETCH_KPS)
    overlay = Image.open(SKETCH_OVERLAY).copy()
    return kps, overlay


def _clear_sketch():
    for p in [SKETCH_KPS, SKETCH_OVERLAY]:
        if os.path.exists(p):
            os.remove(p)


# ════════════════════════════════════════════════════════════════════════════
# HRNet helpers
# ════════════════════════════════════════════════════════════════════════════

def _get_3rd_point(a, b):
    d = a - b
    return b + np.array([-d[1], d[0]], dtype=np.float32)

def _get_dir(src, rot_rad):
    sn, cs = np.sin(rot_rad), np.cos(rot_rad)
    return [src[0]*cs - src[1]*sn, src[0]*sn + src[1]*cs]

def _affine_transform(pt, t):
    return np.dot(t, np.array([pt[0], pt[1], 1.0]))[:2]

def _get_affine_transform(center, scale, rot, output_size, inv=0, pixel_std=200):
    if not isinstance(scale, np.ndarray):
        scale = np.array([scale, scale])
    scale_tmp = scale * pixel_std
    src_w     = scale_tmp[0]
    dst_w, dst_h = output_size
    rot_rad   = np.pi * rot / 180
    src_dir   = _get_dir([0, src_w * -0.5], rot_rad)
    dst_dir   = np.array([0, dst_w * -0.5], np.float32)
    src = np.zeros((3, 2), dtype=np.float32)
    dst = np.zeros((3, 2), dtype=np.float32)
    src[0] = center
    src[1] = center + src_dir
    dst[0] = [dst_w * 0.5, dst_h * 0.5]
    dst[1] = np.array([dst_w * 0.5, dst_h * 0.5]) + dst_dir
    src[2] = _get_3rd_point(src[0], src[1])
    dst[2] = _get_3rd_point(dst[0], dst[1])
    if inv:
        return cv2.getAffineTransform(np.float32(dst), np.float32(src))
    return cv2.getAffineTransform(np.float32(src), np.float32(dst))

def _transform_preds(coords, center, scale, output_size):
    target = np.zeros_like(coords)
    trans  = _get_affine_transform(center, scale, 0, output_size, inv=1)
    for p in range(coords.shape[0]):
        target[p, :2] = _affine_transform(coords[p, :2], trans)
    return target

def _get_max_preds(heatmaps):
    B, J, H, W = heatmaps.shape
    flat  = heatmaps.reshape(B, J, -1)
    idx   = np.argmax(flat, 2).reshape(B, J, 1)
    maxv  = np.amax(flat, 2).reshape(B, J, 1)
    preds = np.tile(idx, (1,1,2)).astype(np.float32)
    preds[:,:,0] = preds[:,:,0] % W
    preds[:,:,1] = np.floor(preds[:,:,1] / W)
    preds *= np.tile(maxv > 0.0, (1,1,2)).astype(np.float32)
    return preds, maxv

def _get_final_preds(heatmaps, center, scale):
    coords, maxvals = _get_max_preds(heatmaps)
    H, W = heatmaps.shape[2], heatmaps.shape[3]
    for n in range(coords.shape[0]):
        for p in range(coords.shape[1]):
            hm = heatmaps[n][p]
            px = int(math.floor(coords[n][p][0] + 0.5))
            py = int(math.floor(coords[n][p][1] + 0.5))
            if 1 < px < W-1 and 1 < py < H-1:
                diff = np.array([hm[py][px+1]-hm[py][px-1],
                                 hm[py+1][px]-hm[py-1][px]])
                coords[n][p] += np.sign(diff) * 0.25
    preds = coords.copy()
    for i in range(coords.shape[0]):
        preds[i] = _transform_preds(coords[i], center[i], scale[i], [W, H])
    return preds, maxvals

def _hrnet_preprocess(img_bgr, pixel_std=200):
    h, w   = img_bgr.shape[:2]
    c      = np.array([w/2, h/2], dtype=np.float32)
    aspect = HRNET_IMG_SIZE[0] / HRNET_IMG_SIZE[1]
    if w > aspect * h:   h = w / aspect
    elif w < aspect * h: w = h * aspect
    s     = np.array([w/pixel_std, h/pixel_std], dtype=np.float32) * 1.25
    trans = _get_affine_transform(c, s, 0, HRNET_IMG_SIZE)
    inp   = cv2.warpAffine(img_bgr, trans, HRNET_IMG_SIZE, flags=cv2.INTER_LINEAR)
    inp   = (inp.astype(np.float32)/255.0 - HRNET_MEAN) / HRNET_STD
    return np.transpose(inp, (2,0,1))[None], c, s


# ════════════════════════════════════════════════════════════════════════════
# Similarity score & per-limb feedback
# ════════════════════════════════════════════════════════════════════════════

def _norm_kps(k: np.ndarray) -> np.ndarray:
    """Centre on hips, normalise by torso height."""
    k = k.astype(float)
    k = k - k[9:10]
    torso = np.linalg.norm(k[1] - k[9]) + 1e-6
    return k / torso


def _err_to_score(err: float) -> float:
    """Piecewise nonlinear mapping: alignment error → 0-100 score."""
    if err < 0.35:
        score = 90.0 + (0.35 - err) / 0.35 * 10.0
    elif err < 0.60:
        score = 60.0 + (0.60 - err) / 0.25 * 30.0
    elif err < 0.80:
        score = 20.0 + (0.80 - err) / 0.20 * 40.0
    else:
        score = max(0.0, 20.0 - (err - 0.80) * 50.0)
    return float(np.clip(score, 0.0, 100.0))


def _limb_err(a_norm: np.ndarray, b_norm: np.ndarray, indices: list) -> float:
    """Mean joint distance for a limb subset, after local centering."""
    sa = a_norm[indices] - a_norm[indices][0:1]
    sb = b_norm[indices] - b_norm[indices][0:1]
    scale = max(np.sqrt((sa**2).sum()), np.sqrt((sb**2).sum()), 1e-6)
    return float(np.mean(np.linalg.norm(sa/scale - sb/scale, axis=1)))


def _elevation_label(dy: float) -> str:
    """dy = tip_y - root_y in image coords (y increases downward)."""
    if dy < -0.3:  return "raised high"
    if dy < -0.05: return "raised"
    if dy <  0.05: return "horizontal"
    if dy <  0.3:  return "lowered"
    return "pointing down"


def _limb_feedback(limb: str, ref_kps: np.ndarray, user_kps: np.ndarray,
                   indices: list) -> Optional[str]:
    """Return a feedback string for one limb, or None if it looks good."""
    r = ref_kps[indices].astype(float)
    u = user_kps[indices].astype(float)

    diff_dy = (u[-1] - u[0])[1] - (r[-1] - r[0])[1]
    diff_dx = (u[-1] - u[0])[0] - (r[-1] - r[0])[0]
    messages = []

    if abs(diff_dy) > 0.15:
        direction = "lower" if diff_dy > 0 else "higher"
        amount    = "much" if abs(diff_dy) > 0.35 else "slightly"
        messages.append(
            f"should be {_elevation_label((r[-1]-r[0])[1])} — move it {amount} {direction}"
        )

    if abs(diff_dx) > 0.15:
        direction = "more to the left" if diff_dx > 0 else "more to the right"
        amount    = "much" if abs(diff_dx) > 0.35 else "slightly"
        messages.append(f"extend it {amount} {direction}")

    if len(indices) == 3:
        def _angle(pts):
            v1 = pts[0] - pts[1]
            v2 = pts[2] - pts[1]
            n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
            if n1 < 1e-6 or n2 < 1e-6:
                return 180.0
            return float(np.degrees(
                np.arccos(np.clip(np.dot(v1/n1, v2/n2), -1, 1))
            ))
        diff_angle = _angle(u) - _angle(r)
        if abs(diff_angle) > 20:
            bend_dir = "less" if diff_angle > 0 else "more"
            amount   = "significantly" if abs(diff_angle) > 40 else "slightly"
            messages.append(f"bend it {amount} {bend_dir}")

    if not messages:
        return None
    return f"  • {limb.capitalize()}: " + ", and ".join(messages) + "."


def _generate_feedback(ref_kps: np.ndarray, user_kps: np.ndarray) -> str:
    """Generate full per-limb feedback comparing user sketch to reference."""
    ref_n  = _norm_kps(ref_kps)
    user_n = _norm_kps(user_kps)

    limb_scores = {}
    for limb, idx in LIMB_GROUPS.items():
        err = _limb_err(ref_n, user_n, idx)
        limb_scores[limb] = (err, _err_to_score(err))

    sorted_limbs = sorted(limb_scores.items(), key=lambda x: x[1][1])

    issues, praise = [], []
    for limb, (err, score) in sorted_limbs:
        if score >= 80:
            praise.append(limb)
        else:
            msg = _limb_feedback(limb, ref_kps, user_kps, LIMB_GROUPS[limb])
            if msg:
                issues.append((score, msg))

    lines = []
    if praise:
        lines.append(f"✓ Looking good: {', '.join(praise)}.")
    if issues:
        lines.append("✗ Needs adjustment:")
        for _, msg in issues[:3]:
            lines.append(msg)
    else:
        lines.append("Great overall pose match!")

    return "\n".join(lines)


def _similarity_score_2d(kps_a: np.ndarray, kps_b: np.ndarray) -> float:
    from scipy.spatial import procrustes

    a = _norm_kps(kps_a.copy())
    b = _norm_kps(kps_b.copy())
    a /= np.sqrt((a**2).sum()) + 1e-6
    b /= np.sqrt((b**2).sum()) + 1e-6

    try:
        _, a_al, b_al = procrustes(a, b)
        per_joint_err = np.linalg.norm(a_al - b_al, axis=1)
    except Exception as e:
        _log.warning(f"Procrustes failed: {e}, falling back to direct comparison")
        per_joint_err = np.linalg.norm(a - b, axis=1)

    p50 = float(np.percentile(per_joint_err, 50))
    p90 = float(np.percentile(per_joint_err, 90))
    err = 0.5 * p50 + 0.5 * p90
    _log.debug(f"similarity p50={p50:.4f} p90={p90:.4f} err={err:.4f}")

    score = _err_to_score(err)
    if not (0.0 <= score <= 100.0):
        _log.warning(f"bad score {score}, clamping to 0")
        score = 0.0
    return round(score, 1)


def _score_label(score: float) -> str:
    if score >= 85: return "excellent match"
    if score >= 70: return "good match"
    if score >= 55: return "fair match"
    if score >= 40: return "needs work"
    return "very different"


# ════════════════════════════════════════════════════════════════════════════
# Visualisation
# ════════════════════════════════════════════════════════════════════════════

def _draw_skeleton(img_pil: Image.Image, kps: np.ndarray,
                   color_bone=(0, 180, 255),
                   color_joint=(255, 60, 60)) -> Image.Image:
    out  = img_pil.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    W, H = out.size
    r    = max(4, int(max(W, H) * 0.012))
    for i, j in SKELETON:
        a, b = kps[i], kps[j]
        draw.line([float(a[0]), float(a[1]), float(b[0]), float(b[1])],
                  fill=color_bone, width=max(2, r // 2))
    for pt in kps:
        x, y = float(pt[0]), float(pt[1])
        draw.ellipse([x-r, y-r, x+r, y+r], fill=color_joint, outline=(0,0,0))
    return out


# ════════════════════════════════════════════════════════════════════════════
# SketchPadModel
# ════════════════════════════════════════════════════════════════════════════

class SketchPadModel:
    """
    Phase 1 — upload sketch:    runs HRNet, saves 2D keypoints + overlay to disk.
    Phase 2 — upload reference: loads Phase 1 data, runs HRNet on reference,
                                 compares keypoints, returns score + feedback.
    """

    def __init__(self):
        _log.info("Loading HRNet")
        self.model_hrnet = cv2.dnn.readNetFromONNX(HRNET_PATH)
        # Uncomment for GPU acceleration on T4:
        # self.model_hrnet.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        # self.model_hrnet.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
        _log.info("HRNet ready")

    @staticmethod
    def _to_bgr(img: Image.Image) -> np.ndarray:
        return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

    def _run(self, img: Image.Image) -> tuple:
        """Returns (kps (18,2), overlay PIL Image)."""
        bgr = self._to_bgr(img)
        blob, c, s = _hrnet_preprocess(bgr)
        self.model_hrnet.setInput(blob)
        heatmaps = self.model_hrnet.forward()
        kps, _   = _get_final_preds(heatmaps, c[None], s[None])
        kps      = kps.squeeze(0)   # (18, 2)
        overlay  = _draw_skeleton(img, kps)
        return kps, overlay

    def process(self, image: Optional[Image.Image], prompt: str) -> dict:
        if not _has_sketch():
            # ── Phase 1: no sketch on disk yet ───────────────────────────
            if image is None:
                return {
                    "text":  "Upload your sketch to get started.",
                    "image": None,
                }
            _log.info("Phase 1: running inference on sketch")
            kps, overlay = self._run(image)
            _save_sketch(kps, overlay)
            return {
                "text":  "✅ Sketch saved! Now upload your reference sketch.",
                "image": overlay,
            }

        else:
            # ── Phase 2: sketch exists, waiting for reference ─────────────
            if image is None:
                _, sk_overlay = _load_sketch()
                return {
                    "text":  "Now upload your reference sketch to compare.",
                    "image": sk_overlay,
                }
            _log.info("Phase 2: running inference on reference")
            kps, overlay  = self._run(image)
            sk_kps, _     = _load_sketch()
            score         = round(float(_similarity_score_2d(sk_kps, kps)), 1)
            feedback      = _generate_feedback(sk_kps, kps)
            _log.info(f"Similarity score: {score}%")
            _log.debug(f"Feedback: {feedback}")
            _clear_sketch()
            return {
                "text":  (
                    f"✅ Pose similarity: {score}% — {_score_label(score)}\n\n"
                    f"{feedback}"
                ),
                "image": overlay,
            }


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sketch_path = sys.argv[1] if len(sys.argv) > 1 else "test.png"
    ref_path    = sys.argv[2] if len(sys.argv) > 2 else sketch_path

    model = SketchPadModel()

    print("=== Phase 1: sketch ===")
    r1 = model.process(Image.open(sketch_path), "")
    print(r1["text"])

    print("\n=== Phase 2: reference ===")
    r2 = model.process(Image.open(ref_path), "")
    print(r2["text"])
    r2["image"].save("comparison.png")
    print("Saved comparison.png")
