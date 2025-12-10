#!/usr/bin/env python3
import serial
import time
import sys

# Grenzen und Schrittweiten wie in deinem Originalcode
cmax = 32768       # obere Grenze für Kapazität in pF
lmax = 512         # obere Grenze für Induktivität in µH
stepsizeC = 0.5    # Schrittgröße für Kapazität
stepsizeL = 0.25   # Schrittgröße für Induktivität
wait = 0.1         # Wartezeit zwischen Senden und Lesen

symbol_map = {
    "C": "0",   # Kapazität
    "L": "1",   # Induktivität gemeinsam
    "L1": "2",  # Induktivität 1
    "L2": "3",  # Induktivität 2
}


def send_line(ser, text):
    """String plus Newline an den Arduino senden."""
    ser.write((text + "\n").encode("utf-8"))
    ser.flush()
    time.sleep(wait)


def read_value(ser):
    """Mehrfach versuchen, einen Float vom Arduino zu lesen."""
    for _ in range(10):
        time.sleep(wait)
        data = ser.read(ser.in_waiting or 1).decode("utf-8").strip()
        if not data:
            continue
        try:
            return float(data)
        except ValueError:
            # falls mal Müll im Buffer ist: einfach nochmal versuchen
            continue
    raise RuntimeError("Keine gültige Float-Antwort vom Arduino erhalten.")


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("get", "set"):
        print("Usage: rc_cmd.py get|set C|L|L1|L2 [value]", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    what = sys.argv[2]

    if what not in symbol_map:
        print("Unbekannte Größe:", what, file=sys.stderr)
        sys.exit(1)

    wahls = symbol_map[what]

    if what == "C":
        stepsize = stepsizeC
        maxval = cmax
    else:
        stepsize = stepsizeL
        maxval = lmax

    ser = serial.Serial("/dev/ttyAMA0", 100000, timeout=1)
    ser.flush()

    try:
        # Symbol an Arduino senden, damit er die richtige Größe auswählt
        send_line(ser, wahls)
        current = read_value(ser)  # aktuellen Wert holen

        if cmd == "get":
            # aktuellen Wert auf stdout -> wird vom PC ausgelesen
            print(current)
        else:  # set
            if len(sys.argv) < 4:
                print("Wert fehlt", file=sys.stderr)
                sys.exit(1)

            value = float(sys.argv[3])

            # Grenzen prüfen
            if not (0 <= value < maxval):
                print(f"Wert außerhalb des Bereichs 0..{maxval}", file=sys.stderr)
                sys.exit(1)

            # Schrittweite prüfen
            steps = value / stepsize
            if abs(steps - round(steps)) > 1e-6:
                print(f"Wert muss ein Vielfaches von {stepsize} sein", file=sys.stderr)
                sys.exit(1)

            # neuen Wert senden
            send_line(ser, str(value))
            new = read_value(ser)
            print(new)

        # Tasten wieder freigeben
        send_line(ser, "STOP")

    finally:
        ser.close()


if __name__ == "__main__":
    main()
