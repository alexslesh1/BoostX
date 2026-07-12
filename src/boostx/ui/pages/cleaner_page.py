from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from boostx.core.services.cleaner.models import (
    CleanResult,
    LargeFileGroup,
    MemoryOptimizationResult,
    ScanResult,
    StartupEntry,
)
from boostx.core.services.cleaner.system_health import disk_health_percent
from boostx.ui.components.card import Card
from boostx.ui.components.cleaner.health_card import SystemHealthCard
from boostx.ui.components.cleaner.large_file_row import LargeFileRow
from boostx.ui.components.cleaner.memory_card import MemoryOptimizationCard
from boostx.ui.components.cleaner.scan_category_card import ScanCategoryCard
from boostx.ui.components.cleaner.startup_row import StartupRow
from boostx.ui.components.cleaner.summary_card import CleaningSummaryCard
from boostx.ui.components.progress_bar import ProgressBar
from boostx.ui.controllers.cleaner_controller import CleanerController
from boostx.ui.pages.base_page import BasePage

_SCAN_PLACEHOLDER = "Click Scan to analyze your system for recoverable space."
_STARTUP_EMPTY = "No startup entries found (Windows only)."
_LARGE_FILES_EMPTY = "No large content found in Downloads or Videos."


class CleanerPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        self._category_cards: dict[str, ScanCategoryCard] = {}
        self._selected_keys: set[str] = set()
        self._startup_rows: dict[str, StartupRow] = {}
        self._last_memory_freed_bytes = 0

        super().__init__(
            title="Cleaner",
            subtitle="Scan and clean temporary files, caches and logs",
            parent=parent,
        )

        # CleanerController is a QObject parented to self, so it can only be
        # constructed after QWidget.__init__ has run (i.e. after super().__init__()).
        self._controller = CleanerController(self)
        self._connect_controller()
        self._health_card.set_health_percent(disk_health_percent())
        self._controller.load_memory_snapshot()
        self._controller.load_startup_entries()
        self._controller.load_large_files()

    def _build_body(self, layout: QVBoxLayout) -> None:
        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(16)

        self._health_card = SystemHealthCard(content)
        self._health_card.scan_requested.connect(self._on_scan_requested)
        self._health_card.clean_requested.connect(self._on_clean_requested)
        content_layout.addWidget(self._health_card)

        content_layout.addWidget(self._build_scan_results_section(content))

        self._progress_bar = ProgressBar(content)
        self._progress_bar.hide()
        self._progress_label = QLabel("", content)
        self._progress_label.setObjectName("MetricCardLabel")
        self._progress_label.hide()
        content_layout.addWidget(self._progress_bar)
        content_layout.addWidget(self._progress_label)

        self._summary_card = CleaningSummaryCard(content)
        content_layout.addWidget(self._summary_card)

        self._memory_card = MemoryOptimizationCard(content)
        self._memory_card.optimize_requested.connect(self._on_optimize_requested)
        content_layout.addWidget(self._memory_card)

        content_layout.addWidget(self._build_startup_section(content))
        content_layout.addWidget(self._build_large_files_section(content))
        content_layout.addStretch(1)

        scroll_area = QScrollArea(self)
        scroll_area.setWidget(content)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        layout.addWidget(scroll_area, stretch=1)

    def _build_scan_results_section(self, parent: QWidget) -> Card:
        card = Card(parent)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(10)

        title = QLabel("Scan Results", card)
        title.setObjectName("CleanerSectionTitle")
        card_layout.addWidget(title)

        self._scan_results_layout = QVBoxLayout()
        self._scan_results_layout.setSpacing(10)
        card_layout.addLayout(self._scan_results_layout)

        self._scan_placeholder_label = QLabel(_SCAN_PLACEHOLDER, card)
        self._scan_placeholder_label.setObjectName("CardPlaceholderLabel")
        card_layout.addWidget(self._scan_placeholder_label)

        return card

    def _build_startup_section(self, parent: QWidget) -> Card:
        card = Card(parent)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(10)

        title = QLabel("Startup Applications", card)
        title.setObjectName("CleanerSectionTitle")
        card_layout.addWidget(title)

        self._startup_layout = QVBoxLayout()
        self._startup_layout.setSpacing(4)
        card_layout.addLayout(self._startup_layout)

        self._startup_empty_label = QLabel(_STARTUP_EMPTY, card)
        self._startup_empty_label.setObjectName("CardPlaceholderLabel")
        card_layout.addWidget(self._startup_empty_label)

        return card

    def _build_large_files_section(self, parent: QWidget) -> Card:
        card = Card(parent)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(10)

        title = QLabel("Large Files", card)
        title.setObjectName("CleanerSectionTitle")
        card_layout.addWidget(title)

        self._large_files_layout = QVBoxLayout()
        self._large_files_layout.setSpacing(4)
        card_layout.addLayout(self._large_files_layout)

        self._large_files_empty_label = QLabel(_LARGE_FILES_EMPTY, card)
        self._large_files_empty_label.setObjectName("CardPlaceholderLabel")
        card_layout.addWidget(self._large_files_empty_label)

        return card

    def _connect_controller(self) -> None:
        self._controller.scan_finished.connect(self._on_scan_finished)
        self._controller.clean_progress.connect(self._on_clean_progress)
        self._controller.clean_finished.connect(self._on_clean_finished)
        self._controller.memory_snapshot_ready.connect(self._memory_card.update_snapshot)
        self._controller.memory_optimize_finished.connect(self._on_memory_optimize_finished)
        self._controller.startup_entries_ready.connect(self._on_startup_entries_ready)
        self._controller.startup_toggle_finished.connect(self._on_startup_toggle_finished)
        self._controller.large_files_ready.connect(self._on_large_files_ready)

    # -- scan / clean ---------------------------------------------------------
    def _on_scan_requested(self) -> None:
        self._health_card.set_busy(True)
        self._summary_card.hide()
        self._controller.scan()

    def _on_scan_finished(self, result: ScanResult) -> None:
        self._health_card.set_busy(False)
        self._scan_placeholder_label.setVisible(not result.categories)

        for category in result.categories:
            card = self._category_cards.get(category.key)
            if card is None:
                card = ScanCategoryCard(category, self._scan_results_layout.parentWidget())
                card.toggled.connect(self._on_category_toggled)
                self._category_cards[category.key] = card
                self._scan_results_layout.addWidget(card)
            else:
                card.update_category(category)
            if card.is_checked():
                self._selected_keys.add(category.key)

        self._health_card.set_recoverable_bytes(result.total_bytes)
        self._health_card.set_has_results(bool(self._selected_keys))

    def _on_category_toggled(self, key: str, checked: bool) -> None:
        if checked:
            self._selected_keys.add(key)
        else:
            self._selected_keys.discard(key)
        self._health_card.set_has_results(bool(self._selected_keys))

    def _on_clean_requested(self) -> None:
        if not self._selected_keys:
            return
        self._health_card.set_busy(True, label="Clean Selected")
        self._progress_bar.show()
        self._progress_bar.setValue(0)
        self._progress_label.setText("Cleaning...")
        self._progress_label.show()
        self._controller.clean(set(self._selected_keys))

    def _on_clean_progress(self, category_label: str) -> None:
        self._progress_label.setText(f"Cleaning {category_label.lower()}...")
        current = self._progress_bar.value()
        self._progress_bar.setValue(min(95, current + 15))

    def _on_clean_finished(self, result: CleanResult) -> None:
        self._progress_bar.setValue(100)
        self._progress_label.setText("Finished.")
        self._health_card.set_busy(False)
        self._summary_card.show_summary(result, self._last_memory_freed_bytes)
        self._health_card.set_health_percent(disk_health_percent())
        self._controller.scan()
        self._progress_bar.hide()
        self._progress_label.hide()

    # -- memory ---------------------------------------------------------------
    def _on_optimize_requested(self) -> None:
        self._memory_card.set_busy(True)
        self._controller.optimize_memory()

    def _on_memory_optimize_finished(self, result: MemoryOptimizationResult) -> None:
        self._memory_card.set_busy(False)
        self._memory_card.show_result(result)
        self._memory_card.update_snapshot(result.after)
        self._last_memory_freed_bytes = result.freed_bytes

    # -- startup ----------------------------------------------------------------
    def _on_startup_entries_ready(self, entries: list[StartupEntry]) -> None:
        self._startup_empty_label.setVisible(not entries)
        for entry in entries:
            row = StartupRow(entry, self._startup_layout.parentWidget())
            row.toggled.connect(self._on_startup_toggled)
            self._startup_rows[entry.name] = row
            self._startup_layout.addWidget(row)

    def _on_startup_toggled(self, entry: StartupEntry, enabled: bool) -> None:
        self._controller.toggle_startup(entry, enabled)

    def _on_startup_toggle_finished(self, name: str, enabled: bool, success: bool) -> None:
        row = self._startup_rows.get(name)
        if row is not None:
            row.apply_result(enabled, success)

    # -- large files --------------------------------------------------------------
    def _on_large_files_ready(self, groups: list[LargeFileGroup]) -> None:
        visible_groups = [group for group in groups if group.size_bytes > 0]
        self._large_files_empty_label.setVisible(not visible_groups)
        for group in visible_groups:
            self._large_files_layout.addWidget(LargeFileRow(group, self._large_files_layout.parentWidget()))

    def shutdown(self) -> None:
        self._controller.shutdown()
