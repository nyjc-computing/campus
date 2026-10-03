"""Per-task git worktree manager for concurrent work streams.

One stream = one worktree = one branch = one PR. The main checkout stays
on `weekly` and only takes `git pull` — switching branches in a shared
checkout makes every other active stream's next commit land on the wrong
branch.

Usage:
    python scripts/worktree.py new <type>/<slug> [--base REF] [--no-venv]
    python scripts/worktree.py remove <type>/<slug> [--force-dirty]
    python scripts/worktree.py list

`new` creates a sibling worktree `../campus-<slug>` on `<branch>` (new
branch off --base, default origin/weekly; an existing branch is checked
out as-is), registers a safe.directory entry, and — unless --no-venv —
builds the worktree .venv from the main checkout's venv (D: is exFAT:
junctions/symlinks and PATH tricks do not work here, the venv must be
real). See docs/CONTRIBUTING.md "Concurrent work streams".

`remove` implements the single-use policy: drop the worktree directory
(its venv goes with it), prune, and clear its safe.directory entry. The
branch itself is kept — branch cleanup is the post-merge SOP.
"""

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
VENV_REL = Path(".venv")


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a git/python command, echoing it for the operator."""
    print(f"  $ {' '.join(args)}")
    result = subprocess.run(args, capture_output=True, text=True)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        sys.exit(f"error: command failed ({result.returncode}):\n  {detail}")
    return result


def main_root() -> Path:
    """Path of the main (first) working tree of this repository."""
    result = run(["git", "worktree", "list", "--porcelain"])
    first = result.stdout.splitlines()[0]
    return Path(first.removeprefix("worktree ").strip())


def worktrees() -> dict[str, dict]:
    """All worktrees: path -> {branch, head}."""
    result = run(["git", "worktree", "list", "--porcelain"])
    trees: dict[str, dict] = {}
    entry: dict = {}
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            entry = {"path": Path(line.removeprefix("worktree ").strip())}
        elif line.startswith("branch "):
            ref = line.removeprefix("branch ").strip()
            entry["branch"] = ref.removeprefix("refs/heads/")
        elif line == "bare" or line.startswith("detached"):
            entry["branch"] = entry.get("branch", "(detached)")
        elif not line and entry:
            trees[str(entry["path"])] = entry
            entry = {}
    if entry:
        trees[str(entry["path"])] = entry
    return trees


def branch_worktree(branch: str) -> Path | None:
    for path, entry in worktrees().items():
        if entry.get("branch") == branch:
            return Path(path)
    return None


def venv_python(root: Path) -> Path:
    name = "python.exe" if IS_WINDOWS else "python"
    return root / VENV_REL / ("Scripts" if IS_WINDOWS else "bin") / name


def site_packages(venv_py: Path) -> Path:
    if IS_WINDOWS:
        return venv_py.parent.parent / "Lib" / "site-packages"
    lib = venv_py.parent.parent / "lib"
    matches = sorted(lib.glob("python3*/site-packages"))
    if not matches:
        sys.exit(f"error: site-packages not found under {lib}")
    return matches[0]


def bootstrap_venv(wt_root: Path, main_root_path: Path) -> None:
    """Build the worktree .venv from the main checkout's venv.

    Copy-based shortcuts do not work on this machine (D: is exFAT — no
    junctions/symlinks; PATH prepends lose to CreateProcess search
    order), so: create a real venv using the main venv's interpreter,
    install the main venv's freeze, and hand-copy the locally-built
    campus packages that no index serves.
    """
    main_py = venv_python(main_root_path)
    if not main_py.exists():
        sys.exit(f"error: main checkout venv not found at {main_py} — "
                 "bootstrap it first or pass --no-venv")
    started = time.perf_counter()
    print("bootstrapping worktree venv (about 2 minutes)...")

    wt_py = venv_python(wt_root)
    run([str(main_py), "-m", "venv", str(wt_root / VENV_REL)])

    freeze = run([str(main_py), "-m", "pip", "freeze", "--exclude-editable"]).stdout
    keep = [line for line in freeze.splitlines()
            if line and not re.match(r"^(pip|setuptools|wheel|campus)", line,
                                     re.IGNORECASE)]
    freeze_file = wt_root / "requirements-freeze.txt"
    freeze_file.write_text("\n".join(keep) + "\n", encoding="utf-8")
    run([str(wt_py), "-m", "pip", "install", "-r", str(freeze_file)],
        check=True)

    # campus_suite / campus_api_python are built locally, not on any
    # index: copy their site-packages content across.
    src = site_packages(main_py)
    dst = site_packages(wt_py)
    copied = []
    for pattern in ("campus_python*", "campus_api_python*"):
        for item in src.glob(pattern):
            target = dst / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
            copied.append(item.name)
    if copied:
        print(f"  copied locally-built packages: {', '.join(copied)}")
    print(f"  freeze kept at {freeze_file.name} (leave it untracked)")
    print(f"venv ready in {time.perf_counter() - started:.0f}s")


def cmd_new(args) -> int:
    branch = args.branch
    if "/" not in branch:
        sys.exit(f"error: branch must look like <type>/<slug>, got {branch!r}")
    slug = branch.rsplit("/", 1)[-1]
    existing = branch_worktree(branch)
    if existing:
        sys.exit(f"error: branch {branch!r} already checked out at {existing}")

    main_path = main_root()
    wt_dir = Path(args.dir) if args.dir else main_path.parent / f"campus-{slug}"
    if wt_dir.exists():
        sys.exit(f"error: {wt_dir} already exists")

    branch_exists = run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        check=False,
    ).returncode == 0
    if branch_exists:
        print(f"branch {branch} exists — checking it out in the new worktree")
        run(["git", "worktree", "add", str(wt_dir), branch])
    else:
        base = args.base
        if base == "origin/weekly" or base == "weekly":
            run(["git", "fetch", "origin", "weekly"])
            base = "origin/weekly"
        run(["git", "worktree", "add", "-b", branch, str(wt_dir), base])

    run(["git", "config", "--global", "--add", "safe.directory",
         wt_dir.as_posix()])
    if not args.no_venv:
        bootstrap_venv(wt_dir, main_path)

    py = ".venv/Scripts/python.exe" if IS_WINDOWS else ".venv/bin/python"
    print(f"\nworktree ready: {wt_dir} (branch {branch})")
    print(f"next:  cd {wt_dir}")
    if not args.no_venv:
        print(f"       {py} tests/run_tests.py unit")
    return 0


def cmd_remove(args) -> int:
    branch = args.branch
    wt_dir = branch_worktree(branch)
    if not wt_dir:
        sys.exit(f"error: no worktree has branch {branch!r} "
                 f"(see: python scripts/worktree.py list)")
    if wt_dir == main_root():
        sys.exit("error: refusing to remove the main checkout")

    status = run(["git", "-C", str(wt_dir), "status", "--porcelain"]).stdout
    dirty = [line for line in status.splitlines()
             if not re.match(r"^\?\? (\.venv/|requirements-freeze\.txt)", line)]
    if dirty and not args.force_dirty:
        print("worktree has uncommitted changes (refusing to discard):")
        for line in dirty:
            print(f"  {line}")
        sys.exit("error: commit/PR them first, or pass --force-dirty")

    run(["git", "worktree", "remove", "--force", str(wt_dir)])
    run(["git", "worktree", "prune"])
    run(["git", "config", "--global", "--unset", "safe.directory",
         f"^{re.escape(wt_dir.as_posix())}$"], check=False)
    print(f"worktree removed: {wt_dir} (branch {branch} kept)")
    return 0


def cmd_list(args) -> int:
    main_path = main_root()
    for path, entry in worktrees().items():
        marker = "*" if Path(path) == main_path else " "
        venv = "venv" if venv_python(Path(path)).exists() else "----"
        print(f"{marker} {entry.get('branch', '?'):<40} [{venv}] {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scripts/worktree.py",
        description="Per-task worktree manager (one stream = one worktree).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="create a worktree for a new task")
    p_new.add_argument("branch", metavar="<type>/<slug>")
    p_new.add_argument("--base", default="origin/weekly",
                       help="base ref for the new branch (default: origin/weekly)")
    p_new.add_argument("--no-venv", action="store_true",
                       help="skip .venv bootstrap (docs-only work)")
    p_new.add_argument("--dir", default=None,
                       help="worktree path (default: sibling campus-<slug>)")

    p_rm = sub.add_parser("remove", help="remove a finished task's worktree")
    p_rm.add_argument("branch", metavar="<type>/<slug>")
    p_rm.add_argument("--force-dirty", action="store_true",
                      help="discard uncommitted changes (venv artifacts are "
                           "always ignored)")

    sub.add_parser("list", help="list worktrees and their venv state")

    args = parser.parse_args(argv)
    return {"new": cmd_new, "remove": cmd_remove, "list": cmd_list}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
