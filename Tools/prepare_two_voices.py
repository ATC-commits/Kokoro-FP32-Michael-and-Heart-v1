"""Keep only Michael and Heart in a sherpa Kokoro v1.0 FP32 package.
Uses the ONNX ModelProto metadata fields without modifying its graph/weights.
"""
from pathlib import Path
import hashlib,json,shutil,sys

def varint(data, offset):
    result=shift=0
    while True:
        b=data[offset];offset+=1;result|=(b&127)<<shift
        if b<128:return result,offset
        shift+=7
        if shift>63:raise ValueError('Invalid protobuf varint')

def encode(value):
    out=bytearray()
    while value>127:out.append((value&127)|128);value>>=7
    out.append(value);return bytes(out)

def field(number,value):return encode(number*8+2)+encode(len(value))+value

def fields(data):
    offset=0
    while offset<len(data):
        start=offset;tag,offset=varint(data,offset);wire=tag&7
        if wire==2:
            size,offset=varint(data,offset);payload=data[offset:offset+size];offset+=size
        elif wire==0:
            begin=offset;_,offset=varint(data,offset);payload=data[begin:offset]
        elif wire in (1,5):
            size=8 if wire==1 else 4;payload=data[offset:offset+size];offset+=size
        else:raise ValueError('Unsupported protobuf wire type')
        if offset>len(data):raise ValueError('Truncated protobuf')
        yield tag>>3,wire,payload,data[start:offset]

def metadata(data):
    result={}
    for number,wire,payload,_ in fields(data):
        if number==14 and wire==2:
            item={n:p.decode() for n,w,p,r in fields(payload)};result[item[1]]=item[2]
    return result

def prepare(source,target):
    data=(source/'model.onnx').read_bytes();meta=metadata(data)
    print('Original speaker metadata:',{k:v for k,v in meta.items() if 'speak' in k})
    voices=(source/'voices.bin').read_bytes();stride=510*256*4
    assert len(voices)%stride==0
    names=meta.get('speaker_names','').replace(' ','').split(',')
    assert names[16]=='am_michael' and names[3]=='af_heart',names
    replacements={'n_speakers':'2','speaker_names':'am_michael,af_heart',
                  'id2speaker':'0->am_michael,1->af_heart',
                  'speaker2id':'am_michael->0,af_heart->1'}
    output=bytearray()
    for number,wire,payload,raw in fields(data):
        if number==14 and wire==2:
            item={n:p.decode() for n,w,p,r in fields(payload)}
            if item[1] in replacements:
                raw=field(14,field(1,item[1].encode())+field(2,replacements[item[1]].encode()))
        output.extend(raw)
    target.mkdir(parents=True,exist_ok=True)
    # Retain packaged pronunciation resources and all upstream license notices.
    for p in source.iterdir():
        if p.name in ['model.onnx','voices.bin','download-receipt.json']:continue
        if p.is_dir():shutil.copytree(p,target/p.name,dirs_exist_ok=True)
        else:shutil.copy2(p,target/p.name)
    (target/'model.onnx').write_bytes(output)
    (target/'voices.bin').write_bytes(voices[16*stride:17*stride]+voices[3*stride:4*stride])
    assert metadata(output)['n_speakers']=='2'
    receipt={'source_archive_sha256':'c5f7e2d2caf082bc1d20fb70334a61d99d20b484500aad32e7cf84c128ea3298',
             'modifications':'Metadata n_speakers/speaker_names/id2speaker/speaker2id remapped; speaker embeddings restricted to Michael and Heart. Graph/weights unchanged.',
             'voices':{'0':'am_michael','1':'af_heart'},'model_sha256':hashlib.sha256(output).hexdigest(),
             'voices_sha256':hashlib.sha256((target/'voices.bin').read_bytes()).hexdigest()}
    (target/'GTL-MODIFICATIONS.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('Prepared:',target)

if __name__=='__main__':prepare(Path(sys.argv[1]),Path(sys.argv[2]))
