const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function setup(){
  const make=(tag,text)=>({tag,textContent:text||'',children:[],files:[],append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items}});
  const target=make('div');let photos=[],messages=[],screen=true;
  const prepared=[];
  const context=vm.createContext({node:make,$:()=>target,navigation:{checkpoint:()=>()=>screen},FormData:class{append(){}},message:v=>messages.push(v),report:e=>{throw e},
    visitMemory:{prepare:async(visit)=>prepared.push(visit)},
    api:async(path,options={})=>{if(path.includes('/outcomes/'))return [{id:'visit',active:true,place_name:'Sample park'}];if(options.method==='POST'){photos.push({id:'photo-'+photos.length,experience_revision:'after-photo'});return photos.at(-1)}if(options.method==='DELETE'){photos=photos.filter(p=>!path.endsWith(p.id));return {}}return [...photos]}});
  const source=fs.readFileSync('src/nukkad/static/app.js','utf8');
  vm.runInContext(source.slice(source.indexOf('let photoRenderRevision'),source.indexOf('const outcomeDrafts')),context);
  const all=(item)=>[item,...item.children.flatMap(all)];
  return {context,target,all,messages,prepared,leave:()=>screen=false};
}
test('a successful photo upload refreshes the displayed count and image',async()=>{
  const f=setup();await f.context.renderPlacePhotos('walk');
  const input=f.all(f.target).find(x=>x.tag==='input');input.files=[{size:10}];
  await f.all(f.target).find(x=>x.textContent==='Save selected photos').onclick();
  assert.ok(f.all(f.target).some(x=>x.textContent.startsWith('1/5 photos')));
  assert.equal(f.all(f.target).filter(x=>x.tag==='img').length,1);
  assert.equal(f.prepared.length,1);assert.equal(f.prepared[0].revision,'after-photo');
  await f.all(f.target).find(x=>x.textContent==='Remove photo').onclick();
  assert.ok(f.all(f.target).some(x=>x.textContent.startsWith('0/5 photos')));
});
