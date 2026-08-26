import ast
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def imported_modules(tree: Path):
    for path in tree.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        parsed = ast.parse(source, filename=str(path))
        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                yield path, *(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                yield path, node.module


class TreeIsolationTests(unittest.TestCase):
    def test_active_and_legacy_trees_do_not_import_each_other(self):
        active = REPOSITORY_ROOT / "Python"
        legacy = REPOSITORY_ROOT / "Python_legacy"
        for tree, forbidden in ((active, "Python_legacy"), (legacy, "Python")):
            for imported in imported_modules(tree):
                path, *names = imported
                self.assertFalse(
                    any(name == forbidden or name.startswith(f"{forbidden}.") for name in names),
                    f"{path} imports from {forbidden}: {names}",
                )

    def test_trees_do_not_add_each_other_to_module_search_path(self):
        active_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (REPOSITORY_ROOT / "Python").rglob("*.py")
            if path != Path(__file__).resolve()
        )
        legacy_sources = "\n".join(
            path.read_text(encoding="utf-8") for path in (REPOSITORY_ROOT / "Python_legacy").rglob("*.py")
        )
        self.assertNotIn('"Python_legacy"', active_sources)
        self.assertNotIn("'Python_legacy'", active_sources)
        self.assertNotIn('"Python"', legacy_sources)
        self.assertNotIn("'Python'", legacy_sources)


if __name__ == "__main__":
    unittest.main()
