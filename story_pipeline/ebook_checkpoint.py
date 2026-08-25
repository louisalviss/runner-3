#!/usr/bin/env python3
"""Generic durable checkpoint adapter for long-form ebook editorial pipelines.

House pattern:
- Cloudflare R2 is the canonical machine artifact store for ebook source/output.
- Runner3 Core + Cloudflare D1 is the durable control plane only.
- Google Sheet is the human control/dashboard projection.
- Dropbox is a human library for long context, samples, and final deliverables.
- A chapter is DONE only after the output artifact and metadata sidecar are
  QA-passed, uploaded to R2, read-back verified by the storage caller, and their
  hashes/keys are supplied here for the final D1 checkpoint.
- Recovery is allowed only when a sidecar proves that an existing artifact was
  produced from the exact current semantic input. Mere file existence is never
  sufficient to recover/skip.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
CORE_HELPERS = ROOT / ".github" / "scripts"
if str(CORE_HELPERS) not in sys.path:
    sys.path.insert(0, str(CORE_HELPERS))

from runner3_core import get_checkpoint, report_status, save_checkpoint  # noqa: E402

PROJECT = "ebook-editorial"
DEFAULT_MANIFEST = ROOT / "story_pipeline" / "books" / "vbth.json"
SIDEcar_SCHEMA = "ebook-chapter-artifact-v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_json(path: str | Path, value: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical_json_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    required = ("schema_version", "book_id", "title", "artifact_store", "editorial")
    missing = [key for key in required if manifest.get(key) in (None, "")]
    if missing:
        raise ValueError(f"book manifest missing: {', '.join(missing)}")
    book_id = str(manifest["book_id"]).strip()
    if not book_id or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for ch in book_id):
        raise ValueError("book_id must use lowercase a-z, 0-9, '-' or '_'")
    store = manifest.get("artifact_store")
    if not isinstance(store, dict) or store.get("kind") != "r2":
        raise ValueError("artifact_store.kind must be 'r2' for the canonical ebook flow")
    if not (store.get("bucket_env") or store.get("default_bucket")):
        raise ValueError("artifact_store requires bucket_env or default_bucket")
    prefix = str(store.get("prefix") or "").strip("/")
    if not prefix:
        raise ValueError("artifact_store.prefix is required")
    return manifest


def load_manifest(path: str | Path) -> dict[str, Any]:
    return require_manifest(read_json(path))


def source_name(manifest: dict[str, Any]) -> str:
    return f"ebook-editorial/{manifest['book_id']}"


def main_scope(manifest: dict[str, Any]) -> str:
    return f"book:{manifest['book_id']}:main"


def chapter_scope(manifest: dict[str, Any], chapter: int) -> str:
    if chapter < 1:
        raise ValueError("chapter must be >= 1")
    return f"book:{manifest['book_id']}:chapter:{chapter:04d}"


def artifact_store_info(manifest: dict[str, Any]) -> dict[str, str | None]:
    store = manifest.get("artifact_store") or {}
    bucket_env = str(store.get("bucket_env") or "").strip() or None
    default_bucket = str(store.get("default_bucket") or "").strip() or None
    return {
        "kind": "r2",
        "bucket_env": bucket_env,
        "bucket": os.getenv(bucket_env) if bucket_env and os.getenv(bucket_env) else default_bucket,
        "prefix": str(store.get("prefix") or "").strip("/"),
    }


def require_r2_key(manifest: dict[str, Any], key: str, *, label: str) -> str:
    value = str(key or "").strip().lstrip("/")
    if not value:
        raise ValueError(f"{label} is required")
    prefix = str((manifest.get("artifact_store") or {}).get("prefix") or "").strip("/")
    if value != prefix and not value.startswith(prefix + "/"):
        raise ValueError(f"{label} must stay under R2 prefix {prefix!r}")
    return value


def semantic_config_payload(
    manifest: dict[str, Any],
    config_files: Iterable[str | Path] = (),
    *,
    model: str | None = None,
) -> dict[str, Any]:
    editorial = manifest.get("editorial") or {}
    payload: dict[str, Any] = {
        "book_id": manifest["book_id"],
        "pipeline_version": editorial.get("pipeline_version"),
        "editor_profile": editorial.get("editor_profile"),
        "prompt_version": editorial.get("prompt_version"),
        "story_bible_version": editorial.get("story_bible_version"),
        "glossary_version": editorial.get("glossary_version"),
        "model": model or editorial.get("model"),
        "config_files": [],
    }
    for raw_path in config_files:
        path = Path(raw_path)
        payload["config_files"].append({"name": path.name, "sha256": file_sha256(path)})
    payload["config_files"].sort(key=lambda row: row["name"])
    return payload


def semantic_identity(source_sha256: str, config_sha256: str) -> str:
    return canonical_json_sha256({"source_sha256": source_sha256, "config_sha256": config_sha256})


def build_identity(
    manifest: dict[str, Any],
    source_file: str | Path,
    config_files: Iterable[str | Path] = (),
    *,
    model: str | None = None,
) -> dict[str, str]:
    source_digest = file_sha256(source_file)
    config_payload = semantic_config_payload(manifest, config_files, model=model)
    config_digest = canonical_json_sha256(config_payload)
    return {
        "source_sha256": source_digest,
        "config_sha256": config_digest,
        "semantic_input_sha256": semantic_identity(source_digest, config_digest),
    }


def build_sidecar(
    manifest: dict[str, Any],
    chapter: int,
    *,
    source_file: str | Path,
    artifact_file: str | Path,
    config_files: Iterable[str | Path] = (),
    model: str | None = None,
    qa: str = "pass",
) -> dict[str, Any]:
    artifact = Path(artifact_file)
    if not artifact.is_file() or artifact.stat().st_size <= 0:
        raise ValueError("artifact_file must exist and be non-empty")
    if qa != "pass":
        raise ValueError("sidecar can only be created for qa='pass'")
    identity = build_identity(manifest, source_file, config_files, model=model)
    return {
        "schema": SIDEcar_SCHEMA,
        "book_id": manifest["book_id"],
        "chapter": chapter,
        **identity,
        "artifact_sha256": file_sha256(artifact),
        "artifact_bytes": artifact.stat().st_size,
        "qa": "pass",
        "created_at": now_iso(),
    }


def validate_sidecar(
    manifest: dict[str, Any],
    chapter: int,
    *,
    sidecar: dict[str, Any],
    identity: dict[str, str],
    artifact_file: str | Path,
) -> tuple[bool, str, str | None]:
    artifact = Path(artifact_file)
    if not artifact.is_file() or artifact.stat().st_size <= 0:
        return False, "artifact-missing", None
    artifact_digest = file_sha256(artifact)
    checks = {
        "schema": sidecar.get("schema") == SIDEcar_SCHEMA,
        "book_id": sidecar.get("book_id") == manifest["book_id"],
        "chapter": int(sidecar.get("chapter") or 0) == chapter,
        "qa": sidecar.get("qa") == "pass",
        "source": sidecar.get("source_sha256") == identity["source_sha256"],
        "config": sidecar.get("config_sha256") == identity["config_sha256"],
        "semantic": sidecar.get("semantic_input_sha256") == identity["semantic_input_sha256"],
        "artifact": sidecar.get("artifact_sha256") == artifact_digest,
        "bytes": int(sidecar.get("artifact_bytes") or -1) == artifact.stat().st_size,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        return False, "sidecar-mismatch:" + ",".join(failed), artifact_digest
    return True, "sidecar-and-artifact-match", artifact_digest


def get_chapter(manifest: dict[str, Any], chapter: int, *, core_url: str | None = None) -> dict[str, Any] | None:
    return get_checkpoint(PROJECT, chapter_scope(manifest, chapter), core_url=core_url)


def inspect_resume(
    manifest: dict[str, Any],
    chapter: int,
    *,
    source_file: str | Path,
    artifact_file: str | Path | None,
    artifact_meta_file: str | Path | None,
    config_files: Iterable[str | Path] = (),
    model: str | None = None,
    core_url: str | None = None,
) -> dict[str, Any]:
    identity = build_identity(manifest, source_file, config_files, model=model)
    checkpoint = get_chapter(manifest, chapter, core_url=core_url)
    position = checkpoint.get("position") if isinstance(checkpoint, dict) else None
    checkpoint_identity_match = bool(
        isinstance(position, dict)
        and checkpoint.get("status") == "success"
        and position.get("phase") == "complete"
        and position.get("semantic_input_sha256") == identity["semantic_input_sha256"]
    )

    artifact_path = Path(artifact_file) if artifact_file else None
    meta_path = Path(artifact_meta_file) if artifact_meta_file else None
    artifact_exists = bool(artifact_path and artifact_path.is_file())
    meta_exists = bool(meta_path and meta_path.is_file())
    sidecar: dict[str, Any] | None = None
    sidecar_ok = False
    sidecar_reason = "sidecar-missing"
    artifact_sha: str | None = None
    if artifact_exists and meta_exists:
        try:
            sidecar = read_json(meta_path)
            sidecar_ok, sidecar_reason, artifact_sha = validate_sidecar(
                manifest,
                chapter,
                sidecar=sidecar,
                identity=identity,
                artifact_file=artifact_path,
            )
        except Exception as exc:
            sidecar_reason = f"sidecar-invalid:{type(exc).__name__}"
    elif artifact_exists:
        artifact_sha = file_sha256(artifact_path)

    checkpoint_artifact_match = bool(
        checkpoint_identity_match
        and sidecar_ok
        and artifact_sha
        and position.get("artifact_sha256") == artifact_sha
        and position.get("artifact_meta_sha256") == file_sha256(meta_path)
    )
    if checkpoint_artifact_match:
        action = "skip"
        reason = "checkpoint-sidecar-artifact-match"
    elif sidecar_ok:
        action = "recover"
        reason = "verified-sidecar-artifact-match-checkpoint-missing-or-stale"
    else:
        action = "edit"
        reason = sidecar_reason if artifact_exists else "artifact-missing"

    return {
        "ok": True,
        "book_id": manifest["book_id"],
        "chapter": chapter,
        "action": action,
        "reason": reason,
        "identity": identity,
        "artifact_exists": artifact_exists,
        "artifact_meta_exists": meta_exists,
        "artifact_sha256": artifact_sha,
        "sidecar_verified": sidecar_ok,
        "checkpoint": checkpoint,
    }


def save_chapter_complete(
    manifest: dict[str, Any],
    chapter: int,
    *,
    source_file: str | Path,
    artifact_file: str | Path,
    artifact_meta_file: str | Path,
    artifact_r2_key: str,
    artifact_meta_r2_key: str,
    config_files: Iterable[str | Path] = (),
    model: str | None = None,
    recovered: bool = False,
    run_id: str | None = None,
    core_url: str | None = None,
) -> dict[str, Any]:
    artifact_r2_key = require_r2_key(manifest, artifact_r2_key, label="artifact_r2_key")
    artifact_meta_r2_key = require_r2_key(manifest, artifact_meta_r2_key, label="artifact_meta_r2_key")
    artifact = Path(artifact_file)
    meta_path = Path(artifact_meta_file)
    if not meta_path.is_file():
        raise ValueError("artifact_meta_file is required before D1 success checkpoint")
    identity = build_identity(manifest, source_file, config_files, model=model)
    sidecar = read_json(meta_path)
    sidecar_ok, sidecar_reason, artifact_digest = validate_sidecar(
        manifest,
        chapter,
        sidecar=sidecar,
        identity=identity,
        artifact_file=artifact,
    )
    if not sidecar_ok or not artifact_digest:
        raise ValueError(f"cannot complete chapter: {sidecar_reason}")
    meta_digest = file_sha256(meta_path)
    store = artifact_store_info(manifest)
    scope = chapter_scope(manifest, chapter)
    position = {
        "schema_version": 2,
        "phase": "complete",
        "book_id": manifest["book_id"],
        "chapter": chapter,
        **identity,
        "artifact_sha256": artifact_digest,
        "artifact_meta_sha256": meta_digest,
        "artifact_bytes": artifact.stat().st_size,
        "artifact_store": "r2",
        "artifact_bucket": store.get("bucket"),
        "artifact_r2_key": artifact_r2_key,
        "artifact_meta_r2_key": artifact_meta_r2_key,
        "qa": "pass",
        "recovered": bool(recovered),
        "completed_at": now_iso(),
        "run_id": run_id or os.getenv("GITHUB_RUN_ID"),
    }
    saved = save_checkpoint(
        PROJECT,
        source_name(manifest),
        scope=scope,
        status="success",
        position=position,
        dropbox_path=None,
        last_error=None,
        core_url=core_url,
    )
    durable = get_checkpoint(PROJECT, scope, core_url=core_url)
    durable_position = durable.get("position") if isinstance(durable, dict) else None
    if not isinstance(durable_position, dict):
        raise RuntimeError("chapter D1 checkpoint not visible after save")
    if durable_position.get("semantic_input_sha256") != identity["semantic_input_sha256"]:
        raise RuntimeError("chapter D1 semantic identity round-trip mismatch")
    if durable_position.get("artifact_sha256") != artifact_digest:
        raise RuntimeError("chapter D1 artifact hash round-trip mismatch")
    if durable_position.get("artifact_meta_sha256") != meta_digest:
        raise RuntimeError("chapter D1 sidecar hash round-trip mismatch")
    if durable_position.get("artifact_r2_key") != artifact_r2_key:
        raise RuntimeError("chapter D1 R2 key round-trip mismatch")
    return {"checkpoint": saved, "verified": durable}


def save_chapter_failure(
    manifest: dict[str, Any],
    chapter: int,
    error: str,
    *,
    run_id: str | None = None,
    core_url: str | None = None,
) -> dict[str, Any]:
    scope = chapter_scope(manifest, chapter)
    position = {
        "schema_version": 2,
        "phase": "failed",
        "book_id": manifest["book_id"],
        "chapter": chapter,
        "failed_at": now_iso(),
        "run_id": run_id or os.getenv("GITHUB_RUN_ID"),
    }
    return save_checkpoint(
        PROJECT,
        source_name(manifest),
        scope=scope,
        status="failed",
        position=position,
        last_error=error,
        core_url=core_url,
    )


def sync_book_main(
    manifest: dict[str, Any], state: dict[str, Any], *, core_url: str | None = None
) -> dict[str, Any]:
    prepared = state.get("prepared_source_parts") or {}
    editing = state.get("editing") or {}
    verified = state.get("verified_original_chapters") or {}
    released = int(editing.get("released_original_chapters_through") or 0)
    edited = int(editing.get("edited_source_parts_through") or 0)
    prepared_through = int(prepared.get("through") or 0)
    verified_through = int(verified.get("through") or 0)
    status = "success" if released and released >= verified_through else "running"
    if prepared_through and edited < prepared_through:
        status = "running"
    store = artifact_store_info(manifest)
    position = {
        "schema_version": 2,
        "book_id": manifest["book_id"],
        "title": manifest.get("title"),
        "pipeline_version": state.get("pipeline_version") or (manifest.get("editorial") or {}).get("pipeline_version"),
        "prepared_source_parts_through": prepared_through,
        "edited_source_parts_through": edited,
        "released_original_chapters_through": released,
        "verified_original_chapters_through": verified_through,
        "story_bible_version": editing.get("story_bible_version") or (manifest.get("editorial") or {}).get("story_bible_version"),
        "next_action": state.get("next_action"),
        "artifact_store": "r2",
        "artifact_bucket": store.get("bucket"),
        "artifact_prefix": store.get("prefix"),
        "human_projection": manifest.get("human_projection"),
        "git_sha": os.getenv("GITHUB_SHA"),
        "run_id": os.getenv("GITHUB_RUN_ID"),
    }
    scope = main_scope(manifest)
    checkpoint = save_checkpoint(
        PROJECT,
        source_name(manifest),
        scope=scope,
        status=status,
        position=position,
        dropbox_path=None,
        last_error=None,
        core_url=core_url,
    )
    durable = get_checkpoint(PROJECT, scope, core_url=core_url)
    durable_position = durable.get("position") if isinstance(durable, dict) else None
    if not isinstance(durable_position, dict) or durable_position.get("book_id") != manifest["book_id"]:
        raise RuntimeError("book D1 checkpoint round-trip mismatch")
    report_status(
        source_name(manifest),
        status,
        run_id=os.getenv("GITHUB_RUN_ID"),
        detail={"scope": scope, "position": position},
        core_url=core_url,
    )
    return {"status": status, "checkpoint": checkpoint, "verified": durable}


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--book", default=str(DEFAULT_MANIFEST), help="Book manifest JSON")
    parser.add_argument("--core-url", default=os.environ.get("RUNNER3_CORE_URL"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sync-main"); add_common(p); p.add_argument("--state", default=str(ROOT / "story_pipeline" / "state.json"))
    p = sub.add_parser("status"); add_common(p); p.add_argument("--chapter", type=int, required=True)
    p = sub.add_parser("prepare-sidecar"); add_common(p); p.add_argument("--chapter", type=int, required=True); p.add_argument("--source-file", required=True); p.add_argument("--artifact-file", required=True); p.add_argument("--meta-out", required=True); p.add_argument("--config-file", action="append", default=[]); p.add_argument("--model")
    p = sub.add_parser("decision"); add_common(p); p.add_argument("--chapter", type=int, required=True); p.add_argument("--source-file", required=True); p.add_argument("--artifact-file"); p.add_argument("--artifact-meta-file"); p.add_argument("--config-file", action="append", default=[]); p.add_argument("--model")
    p = sub.add_parser("complete"); add_common(p); p.add_argument("--chapter", type=int, required=True); p.add_argument("--source-file", required=True); p.add_argument("--artifact-file", required=True); p.add_argument("--artifact-meta-file", required=True); p.add_argument("--artifact-r2-key", required=True); p.add_argument("--artifact-meta-r2-key", required=True); p.add_argument("--config-file", action="append", default=[]); p.add_argument("--model"); p.add_argument("--recovered", action="store_true")
    p = sub.add_parser("fail"); add_common(p); p.add_argument("--chapter", type=int, required=True); p.add_argument("--error", required=True)

    args = parser.parse_args()
    manifest = load_manifest(args.book)
    if args.command == "sync-main":
        emit(sync_book_main(manifest, read_json(args.state), core_url=args.core_url))
    elif args.command == "status":
        emit({"ok": True, "checkpoint": get_chapter(manifest, args.chapter, core_url=args.core_url)})
    elif args.command == "prepare-sidecar":
        sidecar = build_sidecar(manifest, args.chapter, source_file=args.source_file, artifact_file=args.artifact_file, config_files=args.config_file, model=args.model)
        write_json(args.meta_out, sidecar)
        emit({"ok": True, "meta_out": args.meta_out, "sidecar": sidecar})
    elif args.command == "decision":
        emit(inspect_resume(manifest, args.chapter, source_file=args.source_file, artifact_file=args.artifact_file, artifact_meta_file=args.artifact_meta_file, config_files=args.config_file, model=args.model, core_url=args.core_url))
    elif args.command == "complete":
        emit(save_chapter_complete(manifest, args.chapter, source_file=args.source_file, artifact_file=args.artifact_file, artifact_meta_file=args.artifact_meta_file, artifact_r2_key=args.artifact_r2_key, artifact_meta_r2_key=args.artifact_meta_r2_key, config_files=args.config_file, model=args.model, recovered=args.recovered, core_url=args.core_url))
    elif args.command == "fail":
        emit({"ok": True, "checkpoint": save_chapter_failure(manifest, args.chapter, args.error, core_url=args.core_url)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
