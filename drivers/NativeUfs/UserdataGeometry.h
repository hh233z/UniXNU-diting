// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>

// 设备树未指定时使用 Diting 的 userdata 范围（board.toml [userdata]，4 KiB LBA）。
static bool ufsExpectedUserdataGeometry(const void *firstData, size_t firstSize,
                                       const void *lastData, size_t lastSize,
                                       uint64_t *first, uint64_t *last)
{
  if (!firstData && !lastData) {
    *first = 0x2F8A00ULL;
    *last = 0x3ADF3FAULL;
    return true;
  }
  if (!firstData || !lastData || firstSize != sizeof(*first) || lastSize != sizeof(*last))
    return false;
  memcpy(first, firstData, sizeof(*first));
  memcpy(last, lastData, sizeof(*last));
  return *first != 0 && *last >= *first;
}
