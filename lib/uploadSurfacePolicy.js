const MOBILE_WEB_BREAKPOINT = 768;

function usesMobileUploadFlow({ isWeb, viewportWidth }) {
  if (!isWeb) {
    return true;
  }

  return (
    typeof viewportWidth === 'number'
    && Number.isFinite(viewportWidth)
    && viewportWidth > 0
    && viewportWidth < MOBILE_WEB_BREAKPOINT
  );
}

module.exports = {
  MOBILE_WEB_BREAKPOINT,
  usesMobileUploadFlow,
};
