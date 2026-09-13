// Local desktop control; not a substitute for the user-operated iPhone.
const {chromium}=require('C:/Users/rishi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const secure=process.argv.includes('--secure'),urls=JSON.parse(fs.readFileSync('tmp/vina-prepared-idb-url.json'));
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage();page.on('pageerror',e=>console.log('PAGE_ERROR',String(e)));
  await page.goto(secure?urls.local:urls.urls[0]);
  await page.locator('#model').fill('Ryzen 7 7435HS - '+(secure?'localhost WebCrypto':'LAN HTTP')+' IndexedDB');
  await page.locator('#os').fill('Windows headless control');await page.locator('#start').click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Saved.'),null,{timeout:180000});
  console.log(await page.locator('#status').innerText());
  const rejected=await page.evaluate(async()=>{
   const key=new URL(location.href).searchParams.get('key'),manifest=await(await fetch('/manifest?key='+key)).json();
   const db=await new Promise(resolve=>{const r=indexedDB.open('vina-prepared-v1',1);r.onsuccess=()=>resolve(r.result)});
   await new Promise((resolve,reject)=>{const tx=db.transaction('artifacts','readwrite');tx.objectStore('artifacts').put(new Uint8Array(4).buffer,manifest.artifact_sha256);tx.oncomplete=resolve;tx.onerror=reject});db.close();
   return await new Promise(resolve=>{const w=new Worker('/worker.mjs',{type:'module'});w.onmessage=e=>{w.terminate();resolve(e.data.error)};w.postMessage({mode:'cached_restore',index:0,manifest})});
  });
  if(!rejected?.includes('integrity mismatch'))throw Error('Poisoned cache accepted');console.log('Poisoned cache rejected before restoration');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
