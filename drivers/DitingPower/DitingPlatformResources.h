/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#ifndef DITING_PLATFORM_RESOURCES_H
#define DITING_PLATFORM_RESOURCES_H
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void diting_rpmh_init(void);
bool diting_scm_call_lock(void);
void diting_scm_call_unlock(void);
bool diting_rpmh_vote(uint32_t address, uint32_t value);
bool diting_smmu_lease_lock(void);
void diting_smmu_lease_unlock(void);
#ifdef __cplusplus
}
#endif
#endif
