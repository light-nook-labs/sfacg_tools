"""OCR Benchmark: CPU vs GPU performance comparison.

Usage:
    uv run python benchmarks/ocr_benchmark.py
    uv run python benchmarks/ocr_benchmark.py --input path/to/file.gif
    uv run python benchmarks/ocr_benchmark.py --runs 5
"""

import argparse
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')


def benchmark_ocr(gif_path: Path, runs: int = 3) -> dict:
    """Run OCR benchmark on a GIF file."""
    import sfacglib.ocr.engine as engine

    gif_bytes = gif_path.read_bytes()
    file_size_kb = len(gif_bytes) / 1024

    print(f'\nFile: {gif_path.name} ({file_size_kb:.0f} KB)')
    print(f'Runs: {runs}')

    gpu_available = engine._check_gpu_available()
    print(f'GPU available: {gpu_available}')

    # Force CPU mode
    print('\n--- CPU Mode ---')

    engine._ocr_instance = None
    engine._gpu_available = False

    cpu_times = []
    cpu_chars = 0
    for i in range(runs):
        engine._ocr_instance = None
        start = time.perf_counter()
        text = engine.ocr_gif(gif_bytes)
        elapsed = time.perf_counter() - start
        cpu_times.append(elapsed)
        cpu_chars = len(text)
        print(f'  Run {i + 1}: {elapsed:.2f}s, {cpu_chars} chars')

    cpu_avg = sum(cpu_times) / len(cpu_times)
    cpu_min = min(cpu_times)
    cpu_max = max(cpu_times)
    print(f'  Average: {cpu_avg:.2f}s (min={cpu_min:.2f}, max={cpu_max:.2f})')

    result = {
        'file': gif_path.name,
        'file_size_kb': file_size_kb,
        'gpu_available': gpu_available,
        'cpu_avg': cpu_avg,
        'cpu_min': cpu_min,
        'cpu_max': cpu_max,
        'cpu_chars': cpu_chars,
    }

    if gpu_available:
        print('\n--- GPU Mode ---')
        engine._ocr_instance = None
        engine._gpu_available = True

        gpu_times = []
        gpu_chars = 0
        for i in range(runs):
            engine._ocr_instance = None
            start = time.perf_counter()
            text = engine.ocr_gif(gif_bytes)
            elapsed = time.perf_counter() - start
            gpu_times.append(elapsed)
            gpu_chars = len(text)
            print(f'  Run {i + 1}: {elapsed:.2f}s, {gpu_chars} chars')

        gpu_avg = sum(gpu_times) / len(gpu_times)
        gpu_min = min(gpu_times)
        gpu_max = max(gpu_times)
        print(f'  Average: {gpu_avg:.2f}s (min={gpu_min:.2f}, max={gpu_max:.2f})')

        speedup = cpu_avg / gpu_avg if gpu_avg > 0 else 0
        print(f'\nSpeedup: {speedup:.1f}x faster with GPU')

        result.update(
            {
                'gpu_avg': gpu_avg,
                'gpu_min': gpu_min,
                'gpu_max': gpu_max,
                'gpu_chars': gpu_chars,
                'speedup': speedup,
            }
        )
    else:
        print('\nGPU not available, skipping GPU benchmark.')
        print('To enable GPU: uv sync --extra gpu')

    return result


def main():
    parser = argparse.ArgumentParser(description='OCR Benchmark: CPU vs GPU')
    parser.add_argument('--input', '-i', type=Path, default=None, help='GIF file to benchmark (default: first VIP GIF)')
    parser.add_argument('--runs', '-n', type=int, default=3, help='Number of runs per mode (default: 3)')
    args = parser.parse_args()

    if args.input:
        gif_path = args.input
    else:
        gif_files = list(Path('novel_689388_test').rglob('*.gif'))
        if not gif_files:
            print('No GIF files found. Download VIP chapters first or use --input.')
            sys.exit(1)
        gif_path = gif_files[0]

    if not gif_path.exists():
        print(f'File not found: {gif_path}')
        sys.exit(1)

    result = benchmark_ocr(gif_path, args.runs)

    print('\n--- Summary ---')
    print(f'CPU: {result["cpu_avg"]:.2f}s avg ({result["cpu_chars"]} chars)')
    if result.get('gpu_avg'):
        print(f'GPU: {result["gpu_avg"]:.2f}s avg ({result["gpu_chars"]} chars)')
        print(f'Speedup: {result["speedup"]:.1f}x')


if __name__ == '__main__':
    main()
