from dashboard.scenarios import save_scenario,parse_scenario
from dashboard.strategies import strategy_example,selected_strategy
from engine.common import reconstruct
from test_dashboard_manual import web,call


def test_backup_roundtrip_preserves_priorities_and_never_writes(web):
    candidate=selected_strategy(strategy_example(),'smallest-balance')
    id_='a'*32;path=web[1]/(id_+'.json');save_scenario(candidate,path)
    before=path.read_bytes()
    status,headers,raw=call(web,'GET','/backup/'+id_)
    assert status==200
    assert headers['Content-Type']=='application/json; charset=utf-8'
    assert headers['Cache-Control']=='no-store'
    assert headers['X-Content-Type-Options']=='nosniff'
    assert headers['Content-Disposition']==f'attachment; filename="debt-shredder-{id_}.json"'
    loaded=parse_scenario(raw.encode())
    assert loaded==candidate and loaded.project()==candidate.project()
    assert path.read_bytes()==before and len(list(web[1].glob('*.json')))==1
    html=call(web,'GET','/scenario/'+id_)[2]
    assert 'Download scenario backup' in html and 'Restore a backup' in html


def test_backup_filename_never_uses_scenario_name(web):
    id_='b'*32
    save_scenario(reconstruct(strategy_example(),name='Name " <unsafe>\r\nHeader: x'),web[1]/(id_+'.json'))
    status,headers,raw=call(web,'GET','/backup/'+id_)
    assert status==200 and 'unsafe' not in headers['Content-Disposition']
    assert parse_scenario(raw.encode()).name.startswith('Name')


def test_backup_rejects_invalid_file_and_unknown_paths(web):
    id_='a'*32;path=web[1]/(id_+'.json');path.write_text('{broken')
    assert call(web,'GET','/backup/'+id_)[0]==422
    assert path.read_text()=='{broken'
    assert call(web,'GET','/backup/'+'b'*32)[0]==404
    assert call(web,'GET','/backup/../../SCHEMA.py')[0]==404
    assert call(web,'GET','/backup/'+id_,headers={'Host':'untrusted.example'})[0]==403
