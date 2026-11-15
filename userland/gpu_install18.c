/* SPDX-License-Identifier: MIT
 * Fresh installation of project-built Metal files through native APFS VFS.
 * The kernel stages this executable only on the UUID-bound guest Data volume.
 */
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/attr.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/sysctl.h>
#include <sys/wait.h>
#include <unistd.h>
#include <uuid/uuid.h>
#include <zlib.h>
#include "gpu_install_payload.h"

extern const unsigned char diting_gpu_archive[];
static int logfd=-1;
static void record(const char *phase,int error)
{
    if(logfd>=0) {
        (void)dprintf(logfd,"Diting GPU install: %s error=%d source=%s\n",phase,error,DITING_GPU_SOURCE);
        (void)fsync(logfd);
    }
}
static bool argument(const char *args,const char *key)
{
    size_t n=strlen(key);
    for(const char *p=args;(p=strstr(p,key));p+=n)
        if((p==args || p[-1]==' ') && (!p[n] || p[n]==' '))return true;
    return false;
}
static int volume(const char *path,const char *expected)
{
    struct attrlist attrs={.bitmapcount=ATTR_BIT_MAP_COUNT,.volattr=ATTR_VOL_INFO|ATTR_VOL_UUID};
    struct {uint32_t length;uuid_t uuid;} result={0};uuid_t wanted;
    if(uuid_parse(expected,wanted))return EINVAL;
    if(getattrlist(path,&attrs,&result,sizeof(result),0))return errno;
    return result.length==sizeof(result) && !uuid_compare(result.uuid,wanted)?0:EXDEV;
}
static int remount(const char *mode)
{
    pid_t child=fork();if(child<0)return errno;
    if(!child){execl("/sbin/mount","mount","-u",mode,"/",NULL);_exit(127);}
    for(unsigned i=0;i<150;i++) {
        int status=0;pid_t result=waitpid(child,&status,WNOHANG);
        if(result==child)return WIFEXITED(status)&&WEXITSTATUS(status)==0?0:EIO;
        if(result<0 && errno!=EINTR)return errno;
        usleep(100000);
    }
    (void)kill(child,SIGKILL);(void)waitpid(child,NULL,0);return ETIMEDOUT;
}
static int owned_directory(int fd,dev_t device)
{
    struct stat st;
    if(fstat(fd,&st))return errno;
    return S_ISDIR(st.st_mode) && st.st_uid==0 && !(st.st_mode&022) &&
        st.st_dev==device?0:EPERM;
}
static int absent(int fd,const char *name)
{
    struct stat st;
    if(!fstatat(fd,name,&st,AT_SYMLINK_NOFOLLOW))return EEXIST;
    return errno==ENOENT?0:errno;
}
static int write_file(int parent,const char *name,const void *data,size_t bytes,mode_t mode)
{
    int fd=openat(parent,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0)return errno;
    size_t done=0;int error=0;
    while(done<bytes) {
        ssize_t n=write(fd,(const char *)data+done,bytes-done>1048576?1048576:bytes-done);
        if(n<0 && errno==EINTR)continue;
        if(n<=0){error=n<0?errno:EIO;break;}
        done+=(size_t)n;
    }
    if(!error && fchmod(fd,mode))error=errno;
    if(!error && fsync(fd))error=errno;
    if(close(fd) && !error)error=errno;
    if(error)(void)unlinkat(parent,name,0); /* This call created the file exclusively. */
    return error;
}
int main(void)
{
    if(getuid()!=0 || getpid()==1)return 77;
    char args[1024]={0},version[64]={0};size_t n=sizeof(args),v=sizeof(version);
    if(sysctlbyname("kern.bootargs",args,&n,NULL,0) ||
       sysctlbyname("kern.osversion",version,&v,NULL,0))return 77;
    args[sizeof(args)-1]=0;version[sizeof(version)-1]=0;
    if(strcmp(version,"22H374") || !argument(args,"diting_gpu_install=1") ||
       !argument(args,"diting_rootful=1") || !argument(args,"diting_ui_software=1"))return 77;
    int error=volume("/","B07DF049-7AD9-47B5-9F8F-9EE728056398");
    if(!error)error=volume("/private/var","BBD6873C-A3F7-4B19-9086-2F89A3D8C1B7");
    if(error)return 77;
    int logs=open("/private/var/logs",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    struct stat rootst,datast;
    if(stat("/",&rootst) || stat("/private/var",&datast) || logs<0 ||
       owned_directory(logs,datast.st_dev))return 77;
    logfd=openat(logs,"DitingGpuInstall.txt",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(logfd<0){close(logs);return 77;} /* Never overwrite an existing install receipt. */
    close(logs);record("START",0);
    struct statfs os,cache;
    if(statfs("/",&os) || statfs("/private/preboot",&cache))error=errno;
    else if(strcmp(os.f_fstypename,"apfs") || strcmp(cache.f_fstypename,"apfs") ||
        !(os.f_flags&MNT_RDONLY) || !(cache.f_flags&MNT_RDONLY))error=EPERM;
    unsigned char *payload=NULL;
    int parent=-1,stagefd=-1;bool writable=false,bundle=false,clients=false,publish=false,stage=false;
    char temp[80];snprintf(temp,sizeof(temp),".DitingAdrenoMetal.install-%d",getpid());
    const char *bundle_name="DitingAdrenoMetal.bundle";
    if(error)goto done;
    parent=open("/",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(parent<0){error=errno;goto done;}
    for(unsigned i=0;i<3;i++) {
        static const char *parts[]={"System","Library","Extensions"};
        int next=openat(parent,parts[i],O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
        if(next<0){error=errno;goto done;}
        close(parent);parent=next;
        if((error=owned_directory(parent,rootst.st_dev)))goto done;
    }
    if((error=absent(parent,bundle_name)) ||
       (error=absent(parent,"DitingAdrenoMetal.clients")) ||
       (error=absent(parent,"DitingAdrenoMetal.publish")))goto done;
    payload=malloc(DITING_GPU_RAW_BYTES);
    if(!payload){error=ENOMEM;goto done;}
    uLongf bytes=DITING_GPU_RAW_BYTES;
    int zr=uncompress(payload,&bytes,diting_gpu_archive,DITING_GPU_COMPRESSED_BYTES);
    if(zr!=Z_OK || bytes!=DITING_GPU_RAW_BYTES){error=EINVAL;goto done;}
    record("PAYLOAD_READY",0);
    error=remount("-w");
    /* Even a failed mount command can have changed flags. Restore at exit. */
    if(!statfs("/",&os))writable=!(os.f_flags&MNT_RDONLY);
    if(error || !writable){if(!error)error=EROFS;goto done;}
    if(mkdirat(parent,temp,0700)){error=errno;goto done;}
    stage=true;stagefd=openat(parent,temp,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(stagefd<0){error=errno;goto done;}
    if((error=owned_directory(stagefd,rootst.st_dev)))goto done;
    for(unsigned i=0;i<4;i++) {
        const struct diting_gpu_file *f=&diting_gpu_files[i];
        if(f->offset>bytes || f->bytes>bytes-f->offset){error=EINVAL;goto done;}
        if((error=write_file(stagefd,f->name,payload+f->offset,f->bytes,f->mode)))goto done;
    }
    if(fchmod(stagefd,0755) || fsync(stagefd)){error=errno;goto done;}
    if(renameatx_np(parent,temp,parent,bundle_name,RENAME_EXCL)){error=errno;goto done;}
    stage=false;bundle=true;
    error=write_file(parent,"DitingAdrenoMetal.clients","Preferences\n",12,0644);
    if(error)goto done;
    clients=true;
    error=write_file(parent,"DitingAdrenoMetal.publish","1\n",2,0644);
    if(error)goto done;
    publish=true;
    if(fsync(parent)){error=errno;goto done;}
    record("FILES_INSTALLED Preferences-only discovery; activation requires another boot",0);
done:
    if(error && parent>=0) {
        if(publish)(void)unlinkat(parent,"DitingAdrenoMetal.publish",0);
        if(clients)(void)unlinkat(parent,"DitingAdrenoMetal.clients",0);
        if(stagefd>=0) {
            for(unsigned i=0;i<4;i++)(void)unlinkat(stagefd,diting_gpu_files[i].name,0);
            if(bundle)(void)unlinkat(parent,bundle_name,AT_REMOVEDIR);
            if(stage)(void)unlinkat(parent,temp,AT_REMOVEDIR);
        }
    }
    if(stagefd>=0)close(stagefd);
    if(parent>=0)close(parent);
    free(payload);
    if(writable) {
        int restore=remount("-r");record("RESTORE_READONLY",restore);
        if(!error)error=restore;
    }
    if(!error && (statfs("/",&os) || !(os.f_flags&MNT_RDONLY) ||
        statfs("/private/preboot",&cache) || !(cache.f_flags&MNT_RDONLY)))error=EROFS;
    record(error?"FAIL":"PASS",error);close(logfd);
    return error?1:0;
}
