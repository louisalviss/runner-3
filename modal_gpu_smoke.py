import subprocess

import modal

app = modal.App("runner3-modal-gpu-smoke")
image = modal.Image.debian_slim(python_version="3.11").pip_install("fastapi[standard]")


@app.function(
    gpu="T4",
    image=image,
    timeout=120,
    scaledown_window=60,
)
@modal.fastapi_endpoint(method="GET")
def gpu_check() -> dict:
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
    return {"ok": True, "gpu": info}
