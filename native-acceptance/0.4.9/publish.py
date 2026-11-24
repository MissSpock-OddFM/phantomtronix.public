"""Publish exact approved candidate; no signing or client mutation."""
import hashlib,json,pathlib,re,subprocess,tempfile
repo='MissSpock-OddFM/phantomtronix.public'
base=f'repos/{repo}/releases'
here=pathlib.Path(__file__).resolve().parent
artifact=here/'clink-terminal-linux-x64.zip'
feed=here/'update-manifest.json'
pin='5c9ff8c98b4def975d2831f38dfcbc546b57248f0b05833429d14c49f6ce156d'
new='8e7cecf370fd4fcd76e939ec785393d712f1a683c617ef0c02cf715c426f6d27'
old='2d7da0969b561dc91052142e010b41b4944ef304dd6b6e22064106b66971477e'
canonical='update-manifest.json'
backup='update-manifest.previous-0.4.8.json'
staged='update-manifest.next-0.4.9.json'
stable='clink-terminal-stable'
tag='clink-terminal-v0.4.9'
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
    assert artifact.stat().st_size==37857 and sha(artifact)==pin
    assert sha(feed)==new
    game=latest()
    r=lookup('clink-terminal-v0.4.8')
    assert r and not r['draft'] and matches(asset(r,artifact.name),'03eae20ac439047e0aa625a1307782eaf004c757218f92c0ea4969905951ce0c')
    s=lookup(stable)
    assert s and not s['draft'] and not s['prerelease'] and not s.get('immutable')
    cur=asset(s,canonical)
    assert matches(cur,old) or matches(cur,new), 'Unexpected current stable asset; stop'
    assert latest()==game
    r=lookup(tag)
    if r is None:
        gh('release','create',tag,str(artifact),'--repo',repo,'--title','C.Link Terminal 0.4.9','--notes','Signed native version and update visibility.','--draft','--latest=false')
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
    print('PUBLISHED_0.4.9; SIGNED_CATCHUP_PRESERVED; GAME_LATEST',game)
if __name__=='__main__':main()
