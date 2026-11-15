const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const OWNER = '11111111-1111-4111-8111-111111111111', SID = '22222222-2222-4222-8222-222222222222';
const VIDEO = '33333333-3333-4333-8333-333333333333', OTHER = '44444444-4444-4444-8444-444444444444';
const KEY = OWNER + ':' + SID, BACKEND = 'https://api.usepeso.com', GRANT = Buffer.alloc(32, 9).toString('base64url');
const CACHE = 'private, no-store', ASSETS = ['export:barbell','export:clean','export:pose','export:pose-barbell','playback','thumbnail'];
const tick = () => new Promise(setImmediate);
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }
function load(relative, imports = {}, globals = {}) {
  const compiled = ts.transpileModule(fs.readFileSync(path.join(__dirname, '..', relative), 'utf8'), {
    fileName: relative, reportDiagnostics: true, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }); assert.deepEqual(compiled.diagnostics.map(d => ({ code: d.code, message: ts.flattenDiagnosticMessageText(d.messageText, '\n') })), []);
  const module = { exports: {} };
  new Function('require','module','exports',...Object.keys(globals),compiled.outputText)(name => {
    assert.ok(Object.hasOwn(imports,name),name); return imports[name];
  },module,module.exports,...Object.values(globals)); return module.exports;
}
// Marker/framing fixtures are not a claim of decoder conformance. A separately
// generated real FFmpeg JPEG is checked with this same module as build evidence.
function jpeg({ width = 720, height = 720, entropy = [1,2,3], frame = 0xc0 } = {}) {
  return new Uint8Array([255,216,255,frame,0,11,8,height >> 8,height & 255,width >> 8,width & 255,1,1,0x11,0,
    255,218,0,8,1,1,0,0,63,0,...entropy,255,217]);
}
const bytesModule = load('lib/thumbnailBytes.ts');
function imageResponse(bytes = jpeg(), { headers = {}, status = 200 } = {}) {
  return new Response(bytes,{ status,headers:{ 'Content-Type':'image/jpeg','Content-Length':String(bytes.length),'Cache-Control':CACHE,...headers } });
}
function fixture({ browser = false, fetcher, fakeTimers = false } = {}) {
  let epoch=0,active=KEY,backend=BACKEND;
  const releases = new Set(), calls = [], timers = [];
  const root = BACKEND+'/private-media/'+(browser?'session/'+SID+'/':'')+'video/'+VIDEO+'/';
  const globals = { process:{env:{EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED:'true'}},
    setTimeout: fakeTimers ? fn => { timers.push(fn);return timers.length; } : setTimeout,
    clearTimeout: fakeTimers ? () => {} : clearTimeout };
  const lifecycle = {getPrivateMediaEpoch:()=>epoch,getActivePrivateMediaSessionKey:()=>active,
    registerPrivateMediaRelease(fn){releases.add(fn);return()=>releases.delete(fn);}};
  const issueValue = changes => ({resource_kind:'video',resource_id:VIDEO,
    urls:Object.fromEntries((browser?ASSETS:['thumbnail']).map(asset=>[asset,root+encodeURIComponent(asset)])),
    expires_in:120,expires_at:new Date(Date.now()+120000).toISOString(),...(!browser?{media_grant:GRANT}:{}),...changes});
  const issueResponse = changes => Response.json(issueValue(changes),{headers:{'Cache-Control':CACHE}});
  const request = async (url,init) => {calls.push([url,init]); return fetcher ? fetcher(url,init,{issueResponse,issueValue,imageResponse}) : init.method==='POST'?issueResponse():imageResponse();};
  const common = {'expo/fetch':{fetch:request},'react-native':{Platform:{OS:browser?'web':'ios'}},
    './backendConfig':{getBackendApiUrl:()=>backend},'./privateMediaLifecycle':lifecycle};
  const issuer = load('lib/privateVideoPlayback.ts',{...common,
    './backendUrlPolicy':require('../lib/backendUrlPolicy'),'./profilePolicy':require('../lib/profilePolicy'),
    './privateMediaLogout':{getPrivateMediaSessionKey:token=>token==='original-token'?KEY:null},
    './supabase':{supabaseAuthUrl:'https://auth-fixture.invalid/auth/v1'}},globals);
  const reader = load('lib/privateVideoThumbnail.ts',{...common,'./privateVideoPlayback':issuer,'./thumbnailBytes':bytesModule},globals);
  return {reader,calls,timers,root,issueResponse,
    read:signal=>reader.readPrivateVideoThumbnail(VIDEO,'original-token',signal),
    release(){epoch++;for(const fn of [...releases])fn();}, changeSession(){active=OWNER+':'+OTHER;},changeBackend(){backend='https://other.usepeso.com';}};
}

test('thumbnail framing enforces baseline format, bounded dimensions, one scan and exact end before encoding',()=>{
  for(const size of [1,16,720]) {
    const bytes=jpeg({width:size,height:size,entropy:[1,255,0,2,255,208,3]});
    assert.equal(bytesModule.thumbnailDataUri(bytes),'data:image/jpeg;base64,'+Buffer.from(bytes).toString('base64'));
  }
  for(const bytes of [new Uint8Array([255,216,255,217]),new Uint8Array([137,80,78,71]),new TextEncoder().encode('<svg/>'),
    jpeg({width:0}),jpeg({height:0}),jpeg({width:721}),jpeg({height:721}),jpeg({frame:0xc2}),jpeg({frame:0xc1}),
    new Uint8Array([...jpeg(),0]),jpeg().subarray(0,jpeg().length-1),
    new Uint8Array([...jpeg().subarray(0,15),...jpeg().subarray(2)]),
    new Uint8Array([...jpeg().subarray(0,25),...jpeg().subarray(15)])]) {
    assert.throws(()=>bytesModule.thumbnailDataUri(bytes));
  }
  const badLength=jpeg();badLength[5]=2;assert.throws(()=>bytesModule.thumbnailDataUri(badLength));
});

test('base64 chunking preserves bytes across boundaries and rejects the preview budget without a decoder',()=>{
  for(const count of [8190,8191,8192,8193,18001]) {
    const bytes=jpeg({entropy:Array(count).fill(1)});
    assert.equal(bytesModule.thumbnailDataUri(bytes),'data:image/jpeg;base64,'+Buffer.from(bytes).toString('base64'));
  }
  assert.throws(()=>bytesModule.thumbnailDataUri(new Uint8Array(bytesModule.THUMBNAIL_BYTE_LIMIT+1)));
});

for(const browser of [false,true]) {
  test((browser?'browser':'native')+' actual thumbnail reader separates issuance and byte credentials, then returns memory bytes',async()=>{
    const f=fixture({browser});const result=await f.read();result.assertCurrent();
    assert.equal(result.dataUri,'data:image/jpeg;base64,'+Buffer.from(jpeg()).toString('base64'));assert.equal(f.calls.length,2);
    const [post,get]=f.calls;assert.equal(post[0],f.root+'session');assert.equal(post[1].headers.Authorization,'Bearer original-token');
    assert.deepEqual(JSON.parse(post[1].body),{transport:browser?'browser':'native',asset_kinds:['thumbnail']});
    assert.equal(get[0],f.root+'thumbnail');assert.equal(get[1].method,'GET');assert.equal(get[1].credentials,browser?'include':'omit');
    assert.equal(get[1].redirect,'error');assert.equal(get[1].keepalive,false);assert.equal(get[1].headers.Authorization,undefined);
    assert.equal(get[1].headers['X-Peso-Media-Grant'],browser?undefined:GRANT);assert.equal(get[1].headers.Accept,'image/jpeg');
    assert.ok(!result.dataUri.includes(GRANT));f.release();assert.throws(result.assertCurrent);
  });
}

test('wrong byte headers/status, mismatched lengths, oversized previews and decoder-bomb dimensions deny delivery',async()=>{
  for(const response of [imageResponse(jpeg(),{status:206}),imageResponse(jpeg(),{headers:{'Content-Type':'image/png'}}),
    imageResponse(jpeg(),{headers:{'Content-Length':'4194305'}}),imageResponse(jpeg(),{headers:{'Content-Length':'-1'}}),
    imageResponse(jpeg(),{headers:{'Content-Length':'1'}}),imageResponse(jpeg(),{headers:{'Content-Length':'999'}}),
    imageResponse(jpeg(),{headers:{'Cache-Control':'public,no-store'}}),imageResponse(jpeg(),{headers:{'Cache-Control':'private,max-age=60'}}),
    imageResponse(jpeg({width:65535})),imageResponse(jpeg({height:65535})),
    new Response(null,{headers:{'Content-Type':'image/jpeg','Content-Length':'4','Cache-Control':CACHE}})]) {
    const f=fixture({fetcher:(_u,init,h)=>init.method==='POST'?h.issueResponse():response});await assert.rejects(f.read(),/^Error: Unable to load this preview\.$/);
  }
  const redirected=imageResponse();Object.defineProperty(redirected,'redirected',{value:true});
  const f=fixture({fetcher:(_u,init,h)=>init.method==='POST'?h.issueResponse():redirected});await assert.rejects(f.read());
});

test('empty chunks, an unreadable stream and missing length never bypass byte accounting',async()=>{
  for(const response of [new Response(jpeg(),{headers:{'Content-Type':'image/jpeg','Cache-Control':CACHE}}),
    new Response(new ReadableStream({start(controller){controller.enqueue(new Uint8Array());controller.close();}}),{headers:{'Content-Type':'image/jpeg','Content-Length':'4','Cache-Control':CACHE}}),
    new Response(new ReadableStream({start(controller){controller.error(new Error('sensitive fixture'));}}),{headers:{'Content-Type':'image/jpeg','Content-Length':'4','Cache-Control':CACHE}})]) {
    const f=fixture({fetcher:(_u,init,h)=>init.method==='POST'?h.issueResponse():response});await assert.rejects(f.read(),/Unable to load this preview/);
  }
});

test('failed issuance cannot request any image bytes or fall back to a provider URL',async()=>{
  for(const changes of [{resource_id:OTHER},{urls:{thumbnail:'https://provider.invalid/signed?token=secret'}},{media_grant:'short'}]) {
    const f=fixture({fetcher:(_u,_i,h)=>h.issueResponse(changes)});await assert.rejects(f.read());assert.equal(f.calls.length,1);
  }
});

for(const phase of ['issuer','headers','body']) {
  test('cancel, release and deadline settle stalled '+phase+' even if transport ignores abort',async()=>{
    for(const how of ['cancel','release','deadline']) {
      const wait=deferred();const f=fixture({fakeTimers:true,fetcher:(_u,init,h)=>{
        if(init.method==='POST')return phase==='issuer'?wait.promise:h.issueResponse();
        return phase==='headers'?wait.promise:new Response(new ReadableStream({pull:()=>wait.promise}),{headers:{'Content-Type':'image/jpeg','Content-Length':'4','Cache-Control':CACHE}});
      }});
      const controller=new AbortController();const work=f.read(controller.signal);await tick();
      if(how==='cancel')controller.abort();else if(how==='release')f.release();else f.timers[0]();
      await assert.rejects(work);assert.ok(f.calls.every(([,init])=>init.signal.aborted));
      wait.resolve(phase==='issuer'?f.issueResponse():phase==='headers'?imageResponse():undefined);await tick();
    }
  });
}

test('the shared preview pool admits two reads and removes a cancelled queued operation before it can issue',async()=>{
  const wait=deferred();const f=fixture({fetcher:async(_u,init,h)=>{if(init.method==='POST'){await wait.promise;return h.issueResponse();}return imageResponse();}});
  const a=f.read(),b=f.read();const controller=new AbortController();const c=f.read(controller.signal);const rejected=assert.rejects(c);
  await tick();assert.equal(f.calls.length,2);controller.abort();await rejected;wait.resolve();await Promise.all([a,b]);assert.equal(f.calls.filter(([,init])=>init.method==='POST').length,2);
  await f.read();assert.equal(f.calls.filter(([,init])=>init.method==='POST').length,3);
});

test('the queue is bounded and release drains every logical waiter without issuing it',async()=>{
  const wait=deferred();const f=fixture({fetcher:()=>wait.promise});const reads=Array.from({length:67},()=>f.read());for(const read of reads)void read.catch(()=>{});
  await tick();assert.equal(f.calls.length,2);f.release();const results=await Promise.allSettled(reads);assert.ok(results.every(r=>r.status==='rejected'));assert.equal(f.calls.length,2);
  wait.resolve(f.issueResponse());await tick();
});

test('a queued request cannot switch its captured backend after admission',async()=>{
  const wait=deferred();const f=fixture({fetcher:()=>wait.promise});const reads=[f.read(),f.read(),f.read()];for(const read of reads)void read.catch(()=>{});
  await tick();f.changeBackend();wait.resolve(f.issueResponse());await Promise.allSettled(reads);assert.equal(f.calls.length,2);
});

test('session changes during body delivery reject otherwise valid memory bytes',async()=>{
  const wait=deferred();let f;f=fixture({fetcher:(_u,init,h)=>init.method==='POST'?h.issueResponse():wait.promise});
  const work=f.read();await tick();f.changeSession();wait.resolve(imageResponse());await assert.rejects(work);
});


test('actual thumbnail component passes only the hook source to images and isolates Retry from the row action',()=>{
  let preview={uri:'data:image/jpeg;base64,synthetic',error:false,onImageError(){},retry(){}};
  const jsx=(type,props)=>({type,props});const events=[];
  const component=load('src/components/VideoThumbnail.tsx',{
    'react/jsx-runtime':{jsx,jsxs:jsx},'react-native':{Image:'Image',Pressable:'Pressable',Text:'Text',View:'View',StyleSheet:{
      flatten:value=>value,create:value=>value,absoluteFill:{position:'absolute',top:0,right:0,bottom:0,left:0}}},
    '../../context/AuthContext':{useAuth:()=>({session:{access_token:'original-token'}})},
    '../../lib/useVideoThumbnail':{useVideoThumbnail:()=>preview},
  }).default;
  const props={videoId:VIDEO,available:true,legacyUrl:'https://provider.invalid/secret',style:{width:62,height:62},placeholder:'placeholder'};
  let tree=component(props);assert.equal(tree.props.children[0].type,'Image');
  assert.deepEqual(tree.props.children[0].props.source,{uri:preview.uri});assert.ok(!JSON.stringify(tree).includes('original-token'));
  preview={uri:null,error:true,onImageError(){},retry(){events.push('retry');}};
  tree=component(props);assert.equal(tree.props.children[0],null);const retry=tree.props.children[1];
  assert.equal(retry.props.accessibilityLabel,'Retry video preview');assert.ok(retry.props.style.minWidth>=44&&retry.props.style.minHeight>=44);
  retry.props.onPress({stopPropagation(){events.push('stop');}});assert.deepEqual(events,['stop','retry']);
});


test('actual thumbnail transport preserves the committed real FFmpeg JPEG fixture on both platforms',async()=>{
  const input=fs.readFileSync(path.join(__dirname,'fixtures/video-thumbnail-baseline.jpg'));
  const receipt=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/video-thumbnail-baseline.json'),'utf8'));
  assert.equal(require('node:crypto').createHash('sha256').update(input).digest('hex'),receipt.sha256);
  assert.equal(receipt.width,720);assert.equal(receipt.height,720);
  for(const browser of [false,true]) {
    const f=fixture({browser,fetcher:(_u,init,h)=>init.method==='POST'?h.issueResponse():imageResponse(input)});
    const result=await f.read();assert.deepEqual(Buffer.from(result.dataUri.slice('data:image/jpeg;base64,'.length),'base64'),input);
  }
});
