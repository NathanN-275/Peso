const demoVideo = document.querySelector('#peso-demo-video');

if (demoVideo) {
  const attachVideoSource = () => {
    const source = demoVideo.dataset.src;

    if (source && !demoVideo.getAttribute('src')) {
      demoVideo.src = source;
      demoVideo.load();
    }
  };

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  if (reducedMotion.matches) {
    attachVideoSource();
  } else if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting && entry.intersectionRatio >= 0.25) {
          attachVideoSource();
          void demoVideo.play().catch(() => {
            // Browser autoplay policies may require the visitor to use the controls.
          });
        } else {
          demoVideo.pause();
        }
      },
      { threshold: [0, 0.25] },
    );

    observer.observe(demoVideo);
  } else {
    attachVideoSource();
  }
}
