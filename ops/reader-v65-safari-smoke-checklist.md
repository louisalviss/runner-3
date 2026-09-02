# Ebook Reader v65 — Safari/iPhone acceptance

Status: REQUIRED after deploy. Server smoke is necessary but does not replace this device test.

Canonical rollback: v64 Cloudflare version `4fc0bb37-4ffa-49e6-8722-e3631428c6ac`.

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
