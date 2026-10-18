# LC-Circuit-flashing

Remote control of the LC matching circuit of the RFQ ion cooler at the laser-assisted AMS beamline at
CologneAMS. The RFQ has to be driven at resonance; these scripts read and set the capacitance and
inductances of the circuit from the control PC.

```text
control PC (PyQt5) --SSH--> Raspberry Pi --serial--> Arduino --> C, L1, L2
```

## Files

| File | Runs on | Content |
| --- | --- | --- |
| `raspberry_side.py` | Raspberry Pi | command-line bridge to the Arduino on `/dev/ttyAMA0`; `get` or `set` C (pF, 0 to 32768, steps of 0.5) and L, L1, L2 (µH, 0 to 512, steps of 0.25). Installed on the Pi as `rc_cmd_derin.py`. |
| `ALIS_side_threading.py` | control PC | GUI with one panel per channel; reads the values once per second and sends new ones over SSH from a worker thread. Current version. |
| `ALIS_side.py` | control PC | earlier version of the same GUI without a worker thread |
| `test1.py` | control PC | early test that shows the output of a script running on the Pi |

## Usage

On the Raspberry Pi (requires `pyserial`):

```bash
python3 rc_cmd_derin.py get C
python3 rc_cmd_derin.py set L1 120.25
```

On the control PC (requires `PyQt5` and `paramiko`), set `PI_HOST`, `PI_USER`, `PI_PASSWORD` and
`REMOTE_RC_CMD` at the top of the script and run:

```bash
python ALIS_side_threading.py
```

[FLAVIA](https://github.com/Paranoidgrinch/FLAVIA-alpha-1.1-Fully-integrated-Laser-Anion-Variables-for-AMS-)
uses the same Pi interface in its RFQ window.

## License

GPL-3.0, see [LICENSE](LICENSE).
