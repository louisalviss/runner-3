#!/usr/bin/env python3
"""YouTube STORY/NOVEL transcript -> editorial chapters -> EPUB preparation.

This adapter consumes only an already verified youtube-read transcript artifact.
Comments are intentionally outside the contract. Source packets are transport /
editing units, never chapter boundaries. Final chapters are assembled only after
editorial scene-boundary decisions and continuity-state carry-forward.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from story_epub import build_epub

SCHEMA = "youtube-story-editorial-v1"
PACKET_SCHEMA = "youtube-story-source-packet-v1"
EDIT_SCHEMA = "youtube-story-edit-v1"
MIN_COVERAGE = 0.80
DEFAULT_TARGET_CHARS = 18000
DEFAULT_MIN_PACKET_CHARS = 12000
DEFAULT_MAX_PACKET_CHARS = 24000
DEFAULT_MIN_CHAPTER_CHARS = 18000
DEFAULT_MAX_CHAPTER_CHARS = 60000

SYSTEM_PROMPT = """Bạn là biên tập viên truyện tiên hiệp/huyền huyễn/web-novel tiếng Việt cấp xuất bản.
Nhiệm vụ: chuyển transcript tự động thành văn xuôi truyện tự nhiên, liền mạch, dễ đọc như tiểu thuyết; KHÔNG phải tóm tắt.

BẮT BUỘC:
- Giữ toàn bộ tình tiết có giá trị, quan hệ nhân quả, chủ thể hành động, lời thoại quan trọng, tên riêng, số liệu, cảnh giới/cấp bậc, công pháp/kỹ năng, vật phẩm, phe phái, địa điểm và logic hệ thống có trong nguồn.
- Không thêm sự kiện, suy nghĩ, cảm xúc, miêu tả, giải thích hay kết luận mà nguồn không hỗ trợ.
- Được phép sửa câu, gộp/tách câu, phục hồi dấu câu và đại từ để tiếng Việt tự nhiên.
- Bỏ nhiễu caption, lặp do TTS, filler vô nghĩa, intro/outro kênh, CTA like/subscribe và tín hiệu phi truyện.
- Không viết nhận xét, phân tích, summary, lời dẫn của biên tập viên hay bình luận YouTube.
- Nếu nguồn mơ hồ, giữ cách diễn đạt trung tính thay vì tự đoán.
- Packet có thể bắt đầu/kết thúc giữa một cảnh; không tự tạo kết thúc cảnh chỉ để văn đẹp.

Bạn phải trả về đúng MỘT JSON object, không markdown, không code fence, theo schema:
{
  "edited_body": "văn xuôi đã biên tập",
  "chapter_title_hint": "gợi ý tiêu đề ngắn nếu packet chứa mở đầu/chuyển cảnh rõ, nếu không để rỗng",
  "scene_break_after": false,
  "continuity_state": {
    "characters": ["tên + vai trò/trạng thái ngắn"],
    "factions": ["phe/phái + quan hệ ngắn"],
    "realms": ["nhân vật: cảnh giới/cấp hiện tại nếu biết"],
    "techniques": ["công pháp/kỹ năng quan trọng"],
    "items": ["vật phẩm quan trọng + chủ sở hữu/trạng thái"],
    "locations": ["địa điểm quan trọng"],
    "terminology": ["thuật ngữ chuẩn hóa cần giữ"],
    "unresolved_threads": ["mạch truyện chưa giải quyết"],
    "timeline_checkpoint": "điểm thời gian/sự kiện hiện tại",
    "current_scene": "cảnh/địa điểm/chủ thể hiện tại"
  }
}
continuity_state phải là trạng thái ĐẦY ĐỦ hiện tại sau packet, ngắn gọn và kế thừa dữ kiện còn hiệu lực từ trạng thái đầu vào."""

STATE_LIST_FIELDS = (
    "characters",
    "factions",
    "realms",
    "techniques",
    "items",
    "locations",
    "terminology",
    "unresolved_threads",
)
STATE_TEXT_FIELDS = ("timeline_checkpoint", "current_scene")
NOISE_RE = re.compile(r"^\s*\[[^\]\n]{1,48}\]\s*$")
END_PUNCT_RE = re.compile(r"[.!?…][\"'”’)]?\s*$")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as handle:
        handle.write(data)
        tmp = Path(handle.name)
    tmp.replace(target)


def normalize_caption(text: str) -> str:
    return " ".join(str(text or "").replace("\r", " ").replace("\n", " ").split())


def validate_transcript(obj: dict[str, Any], expected_video_id: str | None = None, min_coverage: float = MIN_COVERAGE) -> dict[str, Any]:
    failures: list[str] = []
    video_id = str(obj.get("video_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        failures.append("invalid_video_id")
    if expected_video_id and video_id != expected_video_id:
        failures.append("video_id_mismatch")
    if obj.get("ok") is not True:
        failures.append("transcript_not_ok")
    if obj.get("identity_validated") is not True:
        failures.append("identity_not_validated")
    try:
        coverage = float(obj.get("coverage_ratio"))
    except (TypeError, ValueError):
        coverage = 0.0
    if coverage < min_coverage:
        failures.append("coverage_below_threshold")
    segments = obj.get("segments")
    if not isinstance(segments, list) or not segments:
        failures.append("segments_missing")
        segments = []
    text = str(obj.get("text") or "")
    if not text.strip():
        failures.append("text_missing")
    if segments and int(obj.get("segment_count") or 0) != len(segments):
        failures.append("segment_count_mismatch")
    return {
        "ok": not failures,
        "failures": failures,
        "video_id": video_id,
        "coverage_ratio": coverage,
        "segment_count": len(segments),
        "text_chars": len(text),
        "transcript_sha256": sha256_text(text),
    }


def _packet_from_segments(packet_id: int, start_index: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    pieces = [normalize_caption(row.get("text", "")) for row in rows]
    pieces = [piece for piece in pieces if piece]
    text = " ".join(pieces).strip()
    start_ms = int(rows[0].get("start_ms") or 0)
    last = rows[-1]
    end_ms = int(last.get("start_ms") or 0) + max(0, int(last.get("duration_ms") or 0))
    noise_cues = [piece for piece in pieces if NOISE_RE.fullmatch(piece)]
    return {
        "schema": PACKET_SCHEMA,
        "packet_id": packet_id,
        "segment_start": start_index,
        "segment_end": start_index + len(rows) - 1,
        "segment_count": len(rows),
        "start_ms": start_ms,
        "end_ms": end_ms,
        "source_text": text,
        "source_chars": len(text),
        "source_sha256": sha256_text(text),
        "noise_cues": noise_cues,
    }


def packetize(
    segments: list[dict[str, Any]],
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    min_chars: int = DEFAULT_MIN_PACKET_CHARS,
    max_chars: int = DEFAULT_MAX_PACKET_CHARS,
) -> list[dict[str, Any]]:
    if not (1000 <= min_chars <= target_chars <= max_chars):
        raise ValueError("packet char bounds must satisfy 1000 <= min <= target <= max")
    packets: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    start_index = 0
    for index, segment in enumerate(segments):
        text = normalize_caption(segment.get("text", ""))
        if not current:
            start_index = index
        current.append(segment)
        current_chars += len(text) + (1 if text else 0)
        next_start = None
        if index + 1 < len(segments):
            try:
                next_start = int(segments[index + 1].get("start_ms") or 0)
            except Exception:
                next_start = None
        end_ms = int(segment.get("start_ms") or 0) + max(0, int(segment.get("duration_ms") or 0))
        gap_ms = max(0, (next_start - end_ms)) if next_start is not None else 0
        natural = bool(END_PUNCT_RE.search(text)) or gap_ms >= 1200
        should_break = current_chars >= max_chars or (current_chars >= target_chars and natural)
        if should_break and current_chars >= min_chars:
            packets.append(_packet_from_segments(len(packets) + 1, start_index, current))
            current = []
            current_chars = 0
    if current:
        if packets and current_chars < max(1800, min_chars // 3):
            prior = packets.pop()
            merged_rows = segments[prior["segment_start"] : current[-1] and (start_index + len(current))]
            packets.append(_packet_from_segments(prior["packet_id"], prior["segment_start"], merged_rows))
        else:
            packets.append(_packet_from_segments(len(packets) + 1, start_index, current))
    return packets


def _clean_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for field in STATE_LIST_FIELDS:
        raw = value.get(field)
        if not isinstance(raw, list):
            continue
        seen: set[str] = set()
        items: list[str] = []
        for item in raw:
            text = " ".join(str(item).split())[:360]
            if text and text not in seen:
                seen.add(text)
                items.append(text)
            if len(items) >= 80:
                break
        if items:
            out[field] = items
    for field in STATE_TEXT_FIELDS:
        text = " ".join(str(value.get(field) or "").split())[:1000]
        if text:
            out[field] = text
    if len(json.dumps(out, ensure_ascii=False)) > 20000:
        raise ValueError("continuity_state exceeds 20k serialized characters")
    return out


def _completion_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""
    for key in ("response", "text"):
        if isinstance(payload.get(key), str) and payload[key].strip():
            return payload[key]
    result = payload.get("result")
    if isinstance(result, dict):
        nested = _completion_text(result)
        if nested:
            return nested
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        content = message.get("content")
        if isinstance(content, str):
            return content
    return ""


def _parse_json_object(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
        value = re.sub(r"\s*```$", "", value)
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(value[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("editor response is not a JSON object")


def call_editor(endpoint: str, model: str, messages: list[dict[str, str]], *, max_tokens: int, timeout: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.15,
        "max_tokens": max_tokens,
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    bearer = os.environ.get("YOUTUBE_STORY_EDITOR_BEARER", "").strip()
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"editor HTTP {exc.code}: {body[:1200]}") from exc
    outer = json.loads(raw)
    completion = _completion_text(outer)
    if not completion.strip():
        raise RuntimeError("editor returned no text completion")
    return _parse_json_object(completion)


def _editor_messages(packet: dict[str, Any], state: dict[str, Any], previous_tail: str) -> list[dict[str, str]]:
    user = (
        f"PACKET_ID: {packet['packet_id']}\n"
        f"TIME_RANGE_MS: {packet['start_ms']}..{packet['end_ms']}\n"
        "CONTINUITY_STATE_BEFORE:\n"
        + json.dumps(state, ensure_ascii=False)
        + "\n\nPREVIOUS_EDITED_TAIL (chỉ để nối giọng, không được lặp lại):\n"
        + previous_tail[-1800:]
        + "\n\nTRANSCRIPT_PACKET:\n"
        + packet["source_text"]
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def validate_edit(packet: dict[str, Any], value: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    body = str(value.get("edited_body") or "").strip()
    if not body:
        errors.append("edited_body_empty")
    ratio = len(body) / max(1, int(packet["source_chars"]))
    if body and (ratio < 0.50 or ratio > 1.70):
        errors.append(f"edited_length_ratio:{ratio:.3f}")
    title = " ".join(str(value.get("chapter_title_hint") or "").split())[:160]
    state = _clean_state(value.get("continuity_state"))
    cleaned = {
        "schema": EDIT_SCHEMA,
        "packet_id": int(packet["packet_id"]),
        "input_sha256": packet["source_sha256"],
        "source_chars": int(packet["source_chars"]),
        "edited_body": body,
        "edited_chars": len(body),
        "length_ratio": round(ratio, 4),
        "chapter_title_hint": title,
        "scene_break_after": bool(value.get("scene_break_after")),
        "continuity_state": state,
    }
    return cleaned, errors


def load_numbered(directory: Path, pattern: str) -> list[dict[str, Any]]:
    return [read_json(path) for path in sorted(directory.glob(pattern))]


def cmd_prepare(args: argparse.Namespace) -> int:
    work = Path(args.work)
    packets_dir = work / "packets"
    packets_dir.mkdir(parents=True, exist_ok=True)
    obj = read_json(args.transcript)
    validated = validate_transcript(obj, args.expected_video_id, args.min_coverage)
    if not validated["ok"]:
        print(json.dumps({"ok": False, "stage": "prepare", **validated}, ensure_ascii=False))
        return 2
    packets = packetize(
        obj["segments"],
        target_chars=args.target_chars,
        min_chars=args.min_packet_chars,
        max_chars=args.max_packet_chars,
    )
    for old in packets_dir.glob("packet-*.json"):
        old.unlink()
    for packet in packets:
        atomic_json(packets_dir / f"packet-{packet['packet_id']:04d}.json", packet)
    source = {
        "schema": SCHEMA,
        "stage": "prepared",
        "video_id": validated["video_id"],
        "source_url": args.source_url or "",
        "title": args.title or "",
        "author": args.author or "",
        "language": str(obj.get("language") or "vi"),
        "coverage_ratio": validated["coverage_ratio"],
        "segment_count": validated["segment_count"],
        "transcript_chars": validated["text_chars"],
        "transcript_sha256": validated["transcript_sha256"],
        "packet_count": len(packets),
        "comments_policy": "skip",
        "media_downloaded": bool(obj.get("media_downloaded")),
        "video_rendered": bool(obj.get("video_rendered")),
    }
    atomic_json(work / "source.json", source)
    print(json.dumps({"ok": True, "stage": "prepare", **source}, ensure_ascii=False))
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    work = Path(args.work)
    packets = load_numbered(work / "packets", "packet-*.json")
    if not packets:
        raise SystemExit("no prepared packets")
    edits_dir = work / "edits"
    edits_dir.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {}
    previous_tail = ""
    completed = 0
    for packet in packets:
        path = edits_dir / f"packet-{packet['packet_id']:04d}.edit.json"
        if path.exists() and not args.force:
            existing = read_json(path)
            if existing.get("input_sha256") == packet.get("source_sha256") and existing.get("edited_body"):
                state = _clean_state(existing.get("continuity_state")) or state
                previous_tail = str(existing.get("edited_body") or "")[-1800:]
                completed += 1
                continue
        raw = call_editor(
            args.endpoint,
            args.model,
            _editor_messages(packet, state, previous_tail),
            max_tokens=args.max_tokens,
            timeout=args.timeout,
        )
        edit, errors = validate_edit(packet, raw)
        if errors:
            atomic_json(path.with_suffix(".failed.json"), {"packet": packet, "editor": raw, "errors": errors})
            print(json.dumps({"ok": False, "stage": "edit", "packet_id": packet["packet_id"], "errors": errors}, ensure_ascii=False))
            return 3
        atomic_json(path, edit)
        state = edit["continuity_state"] or state
        previous_tail = edit["edited_body"][-1800:]
        completed += 1
        print(json.dumps({"ok": True, "stage": "edit", "packet_id": packet["packet_id"], "completed": completed, "total": len(packets), "edited_chars": edit["edited_chars"], "scene_break_after": edit["scene_break_after"]}, ensure_ascii=False), flush=True)
    atomic_json(work / "continuity-final.json", state)
    return 0


def _chapter_record(index: int, group: list[dict[str, Any]], packets_by_id: dict[int, dict[str, Any]], forced_boundary: bool) -> dict[str, Any]:
    first_id = int(group[0]["packet_id"])
    last_id = int(group[-1]["packet_id"])
    title_hint = next((str(row.get("chapter_title_hint") or "").strip() for row in group if str(row.get("chapter_title_hint") or "").strip()), "")
    title = title_hint or f"Chương {index}"
    body = "\n\n".join(str(row["edited_body"]).strip() for row in group).strip()
    return {
        "chapter": index,
        "title": title,
        "body": body,
        "body_chars": len(body),
        "source_packet_start": first_id,
        "source_packet_end": last_id,
        "source_packet_ids": list(range(first_id, last_id + 1)),
        "start_ms": int(packets_by_id[first_id]["start_ms"]),
        "end_ms": int(packets_by_id[last_id]["end_ms"]),
        "forced_boundary": forced_boundary,
    }


def cmd_assemble(args: argparse.Namespace) -> int:
    work = Path(args.work)
    packets = load_numbered(work / "packets", "packet-*.json")
    edits = load_numbered(work / "edits", "packet-*.edit.json")
    if not packets or len(edits) != len(packets):
        print(json.dumps({"ok": False, "stage": "assemble", "error": "packet_edit_count_mismatch", "packets": len(packets), "edits": len(edits)}))
        return 2
    packets_by_id = {int(row["packet_id"]): row for row in packets}
    chapters_dir = work / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    for old in chapters_dir.glob("chapter-*.json"):
        old.unlink()
    groups: list[tuple[list[dict[str, Any]], bool]] = []
    current: list[dict[str, Any]] = []
    chars = 0
    for edit in edits:
        current.append(edit)
        chars += int(edit.get("edited_chars") or 0)
        natural_break = bool(edit.get("scene_break_after")) and chars >= args.min_chapter_chars
        forced = chars >= args.max_chapter_chars
        if natural_break or forced:
            groups.append((current, bool(forced and not natural_break)))
            current = []
            chars = 0
    if current:
        if groups and chars < max(5000, args.min_chapter_chars // 3):
            previous, previous_forced = groups.pop()
            groups.append((previous + current, previous_forced))
        else:
            groups.append((current, False))
    chapters: list[dict[str, Any]] = []
    for index, (group, forced) in enumerate(groups, 1):
        chapter = _chapter_record(index, group, packets_by_id, forced)
        atomic_json(chapters_dir / f"chapter-{index:04d}.json", chapter)
        chapters.append(chapter)
    manifest = {
        "schema": SCHEMA,
        "stage": "assembled",
        "chapter_count": len(chapters),
        "packet_count": len(packets),
        "forced_boundaries": sum(bool(row["forced_boundary"]) for row in chapters),
        "edited_chars": sum(int(row["body_chars"]) for row in chapters),
    }
    atomic_json(work / "assemble.json", manifest)
    print(json.dumps({"ok": True, **manifest}, ensure_ascii=False))
    return 0


def cmd_qa(args: argparse.Namespace) -> int:
    work = Path(args.work)
    source = read_json(work / "source.json")
    packets = load_numbered(work / "packets", "packet-*.json")
    edits = load_numbered(work / "edits", "packet-*.edit.json")
    chapters = load_numbered(work / "chapters", "chapter-*.json")
    errors: list[str] = []
    warnings: list[str] = []
    if not packets or len(edits) != len(packets):
        errors.append("packet_edit_count_mismatch")
    packet_ids = [int(row["packet_id"]) for row in packets]
    if packet_ids != list(range(1, len(packets) + 1)):
        errors.append("packet_ids_not_contiguous")
    edits_by_id = {int(row["packet_id"]): row for row in edits}
    for packet in packets:
        pid = int(packet["packet_id"])
        edit = edits_by_id.get(pid)
        if not edit:
            errors.append(f"missing_edit:{pid}")
            continue
        if edit.get("input_sha256") != packet.get("source_sha256"):
            errors.append(f"stale_edit:{pid}")
        ratio = float(edit.get("length_ratio") or 0)
        if ratio < 0.50 or ratio > 1.70:
            errors.append(f"edit_ratio:{pid}:{ratio:.3f}")
    used: list[int] = []
    for chapter in chapters:
        used.extend(int(x) for x in chapter.get("source_packet_ids") or [])
        body = str(chapter.get("body") or "")
        if not body.strip():
            errors.append(f"empty_chapter:{chapter.get('chapter')}")
        if re.search(r"(?i)\b(bình luận\s*\d*|comment(s)?\s*:)", body):
            warnings.append(f"possible_comment_text:chapter:{chapter.get('chapter')}")
        if re.search(r"(?i)đăng ký kênh|like\s*(và|&)\s*subscribe|nhấn chuông", body):
            warnings.append(f"possible_channel_cta:chapter:{chapter.get('chapter')}")
        if re.search(r"\[(âm nhạc|music|la hét|tiếng vỗ tay)\]", body, flags=re.I):
            warnings.append(f"caption_noise:chapter:{chapter.get('chapter')}")
    if sorted(used) != packet_ids or len(used) != len(set(used)):
        errors.append("chapter_packet_coverage_not_exact")
    source_chars = sum(int(row.get("source_chars") or 0) for row in packets)
    edited_chars = sum(int(row.get("edited_chars") or 0) for row in edits)
    global_ratio = edited_chars / max(1, source_chars)
    if global_ratio < 0.55 or global_ratio > 1.60:
        errors.append(f"global_length_ratio:{global_ratio:.3f}")
    expected_sha = args.expect_transcript_sha256 or ""
    if expected_sha and source.get("transcript_sha256") != expected_sha:
        errors.append("transcript_sha256_mismatch")
    if source.get("comments_policy") != "skip":
        errors.append("comments_policy_not_skip")
    report = {
        "schema": SCHEMA,
        "stage": "qa",
        "ok": not errors,
        "errors": errors,
        "warnings": sorted(set(warnings)),
        "packet_count": len(packets),
        "chapter_count": len(chapters),
        "source_chars": source_chars,
        "edited_chars": edited_chars,
        "global_length_ratio": round(global_ratio, 4),
        "transcript_sha256": source.get("transcript_sha256"),
        "comments_policy": source.get("comments_policy"),
    }
    atomic_json(work / "qa.json", report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 4


def cmd_epub(args: argparse.Namespace) -> int:
    work = Path(args.work)
    qa = read_json(work / "qa.json")
    if qa.get("ok") is not True and not args.allow_failed_qa:
        print(json.dumps({"ok": False, "stage": "epub", "error": "qa_not_passed"}))
        return 2
    source = read_json(work / "source.json")
    chapters = load_numbered(work / "chapters", "chapter-*.json")
    title = args.title or str(source.get("title") or "Truyện từ YouTube")
    author = args.author or str(source.get("author") or "Nguồn YouTube")
    source_url = args.source_url or str(source.get("source_url") or "")
    note_parts = [f"Video ID: {source.get('video_id')}", f"Transcript SHA-256: {source.get('transcript_sha256')}"]
    if source_url:
        note_parts.insert(0, source_url)
    result = build_epub(
        chapters,
        args.output,
        title=title,
        author=author,
        language=str(source.get("language") or "vi"),
        source_note=" · ".join(note_parts),
        identifier_seed=f"youtube:{source.get('video_id')}:{source.get('transcript_sha256')}",
    )
    result.update({"ok": True, "stage": "epub", "video_id": source.get("video_id"), "transcript_sha256": source.get("transcript_sha256")})
    atomic_json(work / "epub.json", result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--transcript", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--expected-video-id")
    p.add_argument("--source-url")
    p.add_argument("--title")
    p.add_argument("--author")
    p.add_argument("--min-coverage", type=float, default=MIN_COVERAGE)
    p.add_argument("--target-chars", type=int, default=DEFAULT_TARGET_CHARS)
    p.add_argument("--min-packet-chars", type=int, default=DEFAULT_MIN_PACKET_CHARS)
    p.add_argument("--max-packet-chars", type=int, default=DEFAULT_MAX_PACKET_CHARS)
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("edit")
    p.add_argument("--work", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--model", default="@cf/openai/gpt-oss-120b")
    p.add_argument("--max-tokens", type=int, default=9000)
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("assemble")
    p.add_argument("--work", required=True)
    p.add_argument("--min-chapter-chars", type=int, default=DEFAULT_MIN_CHAPTER_CHARS)
    p.add_argument("--max-chapter-chars", type=int, default=DEFAULT_MAX_CHAPTER_CHARS)
    p.set_defaults(func=cmd_assemble)

    p = sub.add_parser("qa")
    p.add_argument("--work", required=True)
    p.add_argument("--expect-transcript-sha256")
    p.set_defaults(func=cmd_qa)

    p = sub.add_parser("epub")
    p.add_argument("--work", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--title")
    p.add_argument("--author")
    p.add_argument("--source-url")
    p.add_argument("--allow-failed-qa", action="store_true")
    p.set_defaults(func=cmd_epub)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
