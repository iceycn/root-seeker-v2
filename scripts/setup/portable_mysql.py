from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

from scripts.setup.env_writer import merge_env_file

# Pinned community server archives (update checksums when bumping).
MYSQL_VERSION = "8.0.40"

_DOWNLOADS: dict[tuple[str, str], tuple[str, str | None]] = {
    # (os, arch) -> (url, sha256 or None)
    ("windows", "amd64"): (
        "https://dev.mysql.com/get/Downloads/MySQL-8.0/mysql-8.0.40-winx64.zip",
        None,
    ),
    ("linux", "amd64"): (
        "https://dev.mysql.com/get/Downloads/MySQL-8.0/mysql-8.0.40-linux-glibc2.17-x86_64.tar.xz",
        None,
    ),
    ("linux", "arm64"): (
        "https://dev.mysql.com/get/Downloads/MySQL-8.0/mysql-8.0.40-linux-glibc2.17-aarch64.tar.xz",
        None,
    ),
    ("darwin", "amd64"): (
        "https://dev.mysql.com/get/Downloads/MySQL-8.0/mysql-8.0.40-macos14-x86_64.tar.gz",
        None,
    ),
    ("darwin", "arm64"): (
        "https://dev.mysql.com/get/Downloads/MySQL-8.0/mysql-8.0.40-macos14-arm64.tar.gz",
        None,
    ),
}


def resolve_mysql_download(os_name: str, arch: str) -> tuple[str, str | None]:
    key_os = os_name.lower()
    if key_os.startswith("win"):
        key_os = "windows"
    elif key_os == "macos":
        key_os = "darwin"
    key_arch = arch.lower()
    if key_arch in {"x86_64", "amd64"}:
        key_arch = "amd64"
    elif key_arch in {"aarch64", "arm64"}:
        key_arch = "arm64"
    item = _DOWNLOADS.get((key_os, key_arch))
    if item is None:
        raise ValueError(f"不支持的平台: {os_name}/{arch}")
    return item


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract(archive: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(dest)
    elif archive.name.endswith(".tar.xz"):
        with tarfile.open(archive, "r:xz") as tf:
            tf.extractall(dest)
    else:
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(dest)
    # Find extracted root containing bin/mysqld
    for child in dest.iterdir():
        if child.is_dir() and (child / "bin").exists():
            return child
    raise RuntimeError("解压后未找到 MySQL bin 目录")


def _mysqld_bin(mysql_home: Path) -> Path:
    name = "mysqld.exe" if os.name == "nt" else "mysqld"
    path = mysql_home / "bin" / name
    if not path.exists():
        raise FileNotFoundError(f"找不到 {path}")
    return path


def ensure_portable_mysql(repo_root: Path, *, port: int = 3307) -> tuple[bool, str]:
    import platform

    tools = repo_root / ".tools"
    tools.mkdir(parents=True, exist_ok=True)
    archive_dir = tools / "downloads"
    archive_dir.mkdir(parents=True, exist_ok=True)
    mysql_root = tools / "mysql" / MYSQL_VERSION
    data_dir = tools / "mysql-data"
    pid_file = tools / "mysql.pid"

    try:
        url, checksum = resolve_mysql_download(platform.system(), platform.machine())
    except ValueError as exc:
        return False, str(exc)

    archive_name = url.rstrip("/").split("/")[-1]
    archive_path = archive_dir / archive_name
    if not archive_path.exists():
        try:
            print(f"[信息] 下载便携 MySQL: {url}")
            urlretrieve(url, archive_path)  # noqa: S310
        except Exception as exc:  # noqa: BLE001
            return False, f"下载失败: {exc}（可设置 HTTP_PROXY 后重试）"

    if checksum:
        digest = _sha256_file(archive_path)
        if digest.lower() != checksum.lower():
            return False, f"校验失败: expected {checksum}, got {digest}"

    if not (mysql_root / "bin").exists():
        print("[信息] 解压 MySQL...")
        extracted = _extract(archive_path, mysql_root.parent)
        if extracted.resolve() != mysql_root.resolve():
            if mysql_root.exists():
                shutil.rmtree(mysql_root)
            extracted.rename(mysql_root)

    mysqld = _mysqld_bin(mysql_root)
    if not (data_dir / "mysql").exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        init = subprocess.run(
            [
                str(mysqld),
                f"--basedir={mysql_root}",
                f"--datadir={data_dir}",
                "--initialize-insecure",
            ],
            cwd=str(mysql_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if init.returncode != 0:
            return False, f"初始化失败: {init.stderr or init.stdout}"

    # Start if not already running
    if not pid_file.exists() or not _pid_alive(pid_file.read_text(encoding="utf-8").strip()):
        log_file = tools / "mysql.log"
        stdout = open(log_file, "a", encoding="utf-8")  # noqa: SIM115
        kwargs: dict = {"cwd": str(mysql_root), "stdout": stdout, "stderr": subprocess.STDOUT}
        cmd = [
            str(mysqld),
            f"--basedir={mysql_root}",
            f"--datadir={data_dir}",
            f"--port={port}",
            "--bind-address=127.0.0.1",
        ]
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **kwargs)
        pid_file.write_text(str(proc.pid), encoding="utf-8")

    merge_env_file(
        repo_root / ".env",
        {
            "ROOTSEEKER_STORAGE_BACKEND": "mysql",
            "ROOTSEEKER_MYSQL_HOST": "127.0.0.1",
            "ROOTSEEKER_MYSQL_PORT": str(port),
            "ROOTSEEKER_MYSQL_USER": "root",
            "ROOTSEEKER_MYSQL_PASSWORD": "",
            "ROOTSEEKER_MYSQL_DATABASE": "rootseeker",
        },
        overwrite_existing=True,
    )

    # Create database if needed then init schema
    try:
        import time

        import pymysql

        for _ in range(30):
            try:
                conn = pymysql.connect(
                    host="127.0.0.1",
                    port=port,
                    user="root",
                    password="",
                    connect_timeout=2,
                )
                break
            except Exception:  # noqa: BLE001
                time.sleep(1)
        else:
            return False, "MySQL 已启动但连接超时"
        with conn.cursor() as cur:
            cur.execute(
                "CREATE DATABASE IF NOT EXISTS rootseeker CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.close()
    except Exception as exc:  # noqa: BLE001
        return False, f"创建数据库失败: {exc}"

    init_script = repo_root / "scripts" / "init_mysql.py"
    init = subprocess.run(
        [
            sys.executable,
            str(init_script),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--user",
            "root",
            "--password",
            "",
            "--database",
            "rootseeker",
        ],
        cwd=str(repo_root),
        check=False,
    )
    if init.returncode != 0:
        return False, "建表脚本 init_mysql.py 失败"
    return True, f"便携 MySQL 已就绪 (127.0.0.1:{port})"


def _pid_alive(pid_text: str) -> bool:
    if not pid_text.isdigit():
        return False
    pid = int(pid_text)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_portable_mysql(repo_root: Path) -> None:
    pid_file = repo_root / ".tools" / "mysql.pid"
    if not pid_file.exists():
        return
    pid_text = pid_file.read_text(encoding="utf-8").strip()
    if pid_text.isdigit():
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", pid_text, "/F"], check=False)
            else:
                os.kill(int(pid_text), 15)
        except OSError:
            pass
    try:
        pid_file.unlink()
    except OSError:
        pass
