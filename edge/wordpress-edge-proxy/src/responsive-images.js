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

    // The homepage hero is a known, versioned site asset. WordPress/media sync may
    // surface either the original URL or an already-sized variant; normalize both
    // to the same-origin R2 route so the optimization survives snapshot refreshes.
    if (HERO_IMAGE_RE.test(filename)) {
      return {
        srcset: WIDTHS.map((width) => `${HERO_SAME_ORIGIN_PREFIX}-w${width}.webp ${width}w`).join(', '),
      };
    }

    // Keep all non-hero responsive rewrites conservative: only verified originals
    // from this site's public R2 prefix can opt into the prebuilt variant set.
    if (url.protocol !== 'https:' || url.hostname !== R2_HOST || !url.pathname.startsWith(SITE_PREFIX)) return null;
    const relative = url.pathname.slice(SITE_PREFIX.length);
    if (!VERIFIED_IMAGE_RE.test(relative)) return null;
    const stem = relative.replace(/\.webp$/i, '');
    const base = `https://${R2_HOST}${SITE_PREFIX}${VARIANT_DIR}/${stem}`;
    return {
      srcset: WIDTHS.map((width) => `${base}-w${width}.webp ${width}w`).join(', '),
    };
  } catch {
    return null;
  }
}

export class StaticResponsiveImageRewriter {
  element(element) {
    const info = responsiveInfo(element.getAttribute('src'));
    if (!info) return;
    element.setAttribute('srcset', info.srcset);
    if (!element.getAttribute('sizes')) {
      element.setAttribute('sizes', DEFAULT_IMAGE_SIZES);
    }
    if (!element.getAttribute('onerror')) {
      element.setAttribute('onerror', "this.onerror=null;this.removeAttribute('srcset');this.removeAttribute('sizes')");
    }
  }
}

export class StaticImagePreloadRewriter {
  element(element) {
    const info = responsiveInfo(element.getAttribute('href'));
    if (!info) return;
    element.setAttribute('imagesrcset', info.srcset);
    element.setAttribute('imagesizes', HERO_PRELOAD_SIZES);
  }
}
