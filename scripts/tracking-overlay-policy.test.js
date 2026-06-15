const assert = require('node:assert/strict');
const test = require('node:test');

const {
  intersectionArea,
  isReferenceTrackingTime,
  layoutTrackingLabels,
  resolveSelectedTrackingSide,
} = require('../lib/trackingOverlayPolicy');

test('tracking labels remain in bounds without intersecting', () => {
  const labels = layoutTrackingLabels(
    [
      { id: 'shoulder', x: 150, y: 160 },
      { id: 'hip', x: 151, y: 163 },
      { id: 'knee', x: 153, y: 166 },
      { id: 'ankle', x: 155, y: 169 },
      { id: 'barbell', x: 157, y: 171 },
    ],
    { width: 320, height: 240 }
  );

  labels.forEach((label) => {
    assert.ok(label.labelX >= 0);
    assert.ok(label.labelY >= 0);
    assert.ok(label.labelX + label.labelWidth <= 320);
    assert.ok(label.labelY + label.labelHeight <= 240);
  });
  for (let index = 0; index < labels.length; index += 1) {
    for (let other = index + 1; other < labels.length; other += 1) {
      assert.equal(intersectionArea(
        {
          x: labels[index].labelX,
          y: labels[index].labelY,
          width: labels[index].labelWidth,
          height: labels[index].labelHeight,
        },
        {
          x: labels[other].labelX,
          y: labels[other].labelY,
          width: labels[other].labelWidth,
          height: labels[other].labelHeight,
        }
      ), 0);
    }
  }
});

test('reference pins are visible only within 100ms of the saved timestamp', () => {
  assert.equal(isReferenceTrackingTime(1.0, 1000), true);
  assert.equal(isReferenceTrackingTime(1.099, 1000), true);
  assert.equal(isReferenceTrackingTime(1.101, 1000), false);
});

test('pin-selected side takes precedence over pose validation', () => {
  assert.equal(resolveSelectedTrackingSide(
    { selectedSide: 'left' },
    { pose_validation: { selected_side: 'right' }, selected_side: 'right' }
  ), 'left');
});
