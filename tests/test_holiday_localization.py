"""Pinned-library names, stable v1 identities and read-only HTTP projections (#174)."""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from unittest.mock import patch

import holidays
import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.services import calendar_presets as presets
from backend.services.holiday_names import _names
from test_api import api
from test_initial_draft_v4 import rich


def regional(country='RU', **kwargs):
    return dict(country=country, version=presets.VERSION, language='en_US', **kwargs)


def rows(r, locale=None, year=2026):
    return presets.occurrences(r, f'{year}-01-01', f'{year}-12-31', display_language=locale)


def without_names(events):
    return [{k:v for k,v in e.items() if k != 'name'} for e in events]


def test_ru_exact_names_and_legacy_ids():
    r=regional();before=deepcopy(r)
    english=rows(r);russian=rows(r,'ru_RU')
    names={e['date']:e['name'] for e in russian}
    assert names['2026-01-01']=='Новогодние каникулы'
    assert names['2026-01-07']=='Рождество Христово'
    assert names['2026-05-09']=='День Победы'
    assert without_names(russian)==without_names(english)
    for e in english:
        expected='regional:'+sha256(('RU\0'+e['name']).encode()).hexdigest()[:20]+':'+e['date']
        assert e['id']==expected
    assert rows(r,'ru-RU')==russian
    assert rows(r,'en-US')==english
    assert r==before


@pytest.mark.parametrize('country',presets.COUNTRIES)
@pytest.mark.parametrize('year',range(2025,2031))
def test_all_catalog_countries_years_and_fallback(country,year):
    r=regional(country,observed=True)
    english=rows(r,year=year);russian=rows(r,'ru',year)
    assert without_names(english)==without_names(russian)
    assert rows(r,'unsupported_LOCALE',year)==english
    if country!='RU':
        assert russian==english  # Verified supported_languages in holidays 0.87.
    else:
        expected=holidays.country_holidays(country,years=year,language='ru',observed=True)
        assert {(e['date'],e['name']) for e in russian}=={(d.isoformat(),n) for d in expected for n in expected.get_list(d)}


@pytest.mark.parametrize('country,subdivision,locale',[
    ('DE','BY','de-DE'),('CA','QC','fr-CA'),('US','CA','th'),('GB','ENG','th'),('FR','57','fr')])
def test_subdivision_observed_and_localized_rules(country,subdivision,locale):
    r=regional(country,subdivision=subdivision,observed=True)
    language={'de-DE':'de','fr-CA':'fr'}.get(locale,locale)
    for year in range(2025,2031):
        english=rows(r,year=year);localized=rows(r,locale,year)
        assert without_names(localized)==without_names(english)
        expected=holidays.country_holidays(country,subdiv=subdivision,years=year,language=language,observed=True)
        assert {(e['date'],e['name']) for e in localized}=={(d.isoformat(),n) for d in expected for n in expected.get_list(d)}


def test_multi_holiday_date_keeps_name_identity_pairing():
    # Two real holidays on the same date; sorting changes in French.
    r=regional('FR',subdivision='973')
    day='2030-06-10'
    en={e['name']:e for e in rows(r,year=2030) if e['date']==day}
    fr={e['id']:e for e in rows(r,'fr',2030) if e['date']==day}
    assert len(fr)==len(en)==2
    assert fr[en['Abolition of Slavery']['id']]['name']=="Abolition de l'esclavage"
    assert fr[en['Whit Monday']['id']]['name']=='Lundi de Pentecôte'


def test_overrides_before_localization_and_cross_year_move():
    r=regional(observed=True)
    originals=rows(r,year=2025)
    r['overrides']=[dict(id=originals[0]['id'],name='Our New Year',date='2026-01-10'),
                    dict(id=originals[1]['id'],removed=True),
                    dict(id=originals[6]['id'],date='2026-01-11')]
    before=deepcopy(r)
    localized=rows(r,'ru_RU');english=rows(r)
    moved=next(e for e in localized if e['id']==originals[0]['id'])
    assert moved['name']=='Our New Year' and moved['date']=='2026-01-10'
    assert moved['original_date']=='2025-01-01'
    assert next(e for e in localized if e['id']==originals[6]['id'])['name']=='Рождество Христово'
    assert originals[1]['id'] not in {e['id'] for e in rows(r,'ru',2025)}
    assert without_names(localized)==without_names(english)
    assert r==before


def test_missing_catalog_translation_and_environment_fallback(monkeypatch):
    monkeypatch.setenv('LANGUAGE','ru')
    monkeypatch.setenv('LANG','ru_RU.UTF-8')
    assert rows(regional(),'zz_ZZ')==rows(regional())
    _names.cache_clear()
    with patch('backend.services.holiday_names.holidays.country_holidays',side_effect=OSError('missing catalog')):
        # Source validation stays available; only the display lookup fails.
        with patch('backend.services.calendar_presets.source',return_value=holidays.RU(language='en_US')):
            from backend.services.holiday_names import localized_names
            assert localized_names(regional(),[2026],'ru')=={}
    source=presets.source('RU');target=holidays.country_holidays('RU',language='th')
    from backend.services.holiday_names import _translator
    key='День Победы'
    target.tr.__self__._catalog=dict(target.tr.__self__._catalog)
    target.tr.__self__._catalog.pop(key,None)
    assert _translator(source,target)('Victory Day')=='Victory Day'
    _names.cache_clear()


def checked(response):
    assert response.status_code==200,response.text
    return response.json()


def test_http_legacy_draft_export_import_confirm_reload_and_locale_switch(api):
    client,app=api;repo=app.state.repository
    state=presets.apply(rich(),dict(holidays='country',country='RU',seasons='north'),True)
    state['world_clock']['calendar']['start_date']='2026-01-01'
    state['world_clock']['calendar']['start_minute']=state['world_clock']['minute']
    profile=state['world_clock']['calendar']['profile'];r=profile['regional']
    base=rows(r)
    r['overrides']=[dict(id=base[0]['id'],name='Авторский Новый год',date='2026-01-10'),dict(id=base[1]['id'],removed=True)]
    cid=state['controlled_actor_id']
    profile['observances']=[dict(id='personal',name='Our anniversary',month=1,day=7,character_ids=[cid])]
    wid=checked(client.post('/api/workspaces',json={'name':'Legacy English calendar'}))['id']
    url=f'/api/workspaces/{wid}/draft'
    checked(client.post(url+'/import',json=dict(revision=0,format='json',text=json.dumps(state))))
    initial=repo.draft(wid,True)
    for language in ('ru_RU','en_US','unsupported'):
        preview=checked(client.get(url+'/calendar-preview',params={'display_language':language}))
        assert any(e['name']=='Авторский Новый год' for e in preview['events'])
        assert any(e['name']==('Рождество Христово' if language=='ru_RU' else 'Christmas Day') for e in preview['events'])
        proposed=checked(client.post(url+'/calendar-preview',params={'display_language':language},json={'holidays':'country','country':'RU'}))
        assert proposed['events']==preview['events']
        assert repo.draft(wid,True)==initial
    exported=client.get(url+'/export',params=dict(version_id=initial['version_id'],format='json'))
    assert exported.status_code==200
    assert exported.json()['world_clock']['calendar']['profile']==initial['state']['world_clock']['calendar']['profile']
    wid2=checked(client.post('/api/workspaces',json={'name':'Imported'}))['id']
    url2=f'/api/workspaces/{wid2}/draft'
    imported=checked(client.post(url2+'/import',json=dict(revision=0,format='json',text=exported.text)))
    assert imported['state']['world_clock']['calendar']['profile']==initial['state']['world_clock']['calendar']['profile']
    started=checked(client.post(url2+'/confirm',json=dict(revision=imported['revision'],version_id=imported['version_id'],accept_warnings=True)))
    sid=started['save'];snapshot=repo.get_snapshot(sid)
    with repo.connect() as db: before='\n'.join(db.iterdump())
    with TestClient(create_app(repo.path)) as reopened:
        for language in ('ru_RU','en_US','zz'):
            params=dict(start_date='2026-01-01',end_date='2026-01-31',display_language=language)
            events=checked(reopened.get(f'/api/saves/{sid}/calendar',params=params))['events']
            assert any(e['name']=='Our anniversary' and e['character_ids']==[cid] for e in events)
            regional_events=[e for e in events if e.get('source')==presets.VERSION]
            assert regional_events==presets.occurrences(r,'2026-01-01','2026-01-31',display_language=language)
            overview=checked(reopened.get(f'/api/saves/{sid}/calendar',params={'display_language':language}))
            assert overview['regional']==regional_events
    assert repo.get_snapshot(sid)==snapshot
    with repo.connect() as db: assert '\n'.join(db.iterdump())==before


def test_creation_preview_language_is_not_source_language(api):
    client,_=api
    body=dict(world_type='real_world',geography='Россия, Москва',calendar_start=dict(date='2026-01-01',presets=dict(holidays='country',country='RU')))
    ru=checked(client.post('/api/calendar/preview',json=body))
    en=checked(client.post('/api/calendar/preview?display_language=en_US',json=body))
    assert ru['regional']['language']==en['regional']['language']=='en_US'
    assert ru['events'][0]['name']=='Новогодние каникулы'
    assert en['events'][0]['name']=='New Year Holidays'
    assert without_names(ru['events'])==without_names(en['events'])
