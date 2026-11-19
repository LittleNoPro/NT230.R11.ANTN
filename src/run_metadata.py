"""Record a minimal, non-secret runtime and source fingerprint before evaluation."""
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import DATA, ROOT


def command(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def main():
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("This GPU evaluation requires CUDA; refusing a silent CPU fallback")
    x = torch.ones((32, 32), device="cuda")
    assert (x @ x).sum().item() == 32768.0
    torch.cuda.synchronize()
    files = [ROOT / name for name in ("Dockerfile", "requirements.txt", "sources.lock.tsv")]
    for directory in ("src", "scripts", "tests"):
        files += [p for p in (ROOT / directory).rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    metadata = dict(started_at_utc=datetime.now(timezone.utc).isoformat(),
                    python=sys.version, platform=platform.platform(),
                    torch=torch.__version__, cuda_runtime=torch.version.cuda,
                    gpu=torch.cuda.get_device_name(0),
                    gpu_memory_bytes=torch.cuda.get_device_properties(0).total_memory,
                    nvidia=command(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv"]),
                    php=command(["php", "-v"]).splitlines()[0],
                    php_extensions=command(["php", "-m"]).splitlines(),
                    pip_freeze=command([sys.executable, "-m", "pip", "freeze"]).splitlines(),
                    image_id=os.environ.get("GLARESHELL_IMAGE_ID", "not supplied"),
                    source_sha256=hashes,
                    reproducibility="Fixed data splits/seeds; parallel Gensim and CUDA scatter operations may vary numerically")
    path = DATA.parent / "environment.json"
    if path.exists():
        previous = json.loads(path.read_text())
        for field in ("source_sha256", "pip_freeze", "php", "php_extensions", "torch", "cuda_runtime", "gpu"):
            if previous[field] != metadata[field]:
                raise RuntimeError(f"Evaluation environment changed ({field}); choose a new run root")
        print("Environment/source fingerprint matches the existing run")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Recorded environment/source fingerprint: {path}; GPU={metadata['gpu']}")


if __name__ == "__main__":
    main()
