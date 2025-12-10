#!/usr/bin/env python3
import sys
import paramiko
from PyQt5 import QtWidgets, QtCore


# >>>>>> HIER ggf. ANPASSEN <<<<<<
PI_HOST = "raspberrypi.local"    # oder feste IP, die sicher funktioniert
PI_USER = "pi"
PI_PASSWORD = "raspberry"        # dein aktuelles Pi-Passwort
REMOTE_RC_CMD = "python3 ~/Desktop/Python/rc_cmd_derin.py"
POLL_INTERVAL_MS = 1000          # alle 1000 ms (1 s) auslesen/setzen
# >>>>>> ENDE ANPASSUNG <<<<<<


class PiController:
    """Verbindet sich per SSH zum Pi und ruft rc_cmd_derin.py auf."""

    def __init__(self, host, user, password):
        self.host = host
        self.user = user
        self.password = password
        self.client = None
        self._connect()

    def _connect(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            self.host,
            username=self.user,
            password=self.password,
            look_for_keys=False,
            allow_agent=False,
        )

    def exec_rc_cmd(self, args):
        """rc_cmd_derin.py mit Argumenten ausführen, stdout/stderr zurückgeben."""
        cmd = f"{REMOTE_RC_CMD} " + " ".join(args)
        stdin, stdout, stderr = self.client.exec_command(cmd)
        out = stdout.read().decode("utf-8").strip()
        err = stderr.read().decode("utf-8").strip()
        return out, err

    def get_value(self, what: str) -> float:
        out, err = self.exec_rc_cmd(["get", what])
        if err:
            raise RuntimeError(err)
        return float(out)

    def set_value(self, what: str, value: float) -> float:
        out, err = self.exec_rc_cmd(["set", what, str(value)])
        if err:
            raise RuntimeError(err)
        return float(out)

    def close(self):
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None


class ChannelWidget(QtWidgets.QGroupBox):
    """Ein Block für eine Größe (C, L, L1, L2) mit Auto-Polling."""

    def __init__(
        self,
        label: str,
        what: str,
        unit: str,
        min_val: float,
        max_val: float,
        step: float,
        controller: PiController | None,
        parent=None,
    ):
        super().__init__(label, parent)
        self.what = what   # "C", "L", "L1", "L2"
        self.unit = unit
        self.controller = controller

        self.value_label = QtWidgets.QLabel(f"Aktueller Wert: ? {self.unit}")

        self.spin = QtWidgets.QDoubleSpinBox()
        self.spin.setDecimals(3)
        self.spin.setMinimum(min_val)
        self.spin.setMaximum(max_val)
        self.spin.setSingleStep(step)
        self.spin.setKeyboardTracking(False)  # nur bei Enter/Fokuswechsel / Scroll

        # Statusflags
        self._user_modified = False   # hat der User seit letztem Poll gedreht?
        self._last_sent = None        # zuletzt gesetzter Wert

        # Layout
        form = QtWidgets.QFormLayout()
        form.addRow(self.value_label)

        spin_layout = QtWidgets.QHBoxLayout()
        spin_layout.addWidget(self.spin)
        spin_layout.addWidget(QtWidgets.QLabel(self.unit))
        form.addRow("Sollwert:", spin_layout)

        self.setLayout(form)

        # Deaktivieren, falls keine Verbindung
        if self.controller is None:
            self.spin.setEnabled(False)

        # SpinBox-Änderung merken
        self.spin.valueChanged.connect(self.on_spin_changed)

    def on_spin_changed(self, _):
        # Nutzer hat am Wert gedreht → beim nächsten Poll setzen
        self._user_modified = True

    def poll(self):
        """Ein Poll-Zyklus: Wert lesen und ggf. Sollwert setzen."""
        if self.controller is None:
            return

        try:
            # 1) aktuellen Wert vom Pi holen
            remote_val = self.controller.get_value(self.what)
        except Exception as e:
            # Bei Fehler einmal popup (optional kannst du das später entschärfen)
            QtWidgets.QMessageBox.critical(self, "Fehler beim Lesen", str(e))
            return

        # Anzeige aktualisieren
        self.value_label.setText(f"Aktueller Wert: {remote_val} {self.unit}")

        # Wenn der Nutzer NICHT gedreht hat, GUI an Hardware anpassen
        if not self._user_modified:
            self.spin.blockSignals(True)
            self.spin.setValue(remote_val)
            self.spin.blockSignals(False)
            self._last_sent = remote_val
            return

        # Wenn der Nutzer gedreht hat: neuen Sollwert setzen
        desired = float(self.spin.value())

        # Nur senden, wenn sich der Sollwert tatsächlich geändert hat
        if self._last_sent is not None and abs(desired - self._last_sent) < 1e-9:
            # nichts zu tun
            self._user_modified = False
            return

        try:
            new_val = self.controller.set_value(self.what, desired)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Fehler beim Setzen", str(e))
            # Nutzer-Eingabe als "abgehandelt" markieren, um Spam zu vermeiden
            self._user_modified = False
            return

        # Erfolgreich gesetzt → Anzeige & internen Status aktualisieren
        self._last_sent = new_val
        self.value_label.setText(f"Aktueller Wert: {new_val} {self.unit}")
        self.spin.blockSignals(True)
        self.spin.setValue(new_val)
        self.spin.blockSignals(False)
        self._user_modified = False


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("LC-Kreis Steuerung (rc_cmd_derin, Auto-Poll)")

        # Verbindung zum Pi aufbauen
        try:
            self.controller = PiController(PI_HOST, PI_USER, PI_PASSWORD)
            status_text = f"Verbunden mit {PI_HOST}"
        except Exception as e:
            self.controller = None
            status_text = f"Verbindungsfehler: {e}"

        self.status_label = QtWidgets.QLabel(status_text)

        # Channel-Widgets
        self.ch_C = ChannelWidget(
            "Kapazität C",
            "C",
            "pF",
            0.0,
            32768.0,
            0.5,
            self.controller,
        )
        self.ch_L = ChannelWidget(
            "Induktivität gemeinsam L",
            "L",
            "µH",
            0.0,
            512.0,
            0.25,
            self.controller,
        )
        self.ch_L1 = ChannelWidget(
            "Induktivität 1",
            "L1",
            "µH",
            0.0,
            512.0,
            0.25,
            self.controller,
        )
        self.ch_L2 = ChannelWidget(
            "Induktivität 2",
            "L2",
            "µH",
            0.0,
            512.0,
            0.25,
            self.controller,
        )

        # Layout
        grid = QtWidgets.QGridLayout()
        grid.addWidget(self.ch_C, 0, 0)
        grid.addWidget(self.ch_L, 0, 1)
        grid.addWidget(self.ch_L1, 1, 0)
        grid.addWidget(self.ch_L2, 1, 1)

        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addWidget(self.status_label)
        main_layout.addLayout(grid)
        self.setLayout(main_layout)

        # Poll-Timer einrichten
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(POLL_INTERVAL_MS)
        self.timer.timeout.connect(self.poll_all)

        if self.controller is not None:
            self.timer.start()

    def poll_all(self):
        for ch in (self.ch_C, self.ch_L, self.ch_L1, self.ch_L2):
            ch.poll()

    def closeEvent(self, event):
        if self.controller is not None:
            self.controller.close()
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.resize(900, 600)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
