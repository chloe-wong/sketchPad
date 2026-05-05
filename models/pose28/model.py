"""
model.py
--------
Two-phase SketchPadModel:
  Phase 1: User uploads their sketch    → saves coordinates, shows overlay
  Phase 2: User uploads reference sketch → shows side-by-side overlay
                                           + similarity score banner

Session state is persisted to disk (tmp JSON + numpy files) so it survives
the subprocess-per-call execution model used by runner.py.
"""

import logging
import math
import os
import tempfile

import cv2
import numpy as np
import torch
import torch.nn as nn
from PIL import Image, ImageDraw
from typing import Optional

# ── Logging (never touches stdout — runner.py owns that) ─────────────────────
logging.basicConfig(
    filename=os.path.join(tempfile.gettempdir(), "sketchpad.log"),
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)
_log = logging.getLogger("sketchpad")

# ── Model paths ───────────────────────────────────────────────────────────────
BASE       = os.path.dirname(__file__)
MODELS_DIR = os.path.join(BASE, "sketch2pose_models")
HRNET_PATH = os.path.join(MODELS_DIR, "hrn_w48_384x288.onnx")
SPIN_PATH  = os.path.join(MODELS_DIR, "spin_model_smplx_eft_18.pt")
SMPL_MEAN  = os.path.join(MODELS_DIR, "data", "smpl_mean_params.npz")

# ── Session storage directory ─────────────────────────────────────────────────
SESSION_DIR = os.path.join(tempfile.gettempdir(), "sketchpad_sessions")
os.makedirs(SESSION_DIR, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────────────
IMG_RES        = 224
HRNET_IMG_SIZE = (288, 384)
HRNET_MEAN     = np.array([0.485, 0.456, 0.406], dtype=np.float32)
HRNET_STD      = np.array([0.229, 0.224, 0.225], dtype=np.float32)
SPIN_MEAN      = np.array([0.485, 0.456, 0.406], dtype=np.float32)
SPIN_STD       = np.array([0.229, 0.224, 0.225], dtype=np.float32)

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

SPIN_JOINT_NAMES = (
    "Hips","Left Upper Leg","Right Upper Leg","Spine",
    "Left Leg","Right Leg","Spine1",
    "Left Foot","Right Foot","Thorax",
    "Left Toe","Right Toe","Neck",
    "Left Shoulder","Right Shoulder","Head",
    "Left ForeArm","Right ForeArm",
    "Left Arm","Right Arm",
    "Left Hand","Right Hand",
)

PE_KSP_TO_SPIN = {
    "Head":"Head","Neck":"Neck",
    "Right Shoulder":"Right ForeArm","Right Arm":"Right Arm","Right Hand":"Right Hand",
    "Left Shoulder":"Left ForeArm","Left Arm":"Left Arm","Left Hand":"Left Hand",
    "Spine":"Spine1","Hips":"Hips",
    "Right Upper Leg":"Right Upper Leg","Right Leg":"Right Leg","Right Foot":"Right Foot",
    "Left Upper Leg":"Left Upper Leg","Left Leg":"Left Leg","Left Foot":"Left Foot",
    "Left Toe":"Left Toe","Right Toe":"Right Toe",
}

PARENTS   = [-1,0,0,0,1,2,3,4,5,6,7,8,9,9,9,12,13,14,16,17,18,19]
BONE_LENS = [0,0.10,0.10,0.13,0.40,0.40,0.12,0.40,0.40,0.12,
             0.10,0.10,0.15,0.15,0.15,0.13,0.27,0.27,0.27,0.27,0.18,0.18]


# ════════════════════════════════════════════════════════════════════════════
# Session state — fixed file paths, no session IDs needed
# Phase 1 saves to these files; Phase 2 loads, compares, then deletes them.
# ════════════════════════════════════════════════════════════════════════════

SKETCH_JOINTS  = os.path.join(SESSION_DIR, "sketch_joints.npy")
SKETCH_KPS     = os.path.join(SESSION_DIR, "sketch_kps.npy")
SKETCH_OVERLAY = os.path.join(SESSION_DIR, "sketch_overlay.png")


def _has_sketch() -> bool:
    return os.path.exists(SKETCH_JOINTS)


def _save_sketch(joints_3d: np.ndarray, kps: np.ndarray, overlay: Image.Image):
    np.save(SKETCH_JOINTS, joints_3d)
    np.save(SKETCH_KPS, kps)
    overlay.save(SKETCH_OVERLAY)


def _load_sketch() -> tuple:
    joints  = np.load(SKETCH_JOINTS)
    kps     = np.load(SKETCH_KPS)
    overlay = Image.open(SKETCH_OVERLAY).copy()
    return joints, kps, overlay


def _clear_sketch():
    for p in [SKETCH_JOINTS, SKETCH_KPS, SKETCH_OVERLAY]:
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
# SPIN / HMR
# ════════════════════════════════════════════════════════════════════════════

def _rot6d_to_rotmat(x):
    x  = x.view(-1, 3, 2)
    a1, a2 = x[:,:,0], x[:,:,1]
    b1 = nn.functional.normalize(a1)
    b2 = nn.functional.normalize(
        a2 - torch.einsum("bi,bi->b", b1, a2).unsqueeze(-1) * b1)
    b3 = torch.cross(b1, b2, dim=1)  # compatible with all PyTorch versions
    return torch.stack((b1, b2, b3), dim=-1)

class _Bottleneck(nn.Module):
    expansion = 4
    def __init__(self, inplanes, planes, stride=1, downsample=None):
        super().__init__()
        self.conv1 = nn.Conv2d(inplanes, planes, 1, bias=False)
        self.bn1   = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, 3, stride=stride, padding=1, bias=False)
        self.bn2   = nn.BatchNorm2d(planes)
        self.conv3 = nn.Conv2d(planes, planes*4, 1, bias=False)
        self.bn3   = nn.BatchNorm2d(planes*4)
        self.relu  = nn.ReLU(inplace=True)
        self.downsample = downsample
    def forward(self, x):
        r   = x
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.relu(self.bn2(self.conv2(out)))
        out = self.bn3(self.conv3(out))
        if self.downsample: r = self.downsample(x)
        return self.relu(out + r)

class _HMR(nn.Module):
    def __init__(self, smpl_mean_params):
        super().__init__()
        self.inplanes = 64
        npose = 144
        self.conv1   = nn.Conv2d(3, 64, 7, stride=2, padding=3, bias=False)
        self.bn1     = nn.BatchNorm2d(64)
        self.relu    = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(3, stride=2, padding=1)
        self.layer1  = self._make_layer(_Bottleneck, 64,  3)
        self.layer2  = self._make_layer(_Bottleneck, 128, 4, stride=2)
        self.layer3  = self._make_layer(_Bottleneck, 256, 6, stride=2)
        self.layer4  = self._make_layer(_Bottleneck, 512, 3, stride=2)
        self.avgpool = nn.AvgPool2d(7, stride=1)
        self.fc1     = nn.Linear(2048+npose+10+3, 1024)
        self.drop1   = nn.Dropout()
        self.fc2     = nn.Linear(1024, 1024)
        self.drop2   = nn.Dropout()
        self.decpose  = nn.Linear(1024, npose)
        self.decshape = nn.Linear(1024, 10)
        self.deccam   = nn.Linear(1024, 3)
        nn.init.xavier_uniform_(self.decpose.weight,  gain=0.01)
        nn.init.xavier_uniform_(self.decshape.weight, gain=0.01)
        nn.init.xavier_uniform_(self.deccam.weight,   gain=0.01)
        mean = np.load(smpl_mean_params)
        self.register_buffer("init_pose",  torch.from_numpy(mean["pose"][:]).unsqueeze(0))
        self.register_buffer("init_shape", torch.from_numpy(mean["shape"][:].astype("float32")).unsqueeze(0))
        self.register_buffer("init_cam",   torch.from_numpy(mean["cam"]).unsqueeze(0))

    def _make_layer(self, block, planes, blocks, stride=1):
        ds = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            ds = nn.Sequential(
                nn.Conv2d(self.inplanes, planes*block.expansion, 1, stride=stride, bias=False),
                nn.BatchNorm2d(planes*block.expansion))
        layers = [block(self.inplanes, planes, stride, ds)]
        self.inplanes = planes * block.expansion
        for _ in range(1, blocks):
            layers.append(block(self.inplanes, planes))
        return nn.Sequential(*layers)

    def forward(self, x, n_iter=3):
        B  = x.shape[0]
        pp = self.init_pose.expand(B, -1)
        ps = self.init_shape.expand(B, -1)
        pc = self.init_cam.expand(B, -1)
        x  = self.maxpool(self.relu(self.bn1(self.conv1(x))))
        xf = self.avgpool(
                self.layer4(self.layer3(self.layer2(self.layer1(x))))
             ).view(B, -1)
        for _ in range(n_iter):
            xc = self.drop1(torch.relu(self.fc1(torch.cat([xf, pp, ps, pc], 1))))
            xc = self.drop2(torch.relu(self.fc2(xc)))
            pp = self.decpose(xc)  + pp
            ps = self.decshape(xc) + ps
            pc = self.deccam(xc)   + pc
        return _rot6d_to_rotmat(pp).view(B, 24, 3, 3), ps, pc

def _spin_preprocess(img_bgr):
    img = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (IMG_RES, IMG_RES)).astype(np.float32) / 255.0
    img = (img - SPIN_MEAN) / SPIN_STD
    return torch.from_numpy(img.transpose(2,0,1)).unsqueeze(0).float()

def _rotmat_to_joints(rotmat, camera):
    positions   = np.zeros((22, 3), dtype=np.float32)
    global_rots = [np.eye(3)] * 22
    for j in range(22):
        p = PARENTS[j]
        if p == -1:
            global_rots[j] = rotmat[j]
        else:
            global_rots[j] = global_rots[p] @ rotmat[j]
            positions[j]   = positions[p] + global_rots[p] @ np.array([0, BONE_LENS[j], 0])
    positions[:, 0] += camera[1]
    positions[:, 1] += camera[2]
    return camera[0] * positions


# ════════════════════════════════════════════════════════════════════════════
# Similarity score & feedback
# ════════════════════════════════════════════════════════════════════════════

# KPS index reference:
# 0=Head, 1=Neck, 2=RShoulder, 3=RArm, 4=RHand,
# 5=LShoulder, 6=LArm, 7=LHand, 8=Spine, 9=Hips,
# 10=RUpperLeg, 11=RLeg, 12=RFoot,
# 13=LUpperLeg, 14=LLeg, 15=LFoot, 16=LToe, 17=RToe

# Limb groups: name → joint indices (in order from root to tip)
LIMB_GROUPS = {
    "right arm":  [2, 3, 4],    # RShoulder → RArm → RHand
    "left arm":   [5, 6, 7],    # LShoulder → LArm → LHand
    "right leg":  [10, 11, 12], # RUpperLeg → RLeg → RFoot
    "left leg":   [13, 14, 15], # LUpperLeg → LLeg → LFoot
    "torso":      [9, 8, 1],    # Hips → Spine → Neck
    "head":       [1, 0],       # Neck → Head
}


def _norm_kps(k: np.ndarray) -> np.ndarray:
    k = k.astype(float)
    k = k - k[9:10]
    torso = np.linalg.norm(k[1] - k[9]) + 1e-6
    return k / torso


def _err_to_score(err: float) -> float:
    """Piecewise mapping from alignment error to 0-100 score."""
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
    """Mean joint distance for a subset of joints, after local alignment."""
    sa = a_norm[indices]
    sb = b_norm[indices]
    # center each limb on its root joint
    sa = sa - sa[0:1]
    sb = sb - sb[0:1]
    scale = max(np.sqrt((sa**2).sum()), np.sqrt((sb**2).sum()), 1e-6)
    sa /= scale
    sb /= scale
    return float(np.mean(np.linalg.norm(sa - sb, axis=1)))


def _elevation_label(dy: float) -> str:
    """dy = tip_y - root_y in image coords (y increases downward)."""
    if dy < -0.3:   return "raised high"
    if dy < -0.05:  return "raised"
    if dy <  0.05:  return "horizontal"
    if dy <  0.3:   return "lowered"
    return "pointing down"


def _limb_feedback(limb: str, ref_kps: np.ndarray, user_kps: np.ndarray,
                   indices: list) -> Optional[str]:
    """Return a feedback string for one limb, or None if it looks good."""
    r = ref_kps[indices].astype(float)
    u = user_kps[indices].astype(float)

    # Elevation: compare tip relative to root (y axis, image coords)
    ref_dy  = (r[-1] - r[0])[1]
    user_dy = (u[-1] - u[0])[1]
    diff_dy = user_dy - ref_dy  # positive = user is lower than reference

    # Horizontal spread: tip x relative to root x
    ref_dx  = (r[-1] - r[0])[0]
    user_dx = (u[-1] - u[0])[0]
    diff_dx = user_dx - ref_dx

    messages = []

    # Vertical correction
    if abs(diff_dy) > 0.15:
        direction = "lower" if diff_dy > 0 else "higher"
        amount    = "much" if abs(diff_dy) > 0.35 else "slightly"
        target    = _elevation_label(ref_dy)
        messages.append(f"should be {target} — move it {amount} {direction}")

    # Horizontal correction
    if abs(diff_dx) > 0.15:
        direction = "more to the left" if diff_dx > 0 else "more to the right"
        amount    = "much" if abs(diff_dx) > 0.35 else "slightly"
        messages.append(f"extend it {amount} {direction}")

    # Bend: for limbs with 3 joints, check middle-joint angle
    if len(indices) == 3:
        def _angle(pts):
            v1 = pts[0] - pts[1]
            v2 = pts[2] - pts[1]
            n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
            if n1 < 1e-6 or n2 < 1e-6:
                return 180.0
            return float(np.degrees(np.arccos(np.clip(np.dot(v1/n1, v2/n2), -1, 1))))

        ref_angle  = _angle(r)
        user_angle = _angle(u)
        diff_angle = user_angle - ref_angle

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
    for limb, indices in LIMB_GROUPS.items():
        err = _limb_err(ref_n, user_n, indices)
        limb_scores[limb] = (err, _err_to_score(err))

    # Sort by score ascending (worst first)
    sorted_limbs = sorted(limb_scores.items(), key=lambda x: x[1][1])

    issues = []
    praise = []

    for limb, (err, score) in sorted_limbs:
        indices = LIMB_GROUPS[limb]
        if score >= 80:
            praise.append(limb)
        else:
            msg = _limb_feedback(limb, ref_kps, user_kps, indices)
            if msg:
                issues.append((score, msg))

    lines = []
    if praise:
        lines.append(f"✓ Looking good: {', '.join(praise)}.")

    if issues:
        lines.append("✗ Needs adjustment:")
        for _, msg in issues[:3]:  # top 3 worst
            lines.append(msg)
    else:
        lines.append("Great overall pose match!")

    return "\n".join(lines)


def _similarity_score_2d(kps_a: np.ndarray, kps_b: np.ndarray) -> float:
    from scipy.spatial import procrustes

    a = _norm_kps(kps_a.copy())
    b = _norm_kps(kps_b.copy())

    sa = np.sqrt((a**2).sum()) + 1e-6
    sb = np.sqrt((b**2).sum()) + 1e-6
    a /= sa
    b /= sb

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
        _log.warning(f"bad score value {score}, clamping to 0")
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

def _draw_skeleton(img_pil, kps,
                   color_bone=(0, 180, 255), color_joint=(255, 60, 60)):
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

def _label_bar(img_pil, text, bg_color):
    out  = img_pil.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    W, H = out.size
    bar_h = max(28, H // 14)
    draw.rectangle([0, 0, W, bar_h], fill=bg_color)
    draw.text((8, 4), text, fill=(255, 255, 255))
    return out

def _side_by_side(img_a, img_b):
    h = max(img_a.height, img_b.height)
    def _rh(im):
        r = h / im.height
        return im.resize((int(im.width * r), h), Image.LANCZOS)
    a, b = _rh(img_a), _rh(img_b)
    out  = Image.new("RGB", (a.width + b.width, h), (240, 240, 240))
    out.paste(a, (0, 0))
    out.paste(b, (a.width, 0))
    return out

def _score_banner(img_pil, score: float) -> Image.Image:
    W, H  = img_pil.size
    bar_h = max(48, H // 10)
    out   = Image.new("RGB", (W, H + bar_h), (30, 30, 30))
    out.paste(img_pil, (0, 0))
    draw  = ImageDraw.Draw(out)
    bg    = (34,139,34) if score >= 75 else (200,160,0) if score >= 50 else (180,40,40)
    draw.rectangle([0, H, W, H + bar_h], fill=bg)
    label = f"Pose Similarity: {score}%  —  {_score_label(score)}"
    draw.text(((W - len(label) * 6) // 2, H + bar_h // 4), label, fill=(255,255,255))
    return out


# ════════════════════════════════════════════════════════════════════════════
# SketchPadModel
# ════════════════════════════════════════════════════════════════════════════

class SketchPadModel:
    """
    Phase 1 — upload sketch:    runs inference, saves joints+kps+overlay to disk,
                                 returns overlay image.
    Phase 2 — upload reference: loads phase-1 data, runs inference on reference,
                                 compares 2D keypoints, returns overlay + score.
    """

    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        _log.info(f"Using device: {self.device}")
        self.model_hrnet = cv2.dnn.readNetFromONNX(HRNET_PATH)
        self.model_spin  = _HMR(SMPL_MEAN).to(self.device)
        ckpt  = torch.load(SPIN_PATH, map_location="cpu", weights_only=False)
        state = ckpt["model"] if "model" in ckpt else ckpt
        self.model_spin.load_state_dict(state, strict=False)
        self.model_spin.eval()

    @staticmethod
    def _to_bgr(img: Image.Image) -> np.ndarray:
        return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

    def _run(self, img: Image.Image):
        """Returns (joints_3d (22,3), kps (18,2), overlay PIL Image)."""
        bgr = self._to_bgr(img)

        # HRNet — 2D keypoints (used for similarity)
        blob, c, s = _hrnet_preprocess(bgr)
        self.model_hrnet.setInput(blob)
        heatmaps = self.model_hrnet.forward()
        kps, _   = _get_final_preds(heatmaps, c[None], s[None])
        kps      = kps.squeeze(0)   # (18, 2)

        # SPIN — 3D joints (kept for future use but not used in similarity)
        inp = _spin_preprocess(bgr).to(self.device)
        with torch.no_grad():
            with torch.autocast(
                device_type="cuda",
                dtype=torch.float16,
                enabled=self.device.type == "cuda",
            ):
                rotmat, _, camera = self.model_spin(inp)
        joints_3d = _rotmat_to_joints(
            rotmat.squeeze(0).cpu().numpy(),
            camera.squeeze(0).cpu().numpy(),
        )

        overlay = _draw_skeleton(img, kps)
        return joints_3d, kps, overlay

    def process(self, image: Optional[Image.Image], prompt: str) -> dict:
        if not _has_sketch():
            # ── Phase 1: no sketch on disk yet ───────────────────────────
            if image is None:
                return {
                    "text":  "Upload your sketch to get started.",
                    "image": None,
                }
            _log.info("Phase 1: running inference on sketch")
            joints_3d, kps, overlay = self._run(image)
            _save_sketch(joints_3d, kps, overlay)
            return {
                "text":  "✅ Sketch saved! Now upload your reference sketch.",
                "image": overlay,
            }

        else:
            # ── Phase 2: sketch exists, waiting for reference ─────────────
            if image is None:
                _, _, sk_overlay = _load_sketch()
                return {
                    "text":  "Now upload your reference sketch to compare.",
                    "image": sk_overlay,
                }
            _log.info("Phase 2: running inference on reference")
            joints_3d, kps, overlay = self._run(image)
            sk_joints, sk_kps, _    = _load_sketch()
            score    = round(float(_similarity_score_2d(sk_kps, kps)), 1)
            feedback = _generate_feedback(sk_kps, kps)
            _log.info(f"Similarity score: {score}%")
            _log.debug(f"Feedback: {feedback}")
            _clear_sketch()
            text = (
                f"✅ Pose similarity: {score}% — {_score_label(score)}\n\n"
                f"{feedback}"
            )
            return {
                "text":  text,
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
