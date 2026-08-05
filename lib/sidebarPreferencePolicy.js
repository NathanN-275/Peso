const SIDEBAR_PREFERENCE_KEY = 'peso.web.sidebar-collapsed';

function readSidebarCollapsed(storage) {
  if (!storage) {
    return false;
  }

  try {
    return storage.getItem(SIDEBAR_PREFERENCE_KEY) === 'true';
  } catch {
    return false;
  }
}

function writeSidebarCollapsed(storage, collapsed) {
  if (!storage) {
    return;
  }

  try {
    storage.setItem(SIDEBAR_PREFERENCE_KEY, String(collapsed));
  } catch {
    // A blocked storage implementation should not prevent navigation from working.
  }
}

module.exports = {
  SIDEBAR_PREFERENCE_KEY,
  readSidebarCollapsed,
  writeSidebarCollapsed,
};
