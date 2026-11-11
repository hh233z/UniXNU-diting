#ifndef DITING_TOUCH_H
#define DITING_TOUCH_H
#include <stdint.h>
#define DITING_TOUCH_DOWN 1
#define DITING_TOUCH_MOVE 2
#define DITING_TOUCH_UP 3
#define DITING_BUTTON_DOWN 4
#define DITING_BUTTON_UP 5
#define DITING_BUTTON_POWER 0
#define DITING_BUTTON_VOLUME_UP 1
#define DITING_BUTTON_VOLUME_DOWN 2
struct pong_touch {uint64_t time;uint32_t type,finger,x,y;};
void pong_touch_start(void);
#endif
