#!/usr/bin/env python3
"""Prepare verified Kokoro FP32 resources on the build Mac, never on the iPad."""
import argparse, hashlib, json, os, shutil, subprocess, tarfile, tempfile, urllib.request
from pathlib import Path
from prepare_two_voices import prepare

ARCHIVE='kokoro-multi-lang-v1_0.tar.bz2'
URL='https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/'+ARCHIVE
SHA256='c5f7e2d2caf082bc1d20fb70334a61d99d20b484500aad32e7cf84c128ea3298'
VERSION='fp32-michael-heart-v1'
MODEL_SHA256='75a02b80d4970be48fa5803edbcca7f129850225f7bceec544680e91e53d2b12'
VOICES_SHA256='dbdf2ce77d0de7606d68200a7224b0017f55d9e4aaf295cbd9cbcd0c5bb2b4a0'
ROOT=Path(__file__).resolve().parents[1]
REPOSITORY='ATC-commits/StepByStepEnglish.Student-APP'
RELEASE_TAG='kokoro-fp32-michael-heart-v1'
RELEASE_ASSET=RELEASE_TAG+'.tar.gz'
RELEASE_SHA256='aaea5c1a1385878866e70b09fc50e47959e8186ef7f96f4717dcef076b50a4a0'

def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for data in iter(lambda:stream.read(1024*1024),b''):h.update(data)
 return h.hexdigest()

def extract(archive,target):
 with tarfile.open(archive,'r:*') as stream:
  members=stream.getmembers()
  for member in members:
   dest=(target/member.name).resolve()
   if not str(dest).startswith(str(target.resolve())+os.sep) or not (member.isdir() or member.isfile()):
    raise ValueError('Unsafe model archive entry: '+member.name)
  stream.extractall(target,members=members)

def ensure(cache):
 cache.mkdir(parents=True,exist_ok=True)
 prepared=cache/VERSION
 marker=prepared/'GTL-MODIFICATIONS.json'
 if marker.is_file():
  try:
   validate(prepared)
   return prepared
  except (ValueError, OSError, KeyError):
   pass  # Rebuild an interrupted or damaged cache from the verified archive.
 archive=cache/ARCHIVE
 if not archive.is_file() or digest(archive)!=SHA256:
  print('Downloading Kokoro FP32 on the Mac (one-time, about 350 MB)…',flush=True)
  partial=cache/(ARCHIVE+'.partial')
  try:
   with urllib.request.urlopen(URL,timeout=120) as source,partial.open('wb') as output:
    shutil.copyfileobj(source,output,1024*1024)
   if digest(partial)!=SHA256:raise ValueError('Kokoro archive checksum mismatch')
   partial.replace(archive)
  finally:
   if partial.exists():partial.unlink()
 with tempfile.TemporaryDirectory(dir=str(cache),prefix='extract-') as work:
  work=Path(work);extract(archive,work)
  source=work/'kokoro-multi-lang-v1_0'
  target=work/'two-voices';prepare(source,target)
  shutil.copytree(ROOT/'Notices/Kokoro',target/'Dependency-Notices')
  if prepared.exists():shutil.rmtree(prepared)
  shutil.move(str(target),str(prepared))
 return prepared

def ensure_release(cache, local_archive=None):
 cache.mkdir(parents=True,exist_ok=True)
 prepared=cache/VERSION
 try:
  validate(prepared)
  return prepared
 except (ValueError,OSError,KeyError):pass
 archive=local_archive or cache/RELEASE_ASSET
 if not archive.is_file() or digest(archive)!=RELEASE_SHA256:
  if local_archive:raise ValueError('The local release archive is missing or has the wrong checksum')
  gh=shutil.which('gh')
  if not gh:
   gh=next((str(p) for p in [Path('/opt/homebrew/bin/gh'),Path('/usr/local/bin/gh')] if p.is_file()),None)
  if not gh:
   raise ValueError('This private repository requires GitHub authentication. Install GitHub CLI and run "gh auth login" on the Mac, or download '+RELEASE_ASSET+' from the repository Releases page and place it in the project Resources folder.')
  print('Downloading the prepared Michael/Heart FP32 Release asset…',flush=True)
  with tempfile.TemporaryDirectory(dir=str(cache),prefix='download-') as download:
   result=subprocess.run([gh,'release','download',RELEASE_TAG,'--repo',REPOSITORY,'--pattern',RELEASE_ASSET,'--dir',download],check=False)
   if result.returncode:raise ValueError('Release download failed. Check "gh auth login", repository access and that the Kokoro release has been published.')
   downloaded=Path(download)/RELEASE_ASSET
   if digest(downloaded)!=RELEASE_SHA256:raise ValueError('Release archive checksum mismatch')
   downloaded.replace(archive)
 with tempfile.TemporaryDirectory(dir=str(cache),prefix='release-') as work:
  work=Path(work);extract(archive,work)
  source=work/'FreeReadingKokoro';validate(source)
  if prepared.exists():shutil.rmtree(prepared)
  shutil.move(str(source),str(prepared))
 return prepared

def validate(prepared):
 receipt=json.loads((prepared/'GTL-MODIFICATIONS.json').read_text())
 if receipt['source_archive_sha256']!=SHA256 or receipt['voices']!={'0':'am_michael','1':'af_heart'}:
  raise ValueError('Unexpected model provenance or voices')
 for name,expected in [('model.onnx',MODEL_SHA256),('voices.bin',VOICES_SHA256)]:
  if digest(prepared/name)!=expected:raise ValueError('Invalid '+name+' checksum')
 for name in ['tokens.txt','lexicon-us-en.txt','LICENSE','espeak-ng-data/phontab','espeak-ng-data/phondata','espeak-ng-data/phonindex']:
  if not (prepared/name).is_file():raise ValueError('Missing Kokoro dependency: '+name)

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--cache',required=True,type=Path)
 parser.add_argument('--output',required=True,type=Path)
 parser.add_argument('--release-archive',type=Path,help='Use a manually downloaded Release asset')
 parser.add_argument('--source-pack',type=Path,help='Use an already prepared two-voice pack (offline build/testing)')
 args=parser.parse_args()
 local=args.release_archive
 if local is None and (ROOT/'Resources'/RELEASE_ASSET).is_file():local=ROOT/'Resources'/RELEASE_ASSET
 prepared=args.source_pack if args.source_pack else ensure_release(args.cache,local)
 validate(prepared)
 if args.output.resolve()==prepared.resolve():raise ValueError('Output must differ from cached resources')
 # Copy into the built app after Copy Bundle Resources, before Xcode code signing.
 args.output.parent.mkdir(parents=True,exist_ok=True)
 if args.output.exists():shutil.rmtree(args.output)
 shutil.copytree(prepared,args.output)
 (args.output/'.gtl-kokoro-ready').write_text(VERSION+'\n')
 print('Kokoro FP32 Michael/Heart bundled for offline narration.',flush=True)

if __name__=='__main__':
 try:main()
 except Exception as error:raise SystemExit('error: Kokoro resources could not be prepared: '+str(error))
