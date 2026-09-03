# Ebook Reader v65 — Safari/iPhone acceptance

Status: EMERGENCY RESTORED CANDIDATE / DEVICE ACCEPTANCE REQUIRED. Production was restored from broken v65.1 custom management UI to the last Safari-working v65 build. Server smoke passed; it does not replace this device test.

Deployment metadata:
- Emergency restore commit: `96617d7861f9beb4ba79fa94f250757cb2021827`
- v65 restore build validation run: `33698097245` — PASS
- Production restore deploy run: `33698134487` — PASS
- Restored v65 Cloudflare version: `0a6c152e-1032-47c4-8404-1b17b7e3aa9f`
- v65.1 custom management sheet is excluded from the production build chain.
- Canonical rollback remains v64 Cloudflare version `4fc0bb37-4ffa-49e6-8722-e3631428c6ac`.

Run on iPhone Safari with a book that already has saved progress:

1. Fully close Safari, reopen it cold, open `/artifact-library`.
2. Confirm Library loads, covers/list/progress are visible, and the saved book shows non-zero progress when appropriate.
3. Open the saved book once.
   - It must restore directly to the saved CFI.
   - No visible page-walking.
   - No cropped top / vertical layout shift.
4. Open the in-Reader Library and return to the same book.
   - Position must not change.
5. Play audio.
   - Current chapter starts normally.
   - Page/highlight following remains correct.
   - Next-chapter transition/prefetch remains functional.
6. Cross-device sync test:
   - Advance the book on device A and wait ~2 seconds.
   - Open the same book on device B.
   - Device B must use the newer CFI/progress.
   - Then advance on B and confirm A picks up the newer state on next open/Library refresh.
7. Rename test from main Library and from the in-Reader Library panel.
   - Native Safari prompt is temporarily accepted in restored v65.
   - New title appears.
   - Cover/author metadata remains.
   - Saved position/progress follows the renamed key.
   - A rename collision must be rejected, not overwritten.
8. Delete test using a disposable uploaded EPUB.
   - Explicit confirmation appears.
   - Book disappears from Library.
   - EPUB + its scope metadata/cover disappear.
   - Unrelated audio/cache data is not deleted.

PASS rule: v65 becomes canonical only after all device checks pass. Until then v64 remains canonical rollback.
