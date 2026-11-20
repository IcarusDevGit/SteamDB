# Active Python implementation

This directory contains the supported SteamDB extraction, validation, tag-resolution, and database-update implementation.

Start with the repository [`README.md`](../README.md). Detailed operator guides are organized by topic:

- [Python command catalog](../docs/commands.md)
- [Architecture and module responsibilities](../docs/architecture.md)
- [Configuration](../docs/configuration.md)
- [Extraction](../docs/extraction.md)
- [Validation](../docs/validation.md)
- [Tag resolution](../docs/tag-resolution.md)
- [Database updates and repairs](../docs/database-updates.md)
- [Testing](../docs/testing.md)
- [Troubleshooting](../docs/troubleshooting.md)

Every new supported operator command must be registered in [`command_catalog.py`](command_catalog.py). After changing a command or its arguments, run `python Python/generate_command_catalog.py` from the repository root and commit the refreshed catalog.
