// Exact daily freshness refresh for an already-clean personal-v4 profile.
// No feature joins or profile writes: the full scorer stores unrounded ranking
// inputs, so changing freshness and reranking is numerically equivalent.
export const DAILY_SCORE_CACHE_VERSION = "v1-exact-ranking-inputs";

export async function refreshCachedPersonalScores(env, options) {
  const { modelVersion, contractVersion, policyVersion, ontologyVersion,
    freshnessBonus, clamp, readPage, writeBatch, maxRows, maxWrites } = options;
  if (!env?.DB || !Number.isInteger(readPage) || readPage < 1 || readPage > 1000 ||
    !Number.isInteger(writeBatch) || writeBatch < 1 || writeBatch > 50 ||
    !Number.isInteger(maxRows) || maxRows < 1 ||
    !Number.isInteger(maxWrites) || maxWrites < 1) {
    return { ok:false,refreshed:false,status:"daily_score_invalid_budget" };
  }

  const rows = [];
  let cursor = null;
  let freshnessChanged = false;
  while (true) {
    const seek = cursor ? "AND s.item_id > ?" : "";
    const query = env.DB.prepare(`
      SELECT s.item_id,s.reason_json,s.score,i.item_id AS content_item_id,i.published_at
      FROM content_scores s LEFT JOIN content_items i ON i.item_id=s.item_id
      WHERE s.score_type='personal_relevance' AND s.model_version=? ${seek}
      ORDER BY s.item_id LIMIT ?
    `);
    const result = await (cursor ? query.bind(modelVersion,cursor,readPage)
      : query.bind(modelVersion,readPage)).all();
    const page = result?.results;
    if (!Array.isArray(page)) throw new Error("DAILY_SCORE_CACHE_READ_FAILED");
    if (page.length === 0) break;
    if (rows.length + page.length > maxRows) {
      return { ok:false,refreshed:false,status:"daily_score_cache_row_cap",read_rows:rows.length+page.length };
    }
    for (const item of page) {
      let reason;
      try { reason = JSON.parse(item.reason_json || ""); } catch { return null; }
      const relevance = reason?.relevance_signal_exact;
      const novelty = reason?.novelty_bonus_exact;
      if (!item.item_id || !item.content_item_id ||
        reason?.ranking_cache_version !== DAILY_SCORE_CACHE_VERSION ||
        reason?.model !== modelVersion ||
        reason?.contract_version !== contractVersion ||
        reason?.profile_policy !== policyVersion ||
        reason?.ontology_version !== ontologyVersion ||
        typeof relevance !== "number" || !Number.isFinite(relevance) ||
        typeof novelty !== "number" || !Number.isFinite(novelty) ||
        typeof reason.freshness_bonus !== "number" ||
        !Number.isFinite(reason.freshness_bonus) ||
        !Number.isFinite(Number(item.score))) return null;

      const fresh = freshnessBonus(item.published_at);
      if (!Number.isFinite(fresh)) throw new Error("DAILY_SCORE_INVALID_FRESHNESS");
      if (fresh !== reason.freshness_bonus) freshnessChanged = true;
      rows.push({
        item_id:String(item.item_id),reason,old_reason:String(item.reason_json),
        old_score:Number(item.score),freshness_bonus:fresh,
        base_score:50+(38*relevance/(6+Math.abs(relevance)))+fresh+novelty,
      });
    }
    if (page.length < readPage) break;
    const next = String(page[page.length-1].item_id);
    if (cursor !== null && next <= cursor) throw new Error("DAILY_SCORE_CACHE_CURSOR_STALLED");
    cursor = next;
  }
  if (!rows.length) return null;
  if (!freshnessChanged) {
    return { ok:true,refreshed:false,status:"daily_freshness_unchanged",scored_items:rows.length,changed:0 };
  }
  const cmpText = (a,b) => a < b ? -1 : a > b ? 1 : 0;
  const sorted = [...rows].sort((a,b) => a.base_score-b.base_score || cmpText(a.item_id,b.item_id));
  let rank = 1;
  for (let i=0;i<sorted.length;i++) {
    if (i > 0 && sorted[i].base_score !== sorted[i-1].base_score) rank = i+1;
    sorted[i].rank_percentile = sorted.length <= 1 ? 0 : (rank-1)/(sorted.length-1);
  }
  const updates = [];
  for (const row of rows) {
    const score = clamp(0.82*row.base_score+18*row.rank_percentile,0.5,99.5);
    const reason = JSON.stringify({
      ...row.reason,
      base_score:Number(row.base_score.toFixed(3)),
      rank_percentile:Number(row.rank_percentile.toFixed(4)),
      freshness_bonus:row.freshness_bonus,
    });
    if (score !== row.old_score || reason !== row.old_reason) {
      updates.push({ item_id:row.item_id,score,reason,old_reason:row.old_reason });
    }
  }
  // Reject oversized updates BEFORE the first write. No partial budget spills.
  if (updates.length > maxWrites) {
    return { ok:false,refreshed:false,status:"daily_score_write_cap",planned_writes:updates.length };
  }
  let written = 0;
  for (let i=0;i<updates.length;i+=writeBatch) {
    const batch = updates.slice(i,i+writeBatch).map((row) => env.DB.prepare(`
      UPDATE content_scores SET score=?,reason_json=?,scored_at=CURRENT_TIMESTAMP
      WHERE item_id=? AND score_type='personal_relevance' AND model_version=?
        AND reason_json=?
    `).bind(row.score,row.reason,row.item_id,modelVersion,row.old_reason));
    const results = await env.DB.batch(batch);
    const applied = results.reduce((n,r) => n+Number(r?.meta?.changes||0),0);
    if (applied !== batch.length) throw new Error("DAILY_SCORE_CONCURRENT_MODIFICATION");
    written += applied;
  }
  return { ok:true,refreshed:true,status:"daily_freshness_cached",
    scored_items:rows.length,changed:written,read_rows:rows.length };
}
