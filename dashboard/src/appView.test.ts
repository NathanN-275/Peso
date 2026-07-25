import { describe, expect, it } from 'vitest';
import { appViewConnections, appViewKeypoints, mapPointToCoverStage, sideSquatAnnotationTargets, visibleBarbellPoints } from './appView';

describe('app view projection', () => {
  it('uses the visible squat side and favors upper-back landmarks', () => {
    const points = appViewKeypoints({
      landmarks: {
        left_shoulder: { x: .3, y: .2, visibility: .9 },
        left_upper_back: { x: .31, y: .2, visibility: .9 },
        left_hip: { x: .32, y: .45, visibility: .9 },
        left_knee: { x: .34, y: .65, visibility: .8 },
        left_ankle: { x: .35, y: .85, visibility: .8 },
        right_shoulder: { x: .6, y: .2, visibility: .2 },
      },
    }, 'back_squat', 'side');

    expect(points.map((point) => point.name)).toEqual(['left_upper_back', 'left_hip', 'left_knee', 'left_ankle']);
    expect(appViewConnections(points, 'back_squat', 'side')).toEqual([
      ['left_upper_back', 'left_hip'], ['left_hip', 'left_knee'], ['left_knee', 'left_ankle'],
    ]);
  });

  it('matches the app torso fallback for bilateral front squats', () => {
    const shoulderOnly = appViewKeypoints({
      landmarks: {
        left_shoulder: { x: .3, y: .2, visibility: .9 },
        left_hip: { x: .32, y: .45, visibility: .9 },
        right_shoulder: { x: .6, y: .2, visibility: .9 },
        right_hip: { x: .58, y: .45, visibility: .9 },
      },
    }, 'back_squat', 'front');

    expect(appViewConnections(shoulderOnly, 'back_squat', 'front')).toContainEqual(
      ['left_shoulder', 'left_hip'],
    );
    expect(appViewConnections(shoulderOnly, 'back_squat', 'front')).toContainEqual(
      ['right_shoulder', 'right_hip'],
    );

    const upperBackPreferred = appViewKeypoints({
      landmarks: {
        left_upper_back: { x: .31, y: .2, visibility: .9 },
        left_shoulder: { x: .3, y: .2, visibility: .9 },
        left_hip: { x: .32, y: .45, visibility: .9 },
      },
    }, 'back_squat', 'front');

    expect(upperBackPreferred.map((point) => point.name)).not.toContain('left_shoulder');
    expect(appViewConnections(upperBackPreferred, 'back_squat', 'front')).toContainEqual(
      ['left_upper_back', 'left_hip'],
    );
  });

  it('maps normalized coordinates through a cover crop', () => {
    expect(mapPointToCoverStage({ x: .5, y: .5 }, 16 / 9)).toEqual({ x: .5, y: .5 });
    expect(mapPointToCoverStage({ x: 0, y: .5 }, 16 / 9).x).toBeLessThan(0);
  });

  it('keeps estimated pose points and excludes unusable barbell samples', () => {
    const points = appViewKeypoints({ landmarks: { left_knee: { x: .4, y: .6, visibility: .3, tracking_state: 'estimated' } } }, 'back_squat', 'side');
    expect(points[0]).toMatchObject({ name: 'left_knee', estimated: true });
    expect(visibleBarbellPoints([
      { x: .2, y: .3, time: 0 },
      { x: .3, y: .4, time: .2, coasting_frame: true },
      { x: .4, y: .5, time: .4 },
    ], .3)).toEqual([{ x: .2, y: .3, time: 0 }]);
  });

  it('exposes only app-visible side-squat targets with the visible-side keys', () => {
    const targets = sideSquatAnnotationTargets({
      landmarks: {
        right_upper_back: { x: .4, y: .2, visibility: .9 },
        right_hip: { x: .42, y: .45, visibility: .9 },
        right_knee: { x: .44, y: .65, visibility: .9 },
        right_ankle: { x: .46, y: .85, visibility: .9 },
        left_hip: { x: .2, y: .45, visibility: .2 },
      },
    });

    expect(targets).toEqual([
      { label: 'Upper back', key: 'right_upper_back' },
      { label: 'Hip', key: 'right_hip' },
      { label: 'Knee', key: 'right_knee' },
      { label: 'Ankle', key: 'right_ankle' },
      { label: 'Barbell center', key: 'barbell_center' },
    ]);
  });
});
