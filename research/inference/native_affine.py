"""Typed boundary for the optional project-built native affine kernel."""
import ctypes
from pathlib import Path
import numpy as np


class NativeSketch:
    def __init__(self,portable):
        dll=Path(__file__).resolve().parents[2]/'tmp/native-verifier/affine_check.dll'
        library=ctypes.CDLL(str(dll));self._library=library
        self.check=library.pouw_affine4
        self.check.argtypes=[np.ctypeslib.ndpointer(np.int64,flags='C_CONTIGUOUS'),np.ctypeslib.ndpointer(np.int32,flags='C_CONTIGUOUS'),np.ctypeslib.ndpointer(np.uint32,flags='C_CONTIGUOUS'),np.ctypeslib.ndpointer(np.uint32,flags='C_CONTIGUOUS'),np.ctypeslib.ndpointer(np.uint32,flags='C_CONTIGUOUS'),np.ctypeslib.ndpointer(np.int64,flags='C_CONTIGUOUS'),ctypes.c_size_t,ctypes.c_size_t]
        self.check.restype=ctypes.c_int
        self.post_check=library.pouw_post
        self.post_check.argtypes=[np.ctypeslib.ndpointer(np.int32,flags='C_CONTIGUOUS'),np.ctypeslib.ndpointer(np.int64,flags='C_CONTIGUOUS'),np.ctypeslib.ndpointer(np.int64,flags='C_CONTIGUOUS'),ctypes.c_size_t,ctypes.c_size_t,ctypes.c_size_t,ctypes.c_int]
        self.post_check.restype=None
        if portable.r.full.shape[0]!=4:raise ValueError('Native kernel requires four checks')
        self.op=portable.op
        self.r=np.ascontiguousarray(portable.r.full.T,dtype=np.uint32)
        self.s=np.ascontiguousarray(portable.s.full.T,dtype=np.uint32)
        self.rb=np.ascontiguousarray(portable.rb,dtype=np.uint32)
        self.bounds=np.ascontiguousarray(portable.bounds,dtype=np.int64).ravel()
        for value in [self.r,self.s,self.rb,self.bounds]:value.flags.writeable=False

    def verify(self,x,z):
        x,z=np.asarray(x),np.asarray(z)
        if x.shape!=self.op.input_shape or z.shape!=self.op.output_shape:return False
        if x.dtype.kind not in 'iu' or z.dtype.kind not in 'iu':return False
        # Reject before narrowing; no modulus/overflow aliases in the C ABI.
        if x.dtype==np.uint64 and np.any(x>2**63-1):return False
        if np.any(z < -(2**31)) or np.any(z > 2**31-1):return False
        a=np.ascontiguousarray(x,dtype=np.int64).ravel();b=np.ascontiguousarray(z,dtype=np.int32).ravel()
        return bool(self.check(a,b,self.s,self.r,self.rb,self.bounds,len(a),len(b)))

    def post(self,z):
        op=self.op
        if op.multiplier is None:return z*op.final_scale
        # Called only after a successful bound check or trusted recomputation.
        if z.dtype.kind not in 'iu' or z.shape!=op.output_shape or np.any(z < -self.bounds.reshape(z.shape)) or np.any(z > self.bounds.reshape(z.shape)):
            raise ValueError('Unverified post-operation input')
        channels,h,w=op.output_shape if op.conv else (op.output_shape[0],1,1)
        output_shape=(channels,h//2,w//2) if op.pool else op.output_shape
        result=np.empty(output_shape,dtype=np.int64)
        self.post_check(np.ascontiguousarray(z,dtype=np.int32),np.ascontiguousarray(op.multiplier,dtype=np.int64),result,channels,h,w,int(op.pool))
        return result
