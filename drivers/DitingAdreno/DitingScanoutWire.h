/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Fixed records adapted from NativeMobileDisplay/NativeGOPWire.h. */
#pragma once
#include <stdint.h>
enum {DitingScanoutVersion=2,DitingScanoutBgra=1,DitingScanoutMode=0x7000,
      DitingScanoutWait=0x7002,DitingScanoutComplete=0x7003,DitingScanoutResetSources=0x7004,DitingScanoutMemory=0x5343};
// A presenter rejected the frame before committing any GPU command. This is
// distinct from a failed/unknown fence: CPU fallback cannot race DMA here.
enum : uint32_t {DitingScanoutNotSubmitted=0x4e4f444d};
struct DitingScanoutModeInfo {uint32_t version,format;uint64_t width,height,stride,bytes;};
struct DitingScanoutWaitInfo {uint64_t timeout_ms;};
// v2 reuses the last word for a retained source mapping generation (not an address).
struct DitingScanoutFrame {uint64_t sequence,address,bytes,stride;uint32_t width,height,format,source_id;};
struct DitingScanoutDone {uint64_t sequence;uint32_t status,reserved;};
static_assert(sizeof(DitingScanoutModeInfo)==40 && sizeof(DitingScanoutWaitInfo)==8 &&
    sizeof(DitingScanoutFrame)==48 && sizeof(DitingScanoutDone)==16,"Diting scanout wire");
