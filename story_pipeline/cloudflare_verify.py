import json, pathlib, re, sys

LOCKED = ['Phương Lâm','Mộng Yểm Không Gian','Yagami Iori','Kusanagi Kyo','Nest Sound']

# Units must not be silently converted. Example: "200 cân" -> "200 kg" is a hard failure
# even though the numeric token 200 itself was preserved.
UNIT_PATTERN = r'(?:%|phần\s+trăm|giây|phút|giờ|ngày|tháng|năm|cân|kg|kilogram|gram|g|mét|meter|m|cm|km|điểm|cấp|lần|người|bình|viên|tầng)'
COMPARATORS = ['hơn', 'trên', 'dưới', 'ít nhất', 'tối đa', 'không quá', 'không dưới']

# High-signal convert residue that should not survive a deep Vietnamese rewrite.
CONVERT_RED_FLAGS = [
    'không gian trong đó',
    'bản vật phẩm đối',
    'mười phần',
    'kỹ năng phóng thích',
    'hạ thấp 20',
    'cái này trang bị',
    'chói tai nghiền nát thanh âm',
    'tại 30 giây bên trong',
]

# Semantic anchors: only checked when the source contains the left-side concept.
# The edited text may use natural Vietnamese synonyms, but may not erase the meaning.
SEMANTIC_GROUPS = [
    (['không thể'], ['không thể', 'không được']),
    (['vô hiệu'], ['vô hiệu', 'không có tác dụng', 'không hiệu quả']),
    (['hạ thấp', 'giảm'], ['giảm', 'hạ']),
    (['tăng'], ['tăng']),
    (['không có lập tức', 'không lập tức'], ['không trang bị ngay', 'không lập tức', 'chưa trang bị ngay']),
]


def compact(s):
    return re.sub(r'\s+', ' ', s.replace('\u00a0', ' ').replace('\u202f', ' ')).strip()


def nums(s):
    return re.findall(r'(?<!\w)\d+(?:[.,]\d+)?(?!\w)', compact(s))


def number_unit_pairs(s):
    text = compact(s).lower()
    pat = rf'(?<!\w)(\d+(?:[.,]\d+)?)\s*({UNIT_PATTERN})(?!\w)'
    return [(n, re.sub(r'\s+', ' ', u)) for n, u in re.findall(pat, text, flags=re.I)]


def comparator_pairs(s):
    text = compact(s).lower()
    result = []
    for comp in COMPARATORS:
        pat = rf'\b{re.escape(comp)}\s+(\d+(?:[.,]\d+)?)\s*({UNIT_PATTERN})(?!\w)'
        for n, unit in re.findall(pat, text, flags=re.I):
            result.append((comp, n, re.sub(r'\s+', ' ', unit.lower())))
    return result


def semantic_missing(raw, edit):
    r, e = compact(raw).lower(), compact(edit).lower()
    misses = []
    for source_forms, output_forms in SEMANTIC_GROUPS:
        if any(x in r for x in source_forms) and not any(x in e for x in output_forms):
            misses.append({'source_concept': source_forms, 'accepted_output': output_forms})
    return misses


def main():
    src = pathlib.Path('story_pipeline/benchmark_input')
    out = pathlib.Path('story_pipeline/benchmark_output')
    rows = []
    failed = False

    for rawf in sorted(src.glob('*.txt'))[:3]:
        editf = out / rawf.name
        if not editf.exists():
            rows.append({'file': rawf.name, 'pass': False, 'error': 'missing output'})
            failed = True
            continue

        raw = rawf.read_text(encoding='utf-8')
        edit = editf.read_text(encoding='utf-8')
        raw_c, edit_c = compact(raw), compact(edit)

        missing = [x for x in LOCKED if x in raw_c and x not in edit_c]
        nraw, nedit = nums(raw_c), nums(edit_c)
        uraw, uedit = number_unit_pairs(raw_c), number_unit_pairs(edit_c)
        craw, cedit = comparator_pairs(raw_c), comparator_pairs(edit_c)
        sem_missing = semantic_missing(raw_c, edit_c)
        red_flags = [x for x in CONVERT_RED_FLAGS if x in edit_c.lower()]
        ratio = len(edit_c) / max(1, len(raw_c))

        checks = {
            'locked_terms': not missing,
            'numbers_exact': nraw == nedit,
            'number_units_exact': uraw == uedit,
            'comparators_exact': craw == cedit,
            'semantic_anchors': not sem_missing,
            'no_convert_residue': not red_flags,
            'length_sane': 0.65 <= ratio <= 1.45,
            'nonempty': len(edit_c) > 80,
        }
        ok = all(checks.values())
        rows.append({
            'file': rawf.name,
            'pass': ok,
            'checks': checks,
            'length_ratio': round(ratio, 3),
            'missing_locked_terms': missing,
            'numbers_raw': nraw,
            'numbers_edited': nedit,
            'number_units_raw': uraw,
            'number_units_edited': uedit,
            'comparators_raw': craw,
            'comparators_edited': cedit,
            'semantic_missing': sem_missing,
            'convert_red_flags': red_flags,
        })
        failed |= not ok

    (out / 'qc.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    if failed:
        sys.exit(2)


if __name__ == '__main__':
    main()
