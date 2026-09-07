"""Fetch the authors' public CPD benchmark; preserve source byte identity."""
import hashlib
import lzma
from pathlib import Path
import urllib.request
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-ladder/cpd';BASE.mkdir(parents=True,exist_ok=True)
URL='https://web-genobioinfo.toulouse.inrae.fr/~tschiex/CPD/CPD-instances/1BK2.matrix.24p.17aa.usingEref_self_digit8.wcsp.xz'
SHA='d68132d4e2fdea09b7151323677792ce16ba95b746c2f37d306e69452b99632e'
path=BASE/'1BK2.wcsp.xz'
if not path.exists():
    with urllib.request.urlopen(URL,timeout=90) as response:path.write_bytes(response.read())
if hashlib.sha256(path.read_bytes()).hexdigest()!=SHA:raise RuntimeError('Source fingerprint changed')
plain=lzma.decompress(path.read_bytes())
if hashlib.sha256(plain).hexdigest()!='f74ac9ca6c5a8dcf162339972659f83da630d965ecea1e9be2c03a1685eaba27':raise RuntimeError('Decompressed fingerprint changed')
(BASE/'1BK2.wcsp').write_bytes(plain)
print('Verified public 1BK2 CPD model')
