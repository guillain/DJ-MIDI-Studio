"""MainWindow, part: The By Channel / By Deck / By Controller trees and layouts, selection sync between them, the edit panel, function search results, validation and the Ready for live check.

A mixin of `djmidi.gui.main_window.MainWindow` (issue #429); its strings keep the
"MainWindow" translation context."""

from __future__ import annotations

from PySide6.QtCore import (
    QCoreApplication,
    QItemSelectionModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QTableWidgetItem,
    QTreeView,
)

from djmidi import (
    catalog,
    software,
)
from djmidi.function_search import FunctionResult
from djmidi.gui import layout as layout_mod
from djmidi.gui.controller_tree import CELL_KEY_ROLE, build_controller_columns
from djmidi.gui.deck_tree import build_deck_columns
from djmidi.gui.live_ready_dialog import LiveReadyDialog
from djmidi.gui.main_window_parts._shared import (
    _SEVERITY_COLORS,
    MAPPING_COLUMN_MIN_WIDTH,
    _live_ready_translate,
    _refresh_tree_row_layout,
    _validator_translate,
)
from djmidi.gui.mapping_group import MappingGroup
from djmidi.gui.splitter_utils import replace_splitter
from djmidi.gui.theme import mapping_tree_stylesheet
from djmidi.gui.tree_model import (
    NODE_ROLE,
    MappingFilterProxy,
    build_channel_columns,
    relabel_item,
)
from djmidi.live_ready import check_live_ready
from djmidi.model import Control, MappingElement, iter_bindings
from djmidi.validator import ValidationIssue, severity_label, validate


class MappingViewsMixin:
    def _load_tree(self) -> None:
        assert self.config is not None
        definition = software.get_definition(self.software_id)
        self.introduction_view.set_loaded_config_info(
            self.current_path,
            len(self.config.controls),
            software_id=self.software_id,
            software_name=definition.name,
        )
        self._update_window_title()
        self._rebuild_channel_columns()
        self._refresh_layout_usage()
        self._refresh_deck_view()
        self.function_search_view.set_config(self.config)
        self.live_monitor_view.set_config(self.config)
        if self.preferences.auto_start_live_monitor:
            self.live_monitor_view.ensure_monitoring_started()

    def _rebuild_channel_columns(self) -> None:
        assert self.config is not None
        self.channel_splitter = replace_splitter(self._channel_columns_scroll, self.channel_splitter)

        self.node_to_item = {}
        self._channel_model_owner = {}
        self.channel_proxies = []
        search_text = self.search_box.text()

        for _channel, model, node_to_item in build_channel_columns(self.config):
            self.node_to_item.update(node_to_item)

            proxy = MappingFilterProxy(self)
            proxy.setRecursiveFilteringEnabled(True)
            proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            proxy.setSourceModel(model)
            if search_text:
                proxy.setFilterFixedString(search_text)
            self.channel_proxies.append(proxy)

            view = QTreeView()
            view.setMinimumWidth(MAPPING_COLUMN_MIN_WIDTH)
            self._style_mapping_tree(view)
            view.setHeaderHidden(False)
            view.setModel(proxy)
            view.expandToDepth(0)
            view.selectionModel().selectionChanged.connect(
                lambda *_, v=view, p=proxy: self._on_channel_selection_changed(v, p)
            )
            self._channel_model_owner[id(model)] = (view, proxy)
            self.channel_splitter.addWidget(view)

    def _refresh_deck_view(self) -> None:
        assert self.config is not None
        self.deck_splitter = replace_splitter(self._deck_columns_scroll, self.deck_splitter)
        self._deck_tree_views = []

        for _deck_id, model in build_deck_columns(self.config):
            view = QTreeView()
            view.setMinimumWidth(MAPPING_COLUMN_MIN_WIDTH)
            self._style_mapping_tree(view)
            view.setHeaderHidden(False)
            view.setModel(model)
            view.expandToDepth(0)
            view.selectionModel().selectionChanged.connect(lambda *_, v=view: self._on_deck_column_selection_changed(v))
            view.doubleClicked.connect(lambda index, v=view: self._on_deck_item_double_clicked(v, index))
            self.deck_splitter.addWidget(view)
            self._deck_tree_views.append(view)

    def _on_deck_column_selection_changed(self, view: QTreeView) -> None:
        indexes = view.selectionModel().selectedIndexes()
        if not indexes:
            self.edit_panel.set_node(None)
            self._update_layout_selection(None, None, None)
            return
        group = view.model().itemFromIndex(indexes[0]).data(NODE_ROLE)
        if not isinstance(group, MappingGroup):
            self.edit_panel.set_node(None)
            self._update_layout_selection(None, None, None)
            return
        self.edit_panel.set_node(group)
        self._update_layout_selection(group.channel, group.event_type, group.control_no)

    def _on_deck_item_double_clicked(self, view: QTreeView, index) -> None:
        group = view.model().itemFromIndex(index).data(NODE_ROLE)
        if not isinstance(group, MappingGroup):
            return
        control = group.members[0][0]
        self._select_control_in_channel_columns(control)
        self.left_tabs.setCurrentIndex(self._tab_indexes["channel"])

    def _on_group_edit_applied(self) -> None:
        # A group edit may touch every duplicate's deck/slot label (main columns)
        # and can move the group to a different deck/slot column, so the deck
        # columns need a full rebuild rather than a single relabel.
        current_group = self.edit_panel.current_node
        if isinstance(current_group, MappingGroup):
            for control, _, mapping in current_group.members:
                # The control too: a MIDI Learn moves the members' trigger.
                for node in (control, mapping):
                    item = self.node_to_item.get(id(node))
                    if item is not None:
                        relabel_item(item, node)
        QTimer.singleShot(0, self._refresh_edit_panel)
        QTimer.singleShot(0, self._refresh_layout_usage)
        QTimer.singleShot(0, self._refresh_deck_view)

    def _refresh_layout_usage(self) -> None:
        assert self.config is not None
        usage: dict[layout_mod.CellKey, dict[str, set[str]]] = {}
        linked_cells: dict[layout_mod.CellKey, set[layout_mod.CellKey]] = {}
        for control in self.config.controls:
            hits = catalog.lookup(control.channel, control.event_type, control.control)
            if not hits:
                continue
            # A single raw (channel, event_type, control) trigger can match both
            # controllers' catalogs at once (a merged config doesn't record which
            # physical device sent it) — link those cells so the layout can show
            # each controller's interpretation of the same trigger side by side.
            # presentation_key_for_hit() (not the merged cell_key()) so a link
            # from DDJ-XP2's right pad grid points at XDJ-XZ's own right-side
            # hit for the same trigger, not whichever side happens to share
            # the merged key.
            hit_keys = {layout_mod.presentation_key_for_hit(hit) for hit in hits}
            for key in hit_keys:
                others = {other for other in hit_keys if other[0] != key[0]}
                if others:
                    linked_cells.setdefault(key, set()).update(others)
            for userio, _case in iter_bindings(control):
                for mapping in userio.mappings:
                    if not mapping.deck_id:
                        continue
                    for hit in hits:
                        # Stays keyed by the *merged* cell here (unlike
                        # linked_cells above): the "By Controller" text tree
                        # and the classic card grid both read this same
                        # usage dict with no per-side concept at all, so
                        # splitting it at the source would silently
                        # under-report their aggregate deck/tag counts.
                        # ControllerLayoutView._cell_decks_and_tags() does
                        # the side-narrowing itself, downstream, only for
                        # the real-position schematic.
                        cell = usage.setdefault(layout_mod.cell_key(hit), {})
                        cell.setdefault(mapping.deck_id, set()).add(mapping.tag)
        self.layout_view.set_usage(usage, linked_cells)
        self.deck_layout_view.set_usage(usage, linked_cells)
        self.controller_layout_view.set_usage(usage, linked_cells)
        self.introduction_view.set_usage_summary(usage)
        self._refresh_controller_columns(usage)

    def _refresh_controller_columns(self, usage: dict[layout_mod.CellKey, dict[str, set[str]]]) -> None:
        self.controller_splitter = replace_splitter(self._controller_columns_scroll, self.controller_splitter)
        self._controller_tree_views = []

        for _controller, model, expand_flags in build_controller_columns(usage):
            view = QTreeView()
            view.setMinimumWidth(MAPPING_COLUMN_MIN_WIDTH)
            self._style_mapping_tree(view)
            view.setHeaderHidden(False)
            view.setModel(model)
            view.selectionModel().selectionChanged.connect(lambda *_, v=view: self._on_controller_selection_changed(v))
            self.controller_splitter.addWidget(view)
            self._controller_tree_views.append(view)
            # Deferred: expanding items right after setModel(), before the view has
            # done its first layout pass, is unreliable in some Qt/platform
            # combinations (the row exists in the model but the view hasn't built
            # its internal expand-state tracking for it yet).
            QTimer.singleShot(0, lambda v=view, m=model, flags=expand_flags: self._apply_controller_expand_state(v, m, flags))

    @staticmethod
    def _style_mapping_tree(view: QTreeView) -> None:
        """Apply the DJ booth palette to a mapping tree at construction
        time. This used to set a literal hardcoded copy of the dark
        palette's colors, so By Channel/Deck/Controller stayed dark even
        after picking Light -- theme.mapping_tree_stylesheet() builds this
        from the same tokens theme.py substitutes its own app-wide QSS
        from.

        A live Settings -> Preferences theme switch is handled centrally by
        _restyle_mapping_trees (one connection, made once in __init__),
        not by a per-tree theme.signals.themeChanged connection here -- see
        that method's docstring for why the per-tree version, tried first,
        turned out to leak."""
        view.setAlternatingRowColors(True)
        view.setIndentation(16)
        view.setAnimated(True)
        view.setStyleSheet(mapping_tree_stylesheet())

    def _restyle_mapping_trees(self, *_args: object) -> None:
        """Rebuild every *currently live* mapping tree's stylesheet (and
        force-repaint its visible rows -- see _refresh_tree_row_layout) on
        a live Settings -> Preferences theme switch.

        The first version connected each tree individually to
        theme.signals.themeChanged via a closure, at construction
        (_style_mapping_tree). That leaked: reloading a mapping replaces
        self._channel_model_owner / _deck_tree_views / _controller_tree_views
        wholesale (splitter_utils.replace_splitter -> deleteLater() on the
        old widgets) without ever disconnecting their individual
        connections, and a plain closure isn't a bound QObject method
        PySide auto-disconnects on the tree's destruction. Each dead
        connection kept paying for a full restyle on every future theme
        switch for as long as the underlying widget lingered (Qt's
        deferred-deletion timing, not instant) -- measured compounding
        linearly across repeated reloads within a single session, not just
        an artifact of a test file constructing many windows.

        Iterating these three lists instead has nothing to ever go stale:
        they're always replaced, never appended to, so an old tree simply
        isn't in them anymore once something rebuilds the columns -- one
        connection, tied to MainWindow's own genuinely-app-session-long
        lifetime, covers every tree that currently exists no matter how
        many times the mapping has been reloaded."""
        for view, _proxy in self._channel_model_owner.values():
            view.setStyleSheet(mapping_tree_stylesheet())
            _refresh_tree_row_layout(view)
        for view in (*self._deck_tree_views, *self._controller_tree_views):
            view.setStyleSheet(mapping_tree_stylesheet())
            _refresh_tree_row_layout(view)

    def _apply_controller_expand_state(self, view: QTreeView, model: QStandardItemModel, expand_flags: list[tuple[int, bool]]) -> None:
        for row, has_used_leaf in expand_flags:
            view.setExpanded(model.index(row, 0), has_used_leaf)

    def _on_controller_selection_changed(self, view: QTreeView) -> None:
        indexes = view.selectionModel().selectedIndexes()
        if not indexes:
            return
        cell_key = view.model().itemFromIndex(indexes[0]).data(CELL_KEY_ROLE)
        if cell_key is not None:
            self._on_layout_cell_activated(cell_key)

    def _select_control_in_channel_columns(self, control: Control) -> bool:
        item = self.node_to_item.get(id(control))
        if item is None:
            return False
        owner = self._channel_model_owner.get(id(item.model()))
        if owner is None:
            return False
        view, proxy = owner
        proxy_index = proxy.mapFromSource(item.index())
        view.setCurrentIndex(proxy_index)
        view.scrollTo(proxy_index)
        return True

    def _select_model_index(self, view: QTreeView, index: QModelIndex) -> None:
        selection = view.selectionModel()
        selection.clearSelection()
        selection.select(
            index,
            QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
        )
        view.setCurrentIndex(index)
        view.scrollTo(index)

    def _find_index_with_data(self, model, value: object, role: int, parent: QModelIndex | None = None) -> QModelIndex:
        if parent is None:
            parent = QModelIndex()
        for row in range(model.rowCount(parent)):
            index = model.index(row, 0, parent)
            if index.data(role) == value:
                return index
            found = self._find_index_with_data(model, value, role, index)
            if found.isValid():
                return found
        return QModelIndex()

    def _select_controller_cell(self, key: layout_mod.CellKey) -> bool:
        """The "By Controller" text tree (gui/controller_tree.py) has no
        separate row for a right-side real-position marker at all -- it's
        built from build_layout()'s own cells, a merged, aggregate-usage
        view by design (unlike the schematic layout, it never modeled two
        physical grids/clusters as distinct rows), so a right-side key
        simply finds no row here and this returns False.

        Deliberately does NOT fall back to selecting the merged row: doing
        so would select a tree row whose own CELL_KEY_ROLE is the *merged*
        key, and _on_controller_selection_changed's selectionChanged
        handler would immediately re-run _on_layout_cell_activated with
        that merged key -- silently overwriting the correct side-aware
        selection this call was trying to make with whatever the merged
        cell's first (often left-side) match happens to be. Confirmed by a
        real offscreen click simulation: this exact feedback loop is what
        produced a right-side click landing on a left-side deck. Known,
        disclosed limitation -- not silently dropped."""
        for view in self._controller_tree_views:
            index = self._find_index_with_data(view.model(), key, CELL_KEY_ROLE)
            if index.isValid():
                self._select_model_index(view, index)
                return True
        return False

    def _select_deck_group(self, key: layout_mod.CellKey) -> bool:
        for view in self._deck_tree_views:
            model = view.model()
            for row in range(model.rowCount()):
                slot_index = model.index(row, 0)
                for child_row in range(model.rowCount(slot_index)):
                    index = model.index(child_row, 0, slot_index)
                    group = index.data(NODE_ROLE)
                    if not isinstance(group, MappingGroup):
                        continue
                    if any(
                        layout_mod.presentation_key_for_hit(hit) == key
                        for hit in catalog.lookup(group.channel, group.event_type, group.control_no)
                    ):
                        self._select_model_index(view, index)
                        return True
        return False

    def _on_layout_cell_activated(self, key: tuple, source_tab: str = "channel") -> None:
        if self.config is None:
            return
        # find_controls_for_cell() (not a manual cell_key(hit) == key scan)
        # so a right-side real-position marker's presentation key (DDJ-XP2/
        # XDJ-XZ decks 2/4) only matches controls actually on that physical
        # side, instead of jumping to whatever control happens to share the
        # left side's merged cell -- the By Channel/Deck/Controller tabs'
        # own follow-up to the Controller Emulator's identical fix.
        matches = layout_mod.find_controls_for_cell(self.config, key)
        if not matches:
            self.statusBar().showMessage(QCoreApplication.translate("MainWindow", "No control in this file uses '{name}'").format(name=key[2]))
            self._update_layout_selection(None, None, None)
            return
        if source_tab == "controller":
            self._select_controller_cell(key)
        elif source_tab == "deck":
            if not self._select_deck_group(key):
                self._select_control_in_channel_columns(matches[0])
        else:
            self._select_control_in_channel_columns(matches[0])
        self.left_tabs.setCurrentIndex(self._tab_indexes[source_tab])
        self.statusBar().showMessage(
            QCoreApplication.translate("MainWindow", "'{name}': {count} control(s) in this file, showing first").format(name=key[2], count=len(matches))
        )
        # setCurrentIndex above already re-highlights via _on_channel_selection_changed,
        # but do it directly too in case the selection didn't actually change
        # (clicking the same physical control's other half again).
        self._update_layout_selection(matches[0].channel, matches[0].event_type, matches[0].control)

    def _on_function_result_selected(self, result: FunctionResult) -> None:
        """A Find-function result: select its first control in the current
        mapping tab (like a layout cell click), then outline *every* control
        bound to it on the three layouts -- after the selection, whose own
        selectionChanged handler narrows the outline to one control."""
        if self.config is None or not result.controls:
            return
        tab = next(
            (key for key in ("channel", "deck", "controller") if self._tab_indexes[key] == self.left_tabs.currentIndex()),
            "channel",
        )
        first = result.controls[0]
        first_keys = [
            layout_mod.presentation_key_for_hit(hit)
            for hit in catalog.lookup(first.channel, first.event_type, first.control)
        ]
        selected = False
        if tab == "deck":
            selected = self._select_deck_group_for_mappings(result.mappings)
        elif tab == "controller":
            selected = any(self._select_controller_cell(key) for key in first_keys)
            # The tree row stands for a whole cell, and its own handler picks
            # *some* control on it; point the edit panel at this exact one.
            self._select_control_in_channel_columns(first)
        if not selected:
            tab = "channel"
            self._select_control_in_channel_columns(first)
        self.left_tabs.setCurrentIndex(self._tab_indexes[tab])
        keys = {
            layout_mod.presentation_key_for_hit(hit)
            for control in result.controls
            for hit in catalog.lookup(control.channel, control.event_type, control.control)
        }
        self.layout_view.set_selected_keys(keys)
        self.deck_layout_view.set_selected_keys(keys)
        self.controller_layout_view.set_selected_keys(keys)
        self.statusBar().showMessage(
            QCoreApplication.translate("MainWindow", "'{name}' ({location}): {count} control(s), {highlighted} highlighted on the layout").format(
                name=result.label, location=result.location(), count=len(result.triggers), highlighted=len(keys)
            )
        )

    def _select_deck_group_for_mappings(self, mappings: list[MappingElement]) -> bool:
        """Selects the By Deck row whose group holds one of `mappings` --
        the exact deck/slot row, unlike _select_deck_group's first cell hit."""
        wanted = {id(mapping) for mapping in mappings}
        for view in self._deck_tree_views:
            model = view.model()
            for row in range(model.rowCount()):
                slot_index = model.index(row, 0)
                for child_row in range(model.rowCount(slot_index)):
                    index = model.index(child_row, 0, slot_index)
                    group = index.data(NODE_ROLE)
                    if isinstance(group, MappingGroup) and any(id(m) in wanted for _, _, m in group.members):
                        self._select_model_index(view, index)
                        return True
        return False

    def _update_layout_selection(self, channel: str | None, event_type: str | None, control_no: str | None) -> None:
        keys: set[layout_mod.CellKey] = set()
        if channel and event_type and control_no:
            # presentation_key_for_hit() (not the merged cell_key()) so
            # selecting a control mapped to, say, DDJ-XP2's deck 2/4 pad
            # grid highlights only that physical marker, not both left and
            # right at once.
            keys = {
                layout_mod.presentation_key_for_hit(hit)
                for hit in catalog.lookup(channel, event_type, control_no)
            }
        self.layout_view.set_selected_keys(keys)
        self.deck_layout_view.set_selected_keys(keys)
        self.controller_layout_view.set_selected_keys(keys)

    def _find_ancestor_control(self, item) -> Control | None:
        while item is not None:
            node = item.data(NODE_ROLE)
            if isinstance(node, Control):
                return node
            item = item.parent()
        return None

    def _on_search_text_changed(self, text: str) -> None:
        for proxy in self.channel_proxies:
            proxy.setFilterFixedString(text)

    def _on_channel_selection_changed(self, view: QTreeView, proxy: QSortFilterProxyModel) -> None:
        indexes = view.selectionModel().selectedIndexes()
        if not indexes:
            self.edit_panel.set_node(None)
            self._update_layout_selection(None, None, None)
            return
        source_index = proxy.mapToSource(indexes[0])
        item = proxy.sourceModel().itemFromIndex(source_index)
        self.edit_panel.set_node(item.data(NODE_ROLE))
        control = self._find_ancestor_control(item)
        if control is not None:
            self._update_layout_selection(control.channel, control.event_type, control.control)
        else:
            self._update_layout_selection(None, None, None)

    def _on_command_applied(self, relabel_node: object) -> None:
        item = self.node_to_item.get(id(relabel_node))
        if item is not None:
            relabel_item(item, relabel_node)
        # Deferred so we never rebuild the edit panel from inside the very
        # widget signal (editingFinished/itemChanged) that triggered the edit.
        QTimer.singleShot(0, self._refresh_edit_panel)
        if isinstance(relabel_node, (Control, MappingElement)):
            QTimer.singleShot(0, self._refresh_layout_usage)
            QTimer.singleShot(0, self._refresh_deck_view)

    def _refresh_edit_panel(self) -> None:
        self.edit_panel.set_node(self.edit_panel.current_node)

    def _on_structure_changed(self) -> None:
        """After an edit that adds or removes controls: rebuild every view."""
        if self.config is None:
            return
        self.edit_panel.set_node(None)
        self._rebuild_channel_columns()
        self._refresh_layout_usage()
        self._refresh_deck_view()
        self.function_search_view.set_config(self.config)
        self.live_monitor_view.set_config(self.config)
        self._on_validate()

    def _on_live_ready_check(self) -> LiveReadyDialog | None:
        """Issue #254: the pre-gig report, in a non-modal window. Read-only."""
        if self.config is None:
            self.statusBar().showMessage(QCoreApplication.translate("MainWindow", "Ready for live: open a mapping first."))
            return None
        report = check_live_ready(self.config, translate=_live_ready_translate)
        if self._live_ready_dialog is not None:
            self._live_ready_dialog.close()
            self._live_ready_dialog.deleteLater()
        dialog = LiveReadyDialog(report, self)
        dialog.showControlRequested.connect(self._on_live_ready_show_control)
        self._live_ready_dialog = dialog
        dialog.show()
        counts = report.counts()
        self.statusBar().showMessage(
            QCoreApplication.translate("MainWindow", "Ready for live: {errors} error(s), {warnings} warning(s), {infos} info").format(
                errors=counts["error"], warnings=counts["warning"], infos=counts["info"]
            )
        )
        return dialog

    def _on_live_ready_show_control(self, control: Control) -> None:
        if self._select_control_in_channel_columns(control):
            self.left_tabs.setCurrentIndex(self._tab_indexes["channel"])

    def _on_validate(self) -> None:
        if self.config is None:
            return
        issues: list[ValidationIssue] = validate(self.config, _validator_translate)
        self.issues_table.setRowCount(0)
        for issue in issues:
            row = self.issues_table.rowCount()
            self.issues_table.insertRow(row)
            severity_item = QTableWidgetItem(severity_label(issue.severity, _validator_translate))
            message_item = QTableWidgetItem(issue.message)
            location_item = QTableWidgetItem(issue.location)
            color = _SEVERITY_COLORS.get(issue.severity)
            if color is not None:
                for cell in (severity_item, message_item, location_item):
                    cell.setBackground(color)
            self.issues_table.setItem(row, 0, severity_item)
            self.issues_table.setItem(row, 1, message_item)
            self.issues_table.setItem(row, 2, location_item)

        errors = sum(1 for i in issues if i.severity == "error")
        warnings = sum(1 for i in issues if i.severity == "warning")
        infos = sum(1 for i in issues if i.severity == "info")
        self.statusBar().showMessage(
            QCoreApplication.translate("MainWindow", "Validation: {errors} error(s), {warnings} warning(s), {infos} info").format(
                errors=errors, warnings=warnings, infos=infos
            )
        )
