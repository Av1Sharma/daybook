import {day,dateOf,plus,validDate,createTask} from './model.mjs';

export const calendarCourses = [
  {id:'cs',name:'Computer science',short:'CS',theme:'cs'},
  {id:'math',name:'Math',short:'Math',theme:'math'},
  {id:'span',name:'Language',short:'Span',theme:'span'},
  {id:'engl',name:'Writing',short:'Engl',theme:'engl'},
  {id:'backend',name:'Projects',short:'Project',theme:'backend'},
  {id:'notebook',name:'Notebook tasks',short:'Task',theme:'notebook'}
];
export const calendarStart='2026-10-01', calendarEnd='2026-11-30';
// Published builds contain no personal schedule. Events are local notebook data.
export const fall2026Events = [];
const calendarImport='fall-2026-calendar-v1';
// Keep academic records in the existing notebook envelope and backups, without
// automatically turning every exam or cadence reminder into an unfinished task.
export function mergeCalendarData(state){
  if(state.imports?.includes(calendarImport))return state;
  const existing=Array.isArray(state.calendarEvents)?state.calendarEvents:[];
  const ids=new Set(existing.map(e=>e.id));
  return {...state,calendarEvents:[...existing,...fall2026Events.filter(e=>!ids.has(e.id))],imports:[...(state.imports||[]),calendarImport]};
}
export function monthCells(year,month){
  const first=`${year}-${String(month).padStart(2,'0')}-01`;
  const offset=dateOf(first).getDay();
  const count=new Date(year,month,0).getDate();
  return Array.from({length:Math.ceil((offset+count)/7)*7},(_,i)=>i<offset||i>=offset+count?null:plus(first,i-offset));
}
export function calendarEntries(state,{courses=calendarCourses.map(c=>c.id),labs=true}={}){
  const tasks=state.tasks||[];
  const records=(state.calendarEvents||fall2026Events).map(e=>{
    const linked=tasks.find(t=>t.calendarEventId===e.id&&!t.deletedAt);
    return {...e,taskId:linked?.id,taskDue:linked?.due,completed:!!linked?.completedAt};
  });
  const personal=tasks.filter(t=>t.due&&validDate(t.due)&&!t.deletedAt&&t.recordType!=='reference'&&(!t.calendarEventId||!records.some(e=>e.id===t.calendarEventId&&e.date===t.due))).map(t=>({id:'task-'+t.id,taskId:t.id,course:'notebook',date:t.due,title:t.title,kind:'task',completed:!!t.completedAt,source:'Your Daybook notebook',notes:t.category}));
  const breaks=records.filter(e=>e.kind==='break');
  const cadence=[];
  if(labs)for(const rule of state.calendarCadences||[]){
    if(!courses.includes(rule.course)||!Array.isArray(rule.weekdays))continue;
    for(let date=calendarStart;date<=calendarEnd;date=plus(date,1)){
      if(rule.startDate&&date<rule.startDate||rule.endDate&&date>rule.endDate)continue;
      if(rule.weekdays.includes(dateOf(date).getDay())&&!breaks.some(e=>e.date<=date&&(e.endDate||e.date)>=date))cadence.push({id:`cadence-${rule.id}-${date}`,course:rule.course,date,title:rule.title||'Cadence reminder',kind:'cadence',source:'Local notebook cadence rule',notes:'Cadence only. Confirm the actual assignment and submission time in your course system.'});
    }
  }
  return [...records,...personal,...cadence].filter(e=>e.date<=calendarEnd&&(e.endDate||e.date)>=calendarStart&&(e.course==='break'||courses.includes(e.course))).sort((a,b)=>a.date.localeCompare(b.date)||(a.kind==='break'?-1:b.kind==='break'?1:0)||(a.time||'99:99').localeCompare(b.time||'99:99')||a.title.localeCompare(b.title));
}
export function entriesOnDate(entries,date){return entries.filter(e=>e.date<=date&&(e.endDate||e.date)>=date)}
export function calendarTask(tasks,event,now=new Date()){
  if(['break','cadence','activity'].includes(event.kind)||event.tentative||event.endDate)throw Error('This is a calendar reference, not a confirmed task deadline.');
  if(tasks.some(t=>t.calendarEventId===event.id&&!t.deletedAt))return tasks;
  const course=calendarCourses.find(c=>c.id===event.course)?.name||'';
  return [{...createTask({title:`${course} · ${event.title}`,category:event.course==='backend'?'Projects':'Academics / classes',due:event.date,importance:event.kind==='exam'?3:2},now),calendarEventId:event.id},...tasks];
}
export function calendarTime(event){
  if(event.kind==='cadence')return 'Cadence only · confirm details';
  if(event.kind==='break')return 'No classes';
  if(!event.time)return event.kind==='deadline'?'Due date · time not specified':'Time not specified';
  const clock=t=>{const [h,m]=t.split(':').map(Number);return `${h%12||12}:${String(m).padStart(2,'0')} ${h>=12?'pm':'am'}`};
  return `${clock(event.time)}${event.endTime?' – '+clock(event.endTime):''} · Eastern`;
}
