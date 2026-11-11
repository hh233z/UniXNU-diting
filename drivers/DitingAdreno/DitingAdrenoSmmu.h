/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#ifndef DITING_ADRENO_SMMU_H
#define DITING_ADRENO_SMMU_H
#include "ArmSmmu4K/ArmSmmu4KAudit.h"
#include "ArmSmmu4K/ArmSmmu4KStreams.h"
#ifdef __cplusplus
extern "C" {
#endif

typedef enum {DitingAdrenoSmmuGpu,DitingAdrenoSmmuGmu} DitingAdrenoSmmuRole;
typedef struct {
    unsigned attempted,ready,poisoned;
    DitingAdrenoSmmuRole role;
    ArmSmmu4KContextConfig context;
    ArmSmmu4KAuditConfig tables;
    ArmSmmu4KStreamState streams;
} DitingAdrenoSmmuSession;
typedef struct {
    unsigned phase,must_retain_resources;
    ArmSmmu4KProgramResult context;
    ArmSmmu4KStreamResult streams;
    ArmSmmu4KAuditResult tables;
    ArmSmmu4KStatus cleanup;
} DitingAdrenoSmmuResult;

/* Actual Diting GPU SMMU only: physical 0x03da0000/0x40000. It is separate
 * from the applications SMMU used by the working UFS/display drivers.
 * DT mask 0x400 expands to TWO exact SIDs for each role: GPU 0/0x400,
 * GMU 5/0x405. The caller supplies two actually leased slots (not SID=slot)
 * and a leased bank/ASID. Secure and LPAC streams are never taken here.
 *
 * Before calling, platform must establish real power/clocks, stopped masters,
 * exclusive global configuration ownership, context/global fault handlers,
 * Diting ACTLR/SCM setup, and published physical native4KiB table/backing
 * ownership. This module does not establish any of those prerequisites.
 * GPU bank0 uses upper TTBR1; GMU uses a leased nonzero bank and lower TTBR0.
 * No bypass or masked route is installed. Unrelated live routes are preserved.
 * All config/table/result/session storage is disjoint and retained. Normal
 * completion and failure BOTH retain resources: a TLB sync is not a DMA drain.
 */
ArmSmmu4KStatus DitingAdrenoSmmuStart(const ArmSmmu4KIo *,uint64_t physical,
    DitingAdrenoSmmuRole,unsigned bank,const unsigned slots[2],
    const ArmSmmu4KContextConfig *,const ArmSmmu4KAuditConfig *,unsigned budget,
    DitingAdrenoSmmuSession *,DitingAdrenoSmmuResult *);
ArmSmmu4KStatus DitingAdrenoSmmuObserve(const ArmSmmu4KIo *,uint64_t physical,
    const DitingAdrenoSmmuSession *,DitingAdrenoSmmuResult *);
/* Caller must first prove actual masters stopped. Fault both exact streams
 * before disabling their owned bank. Never releases DMA memory or a lease.
 */
ArmSmmu4KStatus DitingAdrenoSmmuStop(const ArmSmmu4KIo *,uint64_t physical,
    unsigned budget,DitingAdrenoSmmuSession *,DitingAdrenoSmmuResult *);
#ifdef __cplusplus
}
#endif
#endif
