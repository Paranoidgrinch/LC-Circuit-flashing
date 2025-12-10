#!/usr/bin/env python3
import sys
import threading
import paramiko
from PyQt5 import QtWidgets, QtCore


# >>>>>>> HIER ggf. ANPASSEN <<<<<<<<
PI_HOST = "raspberrypi.local"   # oder deine IP / Hostname
PI_USER = "pi"
PI_PASSWORD = "raspberry"     # falls geändert: hier dein Passwort
REMOTE_CMD = "cd ~/Desktop/Python && python3 resonantCircuit_derin.py"
# >>>>>>> ENDE ANPASSUNG <<<<<<<<


class SSHWorker(QtCore.QThread):
    received = QtCore.pyqtSignal(str)
    connected = QtCore.pyqtSignal()
    disconnected = QtCore.pyqtSignal(str)

    def __init__(self, host, user, password, command, parent=None):
        super().__init__(parent)
        self.host = host
        self.user = user
        self.password = password
        self.command = command
        self._client = None
        self._channel = None
        self._stop_flag = False
        self._lock = threading.Lock()

    def run(self):
        buffer = ""  # wichtig: vor try initialisieren
        try:
            # SSH-Verbindung aufbauen
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._client.connect(
                self.host,
                username=self.user,
                password=self.password,
                look_for_keys=False,
                allow_agent=False,
            )

            # Session / Channel öffnen
            transport = self._client.get_transport()
            self._channel = transport.open_session()
            self._channel.get_pty()  # Pseudo-Terminal
            self._channel.exec_command(self.command)

            self.connected.emit()

            # Daten lesen
            while not self._stop_flag:
                if self._channel.recv_ready():
                    data = self._channel.recv(4096).decode("utf-8", errors="ignore")
                    if not data:
                        break
                    buffer += data
                    # Zeilenweise an GUI schicken
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        self.received.emit(line + "\n")
                elif self._channel.exit_status_ready():
                    # Programm auf dem Pi ist fertig
                    break
                else:
                    self.msleep(50)

        except Exception as e:
            self.disconnected.emit(f"Fehler: {e}")
        finally:
            if buffer:
                self.received.emit(buffer)
            self._cleanup()

    def send(self, text: str):
        """Textzeile an das Programm auf dem Pi senden."""
        with self._lock:
            if self._channel is not None and not self._channel.closed:
                self._channel.send(text + "\n")

    def stop(self):
        """Verbindung stoppen (z.B. beim Schließen der GUI)."""
        self._stop_flag = True
        with self._lock:
            if self._channel is not None:
                try:
                    self._channel.close()
                except Exception:
                    pass
        self._cleanup()

    def _cleanup(self):
        """SSH-Client sauber schließen."""
        with self._lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None
                self._channel = None
        self.disconnected.emit("Verbindung geschlossen.")


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("LC-Kreis Steuerung (SSH)")

        # Widgets
        self.output = QtWidgets.QPlainTextEdit()
        self.output.setReadOnly(True)

        self.input = QtWidgets.QLineEdit()
        self.input.setPlaceholderText("Befehl eingeben (z.B. 1, +, m, 47.5, z, q...)")

        self.send_button = QtWidgets.QPushButton("Senden")
        self.connect_label = QtWidgets.QLabel("Verbinde mit Raspberry Pi...")

        # Layout
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.input)
        btn_layout.addWidget(self.send_button)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.connect_label)
        layout.addWidget(self.output)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

        # SSH-Worker starten
        self.worker = SSHWorker(PI_HOST, PI_USER, PI_PASSWORD, REMOTE_CMD)
        self.worker.received.connect(self.on_received)
        self.worker.connected.connect(self.on_connected)
        self.worker.disconnected.connect(self.on_disconnected)
        self.worker.start()

        # Signale
        self.send_button.clicked.connect(self.send_input)
        self.input.returnPressed.connect(self.send_input)

    def on_connected(self):
        self.connect_label.setText(f"Verbunden mit {PI_HOST}. Programm läuft.")
        self.append_output(f"[Verbunden mit {PI_HOST}, starte {REMOTE_CMD}]\n")

    def on_disconnected(self, reason):
        self.append_output(f"\n[Verbindung beendet: {reason}]\n")
        self.connect_label.setText("Verbindung beendet.")

    def on_received(self, text):
        self.append_output(text)

    def append_output(self, text):
        # Einfach Text anhängen und automatisch nach unten scrollen
        self.output.appendPlainText(text.rstrip("\n"))
        self.output.verticalScrollBar().setValue(
            self.output.verticalScrollBar().maximum()
        )

    def send_input(self):
        cmd = self.input.text().strip()
        if cmd:
            self.append_output(f"> {cmd}\n")
            self.worker.send(cmd)
            self.input.clear()

    def closeEvent(self, event):
        try:
            self.worker.stop()
        except Exception:
            pass
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.resize(800, 600)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
