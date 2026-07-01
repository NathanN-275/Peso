const DEFAULT_LABEL_WIDTH = 76;
const DEFAULT_LABEL_HEIGHT = 22;
const DEFAULT_GAP = 8;

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum);
}

function intersectionArea(first, second) {
  const width = Math.max(
    Math.min(first.x + first.width, second.x + second.width) - Math.max(first.x, second.x),
    0
  );
  const height = Math.max(
    Math.min(first.y + first.height, second.y + second.height) - Math.max(first.y, second.y),
    0
  );
  return width * height;
}

function layoutTrackingLabels(points, bounds, options = {}) {
  const labelWidth = options.labelWidth ?? DEFAULT_LABEL_WIDTH;
  const labelHeight = options.labelHeight ?? DEFAULT_LABEL_HEIGHT;
  const gap = options.gap ?? DEFAULT_GAP;
  const occupied = [];

  return points.map((point) => {
    const width = point.labelWidth ?? labelWidth;
    const height = point.labelHeight ?? labelHeight;
    const candidates = [0, 1, 2].flatMap((ring) => {
      const extra = ring * (height + 4);
      return [
        { x: point.x + gap, y: point.y - height - gap - extra },
        { x: point.x - width - gap, y: point.y - height - gap - extra },
        { x: point.x + gap, y: point.y + gap + extra },
        { x: point.x - width - gap, y: point.y + gap + extra },
      ];
    }).map((candidate, index) => ({
      x: clamp(candidate.x, 0, Math.max(bounds.width - width, 0)),
      y: clamp(candidate.y, 0, Math.max(bounds.height - height, 0)),
      width,
      height,
      index,
    }));
    const selected = candidates.find((candidate) => (
      occupied.every((rectangle) => intersectionArea(candidate, rectangle) === 0)
    )) ?? candidates.reduce((best, candidate) => {
      const overlap = occupied.reduce(
        (total, rectangle) => total + intersectionArea(candidate, rectangle),
        0
      );
      return overlap < best.overlap ? { candidate, overlap } : best;
    }, { candidate: candidates[0], overlap: Number.POSITIVE_INFINITY }).candidate;

    occupied.push(selected);
    return {
      ...point,
      labelX: selected.x,
      labelY: selected.y,
      labelWidth: width,
      labelHeight: height,
      displaced: selected.index !== 0,
    };
  });
}

function isReferenceTrackingTime(currentTimeSeconds, referenceTimeMs, toleranceMs = 100) {
  if (!Number.isFinite(currentTimeSeconds) || !Number.isFinite(referenceTimeMs)) {
    return false;
  }
  return Math.abs((currentTimeSeconds * 1000) - referenceTimeMs) <= toleranceMs;
}

function resolveSelectedTrackingSide(trackingAssistance, diagnostics) {
  return trackingAssistance?.selectedSide
    ?? diagnostics?.tracking_assistance?.selectedSide
    ?? diagnostics?.pose_validation?.selected_side
    ?? diagnostics?.selected_side
    ?? null;
}

module.exports = {
  intersectionArea,
  isReferenceTrackingTime,
  layoutTrackingLabels,
  resolveSelectedTrackingSide,
};
