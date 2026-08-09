from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "include" / "light_l16_ccb_abi.h"


def test_header_layout_and_ioctl_constant(tmp_path: Path) -> None:
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("no C compiler installed")

    source = tmp_path / "check_light_l16_ccb_abi.c"
    binary = tmp_path / "check_light_l16_ccb_abi"
    source.write_text(
        """
#include <stddef.h>
#include <stdint.h>
#include "light_l16_ccb_abi.h"

int main(void) {
    if (LIGHT_L16_CFG_CCB_WRITE_SEQ32 != 30) return 1;
    if (LIGHT_L16_CFG_CCB_READ_SEQ32 != 31) return 2;
    if (LIGHT_L16_VIDIOC_MSM_SENSOR_CFG32 != UINT32_C(0xc0a856c1)) return 3;
    if (sizeof(struct light_l16_ccb_transfer32) != 12) return 4;
    if (offsetof(struct light_l16_ccb_transfer32, buffer) != 8) return 5;
    if (sizeof(struct light_l16_sensor_cfg32) != 0xa8) return 6;
    if (offsetof(struct light_l16_sensor_cfg32, cfg.setting) != 4) return 7;
    return 0;
}
""".lstrip(),
        encoding="utf-8",
    )

    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(HEADER.parent),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
