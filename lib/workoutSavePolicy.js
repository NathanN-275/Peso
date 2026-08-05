function parseWorkoutSaveDetails(repsText, loadText, loadUnit) {
  const normalizedReps = String(repsText ?? '').trim();
  const normalizedLoad = String(loadText ?? '').trim();

  const performedReps = normalizedReps ? Number(normalizedReps) : null;
  if (performedReps !== null && (!Number.isInteger(performedReps) || performedReps < 1)) {
    return { ok: false, error: 'Reps must be a whole number of at least 1.' };
  }

  const loadValue = normalizedLoad ? Number(normalizedLoad) : null;
  if (loadValue !== null && (!Number.isFinite(loadValue) || loadValue < 0)) {
    return { ok: false, error: 'Weight must be 0 or greater.' };
  }

  if (loadValue !== null && loadUnit !== 'lb' && loadUnit !== 'kg') {
    return { ok: false, error: 'Choose lb or kg.' };
  }

  return {
    ok: true,
    value: {
      performed_reps: performedReps,
      load_value: loadValue,
      load_unit: loadValue === null ? null : loadUnit,
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
