"""Discover and apply unresolved tag mappings to a reviewed CSV artifact."""

from __future__ import annotations

import asyncio
import csv
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import ValidateEntries
import db
from tag_resolution import load_exceptions
from request_scheduler import DEFAULT_POLICIES, ProviderGate
from workflow_clients import RealExtractionClients
from workflow_paths import exceptions_path
from workflow_progress import emit

from .apply_validated_csv import REQUIRED_FIELDS, verify_chart_evidence
from .common import UpdateResult


COMMAND = "tags"


def _key(value: str) -> str:
    return str(value).strip().casefold()


@dataclass(frozen=True, slots=True)
class Mapping:
    name: str
    tag_id: int
    source: str


def parse_explicit_mappings(values) -> dict[str, Mapping]:
    mappings: dict[str, Mapping] = {}
    ids: dict[int, str] = {}
    for value in values or ():
        if "=" not in value:
            raise ValueError(f"invalid mapping {value!r}; expected NAME=ID")
        name, raw_id = value.rsplit("=", 1)
        name = name.strip()
        try:
            tag_id = int(raw_id.strip())
        except ValueError as exc:
            raise ValueError(f"invalid mapping {value!r}; ID must be an integer") from exc
        if not name or tag_id <= 0:
            raise ValueError(f"invalid mapping {value!r}; NAME and a positive ID are required")
        key = _key(name)
        if key in mappings:
            raise ValueError(f"duplicate explicit mapping for {name!r}")
        if tag_id in ids and ids[tag_id] != key:
            raise ValueError(f"tag id {tag_id} has contradictory explicit names")
        mappings[key] = Mapping(name, tag_id, "explicit")
        ids[tag_id] = key
    return mappings


def _read_csv(path: Path):
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or ())
        missing = sorted(REQUIRED_FIELDS - set(fields))
        if missing:
            raise ValueError(f"missing required CSV fields: {', '.join(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError("CSV contains no records")
    return fields, rows


def _unresolved(rows) -> dict[str, str]:
    values = {}
    for row in rows:
        for name in row["unresolved_tags"].split(","):
            display = name.strip()
            if display:
                values.setdefault(_key(display), display)
    return values


def discover(unresolved, catalog, exceptions, steam_tags, explicit):
    known = {_key(name): Mapping(str(name).strip(), int(tag_id), "database")
             for name, tag_id in catalog.items()}
    canonical = {mapping.tag_id: mapping.name for mapping in known.values()}
    aliases = {
        _key(name): Mapping(canonical.get(int(tag_id), str(name).strip()), int(tag_id), "exception")
        for name, tag_id in exceptions.items()
    }
    steam = {_key(item["name"]): Mapping(str(item["name"]).strip(), int(item["id"]), "steam")
             for item in steam_tags}
    outcomes = {}
    for key in unresolved:
        outcomes[key] = known.get(key) or aliases.get(key) or steam.get(key) or explicit.get(key)
    return outcomes


def _atomic_write(path: Path, writer) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(descriptor)
    temp_path = Path(temporary)
    try:
        writer(temp_path)
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _rewrite(rows, outcomes):
    changed = 0
    for row in rows:
        names = [value.strip() for value in row["tags"].split(",") if value.strip()]
        try:
            ids = [int(value.strip()) for value in row["tag_ids"].split(",") if value.strip()]
        except ValueError as exc:
            raise ValueError("CSV contains an invalid tag id") from exc
        if len(names) != len(ids):
            raise ValueError("CSV contains mismatched tag names and identifiers")
        pairs = list(zip(ids, names))
        remaining = []
        for raw in row["unresolved_tags"].split(","):
            name = raw.strip()
            if not name:
                continue
            mapping = outcomes.get(_key(name))
            if mapping:
                pairs.append((mapping.tag_id, mapping.name))
            else:
                remaining.append(name)
        deduped = []
        seen = set()
        for pair in pairs:
            if pair[0] not in seen:
                deduped.append(pair)
                seen.add(pair[0])
        new_names = ", ".join(name for _, name in deduped)
        new_ids = ",".join(str(tag_id) for tag_id, _ in deduped)
        new_unresolved = ", ".join(dict.fromkeys(remaining))
        if (new_names, new_ids, new_unresolved) != (row["tags"], row["tag_ids"], row["unresolved_tags"]):
            changed += 1
        row["tags"], row["tag_ids"], row["unresolved_tags"] = new_names, new_ids, new_unresolved
    return changed


def resolve_csv(path, *, mappings=(), apply=False, database=db, client=None,
                validator=ValidateEntries.run_validation, exception_file=None, reporter=None,
                gate=None):
    path = Path(path)
    explicit = parse_explicit_mappings(mappings)
    fields, rows = _read_csv(path)
    unresolved = _unresolved(rows)
    catalog = database.load_catalog_snapshot().get("tags_by_name", {})
    known = {_key(name): int(tag_id) for name, tag_id in catalog.items()}
    for key, mapping in explicit.items():
        if key in known and known[key] != mapping.tag_id:
            raise ValueError(f"explicit mapping for {mapping.name!r} conflicts with database tag id {known[key]}")
    exception_path = Path(exception_file) if exception_file else exceptions_path()
    exceptions = load_exceptions(exception_path)
    preliminary = discover(unresolved, catalog, exceptions, (), {})
    needs_steam = any(value is None for value in preliminary.values())
    steam_tags = []
    if needs_steam:
        emit(reporter, "stage_started", operation="resolve_tags", stage="steam_tag_list")
        selected_client = client or RealExtractionClients()
        selected_gate = gate or ProviderGate(
            DEFAULT_POLICIES["steam_web"], provider="steam_web", reporter=reporter
        )
        steam_tags = asyncio.run(selected_gate.run(selected_client.tag_list))
        emit(reporter, "stage_completed", operation="resolve_tags", stage="steam_tag_list", tags=len(steam_tags))
    outcomes = discover(unresolved, catalog, exceptions, steam_tags, explicit)
    resolved = {key: value for key, value in outcomes.items() if value is not None}
    missing = [unresolved[key] for key, value in outcomes.items() if value is None]
    messages = tuple(
        [f"{unresolved[key]} -> {value.name} ({value.tag_id}, {value.source})"
         for key, value in sorted(resolved.items())]
        + [f"unresolved: {name}" for name in sorted(missing, key=str.casefold)]
    )
    if not apply:
        return UpdateResult("resolve tags", str(path), proposed=len(resolved), failed=len(missing), messages=messages)

    verify_chart_evidence(path)
    changed = _rewrite(rows, outcomes)
    if changed:
        def write_csv(target):
            with target.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        _atomic_write(path, write_csv)
        explicit_used = {unresolved[key]: mapping.tag_id for key, mapping in resolved.items()
                         if mapping.source == "explicit"}
        if explicit_used:
            payload = {}
            if exception_path.exists():
                payload = json.loads(exception_path.read_text(encoding="utf-8"))
            payload.update(explicit_used)
            _atomic_write(exception_path, lambda target: target.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"))
        result, final_csv, final_report = validator(path)
        messages += (f"CSV={final_csv}", f"REPORT={final_report}", f"validation={result.status.value}")
        validation_failed = result.status is not ValidateEntries.ValidationStatus.PASSED
    else:
        validation_failed = False
    return UpdateResult("resolve tags", str(path), proposed=len(resolved), applied=len(resolved),
                        failed=len(missing) + int(validation_failed), messages=messages)


def register_parser(subparsers):
    parser = subparsers.add_parser(COMMAND, help="Resolve unresolved tags in a reviewed CSV")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--map", action="append", default=[], metavar="NAME=ID")
    parser.add_argument("--apply", action="store_true")
    parser.set_defaults(handler=run)


def run(args, dependencies=None):
    dependencies = dependencies or {}
    return resolve_csv(args.csv, mappings=args.map, apply=args.apply,
                       database=dependencies.get("database", db),
                       client=dependencies.get("client"),
                       validator=dependencies.get("validator", ValidateEntries.run_validation),
                       exception_file=dependencies.get("exception_file"),
                       reporter=dependencies.get("reporter"),
                       gate=dependencies.get("gate"))
