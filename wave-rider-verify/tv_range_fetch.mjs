import fs from 'fs';
import { createSession, createChart, createSeries } from '@ch99q/twc';

const specs = [
  ['EURUSD','OANDA'],
  ['USDJPY','OANDA'],
  ['XAUUSD','OANDA'],
  ['US500','ICMARKETS'],
  ['AAPL','NASDAQ'],
];
const start = Math.floor(Date.parse('2026-02-11T17:00:00Z')/1000);
const end   = Math.floor(Date.parse('2026-08-05T17:00:00Z')/1000);
const outdir='wave-rider-verify/output/tv-range'; fs.mkdirSync(outdir,{recursive:true});

for (const [ticker,exchange] of specs) {
  const session=await createSession(undefined,false);
  try {
    const chart=await createChart(session);
    const sym=await chart.resolve(ticker,exchange);
    console.log('RESOLVED',exchange+':'+ticker, JSON.stringify(sym));
    const range=`r,${start}:${end}`;
    const series=await createSeries(session,chart,sym,'5',0,range);
    const h=series.history || [];
    console.log('HISTORY',exchange+':'+ticker,h.length,h[0],h[h.length-1]);
    fs.writeFileSync(`${outdir}/${exchange}-${ticker}.json`,JSON.stringify({ticker,exchange,symbol:sym,history:h},null,2));
    await series.close();
  } finally { await session.close(); }
}
