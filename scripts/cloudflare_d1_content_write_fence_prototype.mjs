/**
 * PROTOTYPE ONLY — not imported by production Workers and not a cutover gate.
 *
 * A fail-closed, read-only facade for one D1 binding inside a single
 * invocation. It does NOT drain older Worker versions, stop remote REST D1
 * clients, fence external tokens, guarantee rollback, or provide CDC.
 *
 * Intended for OFFLINE contract analysis before any separately approved
 * application-level fence design. Never use this alone as quiescence proof.
 */

// Keep raw prepared statement handles private: no enumerable or symbolic escape.
const SAFE_STATEMENTS = new WeakMap();
const FAILURE = "D1_CONTENT_WRITE_FENCE_BLOCKED";

function deny() {
  throw new Error(FAILURE);
}

function checkSelect(sql) {
  // Deliberately accepts only simple single SELECT statements. Block all
  // comments, semicolons, CTEs, PRAGMAs and unknown SQL: false positives are
  // preferable to a false "no writes" claim during a migration fence.
  if (typeof sql !== "string" || sql.length > 16000 ||
      !/^\s*SELECT\b/i.test(sql) ||
      /(;|--|\/\*|\*\/|\0)/.test(sql)) deny();
}

function statementFacade(inner) {
  if (!inner || typeof inner.bind !== "function") deny();
  const result = {
    bind(...values) {
      return statementFacade(inner.bind(...values));
    },
    first(...args) {
      if (typeof inner.first !== "function") deny();
      return inner.first(...args);
    },
    all(...args) {
      if (typeof inner.all !== "function") deny();
      return inner.all(...args);
    },
    raw(...args) {
      if (typeof inner.raw !== "function") deny();
      return inner.raw(...args);
    },
    run(...args) {
      if (typeof inner.run !== "function") deny();
      return inner.run(...args);
    }
  };
  const facade = Object.freeze(result);
  SAFE_STATEMENTS.set(facade, inner);
  return facade;
}

export function readOnlyD1Facade(db) {
  if (!db || typeof db.prepare !== "function" ||
      typeof db.batch !== "function") deny();
  return Object.freeze({
    prepare(sql) {
      checkSelect(sql);
      return statementFacade(db.prepare(sql));
    },
    batch(statements) {
      if (!Array.isArray(statements) || statements.length > 250 ||
          statements.some(s => !s || !SAFE_STATEMENTS.has(s))) deny();
      return db.batch(statements.map(s => SAFE_STATEMENTS.get(s)));
    },
    withSession(bookmark) {
      if (typeof db.withSession !== "function") deny();
      return readOnlyD1Facade(db.withSession(bookmark));
    },
    // Intentionally no exec/dump. Unknown methods fail at call site.
  });
}

export function fencedContentEnvForPrototype(env) {
  if (!env || !env.CONTENT_DB) deny();
  const original = env.CONTENT_DB;
  const fenced = readOnlyD1Facade(original);
  return {
    ...env,
    CONTENT_DB: fenced,
    // Defend an exact alias to the same physical object, if present.
    DB: env.DB === original ? fenced : env.DB
  };
}
