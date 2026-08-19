import subprocess

import modal

app = modal.App("runner3-modal-gpu-smoke")


@app.function(gpu="T4", timeout=120)
def gpu_smoke() -> str:
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    info = result.stdout.strip()
    print(f"MODAL_GPU={info}")
    return info


@app.local_entrypoint()
def main():
    info = gpu_smoke.remote()
    print(f"GPU_SMOKE_OK={info}")
