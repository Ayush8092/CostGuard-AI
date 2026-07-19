from pathlib import Path

ROOT = Path(r"D:\CostGuard AI\costguard")

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".next",
}

IGNORE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".log",
}

OUTPUT_FILE = ROOT / "project_structure.txt"


def should_ignore(path: Path):
    if path.name in IGNORE_DIRS:
        return True

    if path.suffix in IGNORE_EXTENSIONS:
        return True

    return False


def tree(directory: Path, prefix=""):
    entries = sorted(
        [e for e in directory.iterdir() if not should_ignore(e)],
        key=lambda x: (x.is_file(), x.name.lower()),
    )

    lines = []

    for index, entry in enumerate(entries):
        connector = "└── " if index == len(entries) - 1 else "├── "
        lines.append(prefix + connector + entry.name)

        if entry.is_dir():
            extension = "    " if index == len(entries) - 1 else "│   "
            lines.extend(tree(entry, prefix + extension))

    return lines


def main():
    output = [ROOT.name]
    output.extend(tree(ROOT))

    OUTPUT_FILE.write_text("\n".join(output), encoding="utf-8")

    print(f"\nProject structure saved to:\n{OUTPUT_FILE}\n")


if __name__ == "__main__":
    main()