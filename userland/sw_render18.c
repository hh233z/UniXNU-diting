/* SPDX-License-Identifier: MIT
 * Optional 22H374 software scan conversion scheduling, Diting 4+3+1 CPUs.
 * Pixel sampling, blending, clipping, and completion remain stock.
 */
#include <libkern/OSCacheControl.h>
#include <mach/mach.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <unistd.h>
#include <fcntl.h>

static bool attempted;
static const uint8_t quartz_uuid[16] = {
    0xfa,0xf7,0xd7,0xea,0x18,0xf0,0x3c,0x2d,0x81,0x6c,0xac,0x56,0xd1,0x6c,0x40,0xa3};

static void record(const char *status, int error)
{
    char text[256];
    int n=snprintf(text,sizeof(text),
        "Diting SW18 v1: %s error=%d pid=%d workers<=8 claim_rows=16 pixels=stock\n",
        status,error,getpid());
    if(n<=0 || (size_t)n>=sizeof(text))return;
    (void)write(STDERR_FILENO,text,(size_t)n);
    int fd=open("/private/var/mobile/Library/Logs/DitingSoftwareRender.txt",
                O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW,0600);
    if(fd>=0){(void)write(fd,text,(size_t)n);(void)close(fd);}
}

static void image_added(const struct mach_header *header,intptr_t slide)
{
    if(attempted || header->magic!=MH_MAGIC_64)return;
    const struct mach_header_64 *h=(const void *)header;
    if(h->sizeofcmds>65536)return;
    const char *at=(const char *)(h+1), *end=at+h->sizeofcmds;
    uintptr_t target=(uintptr_t)header+(0x18453c95cULL-0x184339000ULL);
    bool uuid=false, executable=false;
    for(uint32_t i=0;i<h->ncmds;i++) {
        if((size_t)(end-at)<sizeof(struct load_command))return;
        const struct load_command *lc=(const void *)at;
        if(lc->cmdsize<sizeof(*lc) || lc->cmdsize>(size_t)(end-at))return;
        if(lc->cmd==LC_UUID && lc->cmdsize==sizeof(struct uuid_command))
            uuid=memcmp(((const struct uuid_command *)lc)->uuid,quartz_uuid,16)==0;
        if(lc->cmd==LC_SEGMENT_64 && lc->cmdsize>=sizeof(struct segment_command_64)) {
            const struct segment_command_64 *seg=(const void *)lc;
            uintptr_t start=(uintptr_t)(seg->vmaddr+(uint64_t)slide);
            if((seg->initprot&VM_PROT_EXECUTE) && start<=target &&
               seg->vmsize>=40 && target-start<=seg->vmsize-40)executable=true;
        }
        at+=lc->cmdsize;
    }
    if(!uuid)return;
    attempted=true;
    if(!executable){record("SKIP executable range",0);return;}
    /* draw_polygon builds a shared block with an atomic row cursor. Its
     * callback ignores the dispatch iteration index and drains claims until
     * the clipped end row. Hundreds of callbacks repeat polygon setup after
     * the earlier workers have consumed the rows. Keep 1 callback for <=7
     * rows, 8 otherwise; claim 16 instead of 4 rows, including the short tail.
     * Match the complete instruction span, not two free-standing constants. */
    static const uint32_t expected[10]={
        0x53027d0e,0xa9385bb3,0x71001d1f,0x1a9fc5c8,0x293203b0,
        0xbc1983a2,0x2933b7a9,0x52800089,0x2934afa9,0x2935b7aa};
    uint32_t changed[10];memcpy(changed,expected,sizeof(changed));
    changed[0]=0x5280010e; /* mov w14,#8: bounded dispatch_apply callbacks */
    changed[7]=0x52800209; /* mov w9,#16: shared row claim size */
    if(memcmp((const void *)target,expected,sizeof(expected))) {
        record("SKIP instruction mismatch",0);return;
    }
    vm_address_t page=target&~((vm_address_t)vm_page_size-1);
    if(target-page>vm_page_size-sizeof(expected)){record("SKIP page crossing",0);return;}
    kern_return_t kr=vm_protect(mach_task_self(),page,vm_page_size,FALSE,
                               VM_PROT_READ|VM_PROT_WRITE|VM_PROT_COPY);
    if(kr!=KERN_SUCCESS){record("SKIP private copy",kr);return;}
    memcpy((void *)target,changed,sizeof(changed));
    sys_icache_invalidate((void *)target,sizeof(changed));
    kr=vm_protect(mach_task_self(),page,vm_page_size,FALSE,VM_PROT_READ|VM_PROT_EXECUTE);
    if(kr!=KERN_SUCCESS) {
        memcpy((void *)target,expected,sizeof(expected));
        sys_icache_invalidate((void *)target,sizeof(expected));
        (void)vm_protect(mach_task_self(),page,vm_page_size,FALSE,VM_PROT_READ|VM_PROT_EXECUTE);
        record("FAIL RX restore; original instructions restored",kr);return;
    }
    record("APPLIED",0);
}

__attribute__((constructor)) static void start(void)
{
    if(strcmp(getprogname(),"backboardd"))return;
    char args[1024];size_t size=sizeof(args);
    if(sysctlbyname("kern.bootargs",args,&size,NULL,0))return;
    args[size<sizeof(args)?size:sizeof(args)-1]=0;
    const char *keys[]={"diting_sw_render=1","diting_ui_software=1"};
    for(size_t i=0;i<sizeof(keys)/sizeof(keys[0]);i++) {
        size_t n=strlen(keys[i]);bool selected=false;
        for(const char *p=args;(p=strstr(p,keys[i]));p+=n)
            if((p==args || p[-1]==' ' || p[-1]=='\t') &&
               (!p[n] || p[n]==' ' || p[n]=='\t'))selected=true;
        if(!selected)return;
    }
    _dyld_register_func_for_add_image(image_added);
}
