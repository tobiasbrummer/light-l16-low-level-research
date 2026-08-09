/* SPDX-License-Identifier: MIT */
/* Clean-room description of the Light L16 additions to the MSM8996 sensor ABI.
 *
 * The numeric values, field offsets and sizes below were reconstructed from the
 * production LightOS 1.3.5.1 ARM64 kernel and its 32-bit liblight_ccb.so. The
 * identifiers are descriptive names chosen for this project; they are not
 * claimed to be Light's original source identifiers.
 *
 * This header only describes the userspace/kernel ABI. It deliberately contains
 * no helper that opens a camera device or performs an ioctl.
 */
#ifndef LIGHT_L16_CCB_ABI_H
#define LIGHT_L16_CCB_ABI_H

#include <stddef.h>
#include <stdint.h>

enum light_l16_sensor_cfg_type {
	LIGHT_L16_CFG_CCB_WRITE_SEQ32 = 30,
	LIGHT_L16_CFG_CCB_READ_SEQ32 = 31,
};

/* Argument referenced by sensorb_cfg_data32.cfg.setting for cfgtype 30/31. */
struct light_l16_ccb_transfer32 {
	uint32_t addr;
	int32_t size;
	uint32_t buffer; /* 32-bit userspace pointer (compat_uptr_t). */
};

/*
 * Minimal exact-size view of Qualcomm's sensorb_cfg_data32. Only cfg.setting is
 * named because that is the union member used by the two Light commands.
 */
struct light_l16_sensor_cfg32 {
	int32_t cfgtype;
	union {
		uint32_t setting; /* 32-bit userspace pointer. */
		uint8_t opaque[0xa4];
	} cfg;
};

/* _IOWR('V', BASE_VIDIOC_PRIVATE + 1, struct sensorb_cfg_data32). */
#define LIGHT_L16_VIDIOC_MSM_SENSOR_CFG32 UINT32_C(0xc0a856c1)

#if defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
_Static_assert(sizeof(struct light_l16_ccb_transfer32) == 12,
	"Light CCB compat transfer must be 12 bytes");
_Static_assert(offsetof(struct light_l16_ccb_transfer32, addr) == 0,
	"unexpected Light CCB address offset");
_Static_assert(offsetof(struct light_l16_ccb_transfer32, size) == 4,
	"unexpected Light CCB size offset");
_Static_assert(offsetof(struct light_l16_ccb_transfer32, buffer) == 8,
	"unexpected Light CCB buffer offset");
_Static_assert(sizeof(struct light_l16_sensor_cfg32) == 0xa8,
	"sensorb_cfg_data32 must be 0xa8 bytes");
_Static_assert(offsetof(struct light_l16_sensor_cfg32, cfg.setting) == 4,
	"unexpected sensorb_cfg_data32 setting offset");
#endif

#endif /* LIGHT_L16_CCB_ABI_H */
