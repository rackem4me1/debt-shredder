"""Atomic JSON persistence with an accidental-corruption checksum.

This is not authentication or encryption. Treat checkpoint files as financial
records. Loading validates the envelope, checksum, and runtime invariants.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
from engine.simulation import DebtCheckpoint

FORMAT='debt-shredder-debt-checkpoint'
MAX_BYTES=64*1024*1024


def _canonical(payload):
    return json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf-8')


def save_debt_checkpoint(checkpoint:DebtCheckpoint,path:str|Path,*,overwrite:bool=False)->Path:
    cp=DebtCheckpoint.model_validate(checkpoint.model_dump())
    payload=cp.model_dump(mode='json')
    envelope={'format':FORMAT,'version':1,'sha256':hashlib.sha256(_canonical(payload)).hexdigest(),'payload':payload}
    encoded=_canonical(envelope)+b'\n'
    if len(encoded)>MAX_BYTES:raise ValueError('checkpoint exceeds 64 MiB file limit')
    target=Path(path)
    temp=None
    try:
        with tempfile.NamedTemporaryFile(mode='wb',dir=target.parent,prefix='.'+target.name+'.',delete=False) as f:
            temp=Path(f.name)
            f.write(encoded);f.flush();os.fsync(f.fileno())
        if overwrite:os.replace(temp,target)
        else:
            # Atomic no-clobber publication; an existing file is never replaced.
            os.link(temp,target)
            temp.unlink()
        temp=None
    finally:
        if temp is not None:temp.unlink(missing_ok=True)
    return target


def _unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate JSON key')
        result[key]=value
    return result


def load_debt_checkpoint(path:str|Path)->DebtCheckpoint:
    with Path(path).open('rb') as f:raw=f.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('checkpoint exceeds 64 MiB file limit')
    data=json.loads(raw,object_pairs_hook=_unique_object)
    if not isinstance(data,dict) or set(data)!={'format','version','sha256','payload'}:
        raise ValueError('invalid checkpoint envelope')
    if data['format']!=FORMAT or type(data['version']) is not int or data['version']!=1:
        raise ValueError('unsupported checkpoint format/version')
    digest=hashlib.sha256(_canonical(data['payload'])).hexdigest()
    if not isinstance(data['sha256'],str) or not hmac.compare_digest(digest,data['sha256']):
        raise ValueError('checkpoint checksum mismatch')
    return DebtCheckpoint.model_validate(data['payload'])
