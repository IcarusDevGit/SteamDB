"""Pure tag/category normalization used before validated persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from workflow_paths import exceptions_path


@dataclass(slots=True)
class TagResolution:
    ids: list[int] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    missing: dict[int, str] = field(default_factory=dict)


def load_exceptions(path: str | Path | None = None) -> dict[str, int]:
    selected = Path(path) if path else exceptions_path()
    if not selected.exists():
        return {}
    with selected.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {str(name).strip().lower(): int(tag_id) for name, tag_id in data.items()}


def resolve_tags(
    names: list[str],
    tags_by_name: dict[str, int],
    *,
    exceptions: dict[str, int] | None = None,
    canonical_by_id: dict[int, str] | None = None,
) -> TagResolution:
    known = {name.lower(): (name, int(tag_id)) for name, tag_id in tags_by_name.items()}
    aliases = exceptions or {}
    canonical = canonical_by_id or {tag_id: name for name, tag_id in tags_by_name.items()}
    result = TagResolution()
    seen_ids: set[int] = set()
    seen_unresolved: set[str] = set()
    for raw_name in names:
        name = raw_name.strip()
        if not name:
            continue
        key = name.lower()
        resolved = known.get(key)
        if resolved:
            canonical_name, tag_id = resolved
        elif key in aliases:
            tag_id = int(aliases[key])
            canonical_name = canonical.get(tag_id, name)
        else:
            if key not in seen_unresolved:
                result.unresolved.append(name)
                seen_unresolved.add(key)
            continue
        if tag_id not in seen_ids:
            result.ids.append(tag_id)
            result.names.append(canonical_name)
            seen_ids.add(tag_id)
    return result


def merge_category_ids(
    category_ids: list[int],
    tags_by_name: dict[str, int],
    resolved_names: dict[int, str],
) -> TagResolution:
    canonical = {int(tag_id): name for name, tag_id in tags_by_name.items()}
    known_by_name = {
        name.strip().casefold(): (name, int(tag_id))
        for name, tag_id in tags_by_name.items()
    }
    result = TagResolution()
    seen_ids: set[int] = set()
    seen_names: set[str] = set()
    for category_id in dict.fromkeys(int(value) for value in category_ids):
        name = canonical.get(category_id) or resolved_names.get(category_id)
        if not name:
            result.unresolved.append(f"Category ID {category_id}")
            continue
        known = known_by_name.get(name.strip().casefold())
        if known:
            canonical_name, selected_id = known
        else:
            canonical_name, selected_id = name, category_id
        name_key = canonical_name.strip().casefold()
        if selected_id in seen_ids or name_key in seen_names:
            continue
        result.ids.append(selected_id)
        result.names.append(canonical_name)
        seen_ids.add(selected_id)
        seen_names.add(name_key)
        if selected_id not in canonical:
            result.missing[selected_id] = canonical_name
    return result
