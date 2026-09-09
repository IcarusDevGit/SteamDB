"""Generate the committed Python operator-command catalog."""

from command_catalog import write_catalog


def main() -> int:
    """Write the catalog and report its repository-relative path."""
    path = write_catalog()
    print(f"Wrote {path.relative_to(path.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
