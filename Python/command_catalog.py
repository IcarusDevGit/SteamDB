"""Authoritative registry and generated documentation for supported Python CLIs.

Register every new supported operator command in ``COMMANDS``. Update commands
must also be present in the corresponding runtime command tuple; completeness
validation deliberately fails when either side is missing.
"""

from __future__ import annotations

import argparse
import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable


CATALOG_PATH = Path(__file__).resolve().parents[1] / "docs" / "commands.md"
GENERATE_COMMAND = "python Python/generate_command_catalog.py"


@dataclass(frozen=True, slots=True)
class CommandDescriptor:
    """Describe one supported command and its non-parser documentation."""

    identity: str
    script: str
    command_path: tuple[str, ...]
    parser_module: str
    purpose: str
    effects: tuple[str, ...]
    safeguards: tuple[str, ...]
    examples: tuple[str, ...]
    environment_defaults: dict[str, str] = field(default_factory=dict)

    @property
    def invocation(self) -> str:
        """Return the canonical command prefix."""
        suffix = " ".join(self.command_path)
        return f"python {self.script}" + (f" {suffix}" if suffix else "")


@dataclass(frozen=True, slots=True)
class AliasDescriptor:
    """Map one retained compatibility invocation to a supported command."""

    invocation: str
    replacement: str
    note: str = "Retained for compatibility; use the canonical command instead."


@dataclass(frozen=True, slots=True)
class ArgumentDescriptor:
    """Structured facts extracted from one runtime argparse action."""

    names: tuple[str, ...]
    metavar: str
    positional: bool
    required: bool
    nargs: object
    choices: tuple[object, ...]
    default: object
    help: str
    repeatable: bool


COMMANDS = (
    CommandDescriptor(
        "extract", "Python/main.py", (), "main",
        "Extract and validate one completed Steam weekly chart or an inclusive range of charts without database writes.",
        ("Reads the catalog and external providers.", "Writes a staging CSV and validation report for each week."),
        ("Does not update PostgreSQL.", "Start and end dates must be Tuesdays, and the end must not precede the start."),
        ("python Python/main.py 2026-08-04", "python Python/main.py 2026-08-04 2026-08-25 --output review"),
        {"--max-entries": "PIPELINE_MAX_ENTRIES", "--itad-batch-size": "ITAD_BATCH_SIZE", "--itad-batch-wait": "ITAD_BATCH_WAIT"},
    ),
    CommandDescriptor(
        "validate", "Python/ValidateEntries.py", (), "ValidateEntries",
        "Validate one weekly extraction CSV against the Steam Top 100 chart.",
        ("Reads Steam chart data.", "Writes a validation report and classifies the CSV/report artifacts."),
        ("Does not update PostgreSQL.", "Only a passed result returns exit status 0."),
        ("python Python/ValidateEntries.py helpers/CSV_error/steam_top_100_2026-08-04.csv",),
    ),
    CommandDescriptor(
        "apply-csv", "Python/UpdateDB.py", ("apply", "csv"), "UpdateDB",
        "Apply one specified CSV or every validated weekly CSV awaiting database upsert.",
        (
            "Validates each CSV and digest-bound report and writes each file atomically to PostgreSQL.",
            "Moves successful pairs to helpers/CSV upserted and quarantines failed default-batch pairs in helpers/CSV_error before continuing.",
        ),
        (
            "Requires --approved.",
            "Requires a passed validation report matching each exact CSV digest and week.",
            "Any batch failure produces an unsuccessful overall status after all selected files are attempted.",
        ),
        (
            "python Python/UpdateDB.py apply csv --approved",
            "python Python/UpdateDB.py apply csv helpers/CSV/steam_top_100_2026-08-04.csv --approved",
        ),
    ),
    CommandDescriptor(
        "resolve-tags", "Python/UpdateDB.py", ("resolve", "tags"), "UpdateDB",
        "Resolve unresolved tag names in a reviewed extraction CSV.",
        ("Reads catalog, exception, and Steam tag evidence.", "With --apply, rewrites and revalidates the CSV and may persist explicit aliases."),
        ("Defaults to a discovery-only dry run.", "Does not write PostgreSQL."),
        ("python Python/UpdateDB.py resolve tags helpers/CSV/weekly.csv", "python Python/UpdateDB.py resolve tags helpers/CSV/weekly.csv --map Dystopian=1001 --apply"),
    ),
    CommandDescriptor(
        "repair-ratings", "Python/UpdateDB.py", ("repair", "ratings"), "UpdateDB",
        "Discover or repair missing historical ratings.",
        ("Reads repair candidates and external rating data.", "With --apply, writes discovered ratings to PostgreSQL."),
        ("Defaults to a dry run.", "Applied repairs require --week, --appid, or --limit."),
        ("python Python/UpdateDB.py repair ratings --week 2026-08-04", "python Python/UpdateDB.py repair ratings --appid 730 --apply"),
    ),
    CommandDescriptor(
        "repair-rating-labels", "Python/UpdateDB.py", ("repair", "rating-labels"), "UpdateDB",
        "Discover or repair missing historical Steam rating labels.",
        (
            "Loads selected null-label weekly rows once and requests one complete histogram per unique game.",
            "With --apply, bulk-writes all successfully derived labels in one PostgreSQL transaction.",
        ),
        (
            "Defaults to a dry run; null means uncollected or failed and no_label means fewer than 10 reviews.",
            "The complete reported null-label set is the default apply target; --week, --appid, and --limit optionally narrow it.",
        ),
        (
            "python Python/UpdateDB.py repair rating-labels",
            "python Python/UpdateDB.py repair rating-labels --appid 730 --apply",
            "python Python/UpdateDB.py repair rating-labels --week 2026-08-04 --limit 100 --apply",
            "python Python/UpdateDB.py repair rating-labels --apply",
        ),
    ),
    CommandDescriptor(
        "repair-prices", "Python/UpdateDB.py", ("repair", "prices"), "UpdateDB",
        "Discover or repair missing historical prices and discounts.",
        ("Reads repair candidates and external price data.", "With --apply, writes discovered prices and discounts to PostgreSQL."),
        ("Defaults to a dry run.", "Applied repairs require --week, --appid, or --limit."),
        ("python Python/UpdateDB.py repair prices --appid 730", "python Python/UpdateDB.py repair prices --week 2026-08-04 --limit 20 --apply"),
    ),
    CommandDescriptor(
        "repair-weekly-stats", "Python/UpdateDB.py", ("repair", "weekly-stats"), "UpdateDB",
        "Discover or repair last-week-rank and consecutive-week values for one chart week.",
        ("Reads the requested external weekly chart.", "With --apply, writes selected weekly-stat fields to PostgreSQL."),
        ("Defaults to a dry run.", "--week is required and must identify a Tuesday."),
        ("python Python/UpdateDB.py repair weekly-stats --week 2026-08-04", "python Python/UpdateDB.py repair weekly-stats --week 2026-08-04 --field last-week-rank --apply"),
    ),
    CommandDescriptor(
        "repair-game-names", "Python/UpdateDB.py", ("repair", "game-names"), "UpdateDB",
        "Discover or repair empty and whitespace-only catalog game names from Steam.",
        ("Reads whitespace-name catalog candidates and looks up their Steam application details.", "With --apply, transactionally fills names that remain whitespace-only."),
        ("Defaults to a dry run and excludes populated and null names.", "--appid and --limit optionally narrow the default whitespace-name operation; --apply explicitly authorizes writes."),
        ("python Python/UpdateDB.py repair game-names", "python Python/UpdateDB.py repair game-names --appid 730 --apply", "python Python/UpdateDB.py repair game-names --limit 100 --apply"),
    ),
    CommandDescriptor(
        "repair-game-tags", "Python/UpdateDB.py", ("repair", "game-tags"), "UpdateDB",
        "Discover or repair empty catalog game tags from Steam store HTML.",
        ("Reads empty-tag catalog candidates, Steam store pages, and catalog tag mappings.", "With --apply, transactionally fills tag arrays that remain empty."),
        ("Defaults to a dry run.", "Selects all null or empty tag arrays by default; --appid and --limit optionally narrow the operation.", "Unresolved names are reported and never assigned invented tag IDs."),
        ("python Python/UpdateDB.py repair game-tags", "python Python/UpdateDB.py repair game-tags --apply", "python Python/UpdateDB.py repair game-tags --appid 730 --apply", "python Python/UpdateDB.py repair game-tags --limit 100 --apply"),
    ),
    CommandDescriptor(
        "repair-weekly-identities", "Python/UpdateDB.py", ("repair", "weekly-identities"), "UpdateDB",
        "Compare stored weeks with Steam's validated global Top 100 and reconcile identity mismatches.",
        ("Reads every stored weeksheet date by default and fetches only prefix-checked global chart data.", "With --apply, atomically removes unexpected weekly rows, moves retained games, and inserts missing global identities."),
        ("Defaults to a dry run.", "--week optionally narrows the stored-date set.", "Retained price, discount, and rating are preserved; newly inserted weekly identities leave them null."),
        ("python Python/UpdateDB.py repair weekly-identities", "python Python/UpdateDB.py repair weekly-identities --week 2026-08-04", "python Python/UpdateDB.py repair weekly-identities --apply"),
    ),
)


ALIASES = (
    AliasDescriptor("python Python/UpdateDB.py upsert-csv --csv FILE --approved", "apply-csv"),
    AliasDescriptor("python Python/UpdateDB.py update-null-ratings [OPTIONS]", "repair-ratings"),
    AliasDescriptor("python Python/UpdateDB.py update-null-prices [OPTIONS]", "repair-prices"),
    AliasDescriptor("python Python/UpdateDB.py update-last-week-rank --week DATE [OPTIONS]", "repair-weekly-stats"),
    AliasDescriptor("python Python/UpdateDB.py update_last_week_rank --week DATE [OPTIONS]", "repair-weekly-stats"),
    AliasDescriptor("python Python/UpdateDB.py update-consecutive-weeks --week DATE [OPTIONS]", "repair-weekly-stats"),
    AliasDescriptor("python Python/UpdateDB.py update_consecutive_weeks --week DATE [OPTIONS]", "repair-weekly-stats"),
)

# This list is the maintained boundary for supported standalone entry points.
SUPPORTED_STANDALONE_ENTRY_POINTS = {"main": "extract", "ValidateEntries": "validate"}


def _parser_for(command: CommandDescriptor) -> argparse.ArgumentParser:
    """Construct the runtime parser and resolve a descriptor's command leaf."""
    try:
        module = importlib.import_module(command.parser_module)
        parser = module.build_parser()
        for segment in command.command_path:
            subparsers = next(
                action for action in parser._actions
                if isinstance(action, argparse._SubParsersAction)
            )
            parser = subparsers.choices[segment]
        return parser
    except Exception as exc:
        raise ValueError(f"cannot expose parser metadata for {command.identity}: {exc}") from exc


def inspect_arguments(command: CommandDescriptor) -> tuple[ArgumentDescriptor, ...]:
    """Extract stable documentation facts from a command's runtime parser."""
    arguments = []
    for action in _parser_for(command)._actions:
        if isinstance(action, argparse._SubParsersAction) or action.help is argparse.SUPPRESS:
            continue
        positional = not action.option_strings
        names = tuple(action.option_strings) if not positional else (action.dest,)
        raw_metavar = action.metavar or (action.dest.upper() if positional else action.dest.upper())
        metavar = " ".join(raw_metavar) if isinstance(raw_metavar, tuple) else str(raw_metavar)
        choices = tuple(action.choices or ())
        arguments.append(ArgumentDescriptor(
            names=names,
            metavar=metavar,
            positional=positional,
            required=bool(action.required) if not positional else action.nargs not in ("?", "*"),
            nargs=action.nargs,
            choices=choices,
            default=action.default,
            help="" if action.help in (None, argparse.SUPPRESS) else str(action.help),
            repeatable=isinstance(action, argparse._AppendAction),
        ))
    return tuple(arguments)


def _public_update_identities() -> set[str]:
    """Derive canonical registry identities from runtime update command groups."""
    updates = importlib.import_module("database_updates")
    return {
        *(f"apply-{module.COMMAND}" for module in updates.APPLY_COMMANDS),
        *(f"resolve-{module.COMMAND}" for module in updates.RESOLVE_COMMANDS),
        *(f"repair-{module.COMMAND}" for module in updates.REPAIR_COMMANDS),
    }


def validate_registry(
    commands: Iterable[CommandDescriptor] = COMMANDS,
    aliases: Iterable[AliasDescriptor] = ALIASES,
    *,
    runtime_identities: Callable[[], set[str]] = _public_update_identities,
) -> None:
    """Reject incomplete, duplicated, or unusable catalog registrations."""
    commands = tuple(commands)
    aliases = tuple(aliases)
    identities = [command.identity for command in commands]
    duplicates = sorted({value for value in identities if identities.count(value) > 1})
    if duplicates:
        raise ValueError(f"duplicate command identities: {', '.join(duplicates)}")
    invocations = [command.invocation for command in commands]
    duplicate_invocations = sorted({value for value in invocations if invocations.count(value) > 1})
    if duplicate_invocations:
        raise ValueError(f"duplicate canonical invocations: {', '.join(duplicate_invocations)}")
    for command in commands:
        if not all((command.identity, command.script, command.parser_module, command.purpose,
                    command.effects, command.safeguards, command.examples)):
            raise ValueError(f"incomplete command metadata: {command.identity or '<missing identity>'}")
        inspect_arguments(command)
    registered_updates = {command.identity for command in commands if command.command_path}
    expected_updates = runtime_identities()
    if registered_updates != expected_updates:
        missing = sorted(expected_updates - registered_updates)
        extra = sorted(registered_updates - expected_updates)
        raise ValueError(f"update command registration mismatch; missing={missing}, extra={extra}")
    standalone = {command.parser_module: command.identity for command in commands if not command.command_path}
    if standalone != SUPPORTED_STANDALONE_ENTRY_POINTS:
        raise ValueError(
            "standalone command registration mismatch; "
            f"expected={SUPPORTED_STANDALONE_ENTRY_POINTS}, actual={standalone}"
        )
    known = set(identities)
    alias_invocations = [alias.invocation for alias in aliases]
    if len(alias_invocations) != len(set(alias_invocations)):
        raise ValueError("duplicate deprecated alias invocation")
    for alias in aliases:
        if not alias.invocation or alias.replacement not in known or not alias.note:
            raise ValueError(f"invalid deprecated alias: {alias.invocation or '<missing invocation>'}")


def _display(value: object) -> str:
    """Render an argparse value without machine-specific or unstable details."""
    if value is argparse.SUPPRESS:
        return "suppressed"
    if value is None:
        return "none"
    return str(value)


def _argument_details(argument: ArgumentDescriptor, command: CommandDescriptor) -> str:
    """Render the applicable structured facts for one argument."""
    details = ["required" if argument.required else "optional"]
    if argument.nargs not in (None, 1):
        details.append(f"arity `{_display(argument.nargs)}`")
    if argument.choices:
        details.append("choices: " + ", ".join(f"`{choice}`" for choice in argument.choices))
    if argument.repeatable:
        details.append("repeatable")
    primary = argument.names[0]
    environment = command.environment_defaults.get(primary)
    if environment:
        details.append(f"default: `${environment}` (the command-line option takes precedence)")
    elif argument.default not in (None, argparse.SUPPRESS, False):
        details.append(f"default: `{_display(argument.default)}`")
    elif argument.default is False and not argument.positional:
        details.append("default: disabled")
    return "; ".join(details)


def render_catalog(
    commands: Iterable[CommandDescriptor] = COMMANDS,
    aliases: Iterable[AliasDescriptor] = ALIASES,
) -> str:
    """Render deterministic Markdown from registered runtime parsers."""
    commands = tuple(commands)
    aliases = tuple(aliases)
    validate_registry(commands, aliases)
    lines = [
        "# Python command catalog", "",
        "<!-- Generated by Python/generate_command_catalog.py. Do not edit by hand. -->", "",
        "This catalog covers the supported operator commands in `Python/`. Regenerate it after registering or changing a command:", "",
        "```powershell", GENERATE_COMMAND, "```", "",
        "Contributor convention: every supported command must be registered in `Python/command_catalog.py`. Update commands must also be added to the appropriate runtime command tuple in `Python/database_updates/__init__.py`; catalog validation rejects incomplete registration.", "",
        "## Supported commands", "",
    ]
    for command in commands:
        lines.extend((f"### `{command.invocation}`", "", command.purpose, "", "**Usage**", "", "```powershell"))
        usage = command.invocation
        arguments = inspect_arguments(command)
        for argument in arguments:
            if argument.names == ("-h", "--help"):
                continue
            label = argument.metavar if argument.positional else argument.names[0] + (f" {argument.metavar}" if argument.nargs != 0 else "")
            if not argument.required:
                label = f"[{label}]"
            usage += f" {label}"
        lines.extend((usage, "```", "", "**Arguments**", ""))
        for argument in arguments:
            names = ", ".join(f"`{name}`" for name in argument.names)
            description = argument.help or ("Show command help and exit." if argument.names == ("-h", "--help") else "No additional description provided.")
            lines.append(f"- {names} — {description} ({_argument_details(argument, command)}).")
        lines.extend(("", "**Effects**", ""))
        lines.extend(f"- {effect}" for effect in command.effects)
        lines.extend(("", "**Safeguards**", ""))
        lines.extend(f"- {safeguard}" for safeguard in command.safeguards)
        lines.extend(("", "**Examples**", ""))
        for example in command.examples:
            lines.extend(("```powershell", example, "```", ""))
    lines.extend(("## Deprecated compatibility aliases", "", "These hidden forms remain available for existing automation but are not supported for new usage.", ""))
    identities = {command.identity: command.invocation for command in commands}
    for alias in aliases:
        lines.append(f"- `{alias.invocation}` → `{identities[alias.replacement]}`. {alias.note}")
    return "\n".join(lines).rstrip() + "\n"


def write_catalog(path: Path = CATALOG_PATH) -> Path:
    """Write the generated catalog with deterministic UTF-8/LF formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_catalog(), encoding="utf-8", newline="\n")
    return path


def assert_catalog_fresh(path: Path = CATALOG_PATH, *, renderer: Callable[[], str] = render_catalog) -> None:
    """Fail with the regeneration command when committed output is stale."""
    if path.read_text(encoding="utf-8") != renderer():
        raise AssertionError(f"Command catalog is stale; run: {GENERATE_COMMAND}")
