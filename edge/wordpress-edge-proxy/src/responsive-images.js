const R2_HOST = 'pub-f6e5190178814cd5be8f1eb531f1a164.r2.dev';
const SITE_PREFIX = '/sites/runner3-factory-smoke-2/';
const VERIFIED_IMAGE_RE = /^offset-demo-(0[1-8])\.webp$/i;
const HERO_IMAGE_RE = /^offset-demo-01(?:-[a-z0-9_-]+)?\.webp$/i;
const WIDTHS = [360, 480, 640];
const VARIANT_DIR = 'responsive-v2';
const HERO_SAME_ORIGIN_PREFIX = '/__runner3/r2-image/offset-demo-01';
const DEFAULT_IMAGE_SIZES = '(max-width: 767px) 92vw, 1100px';
const HERO_PRELOAD_SIZES = '(max-width: 767px) 80vw, 580px';

function basename(pathname) {
  const parts = String(pathname || '').split('/');
  return parts[parts.length - 1] || '';
}

function responsiveInfo(value) {
  if (!value) return null;
  try {
    const url = new URL(value, 'https://runner3.invalid');
    if (url.protocol !== 'https:' && url.protocol !== 'http:') return null;
    const filename = basename(url.pathname);

    if (HERO_IMAGE_RE.test(filename)) {
      return {
        hero: true,
        srcset: WIDTHS.map((width) => `${HERO_SAME_ORIGIN_PREFIX}-w${width}.webp ${width}w`).join(', '),
      };
    }

    if (url.protocol !== 'https:' || url.hostname !== R2_HOST || !url.pathname.startsWith(SITE_PREFIX)) return null;
    const relative = url.pathname.slice(SITE_PREFIX.length);
    if (!VERIFIED_IMAGE_RE.test(relative)) return null;
    const stem = relative.replace(/\.webp$/i, '');
    const base = `https://${R2_HOST}${SITE_PREFIX}${VARIANT_DIR}/${stem}`;
    return {
      hero: false,
      srcset: WIDTHS.map((width) => `${base}-w${width}.webp ${width}w`).join(', '),
    };
  } catch {
    return null;
  }
}

export class StaticResponsiveImageRewriter {
  constructor() {
    this.heroCount = 0;
  }

  element(element) {
    const info = responsiveInfo(element.getAttribute('src'));
    if (!info) return;

    element.setAttribute('srcset', info.srcset);
    if (!element.getAttribute('sizes')) {
      element.setAttribute('sizes', DEFAULT_IMAGE_SIZES);
    }

    if (info.hero) {
      this.heroCount += 1;
      if (this.heroCount === 1) {
        // The first occurrence is the actual mobile LCP element. Keep it the only
        // eager/high-priority copy and decode it synchronously once its tiny WebP
        // payload arrives so paint is not deferred to a later task.
        element.setAttribute('sizes', HERO_PRELOAD_SIZES);
        element.setAttribute('loading', 'eager');
        element.setAttribute('fetchpriority', 'high');
        element.setAttribute('decoding', 'sync');
      } else {
        // The same article image is repeated below the fold. It must not compete
        // with the true LCP request during initial navigation.
        element.setAttribute('loading', 'lazy');
        element.setAttribute('fetchpriority', 'low');
        element.setAttribute('decoding', 'async');
      }
    }

    if (!element.getAttribute('onerror')) {
      element.setAttribute('onerror', "this.onerror=null;this.removeAttribute('srcset');this.removeAttribute('sizes')");
    }
  }
}

export class StaticImagePreloadRewriter {
  element(element) {
    const info = responsiveInfo(element.getAttribute('href'));
    if (!info || !info.hero) return;
    element.setAttribute('imagesrcset', info.srcset);
    element.setAttribute('imagesizes', HERO_PRELOAD_SIZES);
    element.setAttribute('fetchpriority', 'high');
  }
}
