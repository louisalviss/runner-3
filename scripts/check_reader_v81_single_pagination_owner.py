from pathlib import Path
R=Path('cloudflare/runner3-core')
v2=(R/'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')
v28=(R/'artifact-library-reader-v28-prime-base-position-entry.js').read_text(encoding='utf-8')
v34=(R/'artifact-library-reader-v34-continuous-range-sync-entry.js').read_text(encoding='utf-8')
v35=(R/'artifact-library-reader-v35-continuity-single-owner-entry.js').read_text(encoding='utf-8')
for m in ['r3PageMoveBusyV81','window.__r3MarkReaderIntentV81=r3MarkReaderIntentV81','active!==intent','intent.consumed=true',"r3ScheduleProgressSyncV65(value,cfi||'')",'suppressed-v81:',"String(reason||'').includes('orientationchange')","String(reason||'')==='dock-resize'"]:
 if m not in v2:raise SystemExit('V81_V2_MISSING:'+m)
for bad in ["function pagePrev(){if(rendition)rendition.prev()","function pageNext(){if(rendition)rendition.next()","rendition.on('relocated',loc=>{const cfi=loc?.start?.cfi;if(cfi)persist(keys.position,cfi)"]:
 if bad in v2:raise SystemExit('V81_LEGACY_NAV_PRESENT:'+bad)
if 'Đang mở đúng vị trí…' not in v28:raise SystemExit('V81_RESTORE_MESSAGE_MISSING')
if "r3MarkReaderIntentV81('audio-follow'" not in v34:raise SystemExit('V81_AUDIO_FOLLOW_MISSING')
for m in ['data-r3-pagination-owner-v81="1"',"owner:'single-pagination-owner-v81'",'r3-home-screen-v81','+ 54px','heading-number','X-R3-Reader-Pagination-Owner']:
 if m not in v35:raise SystemExit('V81_V35_MISSING:'+m)
print('READER_V81_SINGLE_PAGINATION_OWNER_CHECK=PASS')
