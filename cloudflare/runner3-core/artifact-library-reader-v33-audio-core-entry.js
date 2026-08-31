import app from './artifact-library-reader-v31-high-speed-serialized-follow-entry.js';
import browserBundle from './reader-audio-core/browser-production-bundle.generated.js';

const ROBOTS = 'noindex, nofollow, noarchive, nosnippet, noimageindex';
const FLAG = `<script data-r3-audio-core-owner-v33="1">window.__R3_READER_AUDIO_CORE_OWNER=true;</script>`;

function replaceScoped(source, marker, needle, replacement, label) {
  const markerAt = source.indexOf(marker);
  if (markerAt < 0) throw new Error(`READER_V33_PATCH_MISSING:${label}:marker`);
  const at = source.indexOf(needle, markerAt);
  if (at < 0) throw new Error(`READER_V33_PATCH_MISSING:${label}:needle`);
  const nextMarker = source.indexOf('<script ', markerAt + marker.length);
  if (nextMarker >= 0 && at > nextMarker) throw new Error(`READER_V33_PATCH_SCOPE:${label}`);
  if (source.indexOf(needle, at + needle.length) >= 0 && (nextMarker < 0 || source.indexOf(needle, at + needle.length) < nextMarker)) {
    throw new Error(`READER_V33_PATCH_AMBIGUOUS:${label}`);
  }
  return source.slice(0, at) + replacement + source.slice(at + needle.length);
}

function patchCoreOwner(html) {
  let out = String(html || '');
  if (out.includes('data-r3-audio-core-runtime-v33="1"')) return out;

  const v6Marker = '<script data-r3-ebook-audio-v6="2">';
  if (!out.includes(v6Marker)) throw new Error('READER_V33_PATCH_MISSING:v6');
  out = out.replace(v6Marker, FLAG + v6Marker);

  const v6Bind = `main.addEventListener('click',(event)=>{event.preventDefault();createOrPlay();});`;
  const v6Suppression = `window.__r3AudioUiV6={dock,audio,main,back,forward,status,title,speed,expand,seek,current,duration,setStatus,setTitle,setMain,setExpanded,syncTimeline};
  if(window.__R3_READER_AUDIO_CORE_OWNER){
    window.__r3AudioLegacyV6Suppressed=true;
    setExpanded(expanded,false);
    setMain('play');
    setStatus('Nam Minh · Reader Audio Core');
    return;
  }
  ${v6Bind}`;
  out = replaceScoped(out, v6Marker, v6Bind, v6Suppression, 'v6-owner');

  const bookGuard = `if(!bookKey)return;`;
  out = replaceScoped(
    out,
    '<script data-r3-audio-follow-v8="1">',
    bookGuard,
    `${bookGuard}\n  if(window.__R3_READER_AUDIO_CORE_OWNER){window.__r3AudioLegacyV8Suppressed=true;return;}`,
    'v8-owner',
  );
  out = replaceScoped(
    out,
    '<script data-r3-audio-text-sync-v11="1">',
    bookGuard,
    `${bookGuard}\n  if(window.__R3_READER_AUDIO_CORE_OWNER){window.__r3AudioLegacyV11Suppressed=true;return;}`,
    'v11-owner',
  );

  const v29Guard = `if(window.__r3AudioMediaStateGuardV29)return;`;
  out = replaceScoped(
    out,
    '<script data-r3-audio-media-state-guard-v29="1">',
    v29Guard,
    `${v29Guard}\n  if(window.__R3_READER_AUDIO_CORE_OWNER){window.__r3AudioLegacyV29Suppressed=true;return;}`,
    'v29-owner',
  );

  const v31Guard = `if(window.__r3AudioHighSpeedFollowV31)return;`;
  out = replaceScoped(
    out,
    '<script data-r3-audio-high-speed-v31="1">',
    v31Guard,
    `${v31Guard}\n  if(window.__R3_READER_AUDIO_CORE_OWNER){window.__r3AudioLegacyV31ClockSuppressed=true;return;}`,
    'v31-clock',
  );

  if (!out.includes('</body>')) throw new Error('READER_V33_BODY_MARKER_MISSING');
  const bundle = String(browserBundle || '').replace(/<\/script/gi, '<\\/script');
  const runtime = `<script data-r3-audio-core-runtime-v33="1">${bundle}</script>`;
  out = out.replace('</body>', runtime + '</body>');
  return out;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== '/artifact-library/read' || request.method !== 'GET') return response;
    const type = response.headers.get('Content-Type') || '';
    if (!type.toLowerCase().includes('text/html') || response.status !== 200) return response;
    try {
      const updated = patchCoreOwner(await response.text());
      const headers = new Headers(response.headers);
      headers.delete('Content-Length');
      headers.set('X-Robots-Tag', ROBOTS);
      headers.set('X-R3-Reader-Runtime', 'v33-audio-core-owner');
      headers.set('X-R3-Reader-Patch-Proof', 'v31+v33:core-single-owner+legacy-suppressed');
      return new Response(updated, { status: 200, headers });
    } catch (error) {
      return new Response('Reader runtime v33 patch failed', {
        status: 503,
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-store',
          'X-R3-Reader-Runtime': 'v33-patch-failed',
          'X-R3-Reader-Patch-Error': String(error?.message || error).slice(0, 220),
        },
      });
    }
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === 'function') return app.scheduled(controller, env, ctx);
  },
};
