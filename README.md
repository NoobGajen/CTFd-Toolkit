<div align="center">
  <img src=".assets/banner.png" alt="CTFd Toolkit Banner" width="100%">

  # CTFd Toolkit

  A fast, terminal-based management tool for CTFd platforms.

  [![Python](https://img.shields.io/badge/Python-3.8+-blue.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
  [![CTFd](https://img.shields.io/badge/Platform-CTFd-red.svg?style=flat-square)](https://ctfd.io/)
  [![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)
</div>

---

## Features

- **Status Dashboard** — Color-coded TUI progress view, grouped by category with solve counts and progress bars
- **Challenge Listing** — Filter by `--list`, `--unsolved`, or category
- **Bulk Download** — Downloads all challenge files into organized `Category/Challenge/` folders, auto-generates per-challenge `README.md`, skips already-downloaded files
- **Flag Submission** — Submits flags with automatic CSRF token handling; detects already-solved challenges
- **Session Caching** — Saves login cookies for 24 hours (`~/.cache/ctfd_toolkit/`), secure `chmod 600`
- **Notifications** — Desktop alerts via `notify-send` and mobile via KDE Connect
- **Env Variable Support** — `CTFD_URL`, `CTFD_USER`, `CTFD_PASS`

---

## Install

```bash
git clone https://github.com/NoobGajen/CTFd-Toolkit.git
cd CTFd-Toolkit
pip install requests
```

---

## Usage

```bash
# Status dashboard (default)
python3 ctfd-toolkit.py -u URL -U user -P pass

# List all / unsolved / by category
python3 ctfd-toolkit.py -u URL -U user -P pass --list
python3 ctfd-toolkit.py -u URL -U user -P pass --unsolved -c Crypto

# Download challenge files
python3 ctfd-toolkit.py -u URL -U user -P pass --download -o ./NoobGajen_CTF

# Submit a flag
python3 ctfd-toolkit.py -u URL -U user -P pass --submit -C "Challenge Name" -f "flag{...}"

# Clear cached session
python3 ctfd-toolkit.py --clear-cache
```

---

## Environment Variables

```bash
export CTFD_URL="https://ctf.example.com"
export CTFD_USER="username"
export CTFD_PASS="password"
```

---

<div align="center">Made by <b>NoobGajen</b></div>
