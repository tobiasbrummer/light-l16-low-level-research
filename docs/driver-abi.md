# Light L16 private camera-driver ABI

## Result

Light did not replace Qualcomm's complete MSM8996 camera sensor driver. The
production kernel keeps the normal Qualcomm structure and adds three
Light-specific regions:

| Region | Runtime address range | Purpose |
| --- | --- | --- |
| modified `msm_sensor_driver.c` | `ffffffc000970320` to `ffffffc0009746fc` | normal probe plus Light sysfs, IRQ, and UDP setup |
| modified `msm_sensor.c` | `ffffffc0009746fc` to `ffffffc00097734c` | standard sensor dispatch plus private compat commands 30/31 |
| `light_ccb_spi.c` | `ffffffc00097734c` to `ffffffc000978028` | three built-in Light SPI devices and factory sysfs |

Two initcalls have the same local symbol name in the recovered symbol table:

```text
ffffffc001840684 msm_sensor_driver_init
  -> platform_driver_register(...)
  -> i2c_add_driver(...)

ffffffc001840734 msm_sensor_driver_init
  -> spi_register_driver(light_ccb_spi)
```

The machine code proves that these are distinct built-in driver registrations,
despite the colliding source-level name.

## Qualcomm baseline

The comparison baseline is Qualcomm MSM commit
[`e1e85fa160463d8c5e55c58c1806668e9740a117`](https://android.googlesource.com/kernel/msm/+/e1e85fa160463d8c5e55c58c1806668e9740a117/).
In its public
[`msm_cam_sensor.h`](https://android.googlesource.com/kernel/msm/+/e1e85fa160463d8c5e55c58c1806668e9740a117/include/uapi/media/msm_cam_sensor.h),
`enum msm_sensor_cfg_type_t` ends at
`CFG_WRITE_I2C_ARRAY_SYNC_BLOCK`, numeric value 29. Its public
[`msm_sensor_config32`](https://android.googlesource.com/kernel/msm/+/e1e85fa160463d8c5e55c58c1806668e9740a117/drivers/media/platform/msm/camera_v2/sensor/msm_sensor.c)
has no cases 30 or 31.

Only the compat/32-bit dispatch in the examined Light kernel contains the two
extra cases. The native 64-bit `msm_sensor_config` does not. The names used in
this repository are descriptive clean-room names, not recovered Light source
identifiers.

## Exact compat interface

The 32-bit ioctl used by `liblight_ccb.so` is:

```c
VIDIOC_MSM_SENSOR_CFG32 == 0xc0a856c1
```

This encodes an outer `sensorb_cfg_data32` size of `0xa8`. For private command
30 or 31, `cfg.setting` points to the following 12-byte structure:

```c
struct light_l16_ccb_transfer32 {
    uint32_t addr;
    int32_t  size;
    uint32_t buffer; /* compat_uptr_t */
};
```

The complete compile-time-checked description is in
[`include/light_l16_ccb_abi.h`](../include/light_l16_ccb_abi.h).

### Command 30: sequential write

Instruction-faithful model:

```c
if (manual_control != 0)
    return 0;

copy_from_user(&xfer, compat_ptr(cdata32->cfg.setting), 12);
buf = kmalloc((int)xfer.size, GFP_KERNEL);
copy_from_user(buf, compat_ptr(xfer.buffer), (int)xfer.size);
rc = i2c_func_tbl->i2c_write_seq(client,
                                  xfer.addr, buf, xfer.size);
kfree(buf);
return rc;
```

The ARM64 instructions load four call arguments: client in `x0`, address in
`w1`, buffer in `x2`, and length in `w3`. A decompiler view that omitted the
fourth argument had an incomplete indirect-function prototype.

### Command 31: sequential read

```c
if (manual_control != 0)
    return 0;

copy_from_user(&xfer, compat_ptr(cdata32->cfg.setting), 12);
buf = kmalloc((int)xfer.size, GFP_KERNEL);
rc = i2c_func_tbl->i2c_read_seq(client,
                                xfer.addr, buf, xfer.size);
if (rc >= 0)
    copy_to_user(compat_ptr(xfer.buffer), buf, xfer.size);
kfree(buf);
return rc;
```

Neither private case checks that `size` is positive or applies an upper bound.
The signed 32-bit field is sign-extended for allocation.

## Confirmed userspace consumer

The examined 32-bit `liblight_ccb.so` directly invokes ioctl `0xc0a856c1`.
There are 35 direct callers of its local `ioctl` PLT thunk:

- 30 construct `sensorb_cfg_data32` with `cfgtype = 30`;
- the other five use handler/event ioctls;
- none sets `cfgtype = 31`.

Examples using command 30 include stream enable, active UCID, start capture,
exposure time, sensitivity, and mirror update. This result applies only to the
library identified in `artifacts/known-builds.json`; it is not a claim about
every Light firmware release.

## `manual_control` is a gate, not a selector

When `manual_control` is nonzero, commands 30 and 31 return success without a
bus transfer. The normal HAL uses command 30 for automatic CCB messages. The
factory `lcc` workflow sets `manual_control=1` while it takes over through a
separate factory bridge, then restores zero.

No camera ID or module mask is stored in `manual_control`. Physical module
selection remains part of the CCB/HAL payload.

## Interrupt and response path

The device tree provides three ASIC interrupt entries:

| Device-tree name | Handler |
| --- | --- |
| `asic-irq1` | `light_ccb_interrupt` |
| `asic-irq2` | `asic2_interrupt` |
| `asic-irq3` | `asic3_interrupt` |

The main handler reads an eight-byte header from CCB address `0x0000`. A
partially named observation layout is:

```c
struct light_l16_ccb_irq_header_observed {
    uint16_t type;       /* accepted range 1..8; type 2 stops draining */
    uint16_t length;     /* at least 4 */
    uint16_t field_4;    /* byte-swapped for types 1 and 8 */
    uint16_t field_6;
};
```

For `length > 4`, the handler reads another `length - 4` bytes from CCB address
`0x0100`. It delivers the result through:

1. V4L2 event `0x08000001`, capped at 64 payload bytes; and
2. a complete localhost UDP datagram on port 5000.

Special notifications use ports 5001, 5002, and 5004. This asynchronous path
explains why the current library has no synchronous command-31 consumer.

## Static safety findings

These are directly reachable code properties, not claims that an exploit was
executed:

| Area | Observed defect or persistent effect |
| --- | --- |
| private commands 30/31 | signed, unbounded transfer size |
| I2C/CCI write sysfs | undersized decimal-prefix storage and unbounded log concatenation on the kernel stack |
| SPI `firmware` | page-sized sysfs input copied with `strcpy` into a 128-byte stack buffer |
| SPI read/eeprom show | up to 1,024 bytes expanded beyond the page-sized sysfs output buffer |
| `camera_enable` | parser/loop count mismatch and error-pointer close path |
| SPI `eeprom` | can persistently overwrite camera data |
| probe/remove paths | incomplete allocation checks and asymmetric cleanup |

Consequently, the raw sysfs nodes are evidence of hardware paths, not suitable
camera-control APIs. Do not probe them on a valuable device.

## Claim boundary

This analysis establishes a transport ABI and driver data flow. It does not
establish:

- Light's original private symbol or structure names;
- command 31 usage in other firmware versions;
- semantic names for all interrupt-header fields;
- a safe raw-sysfs capture sequence;
- a practical privilege-escalation exploit for the static defects.
