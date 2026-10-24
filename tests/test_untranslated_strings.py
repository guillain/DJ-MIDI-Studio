"""Guard against interface text left out of the translation (issue #337).

`test_i18n.py` only sees strings already wrapped in ``tr()``, so a window that
never went through a translation pass stayed English without any test
noticing. This walks the AST of every ``djmidi.gui`` module and fails on a
string literal (or the literal parts of an f-string) passed straight to a
widget text API -- a ``QPushButton("Close")``, ``setWindowTitle("…")``,
``setToolTip(f"Send to {port}")``, ``QMessageBox.question(self, "…", "…")``
-- instead of through ``self.tr()`` / ``QCoreApplication.translate()``.

Text that is the same in every language (product, controller and MIDI names,
units, Serato attribute names) goes in `ALLOWED`, one entry per literal.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

GUI_DIR = Path(__file__).resolve().parent.parent / "src" / "djmidi" / "gui"

# Constructors whose first argument is the widget's visible text.
_TEXT_CONSTRUCTORS = {
    "QAction",
    "QCheckBox",
    "QCommandLinkButton",
    "QDockWidget",
    "QGroupBox",
    "QLabel",
    "QMenu",
    "QPushButton",
    "QRadioButton",
    "QToolButton",
}

# Methods and the positional arguments that carry visible text (None = all).
_TEXT_METHODS: dict[str, tuple[int, ...] | None] = {
    "addAction": None,
    "addButton": (0,),
    "addItem": (0,),
    "addItems": (0,),
    "addMenu": None,
    "addRow": (0,),
    "addTab": (1,),
    "insertItem": (1,),
    "insertTab": (2,),
    "setButtonText": (1,),
    "setCancelButtonText": (0,),
    "setDetailedText": (0,),
    "setHeaderLabels": (0,),
    "setHorizontalHeaderLabels": (0,),
    "setHtml": (0,),
    "setInformativeText": (0,),
    "setItemText": (1,),
    "setLabelText": (0,),
    "setPlaceholderText": (0,),
    "setPlainText": (0,),
    "setSpecialValueText": (0,),
    "setStatusTip": (0,),
    "setSubTitle": (0,),
    "setSuffix": (0,),
    "setTabText": (1,),
    "setTabToolTip": (1,),
    "setText": None,
    "setTitle": (0,),
    "setToolTip": (0,),
    "setVerticalHeaderLabels": (0,),
    "setWhatsThis": (0,),
    "setWindowTitle": (0,),
    "showMessage": (0,),
}

# Static dialogs: QMessageBox.question(parent, title, text, ...),
# QFileDialog.getSaveFileName(parent, caption, dir, filter), ...
_STATIC_DIALOGS: dict[str, dict[str, tuple[int, ...]]] = {
    "QMessageBox": {name: (1, 2) for name in ("about", "critical", "information", "question", "warning")},
    "QFileDialog": {
        "getExistingDirectory": (1,),
        "getOpenFileName": (1, 3),
        "getOpenFileNames": (1, 3),
        "getSaveFileName": (1, 3),
    },
    "QInputDialog": {"getDouble": (1, 2), "getInt": (1, 2), "getItem": (1, 2), "getText": (1, 2)},
}

# The same in every language. Matched against the literal with surrounding
# whitespace and punctuation stripped.
ALLOWED = {
    # Product and MIDI vocabulary.
    "DJ MIDI Studio",
    "BPM",
    "SHIFT",
    "kbps",
    # A trigger's raw channel prefix (``ch1 Note On #36``), as in By Channel.
    "ch",
    # Serato XML attribute names, shown as written (CLAUDE.md, issue #318).
    "action_on",
    "behaviour",
    "name",
    "value",
    # Log levels, as the logging module names them.
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
    # Controller submission ``source`` values, typed as written.
    "learned / xml-import / mixed",
}

_WORD = re.compile(r"[A-Za-z]{2,}")
_MARKUP = re.compile(r"<[^>]*>|&[a-z]+;")


def _literals(node: ast.AST):
    """String literals that end up in the text: plain, f-string parts,
    either side of ``+`` / ``or`` / a conditional, and list items."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, ast.JoinedStr):
        for value in node.values:
            if isinstance(value, ast.Constant):
                yield value.value
    elif isinstance(node, ast.BinOp):
        yield from _literals(node.left)
        yield from _literals(node.right)
    elif isinstance(node, ast.BoolOp):
        for value in node.values:
            yield from _literals(value)
    elif isinstance(node, ast.IfExp):
        yield from _literals(node.body)
        yield from _literals(node.orelse)
    elif isinstance(node, (ast.List, ast.Tuple)):
        for element in node.elts:
            yield from _literals(element)


def _text_arguments(call: ast.Call) -> list[ast.AST]:
    func = call.func
    if isinstance(func, ast.Name) and func.id in _TEXT_CONSTRUCTORS:
        return call.args[:1]
    if not isinstance(func, ast.Attribute):
        return []
    if isinstance(func.value, ast.Name) and func.value.id in _STATIC_DIALOGS:
        positions = _STATIC_DIALOGS[func.value.id].get(func.attr, ())
        return [call.args[i] for i in positions if i < len(call.args)]
    if func.attr not in _TEXT_METHODS:
        return []
    positions = _TEXT_METHODS[func.attr]
    if positions is None:
        return list(call.args)
    return [call.args[i] for i in positions if i < len(call.args)]


def _needs_translation(text: str) -> bool:
    visible = _MARKUP.sub(" ", text).strip(" \t\n—–-·:;,.()[]…/")
    return bool(_WORD.search(visible)) and visible not in ALLOWED


def untranslated_literals() -> list[str]:
    found = []
    for path in sorted(GUI_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for argument in _text_arguments(node):
                for text in _literals(argument):
                    if _needs_translation(text):
                        found.append((path.name, node.lineno, text))
    return [f"{name}:{line}: {text!r}" for name, line, text in sorted(found)]


def test_no_literal_interface_text_bypasses_translation():
    leftovers = untranslated_literals()
    assert not leftovers, "Wrap these in self.tr() / QCoreApplication.translate() (or extend ALLOWED):\n" + "\n".join(
        leftovers
    )


def test_the_guard_catches_a_bare_literal(tmp_path, monkeypatch):
    (tmp_path / "sample.py").write_text(
        "from PySide6.QtWidgets import QMessageBox, QPushButton\n"
        "def build(self, port):\n"
        "    QPushButton('Close')\n"
        "    QPushButton(self.tr('Close'))\n"
        "    self.button.setToolTip(f'Send to {port}')\n"
        "    QMessageBox.question(self, 'Quit?', self.tr('Sure?'))\n"
        "    self.combo.addItem(self.tr('Dark'), 'dark')\n"
        "    QLabel('DJ MIDI Studio')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "GUI_DIR", tmp_path)
    assert untranslated_literals() == [
        "sample.py:3: 'Close'",
        "sample.py:5: 'Send to '",
        "sample.py:6: 'Quit?'",
    ]
