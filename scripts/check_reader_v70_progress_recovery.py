from pathlib import Path
text=Path('cloudflare/runner3-core/artifact-library-simple-entry.js').read_text(encoding='utf-8')
markers=[
"R3_PROGRESS_RECOVERY_V70='v70'",
'r3CollectLocalProgressV70',
'r3ProgressSubstanceV70',
'r3ScopeFromBookKeyV70',
"storageKey.startsWith('r3-reader-last-open:')",
'JSON.stringify({items:upload,client_version:R3_PROGRESS_RECOVERY_V70})',
'async function r3SelectProgressForKeyV70',
'async function r3UpsertProgressV70',
'async function r3SnapshotProgressV70',
"ROOT+'_system/progress-v70/latest.json'",
"ROOT+'_system/progress-v70/snapshots/'+day+'.json'",
"recovery_version:'v70'",
'if (!(await hasBrowserLibrarySession(request, env))) return (await r3LoadLegacyLibraryAppV57()).fetch(request, env, ctx);',
'"X-R3-Progress-Recovery": "v70"',
]
for m in markers:
    if m not in text: raise SystemExit('READER_V70_PROGRESS_RECOVERY_CHECK_MISSING:'+m)
print('READER_V70_PROGRESS_RECOVERY_CHECK=PASS')
