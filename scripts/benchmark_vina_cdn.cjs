const {chromium}=require('C:/Users/rishi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{
const origin=process.env.VINA_CDN_ORIGIN||'https://vina-cdn-benchmark.kelgis.workers.dev',key=fs.readFileSync('tmp/vina-cdn/upload-key.txt','utf8').trim();
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try{for(const variant of ['identity-br9','identity-gzip9','shuffle8-br9']){
 const context=await browser.newContext(),page=await context.newPage();let upload;
 page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname==='/results')upload=JSON.parse(r.postData());});
 await page.goto(origin+'/?key='+key);await page.locator('#model').fill('Ryzen 7 7435HS Chrome fresh-context CDN');await page.locator('#fresh').check();await page.locator('#variant').selectOption(variant);await page.locator('#start').click();
 await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Saved.'),null,{timeout:180000});
 const status=await page.locator('#status').innerText();console.log(variant,status);if(!status.includes('4/4; finalization: true'))throw Error('Validation failed');
 fs.writeFileSync('docs/evaluation/vina_cdn_2026-09-14/desktop_'+variant+'.json',JSON.stringify(upload,null,2)+'\n');
 // Inspect range behavior separately; no claim that a partial compressed body is independently restorable.
 const range=await page.evaluate(async()=>{const m=await(await fetch('/manifest.json')).json();const u=m.variants.find(v=>v.name==='identity-br9').url;const r=await fetch(u,{headers:{Range:'bytes=0-1023'}});return {status:r.status,content_range:r.headers.get('content-range'),content_encoding:r.headers.get('content-encoding'),etag:r.headers.get('etag')};});
 fs.writeFileSync('docs/evaluation/vina_cdn_2026-09-14/range.json',JSON.stringify(range,null,2)+'\n');await context.close();
}}finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
