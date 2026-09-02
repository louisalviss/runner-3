# Ebook Reader v65.1 — Safari/iPhone acceptance

Status: DEPLOYED CANDIDATE / DEVICE ACCEPTANCE REQUIRED. v65.1 server smoke passed; it does not replace this device test.

Deployment metadata:
- Source/deploy commit: `227ad095d45e0829e8c613cd8032456240ee09a2`
- v65.1 build validation run: `33696893615` — PASS
- Production deploy run: `33696933392` — PASS
- v65.1 Cloudflare version: `daa4585b-3dbe-4a5e-8b0d-8140c5e93ad6`
- Post-deploy server smoke run: `33696973393` — PASS (`READER_V65_1_SERVER_SMOKE=PASS`)
- UX change: Safari native prompt/confirm removed; Rename/Delete now use in-app mobile bottom sheets in both main Library and in-Reader Library.
- Canonical rollback remains v64 Cloudflare version `4fc0bb37-4ffa-49e6-8722-e3631428c6ac`.

Run on iPhone Safari with a book that already has saved progress:

1. Fully close Safari, reopen it cold, open `/artifact-library`.
2. Confirm Library loads, covers/list/progress are visible, and the saved book shows non-zero progress when appropriate.
3. Tap the `…` menu on a book.
   - No Safari/browser prompt may appear.
   - In-app sheet must show `Đổi tên`, `Xóa sách`, `Hủy`.
   - Rename opens an in-sheet text input.
   - Delete opens a separate destructive confirmation sheet.
4. Open the saved book once.
   - It must restore directly to the saved CFI.
   - No visible page-walking.
   - No cropped top / vertical layout shift.
5. Open the in-Reader Library, use `…`, and return to the same book.
   - The same custom management sheet must be used.
   - Position must not change.
6. Play audio.
   - Current chapter starts normally.
   - Page/highlight following remains correct.
   - Next-chapter transition/prefetch remains functional.
7. Cross-device sync test:
   - Advance the book on device A and wait ~2 seconds.
   - Open the same book on device B.
   - Device B must use the newer CFI/progress.
   - Then advance on B and confirm A picks up the newer state on next open/Library refresh.
8. Rename test from main Library and from the in-Reader Library panel.
   - New title appears.
   - Cover/author metadata remains.
   - Saved position/progress follows the renamed key.
   - A rename collision must be rejected, not overwritten.
9. Delete test using a disposable uploaded EPUB.
   - Explicit in-app confirmation appears.
   - Book disappears from Library.
   - EPUB + its scope metadata/cover disappear.
   - Unrelated audio/cache data is not deleted.

PASS rule: v65.1 becomes canonical only after all device checks pass. Until then v64 remains canonical rollback.
