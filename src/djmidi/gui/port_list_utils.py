"""Utility for populating a checkable QListWidget with MIDI port names,
re-checking any port that was already checked before the refresh.

Both LiveMonitorView and ControllerSetupView share this exact pattern —
extracting it here removes the duplication and makes future port-list
widgets a one-liner.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem


def refresh_checked_port_list(
    port_list: QListWidget,
    get_ports: Callable[[], list[str]],
) -> None:
    """Clears *port_list* and repopulates it from *get_ports()*.

    Any port whose name was checked before the refresh is re-checked;
    newly-appeared or disappeared ports start unchecked / are removed."""
    checked = {
        port_list.item(i).text()
        for i in range(port_list.count())
        if port_list.item(i).checkState() == Qt.CheckState.Checked
    }
    port_list.clear()
    for name in get_ports():
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if name in checked else Qt.CheckState.Unchecked)
        port_list.addItem(item)


def refresh_selectable_port_list(
    port_list: QListWidget,
    get_ports: Callable[[], list[str]],
) -> None:
    """Clears *port_list* and repopulates it from *get_ports()*.

    Preserves the current selection by port name when possible; otherwise selects
    the first available port.
    """
    current = port_list.currentItem().text() if port_list.currentItem() is not None else None
    port_list.clear()
    ports = get_ports()
    for name in ports:
        port_list.addItem(name)
    if not ports:
        return
    if current is not None:
        for row in range(port_list.count()):
            if port_list.item(row).text() == current:
                port_list.setCurrentRow(row)
                return
    port_list.setCurrentRow(0)


__all__ = ["refresh_checked_port_list", "refresh_selectable_port_list"]

