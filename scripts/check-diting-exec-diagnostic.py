import argparse
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description='在 XNU 源码上验证 spawn 诊断补丁')
parser.add_argument('--xnu-source', type=Path, required=True, help='原始 XNU 源码目录')
args = parser.parse_args()
device = Path(__file__).resolve().parents[1]
source = args.xnu_source / 'bsd/kern/kern_exec.c'
old_patch = device / 'patches/xnu-ipados18/0001-diting-darwin24.patch'
new_patch = device / 'patches/xnu-ipados18/zzzzzzzzz-diting-exec-diagnostic.patch'

stub = r'''
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#define ARM64_BOARD_CONFIG_DITING 1
#define DEVELOPMENT 1
#define DEBUG 0
#define CONFIG_MACF 1
#define XNU_OWNER_DATA_MOUNT 0
#define TUNABLE(type, name, key, initial) type name = initial
#define VATTR_INIT(p) memset((p), 0, sizeof(*(p)))
#define VATTR_WANTED(p, field) ((void)0)
#define MNT_NOSUID 1
#define P_LTRACED 2
#define VSUID S_ISUID
#define VSGID S_ISGID
#define IMGPF_ALLOW_DATA_EXEC 1
#define IMGPF_DISABLE_ASLR 2
#define KAUTH_VNODE_EXECUTE 1
#define KAUTH_VNODE_READ_DATA 2
typedef unsigned long user_size_t;
typedef unsigned kauth_action_t;
struct cred { unsigned uid, gid; };
typedef struct cred *kauth_cred_t;
struct proc { int p_pid; int p_lflag; char p_comm[17]; };
typedef struct proc *proc_t;
struct mount { unsigned mnt_flag; };
struct vnode { struct mount *v_mount; };
struct vnode_attr { unsigned va_uid, va_gid, va_mode; uint64_t va_data_size; };
struct context { proc_t p; kauth_cred_t cred; };
struct image_params { struct vnode *ip_vp; struct vnode_attr *ip_vattr; struct context *ip_vfs_context; uint64_t ip_arch_offset, ip_arch_size; unsigned ip_flags, ip_csflags; int ip_mac_return; };
static struct proc caller = { .p_pid = 22, .p_comm = "xpcproxy" };
static struct cred cred = { 501, 501 };
static struct context context = { &caller, &cred };
static int scenario;
static proc_t current_proc(void) { return &caller; }
static int proc_pid(proc_t p) { return p->p_pid; }
static proc_t vfs_context_proc(struct context *c) { return c->p; }
static kauth_cred_t vfs_context_ucred(struct context *c) { return c->cred; }
static unsigned kauth_cred_getuid(kauth_cred_t c) { return c->uid; }
static unsigned kauth_cred_getgid(kauth_cred_t c) { return c->gid; }
static bool vnode_isreg(struct vnode *v) { (void)v; return scenario != 1; }
static int vnode_getattr(struct vnode *v, struct vnode_attr *a, struct context *c) {
    (void)v; (void)c; if (scenario == 2) return EACCES;
    a->va_mode = scenario == 3 ? 0644 : 0755; a->va_uid = 0; a->va_gid = 0; a->va_data_size = 4096; return 0;
}
static struct mount *vnode_mount(struct vnode *v) { return v->v_mount; }
static bool vfs_authopaque(struct mount *m) { (void)m; return false; }
static int mac_vnode_check_exec(struct context *c, struct vnode *v, struct image_params *i) {
    (void)c; (void)v; (void)i; return scenario == 4 ? EACCES : scenario == 6 ? EPERM : 0;
}
static int vnode_authorize(struct vnode *v, void *n, kauth_action_t a, struct context *c) {
    (void)v; (void)n; (void)a; (void)c; return scenario == 5 ? EACCES : scenario == 7 ? EIO : 0;
}
'''


def section(text, start, end):
    left = text.index(start)
    right = text.index(end, left)
    return text[left:right]


def build_and_run(compiler, directory, name, code, diagnostic):
    c = directory / (name + '.c')
    exe = directory / name
    c.write_text(code)
    subprocess.run([compiler, '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-variable', '-Wno-unused-function', str(c), '-o', str(exe)], check=True)
    return subprocess.check_output([str(exe), str(diagnostic)], text=True)


with tempfile.TemporaryDirectory(prefix='diting-exec-test-') as temporary:
    tmp = Path(temporary)
    path = tmp / 'bsd/kern/kern_exec.c'
    path.parent.mkdir(parents=True)
    path.write_bytes(source.read_bytes())
    subprocess.run(['git', 'apply', '--include=bsd/kern/kern_exec.c', str(old_patch)],
                   cwd=tmp, check=True, capture_output=True)
    baseline = path.read_text()
    subprocess.run(['git', 'apply', '--check', str(new_patch)], cwd=tmp, check=True)
    subprocess.run(['git', 'apply', str(new_patch)], cwd=tmp, check=True)
    modified = path.read_text()
    helper = section(modified, '#if defined(ARM64_BOARD_CONFIG_DITING) && (DEVELOPMENT || DEBUG)\n/* 仅记录',
                     'static void exec_prefault_data')
    start = 'static int\nexec_check_permissions(struct image_params *imgp)\n{'
    end = '\n\n\n/*\n * exec_handle_sugid'
    old_function = section(baseline, start, end)
    new_function = section(modified, start, end)
    main = r'''
int main(int argc, char **argv) {
    if (argc > 2) strcpy(caller.p_comm, "other");
#ifdef WITH_DIAG
    diting_exec_diag = (unsigned)(argv[1][0] == '1');
#else
    (void)argv;
#endif
    struct mount mount = {0}; struct vnode node = {&mount}; struct vnode_attr attr;
    struct image_params img = { .ip_vp = &node, .ip_vattr = &attr, .ip_vfs_context = &context };
    for (scenario = 0; scenario < 8; scenario++) {
        printf("RESULT %d %d\n", scenario, exec_check_permissions(&img));
    }
    return 0;
}
'''
    old = build_and_run('clang', tmp, 'baseline', stub + old_function + main, 0)
    off = build_and_run('clang', tmp, 'disabled', stub + '#define WITH_DIAG 1\n' + helper + new_function + main, 0)
    on = build_and_run('clang', tmp, 'enabled', stub + '#define WITH_DIAG 1\n' + helper + new_function + main, 1)
    unrelated = subprocess.check_output([str(tmp/'enabled'), '1', 'other'], text=True)
    rows = lambda output: [line for line in output.splitlines() if line.startswith('RESULT ')]
    assert rows(old) == rows(off) == rows(on), (old, off, on)
    assert 'DITING EXEC' not in off
    assert 'DITING EXEC' not in unrelated and rows(unrelated) == rows(old)
    for stage in ('nonregular', 'getattr', 'mode', 'mac-vnode', 'vnode-authorize'):
        assert 'stage=' + stage in on, stage
    print('patched XNU source applies; permission outcomes unchanged with diagnostics off/on')

    applog = section(modified, 'static const char *\nexec_applog_path(int fd, const char *path, int oflag)', '\n#endif')
    call_start = '\t\t\terror = open1(imgp->ip_vfs_context, ndp,\n'
    open_block = section(modified, call_start, '\n\t\t\tkfree_type(typeof(*__open_data), __open_data);')
    open_stubs = r'''
static uint32_t exec_applog = 1;
struct openargs { int psfao_oflag; const char *psfao_path; };
struct action { int psfaa_filedes; struct openargs psfaa_openargs; };
static int open1(struct context *c, void *n, int f, void *v, void *a, void *b, int *o, int flags) {
    (void)c;(void)n;(void)f;(void)v;(void)a;(void)b;(void)o;(void)flags; return EACCES;
}
#define AUTH_OPEN_NOAUTHFD 0
'''
    open_main = r'''
int main(void) {
    struct image_params img = { .ip_vfs_context = &context }, *imgp = &img;
    struct action item = {2, {2, "/dev/null"}}, *psfa = &item;
    kauth_cred_t p_cred = &cred; void *ndp = NULL, *vap = NULL; int origfd = 0, error;
    diting_exec_diag = 1;
    if (strcmp(exec_applog_path(2, "/dev/null", O_RDWR), "/dev/null") != 0 ||
        strcmp(exec_applog_path(2, "/dev/null", O_WRONLY), "/dev/console") != 0 ||
        strcmp(exec_applog_path(0, "/dev/null", O_WRONLY), "/dev/null") != 0) return 1;
    exec_applog = 0;
    if (strcmp(exec_applog_path(2, "/dev/null", O_WRONLY), "/dev/null") != 0) return 1;
    exec_applog = 1;
'''+open_block+r'''
    printf("RESULT %d\n", error);
    return 0;
}
'''
    c = tmp/'open.c'; exe=tmp/'open'; c.write_text(stub + helper + open_stubs + applog + open_main)
    subprocess.run(['clang','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-variable',
                    '-Wno-unused-function',str(c),'-o',str(exe)],check=True)
    result = subprocess.check_output([str(exe)],text=True)
    assert 'from=/dev/null to=/dev/null' in result and 'RESULT 13' in result, result
    print('applog preserves O_RDWR; write-only redirection and diagnostic error remain intact')

    spawn_at = modified.index('bad:\n#if defined(ARM64_BOARD_CONFIG_DITING)', modified.index('posix_spawn(proc_t ap,'))
    spawn_end = modified.index('\n\tif (error == 0) {\n\t\t/* reset delay idle sleep status if set */', spawn_at)
    spawn_block = modified[spawn_at + len('bad:\n'):spawn_end]
    spawn_stubs = r'''
typedef const char *user_addr_t;
struct posix_spawn_args { user_addr_t path; };
static kauth_cred_t kauth_cred_get(void) { return &cred; }
static int copyinstr(user_addr_t input, char *out, size_t n, size_t *copied) {
    size_t len = strlen(input) + 1; if (len > n) return 1; memcpy(out, input, len); *copied = len; return 0;
}
static size_t test_strlcpy(char *out, const char *input, size_t n) {
    size_t len = strlen(input); if (n) { size_t take = len < n - 1 ? len : n - 1; memcpy(out, input, take); out[take] = 0; } return len;
}
#define strlcpy test_strlcpy
volatile int native_owner_data_status = 0, native_owner_data_stage = 4, native_owner_data_readonly = 0;
'''
    spawn_main = r'''
int main(void) {
    int error = EACCES; const char *diting_spawn_phase = "file-actions";
    struct posix_spawn_args args = {"/usr/libexec/timed"}, *uap = &args;
    diting_exec_diag = 1;
'''+spawn_block+r'''
    printf("RESULT %d\n", error); return 0;
}
'''
    c = tmp/'spawn.c'; exe=tmp/'spawn'
    c.write_text(stub + '#undef XNU_OWNER_DATA_MOUNT\n#define XNU_OWNER_DATA_MOUNT 1\n' +
                 helper + spawn_stubs + spawn_main)
    subprocess.run(['clang','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-variable',
                    '-Wno-unused-function',str(c),'-o',str(exe)],check=True)
    result = subprocess.check_output([str(exe)],text=True)
    assert 'phase=file-actions' in result and 'path=/usr/libexec/timed' in result, result
    assert 'data status=0 stage=4 readonly=0' in result and 'RESULT 13' in result, result
    print('spawn diagnostic preserves error and reports target, phase and Data status')

    signature = section(modified, '\tos_reason_t launch_constraint_reason;\n',
                        '\n\t/*\n\t * Reject when there\'s subsystem root path set')
    signature_stubs = r'''
typedef int os_reason_t;
static int mac_proc_check_launch_constraints(proc_t p, struct image_params *i, os_reason_t *reason) {
    (void)p; (void)i; *reason = 7; return scenario;
}
'''
    signature_main = r'''
int main(void) {
    struct image_params image = {.ip_csflags = 0x1234}, *imgp = &image; proc_t p = &caller;
    os_reason_t signature_failure_reason = 0; int error = 0; scenario = EACCES; diting_exec_diag = 1;
    strcpy(caller.p_comm, "timed");
'''+signature+r'''
done:
    printf("RESULT %d reason=%d\n", error, signature_failure_reason); return 0;
}
'''
    c = tmp/'signature.c'; exe=tmp/'signature'; c.write_text(stub + helper + signature_stubs + signature_main)
    subprocess.run(['clang','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-variable',
                    '-Wno-unused-function',str(c),'-o',str(exe)],check=True)
    result = subprocess.check_output([str(exe)],text=True)
    assert 'stage=launch-constraints err=13' in result and 'RESULT 13 reason=7' in result, result
    print('launch-constraint diagnostic preserves the error and failure reason')
