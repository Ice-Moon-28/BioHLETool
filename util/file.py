from __future__ import annotations
import argparse
import json
import logging
import os
import random
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, Iterable, Callable


def ensure_dir(dir_name):
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

def dump_json(obj: Dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def safe_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in name)
