from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path


PLUGIN_ID = "wechat"


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def resolve_extension_dir() -> Path:
    extension_dir = Path(files("openclaw_wechat_plugin")).joinpath("openclaw_extension")
    if not extension_dir.exists():
        raise RuntimeError(
            "OpenClaw extension assets are missing from this installation: "
            f"{extension_dir}"
        )
    return extension_dir


def _resolve_openclaw_bin(openclaw_bin: str) -> str:
    if Path(openclaw_bin).exists():
        return str(Path(openclaw_bin))

    candidates = [openclaw_bin]
    if os.name == "nt" and openclaw_bin.lower() == "openclaw":
        candidates = ["openclaw.cmd", "openclaw.exe", "openclaw"]

    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    raise RuntimeError(
        "OpenClaw CLI not found in PATH. Set --openclaw-bin to the OpenClaw executable "
        "(for example: openclaw or C:\\path\\to\\openclaw.cmd)."
    )


def _run(command: list[str]) -> CommandResult:
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    return CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def install_openclaw_extension(
    *,
    openclaw_bin: str = "openclaw",
    enable: bool = True,
    link: bool = False,
    dry_run: bool = False,
) -> dict:
    resolved_bin = openclaw_bin if dry_run else _resolve_openclaw_bin(openclaw_bin)
    extension_dir = resolve_extension_dir()

    install_command = [resolved_bin, "plugins", "install"]
    if link:
        install_command.append("--link")
    install_command.append(str(extension_dir))

    enable_command = [resolved_bin, "plugins", "enable", PLUGIN_ID]

    if dry_run:
        return {
            "mode": "dry-run",
            "plugin_id": PLUGIN_ID,
            "extension_dir": str(extension_dir),
            "commands": [install_command, enable_command] if enable else [install_command],
        }

    install_result = _run(install_command)
    if install_result.returncode != 0:
        raise RuntimeError(
            "OpenClaw plugin install failed.\n"
            f"command: {' '.join(install_result.command)}\n"
            f"stdout: {install_result.stdout.strip()}\n"
            f"stderr: {install_result.stderr.strip()}"
        )

    enable_payload: dict | None = None
    if enable:
        enable_result = _run(enable_command)
        if enable_result.returncode != 0:
            lower = (enable_result.stdout + "\n" + enable_result.stderr).lower()
            if "already enabled" not in lower:
                raise RuntimeError(
                    "OpenClaw plugin enable failed.\n"
                    f"command: {' '.join(enable_result.command)}\n"
                    f"stdout: {enable_result.stdout.strip()}\n"
                    f"stderr: {enable_result.stderr.strip()}"
                )

        enable_payload = {
            "command": enable_result.command,
            "returncode": enable_result.returncode,
            "stdout": enable_result.stdout.strip(),
            "stderr": enable_result.stderr.strip(),
        }

    return {
        "plugin_id": PLUGIN_ID,
        "extension_dir": str(extension_dir),
        "install": {
            "command": install_result.command,
            "returncode": install_result.returncode,
            "stdout": install_result.stdout.strip(),
            "stderr": install_result.stderr.strip(),
        },
        "enable": enable_payload,
    }


def format_install_result(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
