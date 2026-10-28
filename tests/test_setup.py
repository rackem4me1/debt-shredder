from html.parser import HTMLParser
from dashboard.forms import manual_form
from test_dashboard_manual import web, call, token, fields
from test_recurring_cash import submit


class Controls(HTMLParser):
    def __init__(self, html):
        super().__init__();self.names=[];self.scripts=[];self.steps=[];self.feed(html)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in ('input','select') and 'name' in attrs:self.names.append(attrs['name'])
        if tag=='script':self.scripts.append(attrs.get('src'))
        if 'data-setup-step' in attrs:self.steps.append(attrs['data-setup-step'])


def test_progressive_form_preserves_all_fields_without_script():
    html=manual_form('test')
    parsed=Controls(html)
    assert len(parsed.names)==len(set(parsed.names))
    assert set(fields()) <= set(parsed.names)
    assert set(parsed.steps)=={'0','1','2','3'}
    assert parsed.scripts==['/setup.js']
    assert 'novalidate' not in html  # Native validation remains if script cannot load.
    assert '<fieldset hidden' not in html


def test_setup_asset_is_local_fixed_path_and_not_financial_data(web):
    status,headers,body=call(web,'GET','/setup.js')
    assert status==200 and headers['Content-Type'].startswith('text/javascript')
    assert "script-src 'self'" in headers['Content-Security-Policy']
    assert 'localStorage' not in body and 'fetch(' not in body
    assert call(web,'GET','/dashboard/setup.js')[0]==404
    assert not list(web[1].glob('*.json'))


def test_error_recovery_keeps_values_and_practice_mode(web):
    values=fields()|{'token':token(web),'minimum_remaining':'501','cash_0_label':'Paycheck'}
    status,_,html=submit(web,'/preview-example',values)
    assert status==422 and 'role="alert"' in html
    assert 'value="501"' in html and 'value="Paycheck"' in html
    assert 'action="/preview-example"' in html and '<details open>' in html
    assert not list(web[1].glob('*.json'))
