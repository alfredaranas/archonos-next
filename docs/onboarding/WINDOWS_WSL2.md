# Setting up Windows 11 + WSL2 for ArchonOS

> WSL2 is the target environment for ArchonOS Local Alpha. This doc
> walks through a clean Windows 11 install getting to a working
> `python3` in WSL Ubuntu.
>
> **Time required:** ~10 minutes.
>
> **Prerequisite:** Windows 11 (any edition — Home is fine).

---

## 1. Install WSL2

Open **PowerShell as Administrator** (right-click Start → "Windows
Terminal (Admin)" or "PowerShell (Admin)") and run:

```powershell
wsl --install
```

This single command:
- Enables the WSL feature
- Downloads the WSL2 Linux kernel
- Downloads and installs **Ubuntu** (the default distro)
- Prompts you to reboot

**Reboot** when prompted.

After reboot, an "Ubuntu" window opens automatically and asks you to
create a UNIX username and password. Pick anything — this is the
account you'll use inside WSL.

---

## 2. Update Ubuntu

In the Ubuntu window:

```bash
sudo apt update && sudo apt upgrade -y
```

This may take a few minutes. Answer "Y" if prompted about services
that need restarting.

---

## 3. Verify Python 3.11+

Ubuntu 24.04 ships with Python 3.12 by default. Ubuntu 22.04 ships
with Python 3.10, which is **too old** for ArchonOS (we need 3.11+).
Check what you have:

```bash
python3 --version
```

- If it shows `Python 3.11.x` or higher — proceed to step 4.
- If it shows `Python 3.10.x` or lower — install a newer one:

  ```bash
  sudo apt install -y python3.11 python3.11-venv python3.11-dev
  python3.11 --version
  ```

  Then either use `python3.11` everywhere or set up an alias:
  ```bash
  echo "alias python3=python3.11" >> ~/.bashrc
  source ~/.bashrc
  python3 --version   # should now show 3.11+
  ```

---

## 4. Install git and build tools

```bash
sudo apt install -y git build-essential
git --version
gcc --version
```

`build-essential` is rarely needed by ArchonOS itself (pure Python)
but some pip packages may compile C extensions; having it pre-installed
saves you from a confusing "metadata-generation-failed" error later.

---

## 5. Clone ArchonOS

```bash
cd ~
git clone https://github.com/alfredaranas/archonos-next.git
cd archonos-next
```

---

## 6. Create the venv and install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

This installs the `archonos` console script in editable mode.

**Verify:**

```bash
archonos --version
# Expected: archonos 0.1.0
```

If `archonos` is not found, you forgot to activate the venv (`source
.venv/bin/activate`). Always activate before running `archonos`.

---

## 7. Run the test suite

```bash
pytest tests/ -v
```

**Expected: 75 passed in ~1 second.**

If any test fails, the install is broken. Re-create the venv:

```bash
deactivate                  # exit the broken venv
cd ~/archonos-next
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

---

## 8. Run the First Run walkthrough

You're ready. Open `docs/onboarding/FIRST_RUN.md` (or just read it
on GitHub) and complete the 6-step walkthrough. The whole thing takes
~2 minutes once the venv is set up.

---

## WSL tips for ArchonOS users

**Your WSL files are NOT the same as your Windows files.**

- WSL Ubuntu lives in its own filesystem, accessible from Windows at
  `\\wsl$\Ubuntu\home\<you>\` (or just `\\wsl$\` in Explorer).
- Your `archonos` database lives in WSL: `~/.archonos/default/archonos.db`
- To open that file in a Windows tool (e.g. DB Browser for SQLite),
  paste `\\wsl$\Ubuntu\home\<you>\.archonos\default\archonos.db` into
  Explorer's address bar.

**Where to put your corpus.**

You can import files from anywhere in WSL:
```bash
archonos import /mnt/c/Users/<you>/Documents/notes/   # Windows path
archonos import ~/projects/notes/                      # WSL path
```

WSL is fast at reading files in either location. `archonos import`
walks the directory recursively.

**Path translation note:** when you import a file from `/mnt/c/...`,
its `source_path` column in the database stores the WSL-style path
(`/mnt/c/...`), not the Windows path. This is by design — the
database is a Linux artifact.

**Performance: keep the database in WSL ext4, not in `/mnt/c`.**

`/mnt/c` is the Windows C: drive mounted via 9P — file I/O is
significantly slower than the native WSL ext4 filesystem. For best
performance:

```bash
# Default (good): ~/.archonos lives on WSL ext4
archonos init

# Slower: explicitly on /mnt/c
ARCHONOS_HOME=/mnt/c/Users/you/archonos-data archonos init
# Avoid this for any non-trivial corpus.
```

---

## Uninstalling / resetting

To wipe ArchonOS state and start over:

```bash
rm -rf ~/.archonos
archonos init
```

To uninstall the Python package:

```bash
source ~/archonos-next/.venv/bin/activate
pip uninstall archonos
deactivate
```

To remove WSL2 entirely (reclaim disk space):

```powershell
# In Windows PowerShell
wsl --unregister Ubuntu
wsl --shutdown
```

---

## Common WSL issues

**"0x80370102" error during `wsl --install`** — virtualization is
disabled in BIOS. Reboot → enter BIOS → enable "Intel VT-x" or "AMD-V"
→ save and reboot → retry.

**`pip install` is slow or times out** — Windows Defender or another
antivirus is scanning every file. Add an exclusion for
`C:\Users\<you>\AppData\Local\Packages\CanonicalGroupLimited.*\LocalState\`
(where WSL stores its ext4 filesystem).

**"WSL 2 requires an update to its kernel component"** — run
`wsl --update` in an admin PowerShell.

**"The system cannot find the file specified"** when running
`archonos` from Windows Explorer — you need to run it from inside
WSL, not from Windows. Open the Ubuntu app and run from there.
