"""Convert only fully understood component-free iOS entity records.
The serializer order is corroborated by both executables and original-engine
read traces. Component-bearing records and non-unit scale remain unsupported.
"""
import struct

def convert(body):
 if len(body)<22 or body[:5]!=b'\0'*5:raise ValueError('component-bearing or flagged entity unsupported')
 q=struct.unpack_from('<I',body,17)[0]
 end=22 if q==0x40000000 else 33
 if len(body)!=end+25:raise ValueError('unexpected component-free entity length')
 scale=struct.unpack_from('<3i',body,end)
 if scale!=(4096,4096,4096):raise ValueError('non-unit entity scale requires explicit baking')
 if body[-4:]!=b'\0'*4:raise ValueError('nonempty additional entity data unsupported')
 result=body[:end]+body[end+12:-4]
 expected=31 if q==0x40000000 else 42
 if len(result)!=expected:raise ValueError('unexpected converted length')
 return result

def fields(body):
 if body[:5]!=b'\0'*5:raise ValueError('unsupported original entity')
 end=22 if struct.unpack_from('<I',body,17)[0]==0x40000000 else 33
 if len(body)!=end+9:raise ValueError('unexpected original length')
 return {'position':struct.unpack_from('<3i',body,5),'quaternion':body[17:end].hex(),
         'identifiers':body[end:end+8].hex(),'flags':body[-1]}
