export function objectContainRect(containerWidth, containerHeight, sourceWidth, sourceHeight) {
  const safeSourceWidth = Math.max(1, sourceWidth);
  const safeSourceHeight = Math.max(1, sourceHeight);
  const scale = Math.min(
    containerWidth / safeSourceWidth,
    containerHeight / safeSourceHeight,
  );
  const width = safeSourceWidth * scale;
  const height = safeSourceHeight * scale;
  return {
    scale,
    width,
    height,
    offsetX: (containerWidth - width) / 2,
    offsetY: (containerHeight - height) / 2,
  };
}

export function projectVideoPoint(x, y, rect, normalized = false) {
  return {
    x: rect.offsetX + (normalized ? x * rect.width : x * rect.scale),
    y: rect.offsetY + (normalized ? y * rect.height : y * rect.scale),
  };
}
