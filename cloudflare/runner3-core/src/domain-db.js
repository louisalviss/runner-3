export function withDb(env, db) {
  if (!db || db === env?.DB) return env;
  return { ...env, DB: db };
}

export function rssEnv(env) {
  return withDb(env, env?.RSS_DB || env?.DB || null);
}

export function contentEnv(env) {
  return withDb(env, env?.CONTENT_DB || env?.DB || null);
}

export function redditEnv(env) {
  return withDb(env, env?.REDDIT_DB || env?.DB || null);
}

export function ebookEnv(env) {
  return withDb(env, env?.EBOOK_DB || env?.LIBRARY_DB || env?.DB || null);
}
