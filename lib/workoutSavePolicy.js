function parseWorkoutSaveDetails(repsText, loadText, loadUnit) {
  const normalizedReps = String(repsText ?? '').trim();
  const normalizedLoad = String(loadText ?? '').trim();

  if (!normalizedReps) {
    return { ok: false, error: 'Enter the reps you performed.' };
  }

  const performedReps = Number(normalizedReps);
  if (!Number.isInteger(performedReps) || performedReps < 1) {
    return { ok: false, error: 'Reps must be a whole number of at least 1.' };
  }

  if (!normalizedLoad) {
    return { ok: false, error: 'Enter the weight you lifted.' };
  }

  const loadValue = Number(normalizedLoad);
  if (!Number.isFinite(loadValue) || loadValue < 0) {
    return { ok: false, error: 'Weight must be 0 or greater.' };
  }

  if (loadUnit !== 'lb' && loadUnit !== 'kg') {
    return { ok: false, error: 'Choose lb or kg.' };
  }

  return {
    ok: true,
    value: {
      performed_reps: performedReps,
      load_value: loadValue,
      load_unit: loadUnit,
    },
  };
}

function resolveStoredLoadUnit(value) {
  return value === 'kg' || value === 'lb' ? value : 'lb';
}

module.exports = {
  parseWorkoutSaveDetails,
  resolveStoredLoadUnit,
};
