/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#ifndef DITING_ADRENO_POWER_H
#define DITING_ADRENO_POWER_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef enum {DitingPowerSuccess,DitingPowerArgument,DitingPowerCorrupt,
    DitingPowerMissing,DitingPowerDuplicate,DitingPowerRailRange} DitingPowerStatus;
typedef struct {uint32_t address;const uint8_t *aux;size_t bytes;} DitingPowerResource;
typedef struct {
    uint32_t chip_id,db_version;
    DitingPowerResource gfx,mx,cx,sh0,mc0,acv,cn0;
} DitingPowerInputs;
typedef struct {uint32_t hz,level,cx_level,bus,bus_min,bus_max,acd;} DitingPowerLevel;
enum {DitingAdrenoPowerLevelCount=13,DitingAdrenoBandwidthCount=12,
      DitingAdrenoBootPowerLevel=11};
/* Captured live Diting DT profile, descending Android order. Runtime speed-bin
 * policy must select only actual enabled levels; never substitute A740 OPPs.
 */
extern const DitingPowerLevel DitingAdrenoPowerLevels[DitingAdrenoPowerLevelCount];
extern const uint32_t DitingAdrenoDdrBandwidth[DitingAdrenoBandwidthCount];
typedef struct {
    /* Exact modern vendor wire payloads, excluding the HFI message header.
     * PERF has 16 GX entries of (ARC vote,CX index,kHz) and four CX entries.
     */
    uint32_t performance[58],bandwidth[159];
    uint32_t gpu_index,bus_index;
} DitingPowerTables;

/* Parse the actual retained command-db reservation at0x80860000/0x20000.
 * This does not map it, hash it, write it or invent missing resource data.
 * Output spans refer into the caller's immutable retained mapping. No MMIO.
 */
DitingPowerStatus DitingAdrenoReadPowerInputs(const uint8_t *,size_t,uint32_t chip_id,
    DitingPowerInputs *);
/* CPU serialization only: actual gfx/mx/cx aux corners and SH0/MC0/ACV/CN0
 * addresses/aux are required. Rounded primary voltage determines the secondary
 * dependency, and every Diting GPU level gets its actual CX vote. Average DDR
 * bandwidth stays zero; only peak is voted, as in Nothing's gen7_rpmh writer.
 * power_level uses descending Android DT order (0 = 900 MHz, 11 = 285 MHz).
 * Its ascending HFI index and matching DDR vote are selected together.
 * Success is not a regulator vote, clock change, HFI ACK or ready GPU.
 */
DitingPowerStatus DitingAdrenoBuildPowerTables(const DitingPowerInputs *,unsigned power_level,DitingPowerTables *);
#ifdef __cplusplus
}
#endif
#endif
