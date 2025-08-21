compare_ugrep_rg.ps1

This folder contains a PowerShell demo that compares common usage of `ugrep` and `rg` (ripgrep) on Windows PowerShell (pwsh).

Files:

- compare_ugrep_rg.ps1  — creates demo files in `scripts/demo_data` and runs a set of ugrep/rg commands showing outputs.

How to run:

Open PowerShell (pwsh) and run:

```powershell
cd <repo-root>
.\scripts\compare_ugrep_rg.ps1
```

Notes & tips:
- The script checks whether `ugrep` and `rg` are installed. If a tool is missing it will skip that section and print a message.
- To get absolute paths from ugrep output, use PowerShell's `Resolve-Path` as the demo shows.
- For safe handling of filenames with spaces, use the NUL-separated output option (`-0`) and process accordingly.

If you want more cases (file-type magic, zip-inspection, JSON lines, format strings), tell me which scenarios to add.
