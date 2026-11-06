#!/usr/bin/env python3
"""在构建前检查卷布局与目标系统配置是否一致。"""
import json
from pathlib import Path
import sys
import tomllib
import uuid


def check(layout_path, profile_path):
    layout = json.loads(layout_path.read_text())
    profile = tomllib.loads(profile_path.read_text())
    root = profile["root"]
    actual = {role: uuid.UUID(layout[role]["uuid"]) for role in ("os", "systemos", "data")}
    for role, key in (("os", "os_volume_uuid"), ("systemos", "systemos_volume_uuid")):
        if actual[role] != uuid.UUID(root[key]):
            raise ValueError(f"{role} 卷 UUID 与系统配置不一致")
    if layout.get("ci_placeholder"):
        raise ValueError("占位布局不允许作为配套 userdata 镜像")


if __name__ == "__main__":
    try:
        check(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, KeyError, ValueError, TypeError, IndexError) as error:
        raise SystemExit(f"卷布局检查失败：{error}") from error
    print("卷布局与系统配置一致；仍需使用同次生成的 userdata 镜像。")
