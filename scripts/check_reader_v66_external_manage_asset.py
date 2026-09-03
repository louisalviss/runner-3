from pathlib import Path

ROOT=Path('cloudflare/runner3-core')
simple=(ROOT/'artifact-library-simple-entry.js').read_text(encoding='utf-8')
asset=(ROOT/'reader-manage-ui-v66-asset-source.js').read_text(encoding='utf-8')

for marker in [
    'import { READER_MANAGE_UI_V66_SOURCE } from "./reader-manage-ui-v66-asset-source.js";',
    'function r3ManageUiAssetV66',
    'function r3InjectExternalManageAssetV66',
    'if (p === "/artifact-library/assets/manage-v66.js") return r3ManageUiAssetV66(request);',
    'r3InjectExternalManageAssetV66(libraryPage())',
    'r3InjectExternalManageAssetV66(injectIframeSwipe(original))',
    'data-r3-manage-ui-v66="1"',
]:
    if marker not in simple:
        raise SystemExit('READER_V66_SIMPLE_MISSING:'+marker)

for marker in [
    'export const READER_MANAGE_UI_V66_SOURCE',
    'window.__R3_MANAGE_UI_V66=true',
    'r3-manage-layer-v66',
    'Đổi tên sách',
    'Tên này đã tồn tại. Chọn tên khác.',
    'Xóa sách?',
    "event.stopImmediatePropagation()",
]:
    if marker not in asset:
        raise SystemExit('READER_V66_ASSET_MISSING:'+marker)

if 'window.__R3_MANAGE_UI_V66=true' in simple:
    raise SystemExit('READER_V66_RUNTIME_INLINE_REGRESSION')
if "script-src 'self' 'unsafe-inline';" not in simple:
    raise SystemExit('READER_V66_MAIN_CSP_SELF_MISSING')
if "r3ManageBookV65(bookKey,title){const choice=String(prompt(" not in simple:
    raise SystemExit('READER_V66_LEGACY_FALLBACK_MISSING')

print('READER_V66_EXTERNAL_MANAGE_ASSET_CHECK=PASS')
