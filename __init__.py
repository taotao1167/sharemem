#!/usr/bin/env python3

import ctypes, struct

IPC_CREAT   = 0o1000
IPC_EXCL    = 0o2000
IPC_NOWAIT  = 0o4000

IPC_RMID    = 0
IPC_SET     = 1
IPC_STAT    = 2
IPC_INFO    = 3

IPC_PRIVATE = 0
"""
struct ipc_perm
  {
    __key_t __key;          /* Key.  */
    __uid_t uid;            /* Owner's user ID.  */
    __gid_t gid;            /* Owner's group ID.  */
    __uid_t cuid;           /* Creator's user ID.  */
    __gid_t cgid;           /* Creator's group ID.  */
    unsigned short int mode;        /* Read/write permission.  */
    unsigned short int __pad1;
    unsigned short int __seq;       /* Sequence number.  */
    unsigned short int __pad2;
    __syscall_ulong_t __glibc_reserved1;
    __syscall_ulong_t __glibc_reserved2;
  };

struct shmid_ds
  {
    struct ipc_perm shm_perm;       /* operation permission struct */
    size_t shm_segsz;           /* size of segment in bytes */
    __time_t shm_atime;         /* time of last shmat() */
#ifndef __x86_64__
    unsigned long int __glibc_reserved1;
#endif
    __time_t shm_dtime;         /* time of last shmdt() */
#ifndef __x86_64__
    unsigned long int __glibc_reserved2;
#endif
    __time_t shm_ctime;         /* time of last change by shmctl() */
#ifndef __x86_64__
    unsigned long int __glibc_reserved3;
#endif
    __pid_t shm_cpid;           /* pid of creator */
    __pid_t shm_lpid;           /* pid of last shmop */
    shmatt_t shm_nattch;        /* number of current attaches */
    __syscall_ulong_t __glibc_reserved4;
    __syscall_ulong_t __glibc_reserved5;
  };
"""
ipc_perm_members = ["__key", "uid", "gid", "cuid", "cgid", "mode", "__pad1", "__seq", "__pad", "__glibc_reserved1", "__glibc_reserved2"]
shmid_ds_members = ipc_perm_members + ["shm_segsz", "shm_atime", "shm_dtime", "shm_ctime", "shm_cpid", "shm_lpid", "shm_nattch", "__glibc_reserved4", "__glibc_reserved5"]
struct_shmid_ds_str = "@5I4H2LL3L2I3L"
STRUCT_SIZE = 112

libpath="/lib/x86_64-linux-gnu/librt.so.1" 
g_rtlib = ctypes.cdll.LoadLibrary(libpath)

memcpy = g_rtlib.memcpy
memcpy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
memcpy.restype = ctypes.c_void_p
memset = g_rtlib.memset
memset.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
memset.restype = ctypes.c_void_p

class SHAREMEM:
    def __init__(self, size, key=".shm", ):
        self.size = size
        self._ftok = g_rtlib.ftok
        self._ftok.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._ftok.restype = ctypes.c_int
        self._shmget = g_rtlib.shmget
        self._shmget.argtypes = [ctypes.c_int, ctypes.c_long, ctypes.c_int]
        self._shmget.restype = ctypes.c_int
        self._shmat = g_rtlib.shmat
        self._shmat.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        self._shmat.restype = ctypes.c_void_p
        self._shmdt = g_rtlib.shmdt
        self._shmdt.argtypes = [ctypes.c_void_p]
        self._shmdt.restype = ctypes.c_int
        self._shmctl = g_rtlib.shmctl
        self._shmctl.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        self._shmctl.restype = ctypes.c_int
        if type(key) == str:
            self.key = self._ftok(key.encode(), 0)
            assert self.key > 0, "ftok failed, execute \"touch %s\" first."%(key)
        else:
            assert type(key) == int, "typeof key must be string or int."
            self.key = key
            assert self.key > 0 and self.key < 2 **32, "negative integer (signed int, 32bit) can't used as key."
        self.shmid = self._shmget(self.key, 0, 0)
        if self.shmid == -1:
            self.iscreater = True
            self.shmid = self._shmget(self.key, size, IPC_CREAT | 0o666)
        else:
            self.iscreater = False
        assert self.shmid != -1, "shmget failed."
        self.mem = None

    def attach(self):
        self.mem = self._shmat(self.shmid, None, 0)
        return self.mem

    def detach(self):
        return self._shmdt(self.mem)

    def stat(self):
        struct_size = struct.calcsize(struct_shmid_ds_str)
        assert struct_size == STRUCT_SIZE, "unexpected struct size"
        con = ctypes.create_string_buffer(struct_size)
        self._shmctl(self.shmid, IPC_STAT, con)
        struct_data = struct.unpack(struct_shmid_ds_str, bytes(con))
        attrs = {"shm_perm":{}}
        for i in range(0, len(struct_data)):
            if i < len(ipc_perm_members):
                m_name = ipc_perm_members[i]
                attrs["shm_perm"][m_name] = struct_data[i]
                # print("attrs[\"shm_perm\"][\"%s\"] = %d"%(m_name, struct_data[i]))
            else:
                m_name = shmid_ds_members[i]
                attrs[m_name] = struct_data[i]
                # print("attrs[\"%s\"] = %d"%(m_name, struct_data[i]))
        return attrs
        
    def memread(self, size=0, offset=0):
        assert not self.mem is None, "attach first."
        if size == 0:
            size == self.size
        con = ctypes.create_string_buffer(size)
        memcpy(con, self.mem + offset, size)
        return bytes(con)

    def remove(self):
        shmem_stat = self.stat()
        if shmem_stat["shm_nattch"] == 0:
            self._shmctl(self.shmid, IPC_RMID, None)
        else:
            print("Other process using. will not remove")
        return 0

if __name__ == "__main__":
    import time
    shmem = SHAREMEM(4096, 0x8827)
    # shmem = SHAREMEM(4096)
    if not shmem.iscreater:
        print("Already created by another process, use it.")
    pubmem = shmem.attach()
    # shmem.memcpy(pubmem + 3, b"123456\x00", 7)
    print(shmem.memread(40, 0))
    time.sleep(5)
    shmem.detach()
    shmem_stat = shmem.stat()
    print(shmem_stat)
    shmem.remove()

