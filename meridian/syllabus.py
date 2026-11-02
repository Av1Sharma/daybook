"""Preview-first local syllabus imports. Date-only deadlines remain date-only."""
import hashlib
import json
import re
from datetime import date as Date, datetime, time
from pydantic import BaseModel, Field, model_validator
from .extract import plain, TZ
from .store import stamp

MONTHS = {name: i for i, names in enumerate([
    (), ('jan','january'), ('feb','february'), ('mar','march'), ('apr','april'),
    ('may',), ('jun','june'), ('jul','july'), ('aug','august'),
    ('sep','sept','september'), ('oct','october'), ('nov','november'), ('dec','december')
]) for name in names}
DATE_PATTERN = re.compile(r'\b(20\d{2})-(\d{2})-(\d{2})\b|\b(\d{1,2})/(\d{1,2})(?:/(20\d{2}|\d{2}))?\b|\b('+'|'.join(MONTHS)+r')\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d{2}))?\b', re.I)
ACTION = re.compile(r'\bdue\b|\bdeadline\b|\bhand in\b|\bsubmit\b|\bessay\b|\bhomework\b|\bhw\s*#?\s*\d|\bquiz\b|\bexam\b|\bprelim\b|\bcomposition\b|\bcomposici[oó]n\b|\bpeer (?:edits|reviews)\b',re.I)
CLOCK = re.compile(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b|\b([01]?\d|2[0-3]):([0-5]\d)\b',re.I)

class PreviewRequest(BaseModel):
    text: str = Field(min_length=1,max_length=100000)
    course: str = Field(min_length=1,max_length=100)
    year: int = Field(ge=2020,le=2100)

class ImportItem(BaseModel):
    title: str = Field(min_length=1,max_length=250)
    course: str = Field(min_length=1,max_length=100)
    date: Date | None = None
    time: str | None = Field(default=None,pattern=r'^\d{2}:\d{2}$')
    end_date: Date | None = None
    end_time: str | None = Field(default=None,pattern=r'^\d{2}:\d{2}$')
    kind: str = Field(default='deadline',max_length=40)
    evidence: str = Field(default='',max_length=20000)
    source: str = Field(default='Syllabus',max_length=2000)
    track: bool = False

    @model_validator(mode='after')
    def valid_times(self):
        for v in (self.time,self.end_time):
            if v: time.fromisoformat(v)
        if self.time and not self.date: raise ValueError('A time needs a date')
        if self.end_date and (not self.date or self.end_date < self.date): raise ValueError('End date precedes start')
        return self

class CommitRequest(BaseModel):
    items: list[ImportItem] = Field(min_length=1,max_length=250)


def preview(text, course, year):
    items, seen = [],set()
    for raw in plain(text).splitlines():
        line=re.sub(r'[*_]+','',raw).strip()
        if not line or not ACTION.search(line): continue
        # A work named Interview is reading material, not an interview obligation.
        if re.search(r'no class|no (?:final )?exam|last day to (?:add|drop)|\boptional\b|\bopcional\b',line,re.I): continue
        matches=list(DATE_PATTERN.finditer(line))
        # Several columns/dates or a policy paragraph are not a single obligation.
        if len(matches)>1 or re.search(r'policy|slip day|students|grade report|LPS score|SAT II',line,re.I):continue
        match=matches[0] if matches else None
        if match and match[4] and re.search(r'(?:day|día|page|pp\.?)\s*$',line[:match.start()],re.I):
            # Fractions such as presentation day 1/3 are not dates.
            continue
        day=None
        if match:
            try:
                if match[1]: day=Date(int(match[1]),int(match[2]),int(match[3]))
                elif match[4]:
                    y=int(match[6]) if match[6] else year
                    if y<100:y+=2000
                    day=Date(y,int(match[4]),int(match[5]))
                else:day=Date(int(match[9] or year),MONTHS[match[7].lower()],int(match[8]))
            except ValueError:pass
        # Policies and generic assessment descriptions do not become task candidates.
        if not match and (len(line)>160 or not re.match(r'(?:Final (?:project|exam)|Essay|Homework|Quiz|Exam|Assignment|Problem set|Peer edits)\b.*?(?:due|deadline|TBA|TBD)',line,re.I)):continue
        title=(line[:match.start()]+line[match.end():]).strip(' ,:–—-') if match else line
        title=re.sub(r'^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day|sday|nesday|rsday|urday)?[,.]?\s*','',title,flags=re.I)
        title=re.sub(r'\s*(?:due|deadline|by|on)\s*$', '',title,flags=re.I).strip()
        clock=CLOCK.search(title)
        at=None
        if clock and day:
            h=int(clock[1] or clock[4]); m=int(clock[2] or clock[5] or 0)
            if clock[3]:h=h%12+(12 if clock[3].lower()=='pm' else 0)
            try: at=time(h,m).strftime('%H:%M')
            except ValueError:pass
            title=(title[:clock.start()]+title[clock.end():]).strip()
        title=re.sub(r'(?:\s+(?:due|by|on))+(?:\s+via\s+\w+)?\s*$', '',title,flags=re.I).strip(' :,-')
        if not title:title='Course deadline'
        key=(title.casefold(),str(day))
        if key in seen:continue
        seen.add(key)
        items.append(ImportItem(title=title[:250],course=course,date=day,time=at,evidence=line,track=bool(day and day>=datetime.now(TZ).date())))
        if len(items)>250:raise ValueError('Import up to 250 dated items at a time')
    return items


def commit(store,items):
    """Commit selected dated items atomically, idempotently; preserve completions on reimport."""
    if any(not item.date for item in items):raise ValueError('Choose a date for each selected item, or leave it out')
    counts={'events':0,'tasks':0,'existing':0}
    with store.db() as db:
        for item in items:
            day=item.date.isoformat()
            sid='syllabus:'+hashlib.sha256(json.dumps([item.course.casefold(),item.title.casefold(),day]).encode()).hexdigest()[:32]
            prior=db.execute('SELECT id,linked_task_id FROM calendar_events WHERE source_id=?',(sid,)).fetchone()
            if prior:
                event_id=prior['id']; task_id=prior['linked_task_id'];counts['existing']+=1
                # Deliberately leave later user edits and completion state alone.
            else:
                event_id=db.execute('''INSERT INTO calendar_events(source_id,course,title,date,time,end_date,end_time,kind,notes,source)
                    VALUES(?,?,?,?,?,?,?,?,?,?)''',(sid,item.course,item.title,day,item.time,item.end_date.isoformat() if item.end_date else None,item.end_time,item.kind,item.evidence,item.source)).lastrowid
                task_id=None;counts['events']+=1
            if item.track and not task_id:
                due_at=datetime.combine(item.date,time.fromisoformat(item.time),TZ).isoformat() if item.time else None
                task_id=db.execute('''INSERT INTO tasks(identity,title,course,category,confidence,minutes,destination,created_at,updated_at,notebook_id,notebook_category,due_date,due_at,notes,calendar_event_id)
                    VALUES(?,?,?,'academic','confirmed',0,'Canvas',?,?,?,?,?,?,?,?)''',(sid,item.title,item.course,stamp(),stamp(),sid,'Academics / classes',None if due_at else day,due_at,item.evidence,event_id)).lastrowid
                db.execute('INSERT INTO evidence(task_id,source_id,source_type,quote,due_at,fingerprint,observed_at) VALUES(?,?,?,?,?,?,?)',(task_id,sid,'syllabus',item.evidence or item.title,due_at,sid,stamp()))
                db.execute('UPDATE calendar_events SET linked_task_id=? WHERE id=?',(task_id,event_id));counts['tasks']+=1
    return counts


def attach(app,store):
    from fastapi import HTTPException, Request
    from io import BytesIO

    @app.post('/api/import/preview')
    def import_preview(data:PreviewRequest):
        try:return {'items':[i.model_dump(mode='json') for i in preview(data.text,data.course,data.year)]}
        except ValueError as e:raise HTTPException(422,str(e))

    @app.post('/api/import/pdf-preview')
    async def pdf_preview(request:Request,course:str,year:int):
        from pypdf import PdfReader
        content=bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content)>15_000_000:raise HTTPException(413,'Use a PDF smaller than 15 MB')
        try:
            reader=PdfReader(BytesIO(content))
            if len(reader.pages)>100:raise ValueError('Use a PDF with up to 100 pages')
            # Flattened multi-column PDF rows can associate a lecture date with a
            # different assignment. Use reading order, then admit only clean lines.
            text='\n'.join(page.extract_text() or '' for page in reader.pages)
            text='\n'.join(line for line in text.splitlines() if not re.search(r'https?://|download.?frd|wrap=',line,re.I))
            data=PreviewRequest(text=text,course=course,year=year)
            return {'items':[i.model_dump(mode='json') for i in preview(data.text,data.course,data.year)]}
        except Exception:raise HTTPException(422,'Could not read this PDF. Paste its dated assignment lines instead.')

    @app.post('/api/import/commit')
    def import_commit(data:CommitRequest):
        try:return commit(store,data.items)
        except ValueError as e:raise HTTPException(422,str(e))
