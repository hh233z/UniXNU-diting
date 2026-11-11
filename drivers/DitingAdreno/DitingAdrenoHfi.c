/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Derived from UniXNU AdrenoFirmware; Diting's vendor gen7_hfi/adreno_hfi.h
 * uses 17 header slots (210 dwords), three active queues, and queue data
 * after the table rounded to 16 bytes (848 bytes), not at the next page.
 * Reserved queue fields stay zero; debug priority is 40, not 10.
 */
#include "DitingAdrenoHfi.h"
#if !defined(__aarch64__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error Modern GMU HFI transport requires little-endian AArch64
#endif
#define WORDS 1024u
static void acquire(void){__asm__ volatile("dmb oshld":::"memory");}
static void publish(void){__asm__ volatile("dsb oshst":::"memory");}
static void complete(void){__asm__ volatile("dmb osh":::"memory");}
static DitingAdrenoHfiStatus poison(DitingAdrenoHfi *h,DitingAdrenoHfiStatus status)
{h->poisoned=1;return status;}
static DitingAdrenoHfiStatus valid(DitingAdrenoHfi *h,unsigned q,volatile uint32_t **header,
    volatile uint32_t **data,uint32_t *read,uint32_t *write)
{
    if(!h || !h->shared || !h->notify || !h->iova || (h->iova&4095) ||
        ((uintptr_t)h->shared&4095))return DitingAdrenoHfiInvalid;
    if(h->poisoned)return DitingAdrenoHfiPoisoned;
    volatile uint32_t *m=h->shared;acquire();
    if(m[0]!=0 || m[1]!=210 || m[2]!=6 || m[3]!=12 || m[4]!=3 || m[5]!=3)
        return poison(h,DitingAdrenoHfiCorrupt);
    volatile uint32_t *v=m+6+12*q;
    if(v[0]!=1 || v[1]!=h->iova+848+q*4096 || v[2]!=((q==2?0x2800:0xa00)|q) ||
        v[3]!=WORDS || v[4]!=0)return poison(h,DitingAdrenoHfiCorrupt);
    *read=v[10];*write=v[11];acquire();
    if(*read>=WORDS || *write>=WORDS || (*read&3) || (*write&3))return poison(h,DitingAdrenoHfiCorrupt);
    *header=v;*data=m+212+q*WORDS;return DitingAdrenoHfiSuccess;
}
DitingAdrenoHfiStatus DitingAdrenoHfiInitializeStopped(DitingAdrenoHfi *h,volatile uint32_t *shared,
    size_t bytes,uint64_t iova,void *cookie,int (*notify)(void *))
{
    if(!h || !shared || !notify || bytes!=16384 || ((uintptr_t)shared&4095) ||
        (uintptr_t)shared>UINTPTR_MAX-16383 || !iova || (iova&4095) || iova>UINT32_MAX-16383)
        return DitingAdrenoHfiInvalid;
    for(unsigned i=0;i<4096;++i)shared[i]=0;
    shared[1]=210;shared[2]=6;shared[3]=12;shared[4]=3;shared[5]=3;
    for(unsigned q=0;q<3;++q) {
        volatile uint32_t *v=shared+6+12*q;
        v[0]=1;v[1]=(uint32_t)iova+848+q*4096;v[2]=(q==2?0x2800:0xa00)|q;v[3]=WORDS;
    }
    publish();
    *h=(DitingAdrenoHfi){shared,(uint32_t)iova,0,0,0,cookie,notify,0,0,0,0};
    return DitingAdrenoHfiSuccess;
}
DitingAdrenoHfiStatus DitingAdrenoHfiSend(DitingAdrenoHfi *h,unsigned id,const uint32_t *payload,
    size_t words,uint32_t *wire_header)
{
    if(!wire_header || id>255 || words>254 || (words && !payload))return DitingAdrenoHfiInvalid;
    volatile uint32_t *v,*data;uint32_t read,write;
    DitingAdrenoHfiStatus status=valid(h,0,&v,&data,&read,&write);
    if(status!=DitingAdrenoHfiSuccess)return status;
    if(h->pending_header)return DitingAdrenoHfiBusy;
    unsigned count=(unsigned)words+1,padded=(count+3)&~3u;
    if(((read-write-1)&(WORDS-1))<padded)return DitingAdrenoHfiNoSpace;
    uint32_t sequence=(h->sequence+1)%4095;
    uint32_t header=(sequence<<20)|(count<<8)|id;
    data[write]=header;
    for(unsigned i=0;i<words;++i)data[(write+1+i)&(WORDS-1)]=payload[i];
    for(unsigned i=count;i<padded;++i)data[(write+i)&(WORDS-1)]=UINT32_C(0xfafafafa);
    publish();v[11]=(write+padded)&(WORDS-1);publish();
    h->pending_header=header;h->sequence=sequence;*wire_header=header;
    if(h->notify(h->cookie))return poison(h,DitingAdrenoHfiNotifyError);
    return DitingAdrenoHfiSuccess;
}
DitingAdrenoHfiStatus DitingAdrenoHfiPoll(DitingAdrenoHfi *h,uint32_t *payload,size_t capacity,
    size_t *payload_words,uint32_t *error)
{
    if(!payload || capacity<16 || !payload_words || !error)return DitingAdrenoHfiInvalid;
    *payload_words=0;*error=0;
    volatile uint32_t *v,*data;uint32_t read,write;
    DitingAdrenoHfiStatus status=valid(h,1,&v,&data,&read,&write);
    if(status!=DitingAdrenoHfiSuccess)return status;
    if(!h->pending_header)return DitingAdrenoHfiInvalid;
    /* A ring holds at most WORDS/4 packets; each pass consumes one. */
    for(unsigned pass=0;pass<WORDS/4;++pass) {
        if(read==write)return DitingAdrenoHfiEmpty;
        uint32_t packet[19];uint32_t header=data[read];unsigned count=(header>>8)&255;
        unsigned available=(write-read)&(WORDS-1),padded=(count+3)&~3u;
        if(!count || count>19 || padded>available)return poison(h,DitingAdrenoHfiCorrupt);
        for(unsigned i=0;i<count;++i)packet[i]=data[(read+i)&(WORDS-1)];
        complete();
        const int firmware_error=(header&255)==100;
        const int match=!firmware_error && ((header>>16)&15)==1 && count>=3 &&
            (packet[1]>>20)==(h->pending_header>>20);
        if(!match) {
            if(count<2)return poison(h,DitingAdrenoHfiCorrupt);
            if(!h->skipped++) {h->skipped_header=header;h->skipped_ret=packet[1];h->skipped_code=count>2?packet[2]:0;}
            read=(read+padded)&(WORDS-1);v[10]=read;publish();
            continue;
        }
        if(packet[2]) {*error=packet[2];return poison(h,DitingAdrenoHfiFirmwareError);}
        /* Copy only the checked matching response, never padding. This is not
         * cryptographic authentication of firmware or its response. */
        for(unsigned i=3;i<count;++i)payload[i-3]=packet[i];
        complete();v[10]=(read+padded)&(WORDS-1);publish();
        h->pending_header=0;*payload_words=count-3;return DitingAdrenoHfiSuccess;
    }
    return poison(h,DitingAdrenoHfiCorrupt);
}
DitingAdrenoHfiStatus DitingAdrenoHfiExchange(DitingAdrenoHfi *h,unsigned id,const uint32_t *input,
    size_t words,unsigned budget,int (*wait_once)(void *),uint32_t *output,
    size_t capacity,size_t *count,uint32_t *error)
{
    if(!budget || budget>1048576 || !output || capacity<16 || !count || !error)
        return DitingAdrenoHfiInvalid;
    *count=0;*error=0;uint32_t header;
    DitingAdrenoHfiStatus status=DitingAdrenoHfiSend(h,id,input,words,&header);
    if(status!=DitingAdrenoHfiSuccess)return status;
    for(unsigned i=0;i<budget;++i) {
        status=DitingAdrenoHfiPoll(h,output,capacity,count,error);
        if(status!=DitingAdrenoHfiEmpty)return status;
        if(i+1<budget && wait_once && wait_once(h->cookie))return poison(h,DitingAdrenoHfiWaitError);
    }
    return poison(h,DitingAdrenoHfiTimeout);
}

