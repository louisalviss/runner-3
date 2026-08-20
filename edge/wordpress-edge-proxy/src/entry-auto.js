import base, { PublicHtml } from './entry.js';
import { AUTOMATION_EVENTS_PATH, handleAutomationEvents } from './automation-events.js';

export { PublicHtml };

function base64Bytes(value) {
  const binary = atob(String(value || ''));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function verifySignature(request, env, rawBody) {
  const timestampText = request.headers.get('X-Runner3-Timestamp') || '';
  const signatureText = request.headers.get('X-Runner3-Signature') || '';
  const secret = String(env.RUNNER3_CACHE_PURGE_SECRET || '');
  const timestamp = Number(timestampText);
  if (!secret) return { ok: false, error: 'auth_unconfigured' };
  if (!Number.isInteger(timestamp) || Math.abs(Math.floor(Date.now() / 1000) - timestamp) > 300) return { ok: false, error: 'timestamp_invalid' };
  if (!signatureText || rawBody.length > 32768) return { ok: false, error: 'signature_missing' };
  try {
    const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['verify']);
    const valid = await crypto.subtle.verify('HMAC', key, base64Bytes(signatureText), new TextEncoder().encode(`${timestampText}\n${rawBody}`));
    return valid ? { ok: true, algorithm: 'HMAC-SHA256' } : { ok: false, error: 'signature_invalid' };
  } catch (error) {
    return { ok: false, error: String(error?.message || 'signature_verify_failed').slice(0, 120) };
  }
}

export default {
  async fetch(request, env, ctx) {
    const incoming = new URL(request.url);
    if (incoming.pathname === AUTOMATION_EVENTS_PATH) {
      return handleAutomationEvents(request, env, verifySignature);
    }
    return base.fetch(request, env, ctx);
  },
};
