from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton, QGridLayout, QApplication
from PyQt6.QtCore import Qt
from core.calculator import Calculator

class CalculatorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kalkulator")
        self.setFixedSize(300, 540)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.calculator = Calculator()

       
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right() - self.width() - 320
        y = screen.top() + 50
        self.move(x, y)

  
        self.setStyleSheet("""
            QDialog {
                background: #f5f6fa;
                border-radius: 18px;
            }
        """)

        layout = QVBoxLayout(self)
        self.display = QLineEdit()
        self.display.setReadOnly(True)
        self.display.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.display.setFixedHeight(48)
        self.display.setStyleSheet("""
            QLineEdit {
                background: #fff;
                border: 2px solid #dcdde1;
                border-radius: 12px;
                font-size: 28px;
                padding: 6px 12px;
            }
        """)
        layout.addWidget(self.display)

        buttons = [
            ('C', '←', '%', '/'),
            ('7', '8', '9', '*'),
            ('4', '5', '6', '-'),
            ('1', '2', '3', '+'),
            ('0', '.', '+/-', '='),
        ]
        grid = QGridLayout()
        grid.setSpacing(10)  

        for row, keys in enumerate(buttons):
            for col, key in enumerate(keys):
                if key == '':
                    continue
                btn = QPushButton(key)
                btn.setFixedSize(56, 56)  
                grid.addWidget(btn, row, col)
                btn.setStyleSheet(self.button_style())
                if key == 'C':
                    btn.clicked.connect(self.clear_display)
                elif key == '←':
                    btn.clicked.connect(self.backspace)
                else:
                    btn.clicked.connect(self.on_button_clicked)
        layout.addLayout(grid)

        self.current = ""
        self.update_display()

    def button_style(self):
        return """
            QPushButton {
                background: #2980b9;
                color: #fff;
                border: none;
                border-radius: 28px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #3498db;
            }
            QPushButton:pressed {
                background: #1c5d99;
                color: #eaf6fb;
            }
        """

    def on_button_clicked(self):
        sender = self.sender()
        key = sender.text()

        if key == "=":
            self.current = self.calculator.evaluate(self.current)
            self.update_display()
            if self.current == "blad":
                self.current = ""
            return

        if key == "+/-":
            if self.current:
                import re
                numbers = list(re.finditer(r'[\d.]+', self.current))
                if numbers:
                    last = numbers[-1]
                    start, end = last.span()
                    num = self.current[start:end]
                    if self.current[start-1:start] == '-':
                        self.current = self.current[:start-1] + self.current[start:]
                    else:
                        self.current = self.current[:start] + '-' + self.current[start:]
            self.update_display()
            return

        if key == "%":
            if self.current:
                import re
                numbers = list(re.finditer(r'[\d.]+', self.current))
                if numbers:
                    last = numbers[-1]
                    start, end = last.span()
                    num = self.current[start:end]
                    try:
                        percent = str(float(num) / 100)
                        self.current = self.current[:start] + percent + self.current[end:]
                    except Exception:
                        pass
            self.update_display()
            return

        if key in "0123456789":
            if self.current == "" and key == "0":
                self.current = "0"
            elif self.current == "0" and key == "0":
                return
            elif self.current == "0" and key != ".":
                self.current = key
            else:
                if self.current and self.current[-1] in "+-*/" and key == "0":
                    self.current += key
                else:
                    parts = self.current.split("+") + self.current.split("-") + self.current.split("*") + self.current.split("/")
                    last = parts[-1] if parts else ""
                    if last == "0" and key == "0":
                        return
                    self.current += key

        elif key == ".":
            last_num = self._get_last_number()
            if "." not in last_num:
                if self.current == "" or self.current[-1] in "+-*/":
                    self.current += "0."
                else:
                    self.current += "."
        elif key in "+-*/":
            if self.current and self.current[-1] not in "+-*/.":
                self.current += key

        self.update_display()

    def _get_last_number(self):
        import re
        numbers = re.findall(r'[\d.]+', self.current)
        return numbers[-1] if numbers else ""

    def update_display(self):
        if self.current == "" or self.current == "blad":
            self.display.setText("0")
        else:
            self.display.setText(self.current)

    def clear_display(self):
        self.current = ""
        self.update_display()

    def backspace(self):
        self.current = self.current[:-1]
        self.update_display()