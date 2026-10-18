# LC-Circuit-flashing — RFQ resonance control

Remote control of the **LC matching circuit of the RFQ ion cooler** in the laser-assisted AMS beamline at
CologneAMS. The RFQ only works at resonance; these scripts let the control PC read and set the circuit's
capacitance and inductances, so the resonance can be tuned without touching the hardware.

```text
control PC (PyQt5 GUI)  ──SSH──▶  Raspberry Pi  ──serial──▶  Arduino  ──▶  C, L1, L2 of the LC circuit
```

[![License](https://img.shields.io/badge/license-GPL--3.0-394B59?style=flat-square)](LICENSE)

## Files

| File | Runs on | Role |
| --- | --- | --- |
| `raspberry_side.py` | Raspberry Pi | Command-line bridge to the Arduino on `/dev/ttyAMA0`: `get` or `set` C (pF, 0–32768, steps of 0.5), L, L1 or L2 (µH, 0–512, steps of 0.25). Deployed on the Pi as `rc_cmd_derin.py`. |
| `ALIS_side_threading.py` | control PC | PyQt5 GUI: one panel per channel, polls the current values once per second and sends new ones over SSH. All SSH traffic runs in a worker thread. **Recommended.** |
| `ALIS_side.py` | control PC | The same GUI without a worker thread (earlier version). |
| `test1.py` | control PC | Early test: streams the output of a script running on the Pi into a window. |

## Usage

On the Raspberry Pi (with `pyserial`):

```bash
python3 rc_cmd_derin.py get C
python3 rc_cmd_derin.py set L1 120.25
```

On the control PC (with `PyQt5` and `paramiko`), set `PI_HOST`, `PI_USER`, `PI_PASSWORD` and
`REMOTE_RC_CMD` at the top of the script, then:

```bash
python ALIS_side_threading.py
```

The same Pi interface is used by [FLAVIA](https://github.com/Paranoidgrinch/FLAVIA-alpha-1.1-Fully-integrated-Laser-Anion-Variables-for-AMS-)'s
RFQ window (*Read / Send LC values to Pi*).

## License

GPL-3.0 — see [LICENSE](LICENSE).
