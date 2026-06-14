This folder contains a safe network inventory script for networks you own or are authorized to test.

`discover_candidate_camera_ips.py`:
- Uses a top-level `subnet` variable.
- Scans for hosts that expose common camera-related ports.
- Prints a JSON list of matching IP addresses.
- Does not attempt login, auth checks, or access protected streams.

Run it with:

```powershell
python .\network_camera_inventory\discover_candidate_camera_ips.py
```
