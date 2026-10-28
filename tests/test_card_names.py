import pytest
from dashboard.manual import ManualScenario, editable_inputs
from dashboard.scenarios import parse_scenario
from dashboard.report import render
from dashboard.timeline import render_timeline
from dashboard.input_review import render_inputs
from test_multi_manual import scenario, card
from test_dashboard_manual import fields, web, token
from test_recurring_cash import submit, hidden


def test_names_do_not_change_calculations_and_survive_roundtrip():
    original=scenario(card())
    named=scenario(card(card_name='Travel'),card_name='Everyday')
    assert original.project()==named.project()
    assert named.card_names==('Everyday','Travel')
    loaded=parse_scenario(named.model_dump_json().encode())
    assert ManualScenario.model_validate(editable_inputs(loaded)).scenario()==named
    for output in (render(named),render_timeline(named),render_inputs(named)):
        assert 'Everyday' in output and 'Travel' in output


def test_names_escape_markup_and_keep_duplicate_names_distinguishable():
    named=scenario(card(card_name='<Travel>'),card_name='<Travel>')
    html=render(named)
    assert '<Travel>' not in html
    assert '&lt;Travel&gt; (card)' in html and '&lt;Travel&gt; (card-2)' in html


@pytest.mark.parametrize('updates',[{'card_name':'a'*61},{'card_name':123}])
def test_invalid_names_rejected(updates):
    with pytest.raises(ValueError):ManualScenario.model_validate(fields()|updates)


def test_name_count_must_match_existing_accounts():
    from engine.common import reconstruct
    with pytest.raises(ValueError):reconstruct(scenario(card()),card_names=('Only one',))


def test_only_nickname_does_not_create_incomplete_card():
    with pytest.raises(ValueError):ManualScenario.model_validate(fields()|{'card_2_card_name':'Travel'})


def test_optional_name_preserved_through_http_preview(web):
    values=fields()|{'card_name':'My card','token':token(web)}
    status,_,html=submit(web,'/preview-example',values)
    assert status==200 and 'My card (card)' in html
    assert hidden(html)['card_name']=='My card'
    assert not list(web[1].glob('*.json'))
