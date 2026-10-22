import test from 'node:test';
import assert from 'node:assert/strict';
import {fall2026Events,mergeCalendarData,monthCells,calendarEntries,entriesOnDate,calendarTask,calendarTime} from '../dist/calendar.mjs';
import {complete,reopen,plus} from '../dist/model.mjs';
// Synthetic fixtures exercise local event behavior; no personal schedule is bundled.
const sample={id:'fixture-event',course:'math',date:'2026-10-03',title:'Sample assignment',kind:'deadline',source:'Synthetic test fixture'};
const base=()=>mergeCalendarData({version:1,tasks:[],references:[],calendarEvents:[{...sample}],calendarCadences:[{id:'sample-cadence',course:'cs',weekdays:[1,3],title:'Sample cadence'}]});
test('published calendar has no seeded personal schedule or default cadence',()=>{
 assert.deepEqual(fall2026Events,[]);
 assert.deepEqual(calendarEntries(mergeCalendarData({version:1,tasks:[]})),[]);
});
test('November 1 is Sunday, October starts Thursday, and DST preserves dates',()=>{
 assert.equal(monthCells(2026,11)[0],'2026-11-01');
 assert.deepEqual(monthCells(2026,10).slice(0,5),[null,null,null,null,'2026-10-01']);
 assert.equal(monthCells(2026,11).filter(Boolean).length,30);
 assert.equal(plus('2026-10-31',1),'2026-11-01');
 assert.equal(plus('2026-11-01',1),'2026-11-02');
});
test('migration and backup round-trip retain local events without seeding deadlines',()=>{
 const original={...base(),imports:['existing'],extra:'keep'};
 const state=mergeCalendarData(original);
 assert.equal(state.tasks,original.tasks);assert.equal(state.references,original.references);
 assert.equal(state.extra,'keep');assert.equal(state.calendarEvents[0],original.calendarEvents[0]);
 assert.equal(mergeCalendarData(state),state);
 assert.deepEqual(JSON.parse(JSON.stringify(state)).calendarEvents,[sample]);
});
test('cadence uses only local rule weekdays and avoids local break ranges',()=>{
 const state=base();state.calendarEvents.push({id:'fixture-break',course:'break',date:'2026-10-19',endDate:'2026-10-21',kind:'break',title:'Sample break'});
 const cadence=calendarEntries(state).filter(e=>e.kind==='cadence');assert.ok(cadence.length);
 for(const e of cadence){assert.ok([1,3].includes(new Date(e.date+'T12:00:00').getDay()));assert.equal(e.time,undefined);}
 assert.equal(cadence.some(e=>e.date>='2026-10-19'&&e.date<='2026-10-21'),false);
 assert.equal(calendarEntries(state,{labs:false}).some(e=>e.kind==='cadence'),false);
 assert.equal(calendarEntries(state,{courses:['math']}).some(e=>e.kind==='cadence'),false);
});
test('course filters retain breaks and ranges include both endpoints',()=>{
 const state=base();state.calendarEvents.push({id:'fixture-break',course:'break',date:'2026-10-19',endDate:'2026-10-21',kind:'break',title:'Sample break'});
 const entries=calendarEntries(state,{courses:[]});assert.ok(entries.every(e=>e.course==='break'));
 for(const date of ['2026-10-19','2026-10-20','2026-10-21'])assert.equal(entriesOnDate(entries,date).length,1);
 assert.equal(entriesOnDate(entries,'2026-10-22').length,0);
});
test('task linking is idempotent and reflects completion, reopening, and deletion',()=>{
 const tasks=calendarTask([],sample,new Date('2026-10-01T12:00:00'));
 assert.equal(tasks.length,1);assert.equal(tasks[0].due,sample.date);assert.equal(calendarTask(tasks,sample),tasks);
 const state={...base(),tasks:complete(tasks,tasks[0].id)};
 assert.equal(calendarEntries(state).find(e=>e.id===sample.id).completed,true);
 assert.equal(calendarEntries(state).filter(e=>e.taskId===tasks[0].id).length,1);
 state.tasks=reopen(state.tasks,tasks[0].id);assert.equal(calendarEntries(state).find(e=>e.id===sample.id).completed,false);
 state.tasks[0].deletedAt='2026-10-04T12:00:00Z';assert.equal(calendarEntries(state).find(e=>e.id===sample.id).taskId,undefined);
 assert.equal(calendarTask(state.tasks,sample).filter(t=>!t.deletedAt).length,1);
 for(const kind of ['cadence','break','activity'])assert.throws(()=>calendarTask([],{...sample,kind}),/reference/);
 assert.throws(()=>calendarTask([],{...sample,tentative:true}),/reference/);
});
test('date and time details distinguish unspecified deadlines and time ranges',()=>{
 assert.match(calendarTime(sample),/not specified/);
 assert.equal(calendarTime({...sample,time:'10:15',endTime:'11:45'}),'10:15 am – 11:45 am · Eastern');
 assert.equal(calendarTime({...sample,kind:'break'}),'No classes');
});
test('only dated, non-deleted notebook tasks appear and rescheduled links remain visible',()=>{
 const tasks=calendarTask([],sample);tasks[0].due='2026-10-04';
 tasks.push({id:'undated',due:''},{id:'deleted',due:'2026-10-04',deletedAt:'x'},{id:'reference',due:'2026-10-04',recordType:'reference'});
 const entries=calendarEntries({...base(),tasks});
 assert.deepEqual(entries.filter(e=>e.kind==='task').map(e=>e.taskId),[tasks[0].id]);
 assert.equal(entries.find(e=>e.id===sample.id).date,sample.date);
 assert.equal(entries.find(e=>e.id===sample.id).taskDue,'2026-10-04');
});
