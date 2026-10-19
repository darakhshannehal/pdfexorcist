"""The example recipes shipped with the package, found by name."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)
HERE = Path(__file__).parent


def shipped_dir() -> Path:
    """The recipes folder inside the package."""
    return HERE / "recipes"


def shipped_recipes(root: Path | None = None) -> list[Path]:
    """Every recipe file in root (default: the shipped ones), sorted by name."""
    root = root or shipped_dir()
    return sorted([*root.glob("*.toml"), *root.glob("*/*.toml")]) if root.is_dir() else []


def recipe_name(path: Path) -> str:
    """The short name of a shipped recipe: cpcb_aqi, mccd/table9, or crime_in_india at the top."""
    if path.parent == shipped_dir():
        return path.stem
    return path.parent.name if path.stem == "recipe" else f"{path.parent.name}/{path.stem}"


def find_shipped(name: str) -> Path | None:
    """The shipped recipe called name (cpcb_aqi, mccd/table9, mccd/table9.toml), or None."""
    key = name.removesuffix(".toml").strip("/")
    return next((p for p in shipped_recipes() if recipe_name(p) == key), None)


def resolve_recipe(arg: Path) -> Path:
    """A recipe file as given, else the shipped recipe it names (logged)."""
    if arg.is_file():
        return arg
    found = find_shipped(str(arg))
    if found is None:
        return arg  # load() reports the missing file
    logger.info("--recipe %s: using the shipped recipe %s", arg, found)
    return found
