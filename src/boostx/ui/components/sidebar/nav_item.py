from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    page_index: int


NAV_ITEMS: list[NavItem] = [
    NavItem(key="dashboard", label="Dashboard", page_index=0),
    NavItem(key="monitor", label="Monitor", page_index=1),
    NavItem(key="boost", label="Boost", page_index=2),
    NavItem(key="cleaner", label="Cleaner", page_index=3),
    NavItem(key="tweaks", label="Tweaks", page_index=4),
    NavItem(key="settings", label="Settings", page_index=5),
    NavItem(key="account", label="Account", page_index=6),
    NavItem(key="about", label="About", page_index=7),
]
