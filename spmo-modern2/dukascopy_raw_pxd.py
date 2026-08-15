#!/usr/bin/env python3
import requests,lzma,struct,datetime as dt
symbols=['PXDUSUSD','PXD.USUSD','PXDUSUS']
for sym in symbols:
  for host in ['https://datafeed.dukascopy.com/datafeed','https://www.dukascopy.com/datafeed']:
    url=f'{host}/{sym}/2022/BID_candles_day_1.bi5'
    try:
      r=requests.get(url,timeout=30)
      print('GET',url,'status',r.status_code,'bytes',len(r.content),'ctype',r.headers.get('content-type'),flush=True)
      if r.status_code!=200 or not r.content:continue
      try: raw=lzma.decompress(r.content)
      except Exception as e:
        print('LZMA_ERR',repr(e),'head',r.content[:30],flush=True);continue
      print('DECOMP',len(raw),'records',len(raw)//24,flush=True)
      for i in [0,max(0,len(raw)//24-1)]:
        rec=struct.unpack('>IIIIIf',raw[i*24:(i+1)*24])
        print('REC',i,rec,'date',dt.datetime.utcfromtimestamp(rec[0]) if rec[0]>100000000 else 'small-ts',flush=True)
      # print records whose timestamp could correspond to Sep-Nov 2022 if unix seconds
      for i in range(len(raw)//24):
        rec=struct.unpack('>IIIIIf',raw[i*24:(i+1)*24])
        ts=rec[0]
        if 1600000000<ts<1800000000:
          d=dt.datetime.utcfromtimestamp(ts).date()
          if d in [dt.date(2022,9,16),dt.date(2022,11,30)]:print('TARGET_REC',d,rec,flush=True)
      raise SystemExit(0)
    except SystemExit:raise
    except Exception as e:print('ERR',url,type(e).__name__,str(e),flush=True)
raise SystemExit(2)
