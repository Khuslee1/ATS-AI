"""ATS-AI settings window.

    .venv/bin/python app/settings.py

Tab «Миний үгс»: the user's own words (~/.local/share/ats-ai/my_words.tsv) and the corrections
remembered while typing. Tab «Сүүлийн бичсэн»: the last words typed, marked
right or wrong; a fix works at once while typing and is checked training data. All file work is in ats_ai/words.py; this file is
only the window, so the Windows version can reuse the same logic.
Changes reach the input method on the next key press, no restart.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QBrush, QColor  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from datetime import datetime  # noqa: E402

from ats_ai import share, words  # noqa: E402
from ats_ai.config import ESCAPE_CHOICES, Config, models  # noqa: E402

HOW = {"picked": "Жагсаалтаас сонгосон", "latin": "Латинаар үлдээсэн (Esc)"}


def table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    return t


def fill(t, rows):
    # No signals while filling: a handler per cell would make 1000+ rows hang.
    t.blockSignals(True)
    t.setUpdatesEnabled(False)
    t.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            t.setItem(i, j, QTableWidgetItem(value))
    t.setUpdatesEnabled(True)
    t.blockSignals(False)


def check_table(headers):
    """A table whose first column is a checkbox; clicking any cell ticks the row."""
    t = table([""] + headers)
    # Fixed width: measuring the column ("ResizeToContents") over 1000+ rows is slow.
    t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
    t.setColumnWidth(0, 32)

    def toggle(row, column):
        if column != 0:  # the box itself toggles on its own
            item = t.item(row, 0)
            item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    t.cellClicked.connect(toggle)
    return t


def fill_checks(t, rows):
    fill(t, [("",) + tuple(r) for r in rows])
    t.blockSignals(True)
    for i in range(len(rows)):
        box = QTableWidgetItem()
        box.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        box.setCheckState(Qt.Unchecked)
        t.setItem(i, 0, box)
    t.blockSignals(False)
    if hasattr(t, "refresh_check_label"):
        t.refresh_check_label()


def checked(t):
    """Indexes of the ticked rows."""
    # Rows being filled may not have their box yet.
    return [i for i in range(t.rowCount()) if t.item(i, 0) and t.item(i, 0).checkState() == Qt.Checked]


def check_all_button(t):
    """«Бүгдийг сонгох» that turns into «Сонголт цуцлах» while all are ticked."""
    button = QPushButton("Бүгдийг сонгох")

    def label(*_):
        all_on = t.rowCount() > 0 and len(checked(t)) == t.rowCount()
        button.setText("Сонголт цуцлах" if all_on else "Бүгдийг сонгох")

    def flip():
        on = len(checked(t)) < t.rowCount()
        t.blockSignals(True)  # one label update at the end, not one per row
        for i in range(t.rowCount()):
            t.item(i, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)
        t.blockSignals(False)
        t.viewport().update()
        label()

    def one_changed(item):
        if item.column() == 0:
            label()

    button.clicked.connect(flip)
    t.itemChanged.connect(one_changed)
    t.refresh_check_label = label
    return button


class MyWordsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # My words: add / replace / remove
        mine = QGroupBox("Миний заасан үгс — загвараас түрүүлж хэрэглэгдэнэ")
        box = QVBoxLayout(mine)
        form = QHBoxLayout()
        self.latin = QLineEdit(placeholderText="Латинаар, ж: thdee")
        self.cyrillic = QLineEdit(placeholderText="Кириллээр, ж: тэгэхдээ")
        add = QPushButton("Нэмэх")
        add.setDefault(True)
        add.clicked.connect(self.add)
        self.cyrillic.returnPressed.connect(self.add)
        form.addWidget(self.latin)
        form.addWidget(self.cyrillic)
        form.addWidget(add)
        box.addLayout(form)
        self.mine = table(["Латин", "Кирилл"])
        self.mine.itemSelectionChanged.connect(self.pick_mine)
        box.addWidget(self.mine)
        remove = QPushButton("Сонгосныг устгах")
        remove.clicked.connect(self.remove)
        box.addWidget(remove, alignment=Qt.AlignRight)
        layout.addWidget(mine)

        # Remembered while typing: forget
        learned = QGroupBox("Бичих явцад цээжилсэн засварууд")
        box = QVBoxLayout(learned)
        box.addWidget(QLabel(
            "Буруу цээжилсэн бол сонгоод «Мартах» дарна. Дахин жагсаалтаас сонговол буцаж цээжилнэ."
        ))
        self.learned = table(["Латин", "Кирилл", "Хэрхэн"])
        box.addWidget(self.learned)
        forget = QPushButton("Сонгосныг мартах")
        forget.clicked.connect(self.forget)
        box.addWidget(forget, alignment=Qt.AlignRight)
        layout.addWidget(learned)

        self.reload()

    def reload(self):
        fill(self.mine, words.my_words())
        self.remembered = words.remembered()
        fill(self.learned, [(l, c, HOW.get(h, h)) for l, c, h in self.remembered])

    def selected(self, t):
        rows = t.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def pick_mine(self):
        # Selecting a row puts it in the form, so it can be changed and added again.
        i = self.selected(self.mine)
        if i is not None:
            self.latin.setText(self.mine.item(i, 0).text())
            self.cyrillic.setText(self.mine.item(i, 1).text())

    def add(self):
        try:
            words.add_my_word(self.latin.text(), self.cyrillic.text())
        except ValueError as error:
            QMessageBox.warning(self, "Нэмж чадсангүй", str(error))
            return
        self.latin.clear()
        self.cyrillic.clear()
        self.latin.setFocus()
        self.reload()

    def remove(self):
        i = self.selected(self.mine)
        if i is not None:
            words.remove_my_word(self.mine.item(i, 0).text())
            self.reload()

    def forget(self):
        i = self.selected(self.learned)
        if i is not None:
            latin, cyrillic, _ = self.remembered[i]
            words.forget(latin, cyrillic)
            self.reload()


HOW_SHORT = {"accepted": "", "picked": "сонгосон", "latin": "Esc"}
OK_COLOR = QColor("#2e7d32")
WRONG_COLOR = QColor("#c62828")


class RecentTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Сүүлд бичсэн үгс (шинэ нь дээрээ). Буруу гарсныг сонгоод «Буруу…» дарж зөв үгийг бичнэ —\n"
            "дараагийн удаа тэр үгийн өмнө ижил үг байвал шууд зөвөөр гарна. Зөв гарсныг «Зөв» гэж тэмдэглэвэл\n"
            "загвар сургахад шалгагдсан өгөгдөл болно."
        ))
        top = QHBoxLayout()
        self.only_new = QCheckBox("Зөвхөн тэмдэглээгүй")
        self.only_new.toggled.connect(self.reload)
        refresh = QPushButton("Шинэчлэх")
        refresh.clicked.connect(self.reload)
        top.addWidget(self.only_new)
        top.addStretch()
        top.addWidget(refresh)
        layout.addLayout(top)

        self.table = check_table(["Өмнөх үг", "Латин", "Гарсан", "Тэмдэглэл"])
        self.table.cellDoubleClicked.connect(lambda row, _: self.wrong(row))
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        buttons.addWidget(check_all_button(self.table))
        buttons.addStretch()
        ok = QPushButton("✓ Сонгосныг зөв")
        ok.clicked.connect(self.ok)
        wrong = QPushButton("✗ Буруу…")
        wrong.clicked.connect(lambda: self.wrong())
        buttons.addWidget(ok)
        buttons.addWidget(wrong)
        layout.addLayout(buttons)
        self.reload()

    def reload(self):
        self.words = [w for w in words.recent() if not (self.only_new.isChecked() and w["verdict"])]
        rows = []
        for w in self.words:
            if w["verdict"] == "ok":
                note = "✓ зөв"
            elif w["verdict"] == "wrong":
                note = f"✗ → {w['correct']}"
            else:
                note = HOW_SHORT.get(w["how"], w["how"])
            rows.append((w["context"].split()[-1] if w["context"] else "", w["latin"], w["output"], note))
        fill_checks(self.table, rows)
        for i, w in enumerate(self.words):
            color = {"ok": OK_COLOR, "wrong": WRONG_COLOR}.get(w["verdict"])
            if color:
                self.table.item(i, 4).setForeground(QBrush(color))

    def chosen(self):
        return [self.words[i] for i in checked(self.table)]

    def ok(self):
        chosen = self.chosen()
        if not chosen:
            QMessageBox.information(self, "Зөв", "Мөрийн эхний ☐-г тэмдэглэнэ үү.")
            return
        for w in chosen:
            words.mark(w, "ok")
        self.reload()

    def wrong(self, row=None):
        chosen = [self.words[row]] if row is not None else self.chosen()
        if len(chosen) != 1:
            QMessageBox.information(self, "Буруу", "Нэг мөрийг тэмдэглэнэ үү (эсвэл мөрөн дээр 2 дарна).")
            return
        w = chosen[0]
        correct, done = QInputDialog.getText(
            self, "Зөв нь юу вэ?", f"«{w['latin']}» → «{w['output']}» гарсан. Зөв үг:",
            text=w["correct"] or w["output"],
        )
        if not done:
            return
        try:
            words.mark(w, "wrong", correct)
        except ValueError as error:
            QMessageBox.warning(self, "Хадгалсангүй", str(error))
            return
        self.reload()


ESCAPE_LABELS = {1: "1 удаа дарахад", 2: "2 удаа дарахад (санал болгох)", 0: "Хэзээ ч цээжлэхгүй"}


class SettingsTab(QWidget):
    """Every change is saved at once; the input method sees it on the next key."""

    def __init__(self):
        super().__init__()
        self.config = Config()
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.paused = QCheckBox("Суралцахыг түр зогсоох")
        self.paused.setToolTip("Бичсэн үгсийг түүхэнд хадгалахгүй, юу ч цээжлэхгүй (нууц зүйл бичих үед).")
        self.paused.toggled.connect(lambda on: self.config.save(paused=on))
        form.addRow("Суралцах:", self.paused)

        self.escapes = QComboBox()
        for n in ESCAPE_CHOICES:
            self.escapes.addItem(ESCAPE_LABELS[n], n)
        self.escapes.currentIndexChanged.connect(
            lambda i: self.config.save(escapes=self.escapes.itemData(i))
        )
        form.addRow("Esc-ээр латинаар үлдээсэн үгийг\nүргэлж латинаар бичих:", self.escapes)

        self.model = QComboBox()
        self.model.currentIndexChanged.connect(self.pick_model)
        form.addRow("Загвар:", self.model)

        layout.addLayout(form)
        note = QLabel("Өөрчлөлт хадгалагдаж, дараагийн товч дарахад үйлчилнэ.")
        note.setStyleSheet("color: gray")
        layout.addWidget(note)
        layout.addStretch()
        self.reload()

    def reload(self):
        # Fill without saving back what is only being shown.
        for w in (self.paused, self.escapes, self.model):
            w.blockSignals(True)
        self.paused.setChecked(self.config.get("paused"))
        self.escapes.setCurrentIndex(max(0, self.escapes.findData(self.config.get("escapes"))))
        self.model.clear()
        for path in models():
            when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
            self.model.addItem(f"{path.stem}  ({when})", path.name)
        current = self.config.get("model")
        # v5.pt and v5.npz are the same model (torch / numpy): match by version.
        index = next((i for i in range(self.model.count())
                      if not current or Path(self.model.itemData(i)).stem == Path(current).stem), -1)
        if index < 0:
            self.model.addItem(f"{current}  (файл алга)", current)
            index = self.model.count() - 1
        self.model.setCurrentIndex(index)
        for w in (self.paused, self.escapes, self.model):
            w.blockSignals(False)

    def pick_model(self, i):
        name = self.model.itemData(i)
        if name and Path(name).stem != Path(self.config.get("model")).stem:
            self.config.save(model=name)


HOW_LONG = {"accepted": "", "picked": "сонгосон", "latin": "Esc", "undone": "буцаасан"}


class ShareTab(QWidget):
    """Export for a tester: look at everything, remove what is private, save a file."""

    def __init__(self):
        super().__init__()
        self.config = Config()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Сургалтад хэрэглэх файл гаргана. Юу ч автоматаар илгээгдэхгүй — файлыг та өөрөө өгнө.\n"
            "Тоо (3+ оронтой), имэйл, вэб хаягтай мөрийг автоматаар хассан. Доорх бүх мөрийг үзээд,\n"
            "хувийн зүйл байвал сонгоод «Хасах» дарна уу."
        ))
        top = QHBoxLayout()
        top.addWidget(QLabel("Туршигчийн код:"))
        self.code = QLineEdit(placeholderText="ж: tester03 (нэр биш)")
        self.code.setMaximumWidth(200)
        top.addWidget(self.code)
        self.since = QCheckBox("Өмнө хуваалцсанаас хойших л")
        self.since.setChecked(True)
        self.since.toggled.connect(self.reload)
        top.addWidget(self.since)
        top.addStretch()
        layout.addLayout(top)

        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.table = check_table(["Өмнөх үг", "Латин", "Гарсан", "Хэрхэн", "Тэмдэглэл"])
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        buttons.addWidget(check_all_button(self.table))
        remove = QPushButton("Сонгосныг хасах")
        remove.clicked.connect(self.remove)
        save = QPushButton("Файл болгож хадгалах…")
        save.clicked.connect(self.save)
        buttons.addWidget(remove)
        buttons.addStretch()
        buttons.addWidget(save)
        layout.addLayout(buttons)
        self.reload()

    def reload(self):
        self.code.setText(self.code.text() or self.config.get("tester"))
        start = self.config.get("shared_upto") if self.since.isChecked() else 0
        self.rows, self.dropped, self.end = share.rows(start)
        self.removed = 0
        self.show_rows()

    def show_rows(self):
        def note(r):
            if r["verdict"] == "wrong":
                return f"✗ → {r['correct']}"
            return "✓" if r["verdict"] == "ok" else ""

        fill_checks(self.table, [(r["context"].split()[-1] if r["context"] else "", r["latin"], r["output"],
                           HOW_LONG.get(r["how"], r["how"]), note(r)) for r in self.rows])
        self.summary.setText(
            f"Хуваалцах: {len(self.rows)} мөр · автоматаар хассан: {self.dropped} · гараар хассан: {self.removed}"
        )

    def remove(self):
        chosen = set(checked(self.table))
        if not chosen:
            QMessageBox.information(self, "Хасах", "Хасах мөрийн эхний ☐-г тэмдэглэнэ үү.")
            return
        self.rows = [r for i, r in enumerate(self.rows) if i not in chosen]
        self.removed += len(chosen)
        self.show_rows()

    def save(self):
        code = self.code.text().strip().lower()
        if not share.CODE.match(code):
            QMessageBox.warning(self, "Код", "Туршигчийн код: латин жижиг үсэг, тоо, - эсвэл _ (ж: tester03).")
            return
        if not self.rows:
            QMessageBox.information(self, "Хуваалцах", "Хуваалцах мөр алга.")
            return
        answer = QMessageBox.question(
            self, "Шалгасан уу?",
            f"{len(self.rows)} мөрийг бүгдийг нь үзэж, хувийн зүйл байхгүйг шалгасан уу?",
        )
        if answer != QMessageBox.Yes:
            return
        default = str(Path.home() / share.file_name(code))
        path, _ = QFileDialog.getSaveFileName(self, "Хадгалах", default, "TSV (*.tsv)")
        if not path:
            return
        try:
            share.write(Path(path), code, self.rows, self.config.get("model"))
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Хадгалсангүй", str(error))
            return
        self.config.save(tester=code, shared_upto=self.end)
        QMessageBox.information(self, "Хадгаллаа", f"{path}\n\nЭнэ файлыг хөгжүүлэгчид өгнө үү.")
        self.reload()


def main():
    app = QApplication(sys.argv)
    window = QTabWidget()
    window.setWindowTitle("ATS-AI")
    window.addTab(MyWordsTab(), "Миний үгс")
    recent = RecentTab()
    window.addTab(recent, "Сүүлийн бичсэн")
    window.addTab(SettingsTab(), "Тохиргоо")
    window.addTab(ShareTab(), "Хуваалцах")
    window.currentChanged.connect(lambda i: window.widget(i).reload())
    window.resize(640, 640)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
