(() => {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const root = document.documentElement;
  const stage = document.querySelector('.signal-stage');

  if (stage && !reduce) {
    let px = 0.5, py = 0.5, sy = 0, ticking = false;
    const paint = () => {
      root.style.setProperty('--mx', ((px - 0.5) * 2).toFixed(3));
      root.style.setProperty('--my', ((py - 0.5) * 2).toFixed(3));
      root.style.setProperty('--scroll-y', sy.toFixed(0));
      ticking = false;
    };
    const schedule = () => {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(paint);
      }
    };
    window.addEventListener('pointermove', (e) => {
      px = e.clientX / Math.max(window.innerWidth, 1);
      py = e.clientY / Math.max(window.innerHeight, 1);
      schedule();
    }, { passive: true });
    window.addEventListener('scroll', () => {
      sy = window.scrollY;
      schedule();
    }, { passive: true });
  }

  const reveal = document.querySelectorAll('[data-reveal]');
  if (!reduce && 'IntersectionObserver' in window) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -5% 0px' });
    reveal.forEach((el) => io.observe(el));
  } else {
    reveal.forEach((el) => el.classList.add('is-visible'));
  }
})();
