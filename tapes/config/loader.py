import tomllib
from pathlib import Path
from tapes.config.schema import TapesConfig

DEFAULT_PATHS = [
    Path("tapes.toml"),
    Path.home() / ".config" / "tapes" / "tapes.toml",
]


def load_config(path: Path | None = None) -> TapesConfig:
    if path is None:
        for candidate in DEFAULT_PATHS:
            if candidate.exists():
                path = candidate
                break

    if path is None or not path.exists():
        return TapesConfig()

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"Error in config file {path}:\n  {e}") from e

    # Rename 'import' → 'import_' for pydantic
    if "import" in data:
        data["import_"] = data.pop("import")

    return TapesConfig.model_validate(data)
