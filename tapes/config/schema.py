from pydantic import BaseModel
from typing import Literal


class LibraryConfig(BaseModel):
    movies: str = ""
    tv: str = ""
    db_path: str = "~/.local/share/tapes/library.db"


class ImportConfig(BaseModel):
    mode: Literal["copy", "move", "link", "hardlink"] = "copy"
    confidence_threshold: float = 0.9
    interactive: bool = False
    dry_run: bool = False


class MetadataConfig(BaseModel):
    movies: str = "tmdb"
    tv: str = "tmdb"
    tmdb_api_key: str = ""


class TemplatesConfig(BaseModel):
    movie: str = "{title} ({year})/{title} ({year}){ext}"
    tv: str = "{show}/Season {season:02d}/{show} - S{season:02d}E{episode:02d} - {episode_title}{ext}"


class CompanionsMoveConfig(BaseModel):
    subtitle: bool = True
    artwork: bool = True
    nfo: bool = True
    sample: bool = False
    unknown: bool = False


class CompanionsConfig(BaseModel):
    subtitle: list[str] = ["*.srt", "*.ass", "*.vtt", "*.sub", "*.idx", "*.ssa"]
    artwork: list[str] = ["poster.jpg", "folder.jpg", "fanart.jpg", "banner.jpg", "thumb.jpg"]
    sample: list[str] = ["sample.*", "*-sample.*", "*sample*.*"]
    ignore: list[str] = ["*.url", "*.lnk", "Thumbs.db", ".DS_Store"]
    move: CompanionsMoveConfig = CompanionsMoveConfig()


class TapesConfig(BaseModel):
    library: LibraryConfig = LibraryConfig()
    import_: ImportConfig = ImportConfig()
    metadata: MetadataConfig = MetadataConfig()
    templates: TemplatesConfig = TemplatesConfig()
    companions: CompanionsConfig = CompanionsConfig()
    replace: dict[str, str] = {": ": " - ", "/": "-"}

    model_config = {"populate_by_name": True}
