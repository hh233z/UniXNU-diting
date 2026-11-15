/* SPDX-License-Identifier: MIT
 * Spawn the optional installer after launchd has started a root daemon.
 * No work in PID 1, no fork inside a framework host, no renderer injection.
 */
#include <spawn.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/sysctl.h>
#include <unistd.h>

static bool argument(const char *args,const char *key)
{
    size_t n=strlen(key);
    for(const char *p=args;(p=strstr(p,key));p+=n)
        if((p==args || p[-1]==' ') && (!p[n] || p[n]==' '))return true;
    return false;
}

__attribute__((constructor)) static void start(void)
{
    if(getuid()!=0 || strcmp(getprogname(),"containermanagerd_system"))return;
    char args[1024]={0},version[64]={0};size_t n=sizeof(args),v=sizeof(version);
    if(sysctlbyname("kern.bootargs",args,&n,NULL,0) ||
       sysctlbyname("kern.osversion",version,&v,NULL,0))return;
    args[sizeof(args)-1]=0;version[sizeof(version)-1]=0;
    if(strcmp(version,"22H374") || !argument(args,"diting_gpu_install=1") ||
       !argument(args,"diting_rootful=1"))return;
    char *argv[]={"/private/var/db/diting-gpu-install-v1",NULL};
    char *env[]={"PATH=/usr/bin:/bin:/usr/sbin:/sbin",
        "DYLD_SHARED_CACHE_DIR=/private/preboot/System/Library/Caches/com.apple.dyld/",NULL};
    pid_t child=0;int error=posix_spawn(&child,argv[0],NULL,NULL,argv,env);
    (void)dprintf(2,"Diting GPU installer spawn error=%d pid=%d\n",error,child);
    char text[160];int length=snprintf(text,sizeof(text),
        "Diting GPU installer spawn error=%d pid=%d\n",error,child);
    if(length>0 && (size_t)length<sizeof(text))
        (void)sysctlbyname("kern.diting_diagnostic",NULL,NULL,text,(size_t)length);
}
