/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#ifndef DITING_ADRENO_GMU_H
#define DITING_ADRENO_GMU_H
#include <stddef.h>
#include <stdint.h>
#include "DitingAdrenoHfi.h"
#include "DitingAdrenoPower.h"
#ifdef __cplusplus
extern "C" {
#endif

/* SM8475/Diting only. These are hardware TCM/buffer extents, not CPU page
 * granules: all backing memory and translations still use native 4 KiB.
 */
enum {DitingGpuCore,DitingGpuGmu,DitingGpuRscc,DitingGpuPdc,DitingGpuCxMisc,
      DitingGpuClock,DitingGpuSmmu,DitingGpuAo,DitingGpuWindowCount};
typedef struct {uint64_t physical;size_t bytes;} DitingGpuWindow;
extern const DitingGpuWindow DitingAdrenoWindows[DitingGpuWindowCount];
enum {DitingAdrenoChipId=0x07030002,DitingAdrenoGmemBytes=0x200000,
      DitingAdrenoGpuSid=0,DitingAdrenoLpacSid=1,DitingAdrenoSecureSid=2,
      DitingAdrenoGmuSid=5,DitingAdrenoGmuStreamMask=0x400};
/* Device-tree and Mesa profile facts; not an advertised ready GPU device.
 * Mesa names this exact Adreno730v3 revision FD725/A7XX Gen1, so a compiler
 * must keep chip_id intact instead of selecting generic FD730 or A740.
 */
enum {DitingAdrenoGpuIrq=332,DitingAdrenoHfiIrq=336,DitingAdrenoGmuIrq=337,
      DitingAdrenoContextBanks=21,DitingAdrenoStreamSlots=24,
      DitingAdrenoHighestBankBit=16,DitingAdrenoTileWidth=64,DitingAdrenoTileHeight=32,
      DitingAdrenoGmuTimerLow=0x16220,DitingAdrenoGmuTimerHigh=0x16224,
      DitingAdrenoCxGdscr=0x9108,DitingAdrenoCxHwControl=0x953c,
      DitingAdrenoGxGdscr=0x905c,DitingAdrenoSmmuClockVote=0x7000};
typedef enum {DitingGpuSuccess,DitingGpuArgument,DitingGpuPrerequisite,DitingGpuFirmware,
    DitingGpuIo,DitingGpuBusy,DitingGpuTimeout,DitingGpuPoisoned} DitingGpuStatus;
typedef struct {
    void *cookie;
    /* All callbacks return0 on success, nonzero on failure. */
    /* These must check real power/clocks, owned native4K translations and
     * exclusive ownership, not set a software flag to bypass prerequisites. */
    int (*platform_ready)(void *);
    int (*read32)(void *,unsigned window,size_t byte_offset,uint32_t *);
    int (*write32)(void *,unsigned window,size_t byte_offset,uint32_t);
    int (*barrier)(void *);
    int (*publish)(void *,void *owned_cpu,size_t bytes);
    int (*now_us)(void *,uint64_t *);
    int (*wait_us)(void *,unsigned);
} DitingGpuOps;
typedef struct {volatile uint32_t *cpu;size_t bytes;uint32_t iova;} DitingGpuMemory;
typedef struct {
    uint32_t chip_id;
    const uint8_t *firmware;size_t firmware_bytes;
    DitingGpuMemory cache,dummy,hfi,log;
} DitingGpuGmuConfig;
typedef struct {
    DitingGpuOps io;DitingAdrenoHfi hfi;
    unsigned attempted,poisoned,fw_ready,hfi_ready,power_attempted,power_started,gpu_held;
} DitingGpuGmuDevice;
typedef struct {
    unsigned phase,writes,fw_ready,hfi_ready,resources_must_retain;
    uint32_t last_register,last_value;
    uint32_t core_version,hfi_version;
} DitingGpuGmuResult;

/* A real, one-shot loader for an ALREADY owned/powered/mapped Diting GMU.
 * It programs Diting's RSC/PDC, uploads its firmware into real cache/TCM,
 * starts CM3, then waits for fresh firmware/HFI readiness. It does NOT
 * establish regulator votes, SMMU mappings, ZAP authorization, CP execution
 * or a Metal device. There is no IOKit personality/automatic boot entry.
 * Failure after a write attempts reset, poisons the device and retains DMA
 * backing. Only a later hardware quiesce can authorize release.
 */
DitingGpuStatus DitingAdrenoGmuStart(DitingGpuGmuDevice *,const DitingGpuGmuConfig *,DitingGpuGmuResult *);
typedef struct {
    unsigned phase,published,acknowledged,polls,resources_must_retain;
    uint32_t command,header,firmware_error;
    DitingAdrenoHfiStatus transport;
} DitingGpuPowerResult;
/* Exact gen7-4-0 cold-start handshake after actual GMU/HFI readiness:
 * PERF -> BW -> CORE_FW_START -> selected blocking GX/BW vote. power_level
 * is a real Diting DT index; firmware keeps control over the actual clocks.
 * This differs from Sheng's extra START message. ACD/BCL/IFPC are left disabled until
 * their AOP/power prerequisites exist; no A740 feature table is reused.
 * Only actual matching ACKs advance state. Elapsed time and poll counts
 * are bounded, and an uncertain attempt poisons/retains the session.
 * Success is GMU power protocol startup, not CP execution or acceleration.
 */
DitingGpuStatus DitingAdrenoGmuStartPower(DitingGpuGmuDevice *,const DitingPowerInputs *,unsigned power_level,DitingGpuPowerResult *);
/* Vendor gen7_gpu_boot: fresh OOB_GPU acknowledgement followed by START10.
 * Keep OOB held while this port has no idle/slumber/resume owner. */
DitingGpuStatus DitingAdrenoGmuHoldGpu(DitingGpuGmuDevice *,DitingGpuPowerResult *);
#ifdef __cplusplus
}
#endif
#endif
