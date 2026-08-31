function normalizeText(value) {
  return String(value || '')
    .normalize('NFC')
    .replace(/\r/g, '')
    .replace(/\u00a0/g, ' ')
    .replace(/[\u200b-\u200d\u2060\ufeff]/g, '')
    .replace(/https?:\/\/\S+/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function tokensOf(value) {
  const text = normalizeText(value).normalize('NFKC').toLocaleLowerCase('vi-VN');
  if (!text) return [];
  try { return text.match(/[\p{L}\p{M}\p{N}]+/gu) || []; }
  catch { return text.split(/[^A-Za-z0-9À-ỹ]+/).filter(Boolean); }
}

function wordStartSeconds(word) {
  return Math.max(0, Number(word?.startMs) || 0) / 1000;
}

function wordEndSeconds(word) {
  const start = wordStartSeconds(word);
  const duration = Math.max(0, Number(word?.durationMs) || 0) / 1000;
  return start + duration;
}

export class DomSegmentBuilder {
  constructor({ lookahead = 18, minCoverage = 0 } = {}) {
    this.lookahead = Math.max(1, Math.floor(Number(lookahead) || 18));
    this.minCoverage = Math.max(0, Math.min(1, Number(minCoverage) || 0));
  }

  build({ timingWords = [], blocks = [], cfiFromNode } = {}) {
    const words = Array.isArray(timingWords) ? timingWords : [];
    const nodes = Array.isArray(blocks) ? blocks : Array.from(blocks || []);
    const timingTokens = [];
    for (let wi = 0; wi < words.length; wi++) {
      for (const token of tokensOf(words[wi]?.text)) timingTokens.push({ token, wi });
    }

    const rows = nodes.map((node, index) => ({
      node,
      index,
      first: null,
      last: null,
      matches: 0,
      tokens: tokensOf(node?.innerText ?? node?.textContent ?? ''),
      cfi: '',
    }));
    const domTokens = [];
    for (const row of rows) {
      for (const token of row.tokens) domTokens.push({ token, rowIndex: row.index });
    }

    let ti = 0;
    let matched = 0;
    for (const item of domTokens) {
      if (ti >= timingTokens.length) break;
      let found = -1;
      if (timingTokens[ti]?.token === item.token) found = ti;
      else {
        const end = Math.min(timingTokens.length, ti + this.lookahead + 1);
        for (let probe = ti + 1; probe < end; probe++) {
          if (timingTokens[probe]?.token === item.token) {
            found = probe;
            break;
          }
        }
      }
      if (found < 0) continue;
      const wi = timingTokens[found].wi;
      const row = rows[item.rowIndex];
      if (row.first === null) row.first = wi;
      row.last = wi;
      row.matches += 1;
      matched += 1;
      ti = found + 1;
    }

    const denom = Math.max(1, Math.min(domTokens.length, timingTokens.length));
    const coverage = matched / denom;
    if (coverage < this.minCoverage) {
      return { segments: [], rows, coverage, matched, timingTokenCount: timingTokens.length, domTokenCount: domTokens.length, nodeByCfi: new Map() };
    }

    const mappedRows = [];
    const nodeByCfi = new Map();
    for (const row of rows) {
      if (row.first === null) continue;
      let cfi = '';
      try { cfi = String(cfiFromNode?.(row.node) || ''); } catch {}
      if (!cfi) continue;
      row.cfi = cfi;
      mappedRows.push(row);
      if (!nodeByCfi.has(cfi)) nodeByCfi.set(cfi, row.node);
    }

    const segments = [];
    for (let i = 0; i < mappedRows.length; i++) {
      const row = mappedRows[i];
      const next = mappedRows[i + 1] || null;
      const start = wordStartSeconds(words[row.first]);
      const ownEnd = wordEndSeconds(words[row.last]);
      const nextStart = next ? wordStartSeconds(words[next.first]) : ownEnd;
      const end = Math.max(start, next ? nextStart : ownEnd, ownEnd);
      const token = String(words[row.first]?.text || row.tokens[0] || '');
      const previous = segments.at(-1);
      if (previous && previous.cfi === row.cfi && Math.abs(previous.start - start) < 1e-9) continue;
      segments.push({ index: segments.length, start, end, cfi: row.cfi, token });
    }

    return {
      segments,
      rows,
      coverage,
      matched,
      timingTokenCount: timingTokens.length,
      domTokenCount: domTokens.length,
      nodeByCfi,
    };
  }
}

export { normalizeText as normalizeReaderText, tokensOf as tokenizeReaderText };
