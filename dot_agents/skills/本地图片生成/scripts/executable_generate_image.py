#!/usr/bin/env python3
"""Local text-to-image via stable-diffusion.cpp (Iris-3B Q4_K, Vulkan)."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_SD_CPP = Path("/home/hashira/create/hongguo/sd-cpp")
DEFAULT_MODELS = Path("/home/hashira/create/hongguo/models")


def die(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", help="positive prompt (about 260 tokens max)")
    parser.add_argument("-o", "--output", default=None, help="output PNG path")
    parser.add_argument("-W", "--width", type=int, default=1024)
    parser.add_argument("-H", "--height", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--cfg", type=float, default=3.0)
    parser.add_argument("-s", "--seed", type=int, default=None)
    parser.add_argument("-n", "--negative", default="")
    parser.add_argument("-b", "--batch", type=int, default=1)
    parser.add_argument("--sd-cpp", default=None, help="override SD_CPP_DIR")
    parser.add_argument("--models-dir", default=None, help="override SD_MODELS_DIR")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    sd_cpp = Path(args.sd_cpp or os.environ.get("SD_CPP_DIR", str(DEFAULT_SD_CPP))).expanduser().resolve()
    models = Path(args.models_dir or os.environ.get("SD_MODELS_DIR", str(DEFAULT_MODELS))).expanduser().resolve()
    cli = sd_cpp / "sd-cli"
    diffusion = models / "diffusion_models" / "iris-3b-turbo-Q4_K.gguf"
    llm = models / "text_encoders" / "Qwen3VL-4B-Instruct-Q4_K_M.gguf"

    for path, label in ((cli, "sd-cli"), (diffusion, "Iris-3B weights"), (llm, "Qwen3-VL weights")):
        if not path.is_file():
            die(f"{label} not found: {path}")

    if args.width <= 0 or args.height <= 0:
        die("width and height must be positive")
    if args.width % 16 or args.height % 16:
        die("width and height must be multiples of 16 (Iris requirement)")
    if args.steps <= 0:
        die("--steps must be positive")
    if args.batch <= 0:
        die("--batch must be positive")

    output = Path(args.output).expanduser() if args.output else Path.cwd() / "generated.png"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    out_arg = str(output)
    if args.batch > 1 and "%d" not in out_arg:
        out_arg = str(output.with_name(f"{output.stem}_%d{output.suffix}"))

    cmd = [
        str(cli),
        "--diffusion-model", str(diffusion),
        "--llm", str(llm),
        # This prebuilt Vulkan binary hangs in single-threaded graph cutting with
        # --offload-to-cpu; keep weights on the GPU and disable auto-fit instead.
        "--backend", "diffusion=vulkan0,te=vulkan0",
        "--auto-fit", "off",
        "-t", "16",
        "--cfg-scale", str(args.cfg),
        "--steps", str(args.steps),
        "-W", str(args.width),
        "-H", str(args.height),
        "-p", args.prompt,
        "-o", out_arg,
        "-b", str(args.batch),
    ]
    if args.negative:
        cmd += ["-n", args.negative]
    if args.seed is not None:
        cmd += ["-s", str(args.seed)]

    env = os.environ.copy()
    ld = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = str(sd_cpp) + (os.pathsep + ld if ld else "")

    if args.verbose:
        print("running:", " ".join(cmd), flush=True)

    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        die(f"sd-cli exited with {result.returncode}")

    if "%d" in out_arg:
        files = sorted(output.parent.glob(f"{output.stem}_*{output.suffix}"))
    else:
        files = [output]
    for path in files:
        print(path)
    if not files or not all(p.is_file() for p in files):
        die("sd-cli reported success but no output PNG was found")


if __name__ == "__main__":
    main()
