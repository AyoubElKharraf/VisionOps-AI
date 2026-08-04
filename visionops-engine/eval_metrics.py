"""
Detection evaluation metrics: IoU matching, AP@IoU, precision/recall, false-alarm rate.

Pure numpy-friendly helpers — no model dependency (safe for CI).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class Box:
    """Axis-aligned box in absolute pixel coordinates."""

    xyxy: tuple[float, float, float, float]
    class_name: str
    confidence: float = 1.0

    @property
    def x1(self) -> float:
        return float(self.xyxy[0])

    @property
    def y1(self) -> float:
        return float(self.xyxy[1])

    @property
    def x2(self) -> float:
        return float(self.xyxy[2])

    @property
    def y2(self) -> float:
        return float(self.xyxy[3])


@dataclass
class ClassMetrics:
    class_name: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    ap50: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0


@dataclass
class EvalReport:
    num_images: int
    iou_threshold: float
    classes: list[ClassMetrics] = field(default_factory=list)
    map50: float = 0.0
    micro_precision: float = 0.0
    micro_recall: float = 0.0
    micro_f1: float = 0.0
    false_alarm_rate: float = 0.0  # FP / (TP+FP) — false discovery rate
    false_alarms_per_image: float = 0.0
    total_tp: int = 0
    total_fp: int = 0
    total_fn: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "num_images": self.num_images,
            "iou_threshold": self.iou_threshold,
            "map50": round(self.map50, 6),
            "micro_precision": round(self.micro_precision, 6),
            "micro_recall": round(self.micro_recall, 6),
            "micro_f1": round(self.micro_f1, 6),
            "false_alarm_rate": round(self.false_alarm_rate, 6),
            "false_alarms_per_image": round(self.false_alarms_per_image, 6),
            "total_tp": self.total_tp,
            "total_fp": self.total_fp,
            "total_fn": self.total_fn,
            "classes": [asdict(c) for c in self.classes],
        }


def box_iou(a: Box | Sequence[float], b: Box | Sequence[float]) -> float:
    """Intersection-over-union for two xyxy boxes."""
    if isinstance(a, Box):
        ax1, ay1, ax2, ay2 = a.xyxy
    else:
        ax1, ay1, ax2, ay2 = (float(v) for v in a[:4])
    if isinstance(b, Box):
        bx1, by1, bx2, by2 = b.xyxy
    else:
        bx1, by1, bx2, by2 = (float(v) for v in b[:4])

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def _safe_div(n: float, d: float) -> float:
    return n / d if d else 0.0


def _f1(precision: float, recall: float) -> float:
    return _safe_div(2 * precision * recall, precision + recall)


def average_precision(recalls: Sequence[float], precisions: Sequence[float]) -> float:
    """
    VOC-style AP: area under the precision-recall curve with precision envelope.

    Expects points already sorted by decreasing confidence (recall non-decreasing).
    """
    if not recalls:
        return 0.0
    mrec = [0.0, *[float(r) for r in recalls], 1.0]
    mpre = [0.0, *[float(p) for p in precisions], 0.0]
    for i in range(len(mpre) - 2, -1, -1):
        mpre[i] = max(mpre[i], mpre[i + 1])
    ap = 0.0
    for i in range(1, len(mrec)):
        ap += (mrec[i] - mrec[i - 1]) * mpre[i]
    return float(ap)


def match_greedy(
    gts: Sequence[Box],
    preds: Sequence[Box],
    *,
    iou_threshold: float,
) -> tuple[list[bool], list[bool]]:
    """
    Greedy one-to-one match of predictions (already sorted by confidence desc)
    against ground-truth boxes of the same class.

    Returns (pred_is_tp, gt_matched).
    """
    gt_matched = [False] * len(gts)
    pred_is_tp: list[bool] = []
    for pred in preds:
        best_iou = 0.0
        best_j = -1
        for j, gt in enumerate(gts):
            if gt_matched[j]:
                continue
            if gt.class_name != pred.class_name:
                continue
            iou = box_iou(pred, gt)
            if iou > best_iou:
                best_iou = iou
                best_j = j
        if best_j >= 0 and best_iou >= iou_threshold:
            gt_matched[best_j] = True
            pred_is_tp.append(True)
        else:
            pred_is_tp.append(False)
    return pred_is_tp, gt_matched


def evaluate_class(
    class_name: str,
    per_image: Iterable[tuple[Sequence[Box], Sequence[Box]]],
    *,
    iou_threshold: float = 0.5,
) -> ClassMetrics:
    """Compute AP/precision/recall for one class across images."""
    scores: list[tuple[float, bool]] = []  # (confidence, is_tp)
    n_gt = 0

    for gts_all, preds_all in per_image:
        gts = [b for b in gts_all if b.class_name == class_name]
        preds = sorted(
            [b for b in preds_all if b.class_name == class_name],
            key=lambda b: b.confidence,
            reverse=True,
        )
        n_gt += len(gts)
        pred_tp, _ = match_greedy(gts, preds, iou_threshold=iou_threshold)
        for pred, is_tp in zip(preds, pred_tp, strict=True):
            scores.append((pred.confidence, is_tp))

    scores.sort(key=lambda t: t[0], reverse=True)
    tp = fp = 0
    recalls: list[float] = []
    precisions: list[float] = []
    for _conf, is_tp in scores:
        if is_tp:
            tp += 1
        else:
            fp += 1
        recalls.append(_safe_div(tp, n_gt))
        precisions.append(_safe_div(tp, tp + fp))

    ap = average_precision(recalls, precisions) if n_gt > 0 else 0.0
    # Final operating point = all predictions kept (post model conf threshold)
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, n_gt)
    fn = max(0, n_gt - tp)
    return ClassMetrics(
        class_name=class_name,
        tp=tp,
        fp=fp,
        fn=fn,
        ap50=ap,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
    )


def evaluate_dataset(
    images: Sequence[tuple[Sequence[Box], Sequence[Box]]],
    *,
    classes: Sequence[str] | None = None,
    iou_threshold: float = 0.5,
) -> EvalReport:
    """
    Evaluate a list of (gt_boxes, pred_boxes) per image.

    `classes` defaults to the union of labels present in GT + predictions.
    """
    if classes is None:
        names: set[str] = set()
        for gts, preds in images:
            names.update(b.class_name for b in gts)
            names.update(b.class_name for b in preds)
        class_list = sorted(names)
    else:
        class_list = list(classes)

    per_class = [
        evaluate_class(name, images, iou_threshold=iou_threshold) for name in class_list
    ]
    present = [c for c in per_class if (c.tp + c.fn) > 0]
    map50 = _safe_div(sum(c.ap50 for c in present), len(present)) if present else 0.0

    total_tp = sum(c.tp for c in per_class)
    total_fp = sum(c.fp for c in per_class)
    total_fn = sum(c.fn for c in per_class)
    micro_p = _safe_div(total_tp, total_tp + total_fp)
    micro_r = _safe_div(total_tp, total_tp + total_fn)
    n_images = len(images)

    return EvalReport(
        num_images=n_images,
        iou_threshold=iou_threshold,
        classes=per_class,
        map50=map50,
        micro_precision=micro_p,
        micro_recall=micro_r,
        micro_f1=_f1(micro_p, micro_r),
        false_alarm_rate=_safe_div(total_fp, total_tp + total_fp),
        false_alarms_per_image=_safe_div(total_fp, n_images),
        total_tp=total_tp,
        total_fp=total_fp,
        total_fn=total_fn,
    )
