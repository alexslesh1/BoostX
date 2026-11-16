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
    # Executables that carry the application's traffic, for cases where the
    # program found on disk is only a launcher that lives somewhere else.
    network_exes: tuple[str, ...] = field(default_factory=tuple)


BOOST_CATALOG: tuple[BoostCatalogEntry, ...] = (
    BoostCatalogEntry("roblox", "Roblox", network_exes=("RobloxPlayerBeta.exe",)),
    BoostCatalogEntry("minecraft", "Minecraft", network_exes=("javaw.exe", "Minecraft.Windows.exe")),
    BoostCatalogEntry("fortnite", "Fortnite", network_exes=("FortniteClient-Win64-Shipping.exe",)),
    BoostCatalogEntry("league_of_legends", "League of Legends", ("LoL",), network_exes=("League of Legends.exe",)),
    BoostCatalogEntry("gta_v", "Grand Theft Auto V", ("GTA V", "GTA 5", "Grand Theft Auto 5"), network_exes=("GTA5.exe", "GTA5_Enhanced.exe")),
    BoostCatalogEntry("cod_warzone", "Call of Duty: Warzone", ("Warzone", "COD Warzone"), network_exes=("cod.exe",)),
    BoostCatalogEntry("counter_strike_2", "Counter-Strike 2", ("CS2", "CS:GO"), network_exes=("cs2.exe",)),
    BoostCatalogEntry("dota_2", "Dota 2", network_exes=("dota2.exe",)),
    BoostCatalogEntry("pubg_battlegrounds", "PUBG: BATTLEGROUNDS", ("PUBG",), network_exes=("TslGame.exe",)),
    BoostCatalogEntry("apex_legends", "Apex Legends", ("Apex",), network_exes=("r5apex.exe", "r5apex_dx12.exe")),
    BoostCatalogEntry("rust", "Rust", network_exes=("RustClient.exe",)),
    BoostCatalogEntry("delta_force", "Delta Force", network_exes=("DeltaForceClient-Win64-Shipping.exe",)),
    BoostCatalogEntry("marvel_rivals", "Marvel Rivals", network_exes=("Marvel-Win64-Shipping.exe",)),
    BoostCatalogEntry("dead_by_daylight", "Dead by Daylight", ("DBD",), network_exes=("DeadByDaylight-Win64-Shipping.exe",)),
    BoostCatalogEntry("destiny_2", "Destiny 2", network_exes=("destiny2.exe",)),
    BoostCatalogEntry("overwatch_2", "Overwatch 2", ("OW2",), network_exes=("Overwatch.exe",)),
    BoostCatalogEntry("deadlock", "Deadlock", network_exes=("project8.exe",)),
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
