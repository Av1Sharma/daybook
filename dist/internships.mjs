import {createTask} from './model.mjs';

// Preserve the original records, but stop treating reference lists as work to finish.
export function organizeInternships(state, now = new Date()) {
  const migration = 'internship-reminders-v1';
  if ((state.migrations || []).includes(migration)) return state;
  const referenceIds = new Set(['screenshot-open-09','screenshot-open-10','screenshot-open-11','screenshot-open-12','screenshot-open-13']);
  const genericTitles = new Set(['Spam Jobs','Mitre','Other VISA Locations','All SWE','Companies I can cherry pick — look at their internships','TikTok']);
  const companyItems = state.tasks.filter(t => referenceIds.has(t.id) && !t.deletedAt).map(t => t.title);
  const tasks = state.tasks.map(t => !t.completedAt && t.source === 'screenshots-2026-09-23' && genericTitles.has(t.title)
    ? {...t, recordType:'reference'} : t);
  const reminders = Array.from({length:3}, (_,i) => ({
    ...createTask({title:`Internship reminder ${i+1}`, category:'Internships / jobs'}, now),
    id:`internship-reminder-${i+1}-initial`, reminderId:`internship-reminder-${i+1}`, surface:'internships'
  }));
  const internshipTitles = new Set(['Hackathons / companies I’ve applied to','Companies I can cherry pick · maybe']);
  const references = (state.references || []).map(n => internshipTitles.has(n.title) ? {...n, scope:'internships'} : n);
  if (companyItems.length) references.unshift({title:'Places to look',description:'Reference ideas from your notebook. These are not tasks or deadlines.',items:companyItems,scope:'internships'});
  return {...state, tasks:[...reminders,...tasks], references, migrations:[...(state.migrations || []),migration]};
}
export function currentReminders(tasks) {
  return [1,2,3].map(i => tasks.filter(t => t.reminderId===`internship-reminder-${i}` && !t.deletedAt)
    .sort((a,b)=>b.createdAt.localeCompare(a.createdAt))[0]).filter(Boolean);
}
export function nextReminder(tasks,id,now=new Date()) {
  const previous = tasks.find(t=>t.id===id && t.reminderId && t.completedAt && !t.deletedAt);
  if (!previous) throw Error('Complete this reminder before starting the next check-in.');
  if(tasks.some(t=>t.reminderId===previous.reminderId && !t.completedAt && !t.deletedAt)) throw Error('This reminder already has an open check-in.');
  return [{...createTask({title:previous.title,category:'Internships / jobs'},now),reminderId:previous.reminderId,surface:'internships',parentId:previous.id},...tasks];
}
export function renameReminder(tasks,id,title) {
  title=String(title).trim();
  if(!title || title.length>120)throw Error('Use a reminder name from 1 to 120 characters.');
  const task=tasks.find(t=>t.id===id&&t.reminderId&&!t.deletedAt);
  if(!task)throw Error('That reminder is no longer available.');
  return tasks.map(t=>t.id===id?{...t,title}:t);
}
