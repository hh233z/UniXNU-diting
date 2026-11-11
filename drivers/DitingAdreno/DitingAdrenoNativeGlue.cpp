/* SPDX-License-Identifier: MIT */
/* A730 board -> complete upstream NativeAdreno publication/runtime. */
#include "DitingAdrenoCp.h"
#include "DitingAdrenoScanout.h"
#include <IOKit/IOLib.h>
#include <IOKit/IOPlatformExpert.h>
#include <pexpert/pexpert.h>
#include <kern/task.h>
extern "C" IOReturn native_adreno_publish(NativeAdrenoVm *,NativeAdrenoSubmit *,NativeAdrenoRing *,
    const NativeAdrenoRingClock *,const NativeAdrenoTimer *,const NativeAdrenoAbiDeviceInfo *,uint32_t,uint32_t);
extern "C" IOService *native_adreno_published_service(void);
extern "C" void diting_ramoops_diagnostic_write(const char *,int);
extern IOReturn DitingAdrenoPublishMetalAccelerator();
static DitingCpBackend *backend;
extern "C" bool diting_adreno_native_healthy(void)
{return backend && backend->healthy();}
extern "C" const NativeAdrenoStatus *diting_adreno_native_status(void)
{return backend?backend->status:nullptr;}
extern "C" IOReturn native_gop_handoff_call(uint32_t op,task_t task,const void *in,size_t inSize,void *out,size_t outSize)
{return diting_scanout_call(task,op+DitingScanoutMode,in,inSize,out,outSize);}
extern "C" IOMemoryDescriptor *native_gop_handoff_memory(void)
{return diting_scanout_memory(current_task());}
bool DitingAdrenoConfigureService(IOService *service)
{
    if(!service || !diting_adreno_native_healthy())return false;
    service->setProperty("DitingAdrenoCPReady",true);
    service->setProperty("DitingChipID",backend->info.chip_id,32);
    service->setProperty("DitingNativePageBytes",4096,32);
    unsigned metal=0;
    const bool enabled=PE_parse_boot_argn("diting_metal",&metal,sizeof(metal)) && metal==1;
    #if DITING_GUEST_22H374
    service->setProperty("DitingMetal22H374Enabled",enabled);
    unsigned global=0;
    if(enabled && PE_parse_boot_argn("diting_metal_global",&global,sizeof(global)) && global==1)
        service->setProperty("DitingNativeMetalGlobal",kOSBooleanTrue);
#else
    service->setProperty("DitingMetal20G81Enabled",enabled);
#endif
    if(enabled)service->setProperty("NativeSandboxGrantProcess",
        "backboardd,SpringBoard,CollectionsPoster,WidgetRenderer_Default,PosterBoard,Weather,WeatherPoster,GradientPosterExtension"
#if DITING_GUEST_22H374
        ",Preferences,LegacyPoster,MercuryPosterExtension,Unity2025Poster,PridePosterExtension"
#endif
    );
    return true;
}
bool DitingAdrenoPublishClient(DitingCpBackend *device)
{
    if(backend || !device || !device->healthy())return false;
    backend=device;
    const IOReturn result=native_adreno_publish(device->vm,device->submit,device->ring,
        &device->clock,device->timer,&device->info,32,device->output_bits);
    if(result)return false;
    if(!DitingAdrenoConfigureService(native_adreno_published_service()))return false;
    unsigned metal=0;
    if(PE_parse_boot_argn("diting_metal",&metal,sizeof(metal)) && metal==1) {
        const IOReturn status=DitingAdrenoPublishMetalAccelerator();
        char line[160];const int n=snprintf(line,sizeof(line),
            "DITING METAL: NativeAdreno complete runtime publication status=0x%x\n",status);
        IOLog("%s",line);diting_ramoops_diagnostic_write(line,n);
        if(status)return false;
    }
    return true;
}
