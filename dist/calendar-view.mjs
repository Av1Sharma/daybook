import {day,dateOf,plus} from './model.mjs';
import {calendarCourses,calendarStart,calendarEnd,monthCells,calendarEntries,entriesOnDate,calendarTime} from './calendar.mjs';

const calendarEscape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const calendarDateLabel=value=>dateOf(value).toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'});
const calendarKind={deadline:'Due',exam:'Exam',quiz:'Quiz',assessment:'Assessment',activity:'Activity',break:'Break',cadence:'Cadence only',task:'Notebook task'};
export class CalendarView {
  constructor(element,{getState,onTrack,onTask}){
    this.element=element;this.getState=getState;this.onTrack=onTrack;this.onTask=onTask;
    this.courses=new Set(calendarCourses.map(c=>c.id));this.labs=!!getState().calendarCadences?.length;
    const today=day();this.selected=today>=calendarStart&&today<=calendarEnd?today:calendarStart;this.eventId=null;
    element.addEventListener('click',e=>this.click(e));
    element.addEventListener('change',e=>{if(e.target.id==='calendar-labs'){this.labs=e.target.checked;this.render();}});
    element.addEventListener('keydown',e=>this.keydown(e));
  }
  entries(){return calendarEntries(this.getState(),{courses:[...this.courses],labs:this.labs})}
  chip(event){
    const course=calendarCourses.find(c=>c.id===event.course);
    const compact=event.title.replace(/ · .*/, '');
    const title=event.kind==='cadence'?'Lab cadence':compact;
    const prefix=({cs:'CS',math:'Math',span:'SP',engl:'EN',backend:'',notebook:'Task'})[event.course];
    return `<span class="calendar-chip cal-${course?.theme||'break'} ${event.kind==='cadence'?'cal-cadence':''}">${event.completed?'✓ ':''}${course&&prefix?calendarEscape(prefix)+' ':''}${calendarEscape(title)}${event.tentative?' ?':''}</span>`;
  }
  month(month,entries){
    const name=month===10?'October':'November';
    return `<section class="calendar-month" aria-labelledby="calendar-month-${month}"><div class="calendar-month-heading"><h2 id="calendar-month-${month}">${name} <span>2026</span></h2><span>${month===10?'01':'02'} / 02</span></div><div class="calendar-weekdays" aria-hidden="true">${['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map(d=>`<span>${d}</span>`).join('')}</div><div class="calendar-days" role="group" aria-label="${name} dates; use arrow keys to move">${monthCells(2026,month).map(date=>{
      if(!date)return '<div class="calendar-blank" aria-hidden="true"></div>';
      const events=entriesOnDate(entries,date),isBreak=events.some(e=>e.kind==='break');
      const description=events.length?events.map(e=>`${calendarCourses.find(c=>c.id===e.course)?.name||''} ${e.title}${e.tentative?' tentative':''}${e.completed?' completed':''}`).join('; '):'No events in selected courses';
      return `<button type="button" class="calendar-day ${date===this.selected?'selected':''} ${isBreak?'is-break':''} ${date===day()?'is-today':''}" data-calendar-date="${date}" tabindex="${date===this.selected?0:-1}" aria-pressed="${date===this.selected}" ${date===day()?'aria-current="date"':''} aria-label="${calendarEscape(calendarDateLabel(date)+'. '+description)}"><span class="calendar-day-number">${Number(date.slice(-2))}</span><span class="calendar-day-events">${events.slice(0,2).map(e=>this.chip(e)).join('')}${events.length>2?`<span class="calendar-more">+${events.length-2} more</span>`:''}</span></button>`;
    }).join('')}</div></section>`;
  }
  detail(event){
    if(!event)return '<div class="calendar-detail-placeholder"><span class="eyebrow">A CLOSER LOOK</span><h3>Your day, in detail.</h3><p>Select an event to see its time, notes, and source.</p></div>';
    const course=calendarCourses.find(c=>c.id===event.course),canTrack=!event.taskId&&!event.tentative&&!event.endDate&&!['cadence','break','activity','task'].includes(event.kind);
    return `<div class="calendar-event-detail"><p class="eyebrow">${calendarEscape(course?.name||'Academic calendar')} · ${calendarKind[event.kind]||'Event'}</p><h3 id="calendar-detail-title" tabindex="-1">${calendarEscape(event.title)}</h3>${event.tentative?'<span class="calendar-badge">Tentative · confirm date</span>':''}${event.completed?'<span class="calendar-badge">Completed in Day done</span>':''}<dl><dt>Date</dt><dd>${calendarEscape(calendarDateLabel(event.date))}${event.endDate?' – '+calendarEscape(calendarDateLabel(event.endDate)):''}</dd><dt>Time</dt><dd>${calendarEscape(calendarTime(event))}</dd>${event.location?`<dt>Location</dt><dd>${calendarEscape(event.location)}</dd>`:''}</dl>${event.notes?`<p>${calendarEscape(event.notes)}</p>`:''}<p class="calendar-source"><strong>Source</strong> ${calendarEscape(event.source)}</p>${canTrack?`<button class="primary" data-calendar-track="${calendarEscape(event.id)}">Add to My day</button><p class="help">Creates one task with this due date.</p>`:event.taskId?`<p class="help">Linked to your notebook${event.completed?' · completed':''}.${event.taskDue&&event.taskDue!==event.date?' Task scheduled for '+calendarEscape(event.taskDue)+'; the reference date is shown above.':''}</p>${!event.completed?`<button class="text-button" data-calendar-task="${calendarEscape(event.taskId)}">Edit notebook task →</button>`:''}`:''}</div>`;
  }
  render(){
    const focused=this.element.contains(document.activeElement)?document.activeElement:null;
    const focusKey=focused?.dataset.calendarDate?['data-calendar-date',focused.dataset.calendarDate]:focused?.dataset.calendarCourse?['data-calendar-course',focused.dataset.calendarCourse]:focused?.dataset.calendarEvent?['data-calendar-event',focused.dataset.calendarEvent]:focused?.id?['id',focused.id]:null;
    const entries=this.entries(),selectedEvents=entriesOnDate(entries,this.selected);
    const detail=selectedEvents.find(e=>e.id===this.eventId);
    if(!detail)this.eventId=null;
    this.element.innerHTML=`<div class="calendar-intro"><div><p class="eyebrow">FALL SEMESTER / 2026</p><h2>Two months. A little perspective.</h2><p>Deadlines, exams, and space to plan what comes next.</p></div><button class="quiet calendar-today" id="calendar-today" ${day()<calendarStart||day()>calendarEnd?'disabled title="Today is outside October–November 2026"':''}>Select today</button></div><div class="calendar-controls"><div class="calendar-filter-heading"><span class="eyebrow">SHOW COURSES</span><button class="text-button" id="calendar-all">${this.courses.size===calendarCourses.length?'Clear courses':'Show all'}</button></div><div class="calendar-filters" role="group" aria-label="Filter calendar by course">${calendarCourses.map(c=>`<button type="button" class="calendar-filter cal-${c.theme}" data-calendar-course="${c.id}" aria-pressed="${this.courses.has(c.id)}"><span class="calendar-filter-dot" aria-hidden="true"></span>${c.name}</button>`).join('')}</div><label class="calendar-lab-toggle" ${this.getState().calendarCadences?.length?'':'hidden'}><input id="calendar-labs" type="checkbox" ${this.labs?'checked':''}> Show cadence reminders <span>Confirm actual deadlines in your course system</span></label></div><div class="calendar-months">${this.month(10,entries)}${this.month(11,entries)}</div><p class="calendar-footnote">Select a date, then an event below for full details. Arrow keys move between dates. Breaks stay visible with every filter. Dashed lab reminders show cadence only. “?” marks a tentative date. Unspecified deadlines are left open.</p><div class="calendar-day-panel"><section class="calendar-agenda" aria-labelledby="calendar-selected-heading"><p class="eyebrow">SELECTED DAY</p><h2 id="calendar-selected-heading">${calendarEscape(calendarDateLabel(this.selected))}</h2><p class="calendar-event-count" role="status">${selectedEvents.length} ${selectedEvents.length===1?'entry':'entries'} in your selected courses</p><div class="calendar-agenda-list">${selectedEvents.length?selectedEvents.map(e=>`<button type="button" class="calendar-agenda-event ${e.id===this.eventId?'active':''}" data-calendar-event="${calendarEscape(e.id)}" aria-pressed="${e.id===this.eventId}"><span class="calendar-event-course cal-${calendarCourses.find(c=>c.id===e.course)?.theme||'break'}">${calendarEscape(calendarCourses.find(c=>c.id===e.course)?.name||'BREAK')}</span><span class="calendar-event-name">${calendarEscape(e.title)}${e.tentative?' · tentative':''}${e.completed?' · completed':''}<small>${calendarEscape(calendarTime(e))}</small></span><span aria-hidden="true">↗</span></button>`).join(''):'<p class="calendar-empty-day">A little breathing room. No events in these filters.</p>'}</div></section><aside class="calendar-detail" aria-label="Event details">${this.detail(detail)}</aside></div>`;
    if(focusKey)this.element.querySelector(`[${focusKey[0]}="${CSS.escape(focusKey[1])}"]`)?.focus({preventScroll:true});
  }
  async click(e){
    const date=e.target.closest('[data-calendar-date]');if(date){this.selected=date.dataset.calendarDate;this.eventId=null;this.render();return}
    const filter=e.target.closest('[data-calendar-course]');if(filter){const id=filter.dataset.calendarCourse;this.courses.has(id)?this.courses.delete(id):this.courses.add(id);this.render();return}
    if(e.target.closest('#calendar-all')){this.courses=this.courses.size===calendarCourses.length?new Set():new Set(calendarCourses.map(c=>c.id));this.render();return}
    if(e.target.closest('#calendar-today')){this.selected=day();this.eventId=null;this.render();this.element.querySelector(`[data-calendar-date="${this.selected}"]`)?.focus();return}
    const entry=e.target.closest('[data-calendar-event]');if(entry){this.eventId=entry.dataset.calendarEvent;this.render();this.element.querySelector('#calendar-detail-title')?.focus({preventScroll:true});return}
    const track=e.target.closest('[data-calendar-track]');if(track){track.disabled=true;try{await this.onTrack(this.entries().find(e=>e.id===track.dataset.calendarTrack));this.element.querySelector('#calendar-detail-title')?.focus({preventScroll:true});}finally{if(track.isConnected)track.disabled=false}return}
    const task=e.target.closest('[data-calendar-task]');if(task)this.onTask(task.dataset.calendarTask);
  }
  keydown(e){
    const button=e.target.closest('[data-calendar-date]');if(!button||e.altKey||e.ctrlKey||e.metaKey)return;
    let date=button.dataset.calendarDate,next;
    const step={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7};
    if(e.key in step)next=plus(date,step[e.key]);
    else if(e.key==='Home')next=plus(date,-dateOf(date).getDay());
    else if(e.key==='End')next=plus(date,6-dateOf(date).getDay());
    else if(e.key==='PageDown')next=`2026-11-${String(Math.min(30,Number(date.slice(-2)))).padStart(2,'0')}`;
    else if(e.key==='PageUp')next=`2026-10-${date.slice(-2)}`;
    else return;
    e.preventDefault();this.selected=next<calendarStart?calendarStart:next>calendarEnd?calendarEnd:next;this.eventId=null;this.render();this.element.querySelector(`[data-calendar-date="${this.selected}"]`)?.focus();
  }
}
