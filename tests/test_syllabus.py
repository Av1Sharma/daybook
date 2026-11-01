from datetime import date
import pytest
from fastapi.testclient import TestClient
from meridian.app import create_app
from meridian.syllabus import ImportItem, commit, preview
from meridian.store import Store


def test_numeric_month_names_date_only_and_clock():
    items=preview('11/9 Essay #3 Due\nNovember 13 Peer edits due by 5pm\nHand in journals 12/2','Literature',2026)
    assert [(i.title,str(i.date),i.time) for i in items] == [('Essay #3','2026-11-09',None),('Peer edits','2026-11-13','17:00'),('Hand in journals','2026-12-02',None)]


def test_no_reading_interview_policy_or_invented_tba():
    items=preview('12/7 Poet, “Interview”; Writer, “Rain”\nNo final exam\nExam policies: missed exams cannot be made up\nFinal project due TBA','Writing',2026)
    assert len(items)==1 and items[0].date is None and not items[0].track


def test_repeated_journals_keep_distinct_dates():
    items=preview('9/14 Hand in line journals\n10/5 Hand in line journals','Writing',2026)
    assert len(items)==2 and items[0].date != items[1].date


def test_past_defaults_to_calendar_not_backlog():
    items=preview('1/2/2020 Essay due','Writing',2026)
    assert not items[0].track and items[0].date==date(2020,1,2)


def test_atomic_validation_and_reimport_completion(tmp_path):
    store=Store(tmp_path/'test.db')
    item=ImportItem(title='Essay',course='Writing',date='2026-11-09',track=True,evidence='11/9 Essay due')
    assert commit(store,[item])=={'events':1,'tasks':1,'existing':0}
    with store.db() as db:
        db.execute('UPDATE tasks SET completed=1')
    assert commit(store,[item])=={'events':0,'tasks':0,'existing':1}
    with store.db() as db:
        assert db.execute('SELECT completed,due_date,due_at FROM tasks').fetchone()[:] == (1,'2026-11-09',None)
    with pytest.raises(ValueError):commit(store,[item,ImportItem(title='Unknown',course='Writing')])
    with store.db() as db:assert db.execute('SELECT count(*) FROM calendar_events').fetchone()[0]==1


def test_preview_saves_nothing_and_commit_needs_dates(tmp_path):
    app=create_app(tmp_path/'api.db')
    with TestClient(app) as client:
        client.headers['X-Meridian-Token']=client.get('/api/state').json()['token']
        items=client.post('/api/import/preview',json={'text':'11/9 Essay due','course':'Writing','year':2026}).json()['items']
        assert client.get('/api/state').json()['tasks']==[]
        assert client.get('/api/notebook').json()['events']==[]
        assert client.post('/api/import/commit',json={'items':[dict(items[0],date=None,time=None)]}).status_code==422
        assert client.post('/api/import/commit',json={'items':items}).status_code==200
        assert len(client.get('/api/state').json()['tasks'])==1
        assert client.post('/api/import/commit',json={'items':items}).json()['existing']==1
        client.headers.pop('X-Meridian-Token')
        assert client.post('/api/import/commit',json={'items':items}).status_code==403
