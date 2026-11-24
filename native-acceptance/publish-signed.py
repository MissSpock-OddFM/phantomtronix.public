"""Publish exact approved candidate; no signing or client mutation."""
import base64,hashlib,json,pathlib,re,subprocess,tempfile,sys
repo='MissSpock-OddFM/phantomtronix.public'
base=f'repos/{repo}/releases'
version=sys.argv[1]
assert re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',version)
here=pathlib.Path(__file__).resolve().parent/version
plan=json.loads((here/'release-plan.json').read_bytes())
previous=plan['fromVersion']
assert plan['version']==version and re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',previous)
assert tuple(map(int,version.split('.')))>tuple(map(int,previous.split('.')))
artifact=here/'clink-terminal-linux-x64.zip'
feed=here/'update-manifest.json'
pin=plan['archiveSha256']
new=plan['feedSha256']
old=plan['previousFeedSha256']
canonical='update-manifest.json'
backup='update-manifest.previous-'+previous+'.json'
staged='update-manifest.next-'+version+'.json'
stable='clink-terminal-stable'
tag='clink-terminal-v'+version
public_pem=b'-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEAvF0wDh1QSp6CRjo53xB+jXC3yrA7E0D+nZlQVF976Xo=\n-----END PUBLIC KEY-----\n'
def signed_chain():
    data=json.loads(feed.read_bytes())
    assert set(data)=={'schema','releases'} and data['schema']=='clink.native-discovery.v1'
    offers=data['releases']
    assert 2<=len(offers)<=64
    with tempfile.TemporaryDirectory() as tmp:
        p=pathlib.Path(tmp)
        (p/'key').write_bytes(public_pem)
        for i,e in enumerate(offers):
            assert set(e)=={'schema','release','signature'} and e['schema']=='clink.native-update.v1'
            r=e['release']
            assert set(r)=={'productId','channel','publisher','repository','fromVersion','version','platform','arch','prerelease','artifactUrl','sha256','size'}
            assert all(r[k]==v for k,v in dict(productId='clink-terminal',channel='stable',publisher='PhantomTronix',repository=repo,platform='linux',arch='x64',prerelease=False).items())
            assert all(re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',r[k]) for k in ('fromVersion','version'))
            assert tuple(map(int,r['version'].split('.')))>tuple(map(int,r['fromVersion'].split('.')))
            assert r['artifactUrl']==f"https://github.com/{repo}/releases/download/clink-terminal-v{r['version']}/{artifact.name}"
            assert re.fullmatch(r'[0-9a-f]{64}',r['sha256']) and 0<r['size']<=8*1024*1024
            if i:assert offers[i-1]['release']['version']==r['fromVersion']
            (p/'payload').write_bytes(json.dumps(r,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
            (p/'sig').write_bytes(base64.b64decode(e['signature'],validate=True))
            subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(p/'key'),'-rawin','-in',str(p/'payload'),'-sigfile',str(p/'sig')],check=True,capture_output=True,timeout=10)
    assert offers[-1]['release']['version']==version and offers[-1]['release']['fromVersion']==previous
    assert offers[-1]['release']['sha256']==pin and offers[-1]['release']['size']==artifact.stat().st_size
    assert offers[-2]['release']['sha256']==plan['previousArchiveSha256']
    prior=(json.dumps({'schema':data['schema'],'releases':offers[:-1]},separators=(',',':'),ensure_ascii=False)+'\n').encode()
    assert hashlib.sha256(prior).hexdigest()==old
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def gh(*args):
    r=subprocess.run(['gh',*args],capture_output=True,text=True,timeout=90)
    if r.returncode:raise RuntimeError('GitHub operation failed: '+r.stderr[:300])
    return r.stdout
def get(path):return json.loads(gh('api',path))
def lookup(t):
    pages=json.loads(gh('api','--paginate','--slurp',base+'?per_page=100'))
    rows=[r for page in pages for r in page if r['tag_name']==t]
    assert len(rows)<=1
    return rows[0] if rows else None
def asset(r,name):
    rows=[a for a in r['assets'] if a['name']==name]
    assert len(rows)<=1
    return rows[0] if rows else None
def matches(a,d):return a is not None and a['state']=='uploaded' and a['digest']=='sha256:'+d
def readback(t,name,d):
    with tempfile.TemporaryDirectory() as tmp:
        gh('release','download',t,'--repo',repo,'--pattern',name,'--dir',tmp)
        assert sha(pathlib.Path(tmp)/name)==d
def latest():
    r=get(base+'/latest')
    assert re.fullmatch(r'v\d+\.\d+\.\d+',r['tag_name'])
    assert asset(r,'conveyor-club.zip')
    return r['tag_name']
def rename(a,name):
    gh('api','-X','PATCH',base+'/assets/'+str(a['id']),'-f','name='+name)
def main():
    assert artifact.stat().st_size==plan['archiveSize'] and sha(artifact)==pin
    assert sha(feed)==new
    signed_chain()
    game=latest()
    r=lookup('clink-terminal-v'+previous)
    assert r and not r['draft'] and matches(asset(r,artifact.name),plan['previousArchiveSha256'])
    s=lookup(stable)
    assert s and not s['draft'] and not s['prerelease'] and not s.get('immutable')
    cur=asset(s,canonical)
    assert matches(cur,old) or matches(cur,new), 'Unexpected current stable asset; stop'
    assert latest()==game
    r=lookup(tag)
    if r is None:
        gh('release','create',tag,str(artifact),'--repo',repo,'--title','C.Link Terminal '+version,'--notes','Signed native release.','--draft','--latest=false')
        r=lookup(tag)
    assert r and not r['prerelease'] and len(r['assets'])==1 and matches(asset(r,artifact.name),pin)
    readback(tag,artifact.name,pin)
    if r['draft']:
        gh('api','-X','PATCH',base+'/'+str(r['id']),'-F','draft=false','-f','make_latest=false')
    r=lookup(tag)
    assert r and not r['draft'] and matches(asset(r,artifact.name),pin)
    readback(tag,artifact.name,pin)
    assert latest()==game
    s=lookup(stable);cur=asset(s,canonical)
    if matches(cur,new):
        readback(stable,canonical,new)
        print('ALREADY_PUBLISHED',game);return
    assert matches(cur,old) and asset(s,backup) is None
    readback(stable,canonical,old)
    pending=asset(s,staged)
    if pending is None:
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)/staged;p.write_bytes(feed.read_bytes())
            gh('release','upload',stable,str(p),'--repo',repo)
        s=lookup(stable);pending=asset(s,staged)
    assert matches(pending,new)
    readback(stable,staged,new)
    s=lookup(stable);cur=asset(s,canonical);pending=asset(s,staged)
    assert matches(cur,old) and matches(pending,new) and asset(s,backup) is None
    try:
        rename(cur,backup)
        rename(pending,canonical)
    except Exception:
        s=lookup(stable)
        if asset(s,canonical) is None and matches(asset(s,backup),old):
            rename(asset(s,backup),canonical)
        raise
    s=lookup(stable)
    assert matches(asset(s,canonical),new) and matches(asset(s,backup),old)
    readback(stable,canonical,new)
    assert latest()==game
    print('PUBLISHED_'+version+'; SIGNED_CATCHUP_PRESERVED; GAME_LATEST',game)
if __name__=='__main__':main()
