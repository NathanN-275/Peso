const SQUAT_SUFFIX = 'Squat';
const GOBLET_SQUAT = 'Goblet Squat';

/**
 * @param {{ exercise?: string | null, angle?: string | null } | null | undefined} setup
 */
function isSideViewSquatSetup(setup) {
  return Boolean(
    setup?.angle === 'Side'
    && typeof setup.exercise === 'string'
    && setup.exercise.endsWith(SQUAT_SUFFIX)
  );
}

/**
 * @param {{ exercise?: string | null, angle?: string | null } | null | undefined} setup
 */
function isBarbellSideSquatSetup(setup) {
  return isSideViewSquatSetup(setup) && setup?.exercise !== GOBLET_SQUAT;
}

/**
 * @param {{ exercise?: string | null, angle?: string | null } | null | undefined} setup
 */
function getSideSquatRecordingGuidance(setup) {
  if (!isSideViewSquatSetup(setup)) {
    return null;
  }

  const barbellSquat = isBarbellSideSquatSetup(setup);
  const items = [
    {
      id: 'phone_height',
      text: 'Set the phone lens at approximately hip height.',
    },
    {
      id: 'distance_and_framing',
      text: 'Move far enough away to keep the full body in frame while the lifter fills most of the picture.',
    },
    {
      id: 'stationary_camera',
      text: 'Use a stable surface or tripod and keep the phone stationary.',
    },
    {
      id: 'full_body',
      text: 'Keep the head, hips, knees, ankles, and feet visible throughout every rep.',
    },
    ...(barbellSquat
      ? [{
          id: 'barbell_collar',
          text: 'Keep the barbell and visible near-side sleeve–plate interface in frame.',
        }]
      : []),
    {
      id: 'clear_background',
      text: 'Keep other people from crossing behind or in front of the lifter.',
    },
    {
      id: 'lighting',
      text: 'Use enough light to keep the lifter and equipment sharp and easy to see.',
    },
    {
      id: 'digital_zoom',
      text: 'Avoid digital zoom when possible; move the phone instead.',
    },
  ];
  const essentialItems = [
    {
      id: 'essential_camera_position',
      text: 'Set the phone at hip height and square to the lifter.',
    },
    {
      id: 'essential_subject_visibility',
      text: barbellSquat
        ? 'Keep the full body and visible near-side sleeve–plate interface in frame.'
        : 'Keep the full body in frame while the lifter fills most of the picture.',
    },
    {
      id: 'essential_scene_quality',
      text: 'Keep the phone still with bright lighting and a clear background.',
    },
  ];

  return {
    title: 'Set up a trackable side view',
    summary: 'Place the camera square to the lifter before recording or choosing a video.',
    compactSummary: barbellSquat
      ? 'Hip-height phone • full body and near-side sleeve–plate interface visible • steady, bright, clear background • no digital zoom'
      : 'Hip-height phone • full body visible • steady, bright, clear background • no digital zoom',
    barbellSquat,
    essentialItems,
    items,
  };
}

module.exports = {
  getSideSquatRecordingGuidance,
  isBarbellSideSquatSetup,
  isSideViewSquatSetup,
};
