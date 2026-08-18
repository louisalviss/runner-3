const R2_HOST = 'pub-f6e5190178814cd5be8f1eb531f1a164.r2.dev';
const SITE_PREFIX = '/sites/runner3-factory-smoke-2/';
const VERIFIED_IMAGE_RE = /^offset-demo-(0[1-8])\.webp$/i;
const WIDTHS = [360, 480, 640];
const RESPONSIVE_SIZES = '(max-width: 767px) 92vw, 1100px';

function responsiveInfo(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.hostname !== R2_HOST || !url.pathname.startsWith(SITE_PREFIX)) return null;
    const filename = url.pathname.slice(SITE_PREFIX.length);
    if (!VERIFIED_IMAGE_RE.test(filename)) return null;
    const stem = filename.replace(/\.webp$/i, '');
    const base = `https://${R2_HOST}${SITE_PREFIX}responsive/${stem}`;
    return {
      srcset: WIDTHS.map((width) => `${base}-w${width}.webp ${width}w`).join(', '),
    };
  } catch {
    return null;
  }
}

export class StaticResponsiveImageRewriter {
  element(element) {
    // Keep the original R2 `src` untouched. Only the 24 variants verified by a
    // real GET + WebP decode are eligible for srcset.
    const info = responsiveInfo(element.getAttribute('src'));
    if (!info) return;
    element.setAttribute('srcset', info.srcset);
    if (!element.getAttribute('sizes')) {
      element.setAttribute('sizes', RESPONSIVE_SIZES);
    }
    // If a static variant is ever removed later, immediately drop srcset so the
    // browser re-evaluates the untouched original src instead of leaving a hole.
    if (!element.getAttribute('onerror')) {
      element.setAttribute('onerror', "this.onerror=null;this.removeAttribute('srcset');this.removeAttribute('sizes')");
    }
  }
}

export class StaticImagePreloadRewriter {
  element(element) {
    const info = responsiveInfo(element.getAttribute('href'));
    if (!info) return;
    // href stays as the original fallback; responsive-capable browsers select a
    // verified static variant before the hero request starts. Keep imagesizes
    // identical to the rendered img sizes so preload and render choose one file.
    element.setAttribute('imagesrcset', info.srcset);
    element.setAttribute('imagesizes', RESPONSIVE_SIZES);
  }
}
