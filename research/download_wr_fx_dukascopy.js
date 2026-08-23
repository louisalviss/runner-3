const fs = require('fs');
const path = require('path');
const { getHistoricalRates } = require('dukascopy-node');
const symbols = ['eurusd','gbpusd','usdjpy','audusd','usdcad','usdchf','nzdusd'];
const outDir = process.env.WRFX_DATA_DIR || '/tmp/wrfx_data';
const from = process.env.WRFX_FROM || '2022-01-01';
const to = process.env.WRFX_TO || '2026-08-22';
fs.mkdirSync(outDir,{recursive:true});
(async()=>{
  const coverage={};
  for(const instrument of symbols){
    console.log('DOWNLOAD_START',instrument,from,to);
    const csv=await getHistoricalRates({instrument,dates:{from:new Date(`${from}T00:00:00Z`),to:new Date(`${to}T00:00:00Z`)},timeframe:'m5',priceType:'bid',volumes:false,ignoreFlats:true,format:'csv',batchSize:60,pauseBetweenBatchesMs:80,retryCount:3,pauseBetweenRetriesMs:500,retryOnEmpty:false,failAfterRetryCount:true});
    const f=path.join(outDir,`${instrument.toUpperCase()}_M5.csv`); fs.writeFileSync(f,csv);
    const lines=csv.trim().split(/\r?\n/); coverage[instrument.toUpperCase()]={rows:Math.max(0,lines.length-1),first:lines.length>1?lines[1].split(',')[0]:null,last:lines.length>1?lines[lines.length-1].split(',')[0]:null,bytes:Buffer.byteLength(csv)};
    console.log('DOWNLOAD_DONE',instrument,coverage[instrument.toUpperCase()]);
  }
  fs.writeFileSync(path.join(outDir,'coverage.json'),JSON.stringify(coverage,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
