const {test} = require('node:test');
const assert = require('node:assert/strict');
const {create, copyEmail} = require('../src/nukkad/static/notifications.js');
function fixture() {
  const timers = new Map(); let time = 0, next = 0;
  const target = {children: [], append(x) {this.children.push(x);}};
  const node = (tag, text, cls) => ({tag, textContent:text, className:cls, children:[], setAttribute(k,v){this[k]=v;}, append(...x){this.children.push(...x);}, remove(){target.children.splice(target.children.indexOf(this),1);}});
  const setTimer = (cb, ms) => {const id=++next;timers.set(id,{cb,ms});return id;};
  const ui = create({target,node,setTimer,clearTimer:id=>timers.delete(id),now:()=>time});
  return {ui,target,timers,advance:ms=>time+=ms};
}
test('three visible notices, queue, deduplication and persistent errors',()=>{
 const f=fixture(); ['one','two','three','four'].forEach(x=>f.ui.notify(x,true)); f.ui.notify('one',true);
 assert.equal(f.target.children.length,3); assert.equal(f.timers.size,0);
 f.target.children[0].children[2].onclick();
 assert.equal(f.target.children.length,3); assert.equal(f.target.children[2].children[1].textContent,'four');
 assert.equal(f.target.children[0].role,'alert');
});
test('success expires after five seconds excluding hover and focus time',()=>{
 const f=fixture();f.ui.notify('Saved');const box=f.target.children[0];assert.equal([...f.timers.values()][0].ms,5000);
 f.advance(1000);box.onmouseenter();assert.equal(f.timers.size,0);box.onfocusin();box.onmouseleave();assert.equal(f.timers.size,0);
 box.onfocusout({});const timer=[...f.timers.values()][0];assert.equal(timer.ms,4000);timer.cb();assert.equal(f.target.children.length,0);
});
test('clipboard success is deliberate and failure never shows a success',async()=>{
 const tooltip={hidden:true};let copied, timer, failure;
 assert.equal(await copyEmail({clipboard:{writeText:async x=>copied=x},tooltip,notify(){},setTimer:cb=>timer=cb}),true);
 assert.equal(copied,'yajush24606@gmail.com');assert.equal(tooltip.textContent,'Mail Copied');timer();assert.equal(tooltip.hidden,true);
 assert.equal(await copyEmail({clipboard:{writeText:async()=>{throw Error('Denied');}},tooltip,notify:x=>failure=x}),false);
 assert.equal(tooltip.hidden,true);assert.match(failure,/manually/);
});
