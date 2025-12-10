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
    """Verbindet sich per SSH zum Pi und ruft rc_cmd_derin.py auf (nur im Worker-Thread benutzen!)."""

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


class PollWorker(QtCore.QThread):
    """
    Worker-Thread:
    - hält eigene PiController-Instanz
    - pollt alle Kanäle
    - setzt geänderte Sollwerte
    """

    updated = QtCore.pyqtSignal(str, float)   # (what, remote_value)
    error = QtCore.pyqtSignal(str)            # Fehlermeldung als Text

    def __init__(self, host, user, password, channels, parent=None):
        super().__init__(parent)
        self.host = host
        self.user = user
        self.password = password
        self.channels = channels  # Liste von "C", "L", "L1", "L2"
        self._stop_flag = False

        # Zustände je Kanal
        self._desired = {ch: None for ch in channels}
        self._user_modified = {ch: False for ch in channels}
        self._last_sent = {ch: None for ch in channels}

        self._lock = QtCore.QMutex()

    @QtCore.pyqtSlot(str, float)
    def set_desired(self, what: str, value: float):
        """Vom GUI aufgerufen, wenn Nutzer die Spinbox geändert hat."""
        with QtCore.QMutexLocker(self._lock):
            self._desired[what] = value
            self._user_modified[what] = True

    def stop(self):
        self._stop_flag = True

    def run(self):
        controller = None
        try:
            controller = PiController(self.host, self.user, self.password)
        except Exception as e:
            self.error.emit(f"Verbindungsfehler: {e}")
            return

        try:
            while not self._stop_flag:
                # für jeden Kanal nacheinander poll + ggf. setzen
                for ch in self.channels:
                    if self._stop_flag:
                        break

                    try:
                        remote_val = controller.get_value(ch)
                    except Exception as e:
                        self.error.emit(f"Fehler beim Lesen ({ch}): {e}")
                        continue

                    # prüfen, ob Nutzer geändert hat
                    with QtCore.QMutexLocker(self._lock):
                        user_mod = self._user_modified[ch]
                        desired = self._desired[ch]
                        last_sent = self._last_sent[ch]

                    if user_mod and desired is not None:
                        # nur senden, wenn sich der Sollwert echt geändert hat
                        if last_sent is None or abs(desired - last_sent) > 1e-9:
                            try:
                                new_val = controller.set_value(ch, desired)
                                remote_val = new_val
                                with QtCore.QMutexLocker(self._lock):
                                    self._last_sent[ch] = new_val
                                    self._user_modified[ch] = False
                            except Exception as e:
                                self.error.emit(f"Fehler beim Setzen ({ch}): {e}")
                                # bei Fehler: Änderung als "abgehandelt" markieren, damit nicht gespammt wird
                                with QtCore.QMutexLocker(self._lock):
                                    self._user_modified[ch] = False

                    # GUI aktualisieren
                    self.updated.emit(ch, remote_val)

                self.msleep(POLL_INTERVAL_MS)

        finally:
            if controller is not None:
                controller.close()


class ChannelWidget(QtWidgets.QGroupBox):
    """Ein Block für eine Größe (C, L, L1, L2). Nur GUI-Logik, kein SSH hier drin."""

    desiredChanged = QtCore.pyqtSignal(str, float)  # (what, value)

    def __init__(
        self,
        label: str,
        what: str,
        unit: str,
        min_val: float,
        max_val: float,
        step: float,
        parent=None,
    ):
        super().__init__(label, parent)
        self.what = what
        self.unit = unit

        self.value_label = QtWidgets.QLabel(f"Aktueller Wert: ? {self.unit}")

        self.spin = QtWidgets.QDoubleSpinBox()
        self.spin.setDecimals(3)
        self.spin.setMinimum(min_val)
        self.spin.setMaximum(max_val)
        self.spin.setSingleStep(step)
        self.spin.setKeyboardTracking(False)

        form = QtWidgets.QFormLayout()
        form.addRow(self.value_label)

        spin_layout = QtWidgets.QHBoxLayout()
        spin_layout.addWidget(self.spin)
        spin_layout.addWidget(QtWidgets.QLabel(self.unit))
        form.addRow("Sollwert:", spin_layout)

        self.setLayout(form)

        # wenn Nutzer ändert → Signal an Worker
        self.spin.valueChanged.connect(self.on_spin_changed)

        # Flag, um UI-Updates von Worker von User-Änderungen zu unterscheiden
        self._updating_from_remote = False

    def on_spin_changed(self, val):
        if self._updating_from_remote:
            return
        # Nutzer hat gedreht → Worker informieren
        self.desiredChanged.emit(self.what, float(val))

    @QtCore.pyqtSlot(float)
    def set_remote_value(self, val: float):
        """Vom Worker-Thread (über MainWindow) aufgerufen, um den aktuellen Wert anzuzeigen."""
        self.value_label.setText(f"Aktueller Wert: {val} {self.unit}")
        self._updating_from_remote = True
        self.spin.setValue(val)
        self._updating_from_remote = False


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("LC-Kreis Steuerung (auto, rc_cmd_derin)")

        # Channel-Widgets (nur GUI)
        self.ch_C = ChannelWidget(
            "Kapazität C",
            "C",
            "pF",
            0.0,
            32768.0,
            0.5,
        )
        self.ch_L = ChannelWidget(
            "Induktivität gemeinsam L",
            "L",
            "µH",
            0.0,
            512.0,
            0.25,
        )
        self.ch_L1 = ChannelWidget(
            "Induktivität 1",
            "L1",
            "µH",
            0.0,
            512.0,
            0.25,
        )
        self.ch_L2 = ChannelWidget(
            "Induktivität 2",
            "L2",
            "µH",
            0.0,
            512.0,
            0.25,
        )

        grid = QtWidgets.QGridLayout()
        grid.addWidget(self.ch_C, 0, 0)
        grid.addWidget(self.ch_L, 0, 1)
        grid.addWidget(self.ch_L1, 1, 0)
        grid.addWidget(self.ch_L2, 1, 1)

        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addLayout(grid)
        self.setLayout(main_layout)

        # Worker-Thread starten
        self.worker = PollWorker(
            PI_HOST,
            PI_USER,
            PI_PASSWORD,
            ["C", "L", "L1", "L2"],
            self,
        )
        self.worker.updated.connect(self.on_worker_updated)
        self.worker.error.connect(self.on_worker_error)

        # GUI → Worker: gewünschte Sollwerte
        self.ch_C.desiredChanged.connect(self.worker.set_desired)
        self.ch_L.desiredChanged.connect(self.worker.set_desired)
        self.ch_L1.desiredChanged.connect(self.worker.set_desired)
        self.ch_L2.desiredChanged.connect(self.worker.set_desired)

        self.worker.start()

    @QtCore.pyqtSlot(str, float)
    def on_worker_updated(self, what: str, value: float):
        if what == "C":
            self.ch_C.set_remote_value(value)
        elif what == "L":
            self.ch_L.set_remote_value(value)
        elif what == "L1":
            self.ch_L1.set_remote_value(value)
        elif what == "L2":
            self.ch_L2.set_remote_value(value)

    @QtCore.pyqtSlot(str)
    def on_worker_error(self, msg: str):
        # Einmalig anzeigen; du kannst das später auch in eine Statuszeile schreiben.
        QtWidgets.QMessageBox.critical(self, "Fehler im Worker", msg)

    def closeEvent(self, event):
        try:
            self.worker.stop()
            self.worker.wait(2000)
        except Exception:
            pass
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.resize(900, 600)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
