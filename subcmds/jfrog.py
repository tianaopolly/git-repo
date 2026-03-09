#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# @file:        jfrog_sync.py
# @author:      Polly.Ma
# @date:        2026年01月09日
# @version:     1.0.0
# @brief:       摘要：
# @details:     明细：
# @note:        示例: python jfrog_sync.py

import base64
import getpass
import subprocess
import requests
import time
import os
from pathlib import Path
from typing import Optional, Tuple
import shutil


MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds

# 为 repo 子命令扫描器提供占位命令类，避免 init 时报错
from command import Command
from command import MirrorSafeCommand


class Jfrog(Command, MirrorSafeCommand):
    COMMON = False
    helpSummary = "internal jfrog helper"
    helpUsage = """
%prog
"""
    helpDescription = """
internal helper for jfrog artifact sync; not intended for direct use
"""

    def _Options(self, p):
        # 无命令行参数；该命令仅为加载占位
        pass

    def Execute(self, opt, args):
        # 占位实现：什么也不做
        return 0


# @brief 去除 URL 末尾的斜杠。
def _normalize_url(url: str) -> str:
    return url.rstrip("/")


# @brief 从本地凭证文件或交互输入加载用户名与密码（Base64 存储）。
# @return (username, password)
def _load_credentials() -> Tuple[str, str]:
    cred_file = Path.home() / ".ssh" / "jfrog_cred"
    username: Optional[str] = None
    password_b64: Optional[str] = None

    if cred_file.is_file():
        lines = [ln.strip() for ln in cred_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if len(lines) >= 2:
            if "=" in lines[0]:
                kv = dict(item.split("=", 1) for item in lines if "=" in item)
                username = kv.get("username") or kv.get("user")
                password_b64 = kv.get("password") or kv.get("passwd") or kv.get("pwd")
                # 兼容旧字段名 api_key / apikey，内容视为密码存储
                password_b64 = password_b64 or kv.get("api_key") or kv.get("apikey")
            else:
                username, password_b64 = lines[0], lines[1]

    if not username or not password_b64:
        username = input("请输入您登录jfrog的用户名: ").strip()
        raw_password = getpass.getpass("请输入您的密码: ")
        password_b64 = base64.b64encode(raw_password.encode("utf-8")).decode("utf-8")
        # 首次输入后写入 ~/.ssh/jfrog_cred，便于后续复用
        try:
            cred_file.parent.mkdir(parents=True, exist_ok=True)
            cred_file.write_text(f"username={username}\npassword={password_b64}\n", encoding="utf-8")
        except Exception as e:
            # 写文件失败不阻塞流程，仅提示
            print(f"警告: 无法保存 jfrog 凭证到 {cred_file}: {e}")

    password = base64.b64decode(password_b64).decode("utf-8")
    return username, password


# @brief 撤销给定 token，忽略撤销失败。
def _revoke_token(base_url: str, token: str):
    revoke_api = f"{base_url}/access/api/v1/tokens/revoke"
    try:
        requests.post(
            revoke_api,
            data={"token": token},
            timeout=10,
            verify=False if base_url.startswith("https://") else False,
        )
    except Exception:
        pass


# @brief 调用 jf rt dl 下载指定制品，使用 token 认证。
def _run_download(base_url: str, remote: str, local_path: str, token: str):
    # 固定将制品下载到缓存目录 ~/.jfrog/.catch/
    # 下载完成后，将缓存文件创建软链接到目标路径
    cache_root = Path.home() / ".jfrog" / ".catch"

    # remote 可能包含斜杠，用作缓存子目录
    cache_remote_dir = cache_root / Path(remote)

    if not cache_remote_dir.exists():
        print(f"本地缓存目录不存在，开始下载制品 {remote} 到缓存目录...")
        cache_remote_dir.mkdir(parents=True, exist_ok=True)
        # 固定下载到缓存目录
        cmd = [
            "jf",
            "rt",
            "dl",
            f"{remote}/(*)",
            f"{str(cache_remote_dir)}/{{1}}",
            "--threads=20",
            "--flat=true",
        ]
        subprocess.run(cmd, check=True)

    # 将 local_path 目录按规则创建/更新软链接
    # 如果local_path存在且非空，并且不是软链接
    # 则在local_dir下为cache_remote_dir下的每一个一级子目录和文件创建软链接
    def _link_children(src_dir: Path, dst_dir: Path) -> None:
        for child in src_dir.iterdir():
            dst = dst_dir / child.name
            if dst.exists() or dst.is_symlink():
                if dst.is_symlink():
                    try:
                        if dst.resolve() == child.resolve():
                            continue
                    except Exception:
                        pass
                raise RuntimeError(f"目标已存在，无法创建软链接: {dst} -> {child}")
            try:
                print(f"创建软链接: {dst} -> {child}")
                os.symlink(child, dst)
            except OSError as link_err:
                raise RuntimeError(f"创建软链接失败: {dst} -> {child}: {link_err}") from link_err

    local_dir = Path(local_path)
    local_parent = local_dir.parent
    local_parent.mkdir(parents=True, exist_ok=True)

    # 如果local_path目录不存在则创建一个local_path的软链接，指向cache_remote_dir
    if not local_dir.exists():
        try:
            print(f"创建软链接: {local_dir} -> {cache_remote_dir}")
            os.symlink(cache_remote_dir, local_dir)
        except OSError as link_err:
            raise RuntimeError(f"创建软链接失败: {local_dir} -> {cache_remote_dir}: {link_err}") from link_err
        return

    # 如果local_path存在、并且是个软链接，则先将软链接删除
    # 并且在创建一个local_path的实体路径，并在local_dir下为原本软链接指向的路径下的每一个一级子目录和文件创建软链接
    # 然后再为当前cache_remote_dir下的每一个一级子目录和文件创建软链接
    if local_dir.is_symlink():
        try:
            old_target = local_dir.resolve()
        except Exception as resolve_err:
            raise RuntimeError(f"解析软链接失败: {local_dir}: {resolve_err}") from resolve_err
        local_dir.unlink()
        local_dir.mkdir(parents=True, exist_ok=True)
        _link_children(old_target, local_dir)
        _link_children(cache_remote_dir, local_dir)
        return

    # local_path 存在且不是软链接
    _link_children(cache_remote_dir, local_dir)


# @brief 模拟 Web 登录以激活客户端在线状态，失败仅警告不阻塞。
# @param login_url 登录接口 URL。
# @param username 登录用户名。
# @param password 登录密码。
def _web_login(username: str, password: str) -> None:
    login_url = "http://10.11.10.244:8082/ui/api/v1/access/auth/login?_spring_security_remember_me=true"
    get_url = "http://10.11.10.244:8082/ui/api/v1/ui/auth/current"

    try:
        sess = requests.Session()
        payload = {"username": username, "password": password}
        headers = {"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}

        resp = sess.post(login_url, json=payload, headers=headers, timeout=10, verify=False)
        if resp.status_code not in (200, 201, 204):
            # 若服务端期望字段为 user，再尝试一次
            payload2 = {"user": username, "password": password}
            resp2 = sess.post(login_url, json=payload2, headers=headers, timeout=10, verify=False)
            if resp2.status_code not in (200, 201, 204):
                print(f"警告: Web 登录({login_url})返回HTTP {resp.status_code}: {resp.text}")

        # 追加一次 GET 请求以模拟完整登录流程
        try:
            resp_get = sess.get(get_url, timeout=10, verify=False)
            if resp_get.status_code not in (200, 201, 204):
                print(f"警告: Web 登录 GET({get_url})返回HTTP {resp_get.status_code}: {resp_get.text}")
        except Exception as ge:
            print(f"警告: 模拟 Web 登录 GET 请求失败: {ge}")

    except Exception as e:
        print(f"警告: 模拟 Web 登录失败: {e}")


# @brief 同步单个制品：获取 token、模拟登录、重试下载。
# @param name 制品名称。
# @param version 制品版本。
# @param local_path 本地保存路径。
# @param artifactory_url JFrog 服务器地址。
def sync_one(name: str, version: str, local_path: str, artifactory_url: str):
    base_url = _normalize_url(artifactory_url)
    username, password = _load_credentials()
    token = None
    try:
        # 在进行 jf rt dl 前，先模拟一次 Web 登录以激活客户端在线状态
        _web_login(username, password)
        remote = f"{name}/{version}"
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                _run_download(base_url, remote, local_path, token)
                return
            except subprocess.CalledProcessError as err:
                last_err = err
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                else:
                    raise RuntimeError(f"jf rt dl failed after {MAX_RETRIES} retries: {err}") from err
    finally:
        if token:
            _revoke_token(base_url, token)
