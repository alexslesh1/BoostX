import re
from dataclasses import dataclass, field

DEMO_EXECUTABLE_SENTINEL = "demo"


@dataclass(frozen=True)
class BoostCatalogEntry:
    key: str
    display_name: str
    match_aliases: tuple[str, ...] = field(default_factory=tuple)
    is_demo: bool = False
    is_communication_app: bool = False


BOOST_CATALOG: tuple[BoostCatalogEntry, ...] = (
    BoostCatalogEntry("roblox", "Roblox"),
    BoostCatalogEntry("minecraft", "Minecraft"),
    BoostCatalogEntry("fortnite", "Fortnite"),
    BoostCatalogEntry("league_of_legends", "League of Legends", ("LoL",)),
    BoostCatalogEntry("gta_v", "Grand Theft Auto V", ("GTA V", "GTA 5", "Grand Theft Auto 5")),
    BoostCatalogEntry("cod_warzone", "Call of Duty: Warzone", ("Warzone", "COD Warzone")),
    BoostCatalogEntry("counter_strike_2", "Counter-Strike 2", ("CS2", "CS:GO")),
    BoostCatalogEntry("dota_2", "Dota 2"),
    BoostCatalogEntry("pubg_battlegrounds", "PUBG: BATTLEGROUNDS", ("PUBG",)),
    BoostCatalogEntry("apex_legends", "Apex Legends", ("Apex",)),
    BoostCatalogEntry("rust", "Rust"),
    BoostCatalogEntry("delta_force", "Delta Force"),
    BoostCatalogEntry("marvel_rivals", "Marvel Rivals"),
    BoostCatalogEntry("dead_by_daylight", "Dead by Daylight", ("DBD",)),
    BoostCatalogEntry("destiny_2", "Destiny 2"),
    BoostCatalogEntry("overwatch_2", "Overwatch 2", ("OW2",)),
    BoostCatalogEntry("deadlock", "Deadlock"),
    BoostCatalogEntry("discord", "Discord", is_communication_app=True),
    BoostCatalogEntry("telegram", "Telegram", is_communication_app=True),
    BoostCatalogEntry("test", "Test", is_demo=True),
)

_STRIP_PATTERN = re.compile(r"[™®©]|[^a-z0-9]+")


def normalize_name(raw: str) -> str:
    lowered = raw.lower()
    return _STRIP_PATTERN.sub("", lowered)


def build_alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for entry in BOOST_CATALOG:
        index[normalize_name(entry.display_name)] = entry.key
        for alias in entry.match_aliases:
            index[normalize_name(alias)] = entry.key
    return index
