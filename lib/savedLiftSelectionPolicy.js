const SAVED_LIFT_VIEWS = new Set(['list', 'grid']);

function normalizeSavedLiftView(value) {
  return SAVED_LIFT_VIEWS.has(value) ? value : 'list';
}

function normalizeSavedLiftIds(values) {
  if (!Array.isArray(values)) return [];
  return [...new Set(values.filter((value) => typeof value === 'string' && value.length > 0))];
}

function toggleSavedLiftSelection(selectedIds, liftId) {
  const normalized = normalizeSavedLiftIds(selectedIds);
  return normalized.includes(liftId)
    ? normalized.filter((selectedId) => selectedId !== liftId)
    : [...normalized, liftId];
}

function selectVisibleSavedLifts(selectedIds, visibleIds) {
  return normalizeSavedLiftIds([...normalizeSavedLiftIds(selectedIds), ...normalizeSavedLiftIds(visibleIds)]);
}

function pruneSavedLiftSelection(selectedIds, availableIds) {
  const available = new Set(normalizeSavedLiftIds(availableIds));
  return normalizeSavedLiftIds(selectedIds).filter((selectedId) => available.has(selectedId));
}

module.exports = {
  normalizeSavedLiftIds,
  normalizeSavedLiftView,
  pruneSavedLiftSelection,
  selectVisibleSavedLifts,
  toggleSavedLiftSelection,
};
