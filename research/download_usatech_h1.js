const fs=require('fs');
const {getHistoricalRates}=require('dukascopy-node');
(async()=>{
  const csv=await getHistoricalRates({
    instrument:'usatechidxusd',
    dates:{from:new Date('2018-01-01T00:00:00Z'),to:new Date('2026-08-22T00:00:00Z')},
    timeframe:'h1',priceType:'bid',volumes:false,ignoreFlats:true,format:'csv',
    batchSize:60,pauseBetweenBatchesMs:120,retryCount:4,pauseBetweenRetriesMs:1200,failAfterRetryCount:true
  });
  fs.writeFileSync('/tmp/usatech_h1.csv',csv);
  console.log('USATECH_BYTES',Buffer.byteLength(csv),'LINES',csv.trim().split(/\r?\n/).length);
})().catch(e=>{console.error(e);process.exit(1)});
