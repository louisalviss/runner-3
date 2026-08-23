const fs = require('fs');
const path = require('path');
const { getHistoricalRates } = require('dukascopy-node');
const symbols = ['eurusd','gbpusd','usdjpy','audusd','usdcad','usdchf','nzdusd'];
const outDir = process.env.WRFX_DATA_DIR || '/tmp/wrfx_data';
const from = process.env.WRFX_FROM || '2024-01-01';
const to = process.env.WRFX_TO || '2026-08-22';
fs.mkdirSync(outDir,{recursive:true});
const sleep = ms => new Promise(r=>setTimeout(r,ms));
(async()=>{
  const coverage={};
  for(const instrument of symbols){
    console.log('DOWNLOAD_START',instrument,from,to);
    let csv=null, lastErr=null;
    for(let attempt=1; attempt<=4; attempt++){
      try {
        csv=await getHistoricalRates({instrument,dates:{from:new Date(`${from}T00:00:00Z`),to:new Date(`${to}T00:00:00Z`)},timeframe:'m5',priceType:'bid',volumes:false,ignoreFlats:true,format:'csv',batchSize:8,pauseBetweenBatchesMs:350,retryCount:4,pauseBetweenRetriesMs:1500,retryOnEmpty:false,failAfterRetryCount:true});
        break;
      } catch(e) {
        lastErr=e; console.error('DOWNLOAD_RETRY',instrument,attempt,String(e));
        await sleep(15000*attempt);
      }
    }
    if(!csv) throw lastErr || new Error(`download failed ${instrument}`);
    const f=path.join(outDir,`${instrument.toUpperCase()}_M5.csv`); fs.writeFileSync(f,csv);
    const lines=csv.trim().split(/\r?\n/); coverage[instrument.toUpperCase()]={rows:Math.max(0,lines.length-1),first:lines.length>1?lines[1].split(',')[0]:null,last:lines.length>1?lines[lines.length-1].split(',')[0]:null,bytes:Buffer.byteLength(csv)};
    console.log('DOWNLOAD_DONE',instrument,coverage[instrument.toUpperCase()]);
    await sleep(3000);
  }
  fs.writeFileSync(path.join(outDir,'coverage.json'),JSON.stringify(coverage,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
