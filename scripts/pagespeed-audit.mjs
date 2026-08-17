import fs from 'fs';
import path from 'path';

const target = process.env.PSI_URL || 'https://runner3-factory-smoke-2.wasmer.app/';
const out = process.env.PSI_OUT || 'ops/pagespeed/latest.json';
const strategies = ['mobile','desktop'];

const pickAudit = (audits, id) => {
  const a = audits?.[id];
  if (!a) return null;
  return {
    id,
    score: a.score,
    numericValue: a.numericValue ?? null,
    displayValue: a.displayValue ?? null,
    title: a.title,
    description: a.description,
    detailsType: a.details?.type ?? null,
    overallSavingsMs: a.details?.overallSavingsMs ?? null,
    overallSavingsBytes: a.details?.overallSavingsBytes ?? null,
  };
};

const opportunityIds = [
  'largest-contentful-paint','first-contentful-paint','speed-index','total-blocking-time','cumulative-layout-shift','interactive',
  'server-response-time','render-blocking-resources','unused-css-rules','unused-javascript','modern-image-formats','uses-optimized-images','uses-responsive-images','offscreen-images','uses-text-compression','uses-long-cache-ttl','font-display','third-party-summary','mainthread-work-breakdown','bootup-time','network-requests','network-rtt','network-server-latency','total-byte-weight','dom-size','lcp-lazy-loaded','prioritize-lcp-image','preload-lcp-image','image-delivery-insight','network-dependency-tree-insight','render-blocking-insight','document-latency-insight','font-display-insight','cache-insight'
];

const result = { status: 'running', target, checkedAt: new Date().toISOString(), source: 'Google PageSpeed Insights API v5', runs: {}, detail: null };
const persist = () => {
  fs.mkdirSync(path.dirname(out), {recursive:true});
  fs.writeFileSync(out, JSON.stringify(result,null,2));
};

try {
  for (const strategy of strategies) {
    const endpoint = new URL('https://www.googleapis.com/pagespeedonline/v5/runPagespeed');
    endpoint.searchParams.set('url', target);
    endpoint.searchParams.set('strategy', strategy);
    endpoint.searchParams.append('category', 'performance');
    endpoint.searchParams.append('category', 'accessibility');
    endpoint.searchParams.append('category', 'best-practices');
    endpoint.searchParams.append('category', 'seo');
    let r;
    for (let i=0;i<4;i++) {
      r = await fetch(endpoint, {headers:{'User-Agent':'Runner3-PSI/1.0'}}).catch(()=>null);
      if (r?.ok) break;
      if (i<3) await new Promise(res=>setTimeout(res, 4000*(i+1)));
    }
    if (!r?.ok) {
      const text = r ? await r.text() : 'network_error';
      throw new Error(`PSI ${strategy} failed ${r?.status}: ${text.slice(0,500)}`);
    }
    const json = await r.json();
    const lh = json.lighthouseResult || {};
    const cats = lh.categories || {};
    const audits = lh.audits || {};
    result.runs[strategy] = {
      fetchTime: lh.fetchTime,
      lighthouseVersion: lh.lighthouseVersion,
      finalUrl: lh.finalUrl,
      scores: Object.fromEntries(Object.entries(cats).map(([k,v])=>[k, Math.round((v.score||0)*100)])),
      metrics: {
        fcp: pickAudit(audits,'first-contentful-paint'),
        lcp: pickAudit(audits,'largest-contentful-paint'),
        tbt: pickAudit(audits,'total-blocking-time'),
        cls: pickAudit(audits,'cumulative-layout-shift'),
        speedIndex: pickAudit(audits,'speed-index'),
        interactive: pickAudit(audits,'interactive'),
      },
      opportunities: opportunityIds.map(id=>pickAudit(audits,id)).filter(Boolean),
      failedAudits: Object.values(audits).filter(a=>a && a.score !== null && a.score < 1 && ['binary','numeric'].includes(a.scoreDisplayMode)).slice(0,100).map(a=>({id:a.id,title:a.title,score:a.score,displayValue:a.displayValue||null,numericValue:a.numericValue??null}))
    };
    persist();
  }
  result.status = 'ready';
  persist();
  console.log(JSON.stringify({target, mobile:result.runs.mobile.scores, desktop:result.runs.desktop.scores},null,2));
} catch (e) {
  result.status = 'failed';
  result.detail = String(e?.message || e);
  result.checkedAt = new Date().toISOString();
  persist();
  console.error(result.detail);
  process.exitCode = 1;
}
