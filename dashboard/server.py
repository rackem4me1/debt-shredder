"""Loopback-only local UI. No external assets, remote accounts or payment actions."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
from pathlib import Path
import re
import secrets
from threading import Lock
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
from pydantic import ValidationError
from dashboard.forms import shell, manual_form, validation_messages
from dashboard.manual import ManualScenario, editable_inputs
from dashboard.scenarios import save_scenario, load_scenario, parse_scenario, MAX_BYTES
from dashboard.report import render
from dashboard.comparison import render_comparison, selector
from dashboard.guidance import practice_inputs
from dashboard.input_review import render_inputs
from dashboard.timeline import render_timeline
from dashboard.preview import render_preview
from dashboard.strategies import render_strategies, strategy_example, render_strategy_review, selected_strategy, strategy_fingerprint, payment_order
from dashboard.payment_edit import payment_form, change_payments, payment_preview
from dashboard.multimonth import render_example as render_multimonth
from dashboard.portfolio_forecast import render_example as render_portfolio_forecast
from dashboard.library import render_library
from dashboard.identity import application_identity
from dashboard import my_money, bills, payday_cash, paycheck_week, payoff_view, payoff_repeat, payoff_runs, mixed_payoff_runs, payoff_setup, setup_plan, setup_plan_view, setup_backup, weekly_check, weekly_snapshots
from dashboard.simple_view import saved_plan, walkthrough
from dashboard.forecast_terms import terms_form, change_terms, terms_preview
from dashboard.personal_forecast import form as personal_forecast_form, preview as personal_forecast_preview
from dashboard.restore import restore_form, restore_preview, review_signature
from engine.common import reconstruct
from demo_portfolio import scenario as demo_scenario

MAX_FORM = 32 * 1024


def make_server(directory: Path, port=8765):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    identity = application_identity(Path(__file__).resolve().parent.parent, directory)
    token = secrets.token_urlsafe(32)
    money_lock=Lock()
    bills_lock=Lock()
    cash_lock=Lock()
    setup_lock=Lock()

    def saved_choices():
        choices=[]
        for file in sorted(directory.glob('*.json')):
            if not re.fullmatch(r'[0-9a-f]{32}',file.stem):continue
            try:choices.append((file.stem,load_scenario(file).name))
            except (ValueError,OSError,ArithmeticError):continue
        return choices

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass  # Do not log financial form values or scenario names.

        def send_html(self, html, status=200, *, content_type='text/html; charset=utf-8'):
            encoded=html.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(encoded)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(encoded)

        def valid_host(self):
            host=self.headers.get('Host','')
            return host in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}

        def reject(self, message, status):
            self.send_html(shell('Request not accepted',f'<h1>Request not accepted</h1><p>{escape(message)}</p><a href="/">Return home</a>'),status)

        def do_GET(self):
            if not self.valid_host():
                return self.reject('Open this app using its local address.',403)
            path=urlsplit(self.path).path
            if path=='/app-identity':
                import json
                return self.send_html(json.dumps(identity), content_type='application/json; charset=utf-8')
            if path=='/weekly-checks':
                if urlsplit(self.path).query:return self.reject('Open saved weekly comparisons without extra parameters.',400)
                return self.send_html(weekly_snapshots.library(directory))
            weekly_saved=re.fullmatch(r'/weekly-checks/([0-9a-f]{32})(/(?:inputs\.json|summary\.csv))?',path)
            if weekly_saved:
                if urlsplit(self.path).query:return self.reject('Saved weekly comparisons retain their original inputs. Open the current report to test changes.',400)
                try:
                    snapshot=weekly_snapshots.load(directory,weekly_saved[1])
                    if weekly_saved[2]=='/inputs.json':return self.send_html(snapshot.model_dump_json(indent=2),content_type='application/json; charset=utf-8')
                    if weekly_saved[2]=='/summary.csv':return self.send_html(weekly_snapshots.summary_csv(snapshot),content_type='text/csv; charset=utf-8')
                    return self.send_html(weekly_snapshots.render(snapshot,weekly_saved[1]))
                except FileNotFoundError:return self.reject('This weekly comparison was not found.',404)
                except (ValueError,ArithmeticError):return self.reject('This weekly comparison could not be validated. Its file has been kept.',422)
                except OSError:return self.reject('Could not open this weekly comparison.',500)
            if path=='/weekly-check':
                try:
                    value=weekly_check.load(directory);query=urlsplit(self.path).query
                    try:snapshot=weekly_snapshots.prepare(value,query)
                    except (ValueError,ArithmeticError) as exc:return self.send_html(weekly_check.render_error(value,query,str(exc)),422)
                    return self.send_html(weekly_check.render(value,query,save_section=weekly_snapshots.save_form(snapshot,token)))
                except FileNotFoundError:return self.reject('No weekly system report has been prepared yet.',404)
                except (ValueError,ArithmeticError):return self.reject('The weekly comparison needs valid planning inputs and nonnegative whole-cent amounts. Saved records are unchanged.',422)
                except OSError:return self.reject('Could not read the weekly planning reference.',500)
            if path=='/setup':return self.send_html(payoff_setup.counts_form(token,has_saved=(directory/'money_snapshot.json').exists()))
            if path=='/setup/drafts':return self.send_html(payoff_setup.library(directory))
            if path=='/setup/restore':return self.send_html(setup_backup.form(token))
            complete_backup=re.fullmatch(r'/setup/([0-9a-f]{32})/complete-backup.json',path)
            if complete_backup:
                try:
                    with setup_lock:backup=setup_backup.capture(directory,complete_backup[1])
                    return self.send_html(backup.model_dump_json(indent=2),content_type='application/json; charset=utf-8')
                except FileNotFoundError:return self.reject('This account setup was not found.',404)
                except (ValueError,ArithmeticError):return self.reject('The complete setup could not be validated. Existing files have been kept.',422)
                except OSError:return self.reject('Could not read the complete setup.',500)
            plan_match=re.fullmatch(r'/setup/([0-9a-f]{32})/plan(?:/(settings|balances|terms/(?:card|loan)-[1-9][0-9]?|flow/[0-9a-f]{32}))?',path)
            if plan_match:
                try:
                    identifier=plan_match[1];wizard=payoff_setup.load(directory,identifier);planning=setup_plan.load(directory,identifier);action=plan_match[2]
                    if action is None:return self.send_html(setup_plan_view.overview(wizard,planning,identifier,token))
                    if action=='settings':return self.send_html(setup_plan_view.settings_form(wizard,planning,identifier,token))
                    if action=='balances':return self.send_html(setup_plan_view.balances_form(wizard,planning,identifier,token))
                    if action.startswith('terms/'):
                        account=action.split('/')[1]
                        if account not in {a.account_id for a in wizard.accounts if a.kind in ('card','loan')}:return self.reject('This debt was not found.',404)
                        return self.send_html(setup_plan_view.terms_form(wizard,planning,identifier,account,token))
                    flow=next((f for f in planning.flows if f.flow_id==action.split('/')[1]),None)
                    if flow is None:return self.reject('This cash event was not found.',404)
                    return self.send_html(setup_plan_view.flow_form(wizard,planning,identifier,flow,token))
                except FileNotFoundError:return self.reject('This account setup was not found.',404)
                except (ValueError,ArithmeticError):return self.reject('The saved planning inputs could not be validated. Existing files have been kept.',422)
                except OSError:return self.reject('Could not read the planning inputs.',500)
            setup_match=re.fullmatch(r'/setup/([0-9a-f]{32})(?:/(?:account/([0-9]+)|(backup.json)))?',path)
            if setup_match:
                try:
                    wizard=payoff_setup.load(directory,setup_match[1])
                    if setup_match[3]:return self.send_html(wizard.model_dump_json(indent=2),content_type='application/json; charset=utf-8')
                    if setup_match[2] is not None:
                        step=int(setup_match[2])
                        if not 0<=step<len(wizard.accounts):return self.reject('This account step was not found.',404)
                        return self.send_html(payoff_setup.account_form(wizard,setup_match[1],step,token))
                    return self.send_html(payoff_setup.summary(wizard,setup_match[1],token))
                except FileNotFoundError:return self.reject('This account setup was not found.',404)
                except (ValueError,ArithmeticError):return self.reject('This account setup could not be validated. Its file has been kept.',422)
                except OSError:return self.reject('Could not open the saved account setup.',500)
            if path in ('/mixed-payoff-example','/mixed-payoff-example/inputs.json','/mixed-payoff-example/highest-interest.csv','/mixed-payoff-example/smallest-balance.csv'):
                from dashboard.mixed_payoff_view import sample,render as render_mixed
                from engine.mixed_payoff import plan_mixed_payoff
                from payoff_exports import payment_csv
                try:
                    query=urlsplit(self.path).query
                    if len(query)>100:raise ValueError('Payment target is too long')
                    value=sample(parse_qs(query,keep_blank_values=True,max_num_fields=2))
                    if path.endswith('/inputs.json'):return self.send_html(value.model_dump_json(indent=2),content_type='application/json; charset=utf-8')
                    if path.endswith('.csv'):
                        strategy='highest_interest_first' if path.endswith('/highest-interest.csv') else 'smallest_balance_first'
                        return self.send_html(payment_csv(plan_mixed_payoff(value,strategy)),content_type='text/csv; charset=utf-8')
                    run=mixed_payoff_runs.MixedPayoffRun(name='Sample cards and loan: shared '+str(value.payment_target)+' target',origin='synthetic_demo',inputs=value)
                    return self.send_html(render_mixed(value,mixed_payoff_runs.save_form(run,token)))
                except (ValueError,ArithmeticError) as exc:return self.reject(str(exc),400)
            if path=='/mixed-payoff/import':return self.send_html(mixed_payoff_runs.import_form(token))
            mixed_run=re.fullmatch(r'/mixed-payoff-run/([0-9a-f]{32})(?:/(inputs.json|summary.json|highest-interest.csv|smallest-balance.csv))?',path)
            if path=='/mixed-payoff-runs' or mixed_run:
                try:
                    if not mixed_run:return self.send_html(mixed_payoff_runs.library(directory))
                    run=mixed_payoff_runs.load(directory,mixed_run[1]);kind=mixed_run[2]
                    if kind=='inputs.json':return self.send_html(run.inputs.model_dump_json(indent=2),content_type='application/json; charset=utf-8')
                    if kind=='summary.json':
                        import json
                        from payoff_cli import mixed_summary
                        from engine.mixed_payoff import compare_mixed_payoff
                        return self.send_html(json.dumps(mixed_summary(compare_mixed_payoff(run.inputs)),indent=2),content_type='application/json; charset=utf-8')
                    if kind:
                        from engine.mixed_payoff import plan_mixed_payoff
                        from payoff_exports import payment_csv
                        strategy='highest_interest_first' if kind=='highest-interest.csv' else 'smallest_balance_first'
                        return self.send_html(payment_csv(plan_mixed_payoff(run.inputs,strategy)),content_type='text/csv; charset=utf-8')
                    return self.send_html(mixed_payoff_runs.render_saved(run,mixed_run[1]))
                except FileNotFoundError:return self.reject('This combined payoff run was not found.',404)
                except (ValueError,ArithmeticError):return self.reject('This combined payoff run could not be validated. Its file has been kept.',422)
                except OSError:return self.reject('The combined payoff run could not be opened.',500)
            if path in ('/loan-payoff-example','/loan-payoff-example/inputs.json','/loan-payoff-example/payments.csv'):
                from demo_payoff import loan_example
                from dashboard.loan_payoff_view import render as render_loan
                from engine.loan_payoff import plan_loan_payoff
                from payoff_exports import loan_payment_csv
                value=loan_example()
                if path.endswith('/inputs.json'):return self.send_html(value.model_dump_json(indent=2),content_type='application/json; charset=utf-8')
                if path.endswith('/payments.csv'):return self.send_html(loan_payment_csv(plan_loan_payoff(value)),content_type='text/csv; charset=utf-8')
                return self.send_html(render_loan(value))
            run_export=re.fullmatch(r'/payoff-run/([0-9a-f]{32})/(inputs.json|template.json|highest-interest.csv|smallest-balance.csv)',path)
            if run_export:
                try:
                    run=payoff_runs.load(directory,run_export[1]);kind=run_export[2]
                    if kind in ('inputs.json','template.json'):
                        data=run.expanded.inputs if kind=='inputs.json' else run.expanded.template
                        return self.send_html(data.model_dump_json(indent=2),content_type='application/json; charset=utf-8')
                    from engine.payoff import plan_payoff
                    from payoff_exports import payment_csv
                    from dashboard.report import card_label
                    strategy='highest_interest_first' if kind=='highest-interest.csv' else 'smallest_balance_first'
                    plan=plan_payoff(run.expanded.inputs,strategy)
                    return self.send_html(payment_csv(plan,lambda account:card_label(run.source,account)),content_type='text/csv; charset=utf-8')
                except FileNotFoundError:return self.reject('This payoff run was not found.',404)
                except (ValueError,OSError,ArithmeticError):return self.reject('The payoff export could not be calculated. Its saved file has been kept.',422)
            run_match=re.fullmatch(r'/payoff-run/([0-9a-f]{32})',path)
            if path=='/payoff-runs' or run_match:
                try:return self.send_html(payoff_runs.library(directory) if not run_match else payoff_runs.render(payoff_runs.load(directory,run_match[1]),run_match[1]))
                except FileNotFoundError:return self.reject('This saved payoff run was not found.',404)
                except (ValueError,ArithmeticError,OSError):return self.reject('This saved payoff run could not be opened. Its file has been kept.',422)
            week_match=re.fullmatch(r'/week-draft/([0-9a-f]{32})',path)
            if path in ('/paycheck-week','/paycheck-week/settings','/paycheck-week/saved') or week_match:
                try:
                    if path.endswith('/saved'):return self.send_html(paycheck_week.library(directory))
                    if path.endswith('/settings'):return self.send_html(paycheck_week.form(paycheck_week.load_settings(directory),token))
                    if week_match:return self.send_html(paycheck_week.render(paycheck_week.load_draft(directory,week_match[1]),saved=True))
                    return self.send_html(paycheck_week.render(paycheck_week.load_inputs(directory),token))
                except FileNotFoundError:return self.reject('The balances, bills, cushions or paycheck settings needed for this view have not been saved.',404)
                except (ValueError,ArithmeticError) as exc:return self.reject(str(exc),422)
                except OSError:return self.reject('Could not open the week draft. Its files have been kept.',422)
            cash_draft_match=re.fullmatch(r'/cash-draft/([0-9a-f]{32})',path)
            if path in ('/cash-until-payday','/cash-until-payday/budget','/cash-until-payday/saved') or cash_draft_match:
                try:
                    if path.endswith('/saved'):return self.send_html(payday_cash.library(directory))
                    if path.endswith('/budget'):return self.send_html(payday_cash.budget_form(payday_cash.load_budget(directory),token))
                    if cash_draft_match:return self.send_html(payday_cash.render(payday_cash.load_draft(directory,cash_draft_match[1]),saved=True))
                    return self.send_html(payday_cash.render(payday_cash.load_inputs(directory),token))
                except FileNotFoundError:return self.reject('The balances, bill draft or spending cushions needed for this cash view have not been saved.',404)
                except (ValueError,ArithmeticError) as exc:return self.reject(str(exc),422)
                except OSError:return self.reject('Could not read the cash draft. Its files have been kept.',422)
            if path=='/bills' or re.fullmatch(r'/bills/edit/[a-z0-9-]{1,60}',path):
                try:
                    book=bills.load(directory)
                    if path=='/bills':return self.send_html(bills.render(book,my_money.load(directory)))
                    return self.send_html(bills.form(book,path.rsplit('/',1)[-1],token))
                except FileNotFoundError:return self.reject('No bill draft has been saved yet.',404)
                except KeyError:return self.reject('This bill was not found.',404)
                except (ValueError,ArithmeticError) as exc:return self.reject(str(exc),422)
                except OSError:return self.reject('Could not open the bill draft. Its file has been kept.',422)
            if path in ('/my-money','/my-money/edit'):
                try:
                    snapshot=my_money.load(directory)
                    return self.send_html(my_money.form(snapshot,token) if path.endswith('/edit') else my_money.render(snapshot,has_bills=(directory/bills.FILENAME).exists()))
                except FileNotFoundError:return self.send_html(shell('My Money','<h1>My Money</h1><p>No starting picture has been saved yet. Your existing plans are available from home.</p><a href="/">Back home</a>'))
                except (ValueError,OSError,ArithmeticError):return self.reject('Your starting picture could not be opened. Its file has been kept.',422)
            if path in ('/walkthrough','/walkthrough-shortage'):
                return self.send_html(walkthrough(path=='/walkthrough-shortage'))
            simple_match=re.fullmatch(r'/plan/([0-9a-f]{32})',path)
            if simple_match:
                try:
                    scenario=load_scenario(directory/(simple_match[1]+'.json'))
                    return self.send_html(saved_plan(scenario,simple_match[1],payoff_view.form_section(scenario,simple_match[1],token)+payoff_repeat.form_section(scenario,simple_match[1],token)+'<p><a href="/payoff-runs">Saved payoff runs</a></p>'))
                except FileNotFoundError:return self.reject('This saved plan was not found.',404)
                except (ValueError,OSError,ArithmeticError):return self.reject('This plan could not be opened. Its file has been kept.',422)
            if path=='/':
                entries=[]
                for file in sorted(directory.glob('*.json'), key=lambda p:p.name):
                    if not re.fullmatch(r'[0-9a-f]{32}',file.stem):continue
                    try:entries.append((file.stem,load_scenario(file)))
                    except (ValueError,OSError,ArithmeticError):entries.append((file.stem,None))
                try:return self.send_html(render_library(entries,urlsplit(self.path).query,has_money=(directory/my_money.FILENAME).exists(),setup_resume=payoff_setup.latest_personal(directory),has_weekly_check=(directory/weekly_check.FILENAME).exists()))
                except ValueError:return self.reject('Use the saved-scenario search form.',400)
            forecast_match=re.fullmatch(r'/personal-forecast/([0-9a-f]{32})',path)
            if forecast_match:
                try:return self.send_html(personal_forecast_form(load_scenario(directory/(forecast_match[1]+'.json')),forecast_match[1],token))
                except FileNotFoundError:return self.reject('The saved plan was not found.',404)
                except (ValueError,ArithmeticError) as exc:return self.reject(str(exc),422)
                except OSError:return self.reject('Could not read the saved plan.',500)
            terms_match=re.fullmatch(r'/forecast-terms/([0-9a-f]{32})',path)
            if terms_match:
                try:return self.send_html(terms_form(load_scenario(directory/(terms_match[1]+'.json')),terms_match[1],token))
                except FileNotFoundError:return self.reject('The saved plan was not found.',404)
                except (ValueError,OSError,ArithmeticError):return self.reject('The saved plan could not be reviewed.',422)
            if path=='/portfolio-forecast-example':return self.send_html(render_portfolio_forecast())
            if path=='/multimonth-example':return self.send_html(render_multimonth())
            if path=='/strategies-example':
                return self.send_html(render_strategies(strategy_example(), source="example"))
            strategies=re.fullmatch(r'/strategies/([0-9a-f]{32})',path)
            if strategies:
                try:return self.send_html(render_strategies(load_scenario(directory/(strategies[1]+'.json')), '/scenario/'+strategies[1], source=strategies[1]))
                except FileNotFoundError:return self.reject('This saved scenario was not found.',404)
                except (ValueError,OSError,ArithmeticError):return self.reject('This comparison could not be validated. Your saved scenario is unchanged.',422)
            strategy_review=re.fullmatch(r'/strategy-review/(example|[0-9a-f]{32})/(highest-interest|smallest-balance)',path)
            if strategy_review:
                source,choice=strategy_review.groups()
                try:
                    original=strategy_example() if source=='example' else load_scenario(directory/(source+'.json'))
                    return self.send_html(render_strategy_review(original,source,choice,token))
                except FileNotFoundError:return self.reject('The source scenario was not found.',404)
                except (ValueError,OSError,ArithmeticError):return self.reject('This alternative could not be validated. No scenario was saved.',422)
            if path=='/compare-example':
                left=reconstruct(demo_scenario(),name='Request $500 extra')
                right=reconstruct(left,name='Request $200 extra',requests=tuple(reconstruct(r,amount='200') if r.request_id=='extra-a' else r for r in left.requests))
                return self.send_html(render_comparison(left,right).replace('<h1>Compare two what-ifs</h1>', '<h1>Compare two what-ifs</h1><p>Example: both choices include two $50 minimum requests. The extra request changes from $500 to $200, so the total requested payments are $600 and $300.</p>',1))
            if path=='/compare':
                try:
                    params=parse_qs(urlsplit(self.path).query,keep_blank_values=True,max_num_fields=2,strict_parsing=True)
                    if set(params)-{'left','right'} or any(len(v)!=1 for v in params.values()):raise ValueError()
                    left=params.get('left',[''])[0];right=params.get('right',[''])[0]
                    if any(v and not re.fullmatch(r'[0-9a-f]{32}',v) for v in (left,right)):raise ValueError()
                except ValueError:return self.reject('Choose scenarios from the comparison page.',400)
                if not left or not right:return self.send_html(selector(saved_choices(),left,right))
                if left==right:return self.send_html(selector(saved_choices(),left,right,'Choose two different saved scenarios.'),422)
                try:
                    return self.send_html(render_comparison(load_scenario(directory/(left+'.json')),load_scenario(directory/(right+'.json'))))
                except FileNotFoundError:return self.reject('One of the selected scenarios was not found. Choose again from the comparison page.',404)
                except (ValueError,OSError,ArithmeticError):return self.reject('One of the selected scenarios could not be validated. Both files are unchanged.',422)
            backup=re.fullmatch(r'/backup/([0-9a-f]{32})',path)
            if backup:
                try:
                    saved=load_scenario(directory/(backup[1]+'.json'))
                    raw=(saved.model_dump_json(indent=2)+'\n').encode('utf-8')
                except FileNotFoundError:return self.reject('This saved scenario was not found.',404)
                except (ValueError,OSError,ArithmeticError):return self.reject('This scenario could not be validated for backup. Its file is unchanged.',422)
                self.send_response(200)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Content-Disposition',f'attachment; filename="debt-shredder-{backup[1]}.json"')
                self.send_header('Content-Length',str(len(raw)))
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Security-Policy',"default-src 'none'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(raw)
                return
            payment_edit=re.fullmatch(r'/payment-edit/([0-9a-f]{32})',path)
            if payment_edit:
                try:return self.send_html(payment_form(load_scenario(directory/(payment_edit[1]+'.json')),payment_edit[1],token))
                except FileNotFoundError:return self.reject('This saved scenario was not found.',404)
                except (ValueError,OSError,ArithmeticError):return self.reject('This scenario cannot be edited here. The saved file is unchanged.',422)
            if path=='/restore':return self.send_html(restore_form(token))
            if path=='/restore.js':
                return self.send_html(Path(__file__).with_name('restore.js').read_text(), content_type='text/javascript; charset=utf-8')
            if path=='/setup.js':
                return self.send_html(Path(__file__).with_name('setup.js').read_text(), content_type='text/javascript; charset=utf-8')
            if path=='/practice':return self.send_html(manual_form(token,practice_inputs(),sample=True))
            if path=='/new':return self.send_html(manual_form(token))
            if path=='/demo/timeline':return self.send_html(render_timeline(demo_scenario()))
            if path=='/demo':return self.send_html(render(demo_scenario()).replace('<main>','<main><p><a href="/">Back to scenarios</a> · <a href="/demo/timeline">See the payment timeline</a></p>',1))
            edit=re.fullmatch(r'/edit/([0-9a-f]{32})',path)
            if edit:
                try:
                    saved=load_scenario(directory/(edit[1]+'.json'))
                    values=editable_inputs(saved)
                    values['name']=(values['name'][:110]+' (copy)')
                    return self.send_html(manual_form(token,values,sample=saved.origin=='synthetic_demo').replace('<h1>Try a payment scenario</h1>', '<h1>Adjust a copy</h1><p>Your original stays unchanged. Change the payment or another input, then calculate to save a separate scenario.</p>'))
                except FileNotFoundError:return self.reject('This saved scenario was not found.',404)
                except (ValueError,OSError,ArithmeticError) as exc:return self.reject(str(exc),422)
            timeline=re.fullmatch(r'/timeline/([0-9a-f]{32})',path)
            if timeline:
                try:return self.send_html(render_timeline(load_scenario(directory/(timeline[1]+'.json'))).replace('<a href="/">Back to saved scenarios</a>',f'<a href="/scenario/{timeline[1]}">Back to result</a> · <a href="/">Back to saved scenarios</a>',1))
                except FileNotFoundError:return self.reject('This saved scenario was not found.',404)
                except (ValueError,OSError,ArithmeticError):return self.reject('This timeline could not be validated. Your saved scenario is unchanged.',422)
            review=re.fullmatch(r'/inputs/([0-9a-f]{32})',path)
            if review:
                try:return self.send_html(render_inputs(load_scenario(directory/(review[1]+'.json'))).replace('<a href="/">Back to saved scenarios</a>',f'<a href="/scenario/{review[1]}">Back to result</a> · <a href="/">Back to saved scenarios</a>',1))
                except FileNotFoundError:return self.reject('This saved scenario was not found.',404)
                except (ValueError,OSError,ArithmeticError):return self.reject('This scenario cannot be represented by the simple input review. Its saved report remains available.',422)
            match=re.fullmatch(r'/scenario/([0-9a-f]{32})',path)
            if match:
                try:
                    saved=load_scenario(directory/(match[1]+'.json'))
                    edit_notice=''
                    payment_link=f' · <a href="/payment-edit/{match[1]}">Adjust payment amounts</a>' if 1<=len(saved.requests)<=100 else ''
                    strategy_link=''
                    try:
                        editable_inputs(saved)
                        strategy_link=f' · <a href="/strategies/{match[1]}">Compare payment priorities</a>'
                        edit_link=f' · <a href="/edit/{match[1]}">Adjust a copy</a> · <a href="/inputs/{match[1]}">Review inputs and assumptions</a>'
                    except ValueError:
                        edit_link=''
                        edit_notice='<p>This saved plan uses inputs or a payment order that the simple editor cannot preserve. You can still review its results, timeline and payment request order.</p>'
                    return self.send_html(render(saved).replace('<main>',f'<main><p><a href="/plan/{match[1]}">Open simple plan view</a></p>',1).replace('</main>',payment_order(saved)+f'<section><h2>Keep a backup</h2><p>Download this scenario’s inputs, schedules and exact payment priorities as a local file. It contains any financial details you entered. It does not include other scenarios or a record of real payments.</p><p><a href="/backup/{match[1]}" download>Download scenario backup</a></p><p>Keep it somewhere you can find later. <a href="/restore">Restore a backup</a> when you need a new copy.</p></section></main>',1).replace('<main>','<main><p><a href="/">Back to saved scenarios</a> · <a href="/new">New scenario</a>'+edit_link+payment_link+f' · <a href="/timeline/{match[1]}">See the payment timeline</a>{strategy_link} · <a href="/forecast-terms/{match[1]}">Review future minimum terms</a> · <a href="/personal-forecast/{match[1]}">Plan future minimums</a> · <a href="/compare?left={match[1]}">Compare with another scenario</a></p>'+edit_notice,1))
                except FileNotFoundError:return self.reject('This saved scenario was not found.',404)
                except (ValueError,OSError,ArithmeticError):return self.reject('This scenario could not be validated. Its file has been kept unchanged.',422)
            return self.reject('Page not found.',404)

        def do_POST(self):
            if not self.valid_host():return self.reject('Local address required.',403)
            payoff_match=re.fullmatch(r'/payoff-preview/([0-9a-f]{32})',self.path)
            repeat_match=re.fullmatch(r'/payoff-repeat/([0-9a-f]{32})',self.path)
            repeat_save_match=re.fullmatch(r'/payoff-repeat-save/([0-9a-f]{32})',self.path)
            plan_save=re.fullmatch(r'/setup/([0-9a-f]{32})/plan/(settings|balances|preview|add-flow|import-cash|terms/(?:card|loan)-[1-9][0-9]?|flow/[0-9a-f]{32})',self.path)
            setup_save=re.fullmatch(r'/setup/([0-9a-f]{32})/(?:account/([0-9]+)|(add))',self.path)
            if not (payoff_match or repeat_match or repeat_save_match or setup_save or plan_save) and self.path not in ('/create','/create-example','/preview','/preview-example','/revise','/revise-example','/save-strategy','/restore-preview','/restore-save','/payment-preview','/payment-save','/forecast-terms-preview','/personal-forecast-preview','/my-money/save','/bills/save','/cash-until-payday/save','/cash-until-payday/budget-save','/paycheck-week/save','/paycheck-week/settings-save','/mixed-payoff/import-preview','/mixed-payoff/save','/setup/start','/setup/practice','/setup/restore-preview','/setup/restore-save','/weekly-check/save'):return self.reject('Page not found.',404)
            expected={f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}
            if self.headers.get('Origin') not in expected|{None}:return self.reject('Open the form from this local app.',403)
            if self.headers.get_content_type()!='application/x-www-form-urlencoded':return self.reject('Use the scenario form.',415)
            try:
                length=int(self.headers.get('Content-Length','0'))
                limit=3*weekly_snapshots.MAX_BYTES+4096 if self.path=='/weekly-check/save' else 3*setup_backup.MAX_BYTES+4096 if self.path in ('/setup/restore-preview','/setup/restore-save') else 3*MAX_BYTES+4096 if repeat_save_match or self.path in ('/restore-preview','/restore-save','/payment-save','/mixed-payoff/import-preview','/mixed-payoff/save') else MAX_FORM
                if not 0<length<=limit:raise ValueError()
            except ValueError:return self.reject('Form is empty or too large.',413)
            try:
                parsed=parse_qs(self.rfile.read(length).decode('utf-8'),keep_blank_values=True,strict_parsing=True,max_num_fields=200 if plan_save and plan_save[2]=='balances' else 140)
                if any(len(v)!=1 for v in parsed.values()):raise ValueError('Repeated fields')
                values={key:value[0] for key,value in parsed.items()}
            except (ValueError,UnicodeError):return self.reject('Malformed form.',400)
            if not secrets.compare_digest(values.pop('token','').encode('utf-8'),token.encode('ascii')):return self.reject('The form expired. Open a fresh form and try again.',403)
            if self.path=='/weekly-check/save':
                if set(values)!={'payload','signature'}:return self.reject('Use the weekly comparison save button.',400)
                payload=values['payload']
                if len(payload.encode())>weekly_snapshots.MAX_BYTES:return self.reject('Weekly comparison too large.',413)
                if not secrets.compare_digest(review_signature(payload,token).encode(),values['signature'].encode()):return self.reject('The reviewed weekly comparison changed. Reopen the current report before saving.',409)
                try:
                    snapshot=weekly_snapshots.parse(payload.encode())
                    with setup_lock:
                        current=weekly_check.load(directory)
                        if weekly_snapshots.fingerprint(current)!=weekly_snapshots.fingerprint(snapshot.report):return self.reject('The weekly reference changed after this preview. Reopen the current report before saving.',409)
                        identifier=weekly_snapshots.save(directory,snapshot)
                except FileNotFoundError:return self.reject('The current weekly reference is missing. Nothing was saved.',404)
                except (ValueError,ArithmeticError):return self.reject('This weekly comparison could not be validated. Nothing was saved.',422)
                except OSError:return self.reject('Could not save this weekly comparison locally.',500)
                self.send_response(303);self.send_header('Location','/weekly-checks/'+identifier);self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers();return
            if self.path in ('/setup/restore-preview','/setup/restore-save'):
                saving=self.path=='/setup/restore-save'
                if set(values)!=({'payload','signature'} if saving else {'payload'}):return self.reject('Use the complete setup restore form.',400)
                payload=values['payload']
                if len(payload.encode())>setup_backup.MAX_BYTES:return self.send_html(setup_backup.form(token,'This complete setup exceeds the 1 MiB limit.'),413)
                if saving and not secrets.compare_digest(review_signature(payload,token).encode(),values['signature'].encode()):return self.reject('The reviewed setup changed. Preview it again before saving.',409)
                try:
                    backup=setup_backup.parse(payload.encode())
                    if not saving:return self.send_html(setup_backup.preview(backup,token))
                    with setup_lock:identifier=setup_backup.restore(directory,backup)
                except (ValueError,ArithmeticError,RecursionError):return self.send_html(setup_backup.form(token,'This is not a valid complete setup backup. Nothing was saved. Choose the complete backup downloaded from plan review.'),422)
                except OSError:return self.reject('Could not restore this setup locally. Existing setups have been kept.',500)
                self.send_response(303);self.send_header('Location','/setup/'+identifier+'/plan');self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers();return
            if plan_save:
                identifier=plan_save[1];action=plan_save[2];fingerprint=values.pop('fingerprint','')
                try:
                    with setup_lock:
                        wizard=payoff_setup.load(directory,identifier);planning=setup_plan.load(directory,identifier)
                        if not secrets.compare_digest(fingerprint.encode(),setup_plan.context(wizard,planning).encode()):return self.reject('Your accounts or planning inputs changed. Reopen this page before saving.',409)
                        clean=lambda data:{k:(None if v=='' else v) for k,v in data.items()}
                        destination='/setup/'+identifier+'/plan'
                        if action=='preview':
                            if values:return self.reject('Use the payoff calculation button.',400)
                            try:
                                run=setup_plan.build(wizard,planning,identifier)
                                html=mixed_payoff_runs.render_saved(run,save_section=mixed_payoff_runs.save_form(run,token))
                                html=html.replace('</main>','<p><a href="/setup/'+identifier+'/plan">Back to my plan inputs</a></p></main>',1)
                                return self.send_html(html)
                            except (ValueError,ArithmeticError) as exc:
                                return self.send_html(setup_plan_view.overview(wizard,planning,identifier,token,'The calculation needs review: '+str(exc)),422)
                        elif action=='balances':
                            try:changed=setup_plan.change_balances(wizard,planning,values)
                            except (ValueError,ArithmeticError):return self.send_html(setup_plan_view.balances_form(wizard,planning,identifier,token,values,'Check balances and protected amounts for whole cents, and check the dates. Debt balances cannot be negative. Nothing was saved.'),422)
                            payoff_setup.write(directory,identifier,changed,previous=wizard)
                            self.send_response(303);self.send_header('Location',destination);self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers();return
                        elif action=='settings':
                            if set(values)!=set(setup_plan.Settings.model_fields):return self.reject('Use the forecast settings form.',400)
                            try:updated=reconstruct(planning,settings=setup_plan.Settings.model_validate(clean(values)))
                            except (ValueError,ArithmeticError):return self.send_html(setup_plan_view.settings_form(wizard,planning,identifier,token,values,'Check the dates, timezone, whole-cent target and whole calendar-day delays.'),422)
                        elif action=='add-flow':
                            if set(values)!={'kind'} or values['kind'] not in ('income','expense','transfer','contribution'):return self.reject('Use an add-cash-event button.',400)
                            flow=setup_plan.Flow(flow_id=uuid4().hex,kind=values['kind'],name='New '+values['kind'])
                            updated=setup_plan.update_flow(planning,flow);destination+='/flow/'+flow.flow_id
                        elif action=='import-cash':
                            if values:return self.reject('Use the saved-cash review button.',400)
                            updated=setup_plan.import_cash(directory,wizard,planning)
                        elif action.startswith('terms/'):
                            account=action.split('/')[1]
                            a=next((a for a in wizard.accounts if a.account_id==account),None)
                            if a is None:return self.reject('This debt was not found.',404)
                            expected={'day_count','rounding','accrued'}|({'ordinary','previous_start','previous_close','next_close','next_due','close_day','due_day','original_minimum','minimum_floor','minimum_rate'} if a.kind=='card' else {'fees','due_day','monthly'})
                            if set(values)!=expected:return self.reject('Use the calculation terms form.',400)
                            try:updated=setup_plan.update_terms(planning,reconstruct(setup_plan.term_for(planning,account),**clean(values)))
                            except (ValueError,ArithmeticError):return self.send_html(setup_plan_view.terms_form(wizard,planning,identifier,account,token,values,'Check the statement dates, day numbers, rates, balances and rounding choices.'),422)
                        else:
                            flow=next((f for f in planning.flows if f.flow_id==action.split('/')[1]),None)
                            if flow is None:return self.reject('This cash event was not found.',404)
                            expected={'name','amount','first_date','cadence','clock','until','include','notes'}
                            if flow.kind!='income':expected.add('source')
                            if flow.kind!='expense':expected.add('destination')
                            if flow.kind in ('transfer','contribution'):expected|={'debit_days','credit_days','settlement_days'}
                            if set(values)!=expected:return self.reject('Use the cash event form.',400)
                            try:updated=setup_plan.update_flow(planning,reconstruct(flow,**(clean(values)|{'name':values['name'],'notes':values['notes']})))
                            except (ValueError,ArithmeticError):return self.send_html(setup_plan_view.flow_form(wizard,planning,identifier,flow,token,values,'Check the amount, dates, times, frequency and routing. Use explicit zero for a known zero.'),422)
                        setup_plan.save(directory,identifier,updated,planning)
                except FileNotFoundError:return self.reject('This account setup was not found.',404)
                except (ValueError,ArithmeticError):return self.reject('The planning update could not be validated. Previous inputs have been kept.',422)
                except OSError:return self.reject('The planning inputs could not be saved.',500)
                self.send_response(303);self.send_header('Location',destination);self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers();return
            if self.path=='/setup/practice':
                if values:return self.reject('Use the practice setup button.',400)
                try:
                    with setup_lock:identifier=payoff_setup.start(directory,payoff_setup.Counts(checking=1,savings=1,cards=1,loans=1),practice=True)
                except (ValueError,OSError):return self.reject('Could not start the practice setup.',500)
                self.send_response(303);self.send_header('Location','/setup/'+identifier+'/account/0');self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers();return
            if self.path=='/setup/start':
                try:
                    reuse=values.pop('reuse','')
                    if set(values)!={'checking','savings','cards','loans'} or reuse not in ('','yes') or any(not re.fullmatch(r'[0-9]{1,2}',v) for v in values.values()):raise ValueError('Enter a whole-number count from 0 to 20 for each account type')
                    counts=payoff_setup.Counts.model_validate({k:int(v) for k,v in values.items()})
                    with setup_lock:identifier=payoff_setup.start(directory,counts,reuse=='yes')
                    destination='/setup/'+identifier+'/account/0'
                except (ValueError,ArithmeticError) as exc:return self.send_html(payoff_setup.counts_form(token,values,'Check the account counts: use whole numbers from 0 to 20 and at most 20 bank accounts in total.',has_saved=(directory/'money_snapshot.json').exists()),422)
                except OSError:return self.reject('Could not save your account setup.',500)
                self.send_response(303);self.send_header('Location',destination);self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers();return
            if setup_save:
                fingerprint=values.pop('fingerprint','')
                try:
                    with setup_lock:
                        wizard=payoff_setup.load(directory,setup_save[1])
                        if not secrets.compare_digest(fingerprint.encode(),payoff_setup.fingerprint(wizard).encode()):return self.reject('This setup changed in another tab. Reopen it before saving.',409)
                        if setup_save[3]:
                            if set(values)!={'kind'}:return self.reject('Use an add-account button.',400)
                            updated=payoff_setup.add_account(wizard,values['kind'])
                            destination='/setup/'+setup_save[1]+'/account/'+str(updated.next_step)
                        else:
                            step=int(setup_save[2]);intent=values.pop('intent','')
                            if not 0<=step<len(wizard.accounts):return self.reject('This account step was not found.',404)
                            if set(values)!=set(payoff_setup.fields(wizard.accounts[step])):return self.reject('Use the account questions shown.',400)
                            try:updated=payoff_setup.change(wizard,step,values,intent)
                            except (ValueError,ArithmeticError) as exc:
                                message='Check the entered values. Leave unknown numbers blank, use whole cents for balances/payments, and check promotion details against the selected promotion type.'
                                return self.send_html(payoff_setup.account_form(wizard,setup_save[1],step,token,values,message),422)
                            destination='/setup/'+setup_save[1] if intent=='later' or updated.next_step==len(updated.accounts) else '/setup/'+setup_save[1]+'/account/'+str(updated.next_step)
                        updated=reconstruct(updated,revision=wizard.revision+1)
                        payoff_setup.write(directory,setup_save[1],updated,previous=wizard)
                except FileNotFoundError:return self.reject('This account setup was not found.',404)
                except (ValueError,ArithmeticError):return self.reject('The setup could not be updated. Its previous version has been kept.',422)
                except OSError:return self.reject('Could not save this account. Your previous version has been kept.',500)
                self.send_response(303);self.send_header('Location',destination);self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers();return
            if self.path=='/mixed-payoff/import-preview':
                if set(values)!={'name','inputs'}:return self.reject('Use the combined input review form.',400)
                try:
                    run=mixed_payoff_runs.review(values['name'],values['inputs'].encode())
                    return self.send_html(mixed_payoff_runs.render_saved(run,save_section=mixed_payoff_runs.save_form(run,token)))
                except (ValueError,ArithmeticError):return self.send_html(mixed_payoff_runs.import_form(token,values['name'],values['inputs'],'The supplied inputs could not be validated. Check the contract terms, dates, funding routes and decimal-string amounts. Nothing was saved.'),422)
            if self.path=='/mixed-payoff/save':
                if set(values)!={'payload','signature'}:return self.reject('Use the reviewed combined payoff save button.',400)
                if len(values['payload'].encode())>MAX_BYTES:return self.reject('Combined payoff run is too large.',413)
                if not secrets.compare_digest(values['signature'].encode('utf-8'),review_signature(values['payload'],token).encode('ascii')):
                    return self.reject('The combined payoff review changed. Calculate it again before saving.',409)
                try:identifier=mixed_payoff_runs.save(directory,mixed_payoff_runs.parse(values['payload'].encode()))
                except (ValueError,ArithmeticError):return self.reject('The combined payoff run could not be validated. Nothing was saved.',422)
                except OSError:return self.reject('Could not save the combined payoff run locally.',500)
                self.send_response(303);self.send_header('Location','/mixed-payoff-run/'+identifier);self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers();return
            if repeat_save_match:
                if set(values)!={'payload','signature'}:return self.reject('Use the reviewed payoff save button.',400)
                if len(values['payload'].encode())>MAX_BYTES:return self.reject('Payoff run is too large.',413)
                if not secrets.compare_digest(values['signature'].encode('utf-8'),review_signature(values['payload'],token).encode('ascii')):
                    return self.reject('The payoff review changed. Calculate it again before saving.',409)
                try:
                    run=payoff_runs.parse(values['payload'].encode())
                    if run.source_id!=repeat_save_match[1]:return self.reject('The payoff source changed.',409)
                    current=load_scenario(directory/(run.source_id+'.json'))
                    if strategy_fingerprint(current)!=strategy_fingerprint(run.source):
                        return self.reject('The original saved plan changed. Recalculate before saving this run.',409)
                    identifier=payoff_runs.save(directory,run)
                except FileNotFoundError:return self.reject('The source plan was not found. Nothing was saved.',404)
                except (ValueError,ArithmeticError):return self.reject('The payoff run could not be validated. Nothing was saved.',422)
                except OSError:return self.reject('Could not save the payoff run locally.',500)
                self.send_response(303);self.send_header('Location','/payoff-run/'+identifier);self.send_header('Content-Length','0');self.end_headers();return
            if repeat_match:
                fingerprint=values.pop('fingerprint','')
                try:
                    source=repeat_match[1];scenario=load_scenario(directory/(source+'.json'))
                    if not secrets.compare_digest(fingerprint.encode('utf-8'),strategy_fingerprint(scenario).encode('ascii')):
                        return self.reject('The saved plan changed. Reopen it before repeating the calendar.',409)
                    try:
                        expanded,section=payoff_repeat.calculate(scenario,values)
                        run=payoff_runs.PayoffRun(source_id=source,source=scenario,expanded=expanded)
                        section+=payoff_runs.save_form(run,token)+payoff_repeat.form_section(scenario,source,token,values)
                    except (ValueError,ArithmeticError) as exc:
                        return self.send_html(saved_plan(scenario,source,payoff_repeat.form_section(scenario,source,token,values,str(exc))),422)
                    return self.send_html(saved_plan(scenario,source,section,payoff_preview=True))
                except FileNotFoundError:return self.reject('The saved plan was not found.',404)
                except (ValueError,ArithmeticError):return self.reject('This saved plan could not be repeated. Its file has been kept.',422)
                except OSError:return self.reject('Could not open the saved plan.',500)
            if payoff_match:
                if set(values)!={'fingerprint','payment_target'}:return self.reject('Use the payoff target form.',400)
                source=payoff_match[1]
                try:
                    scenario=load_scenario(directory/(source+'.json'))
                    if not secrets.compare_digest(values['fingerprint'].encode('utf-8'),strategy_fingerprint(scenario).encode('ascii')):
                        return self.reject('The saved plan changed. Reopen it before calculating payoff.',409)
                    try:section=payoff_view.calculate_section(scenario,values['payment_target'])
                    except (ValueError,ArithmeticError) as exc:
                        return self.send_html(saved_plan(scenario,source,payoff_view.form_section(scenario,source,token,value=values['payment_target'],error=str(exc))),422)
                    section+=payoff_view.form_section(scenario,source,token,value=values['payment_target'])+payoff_repeat.form_section(scenario,source,token)
                    return self.send_html(saved_plan(scenario,source,section,payoff_preview=True))
                except FileNotFoundError:return self.reject('The saved plan was not found.',404)
                except (ValueError,ArithmeticError):return self.reject('The saved plan could not be calculated. Its file has been kept.',422)
                except OSError:return self.reject('Could not open the saved plan.',500)
            if self.path in ('/paycheck-week/save','/paycheck-week/settings-save'):
                fingerprint=values.pop('fingerprint','')
                try:
                    with money_lock,bills_lock,cash_lock:
                        if self.path.endswith('/settings-save'):
                            original=paycheck_week.load_settings(directory)
                            if not secrets.compare_digest(payday_cash.digest(original).encode(),fingerprint.encode('utf-8')):
                                return self.reject('The paycheck settings changed. Reopen them before saving.',409)
                            try:
                                updated=paycheck_week.change(original,values)
                                candidate=paycheck_week.WeekInputs(base=payday_cash.load_inputs(directory),settings=updated)
                                paycheck_week.calculate(candidate)
                                paycheck_week.calculate(candidate,bills_first=True)
                            except (ValueError,ArithmeticError):return self.send_html(paycheck_week.form(original,token,values,'Use whole-cent amounts, nonnegative transfers/cushions, and whole calendar-day delays from 0 to 14. KC balance/date must both be blank if unknown, or match the reported starting date in My Money.'),422)
                            paycheck_week.save_settings(directory,updated)
                            destination='/paycheck-week'
                        else:
                            if values:return self.reject('Use the week draft save button.',400)
                            inputs=paycheck_week.load_inputs(directory)
                            if not secrets.compare_digest(payday_cash.digest(inputs).encode(),fingerprint.encode('utf-8')):
                                return self.reject('Your balances, bills, cushions or paycheck settings changed. Reopen the week view.',409)
                            id_=paycheck_week.save_draft(directory,inputs)
                            destination='/week-draft/'+id_
                    self.send_response(303);self.send_header('Location',destination);self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers();return
                except FileNotFoundError:return self.reject('Required week-draft inputs were not found. Nothing saved.',404)
                except (ValueError,ArithmeticError) as exc:return self.reject(str(exc),422)
                except OSError:return self.reject('Could not save the week draft. Check the local data folder.',500)
            if self.path in ('/cash-until-payday/save','/cash-until-payday/budget-save'):
                fingerprint=values.pop('fingerprint','')
                try:
                    with money_lock,bills_lock,cash_lock:
                        if self.path.endswith('/budget-save'):
                            original=payday_cash.load_budget(directory)
                            if not secrets.compare_digest(payday_cash.digest(original).encode(),fingerprint.encode('utf-8')):
                                return self.reject('The spending cushions changed. Reopen them before saving.',409)
                            try:
                                if set(values)!={'food','fuel'}:raise ValueError('Use the spending cushion form.')
                                updated=payday_cash.EverydayBudget(**values)
                            except (ValueError,ArithmeticError):return self.send_html(payday_cash.budget_form(original,token,values,'Use nonnegative whole-cent amounts for food and fuel.'),422)
                            payday_cash.save_budget(directory,updated)
                            destination='/cash-until-payday'
                        else:
                            if values:return self.reject('Use the cash-draft save button.',400)
                            inputs=payday_cash.load_inputs(directory)
                            if not secrets.compare_digest(payday_cash.digest(inputs).encode(),fingerprint.encode('utf-8')):
                                return self.reject('Your balances, bills or cushions changed. Reopen the cash view before saving.',409)
                            id_=payday_cash.save_draft(directory,inputs)
                            destination='/cash-draft/'+id_
                    self.send_response(303);self.send_header('Location',destination);self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers();return
                except FileNotFoundError:return self.reject('Required cash-draft inputs were not found. Nothing saved.',404)
                except (ValueError,ArithmeticError) as exc:return self.reject(str(exc),422)
                except OSError:return self.reject('Could not save the cash draft. Check the local data folder.',500)
            if self.path=='/bills/save':
                fingerprint=values.pop('fingerprint','');bill_id=values.pop('bill_id','')
                if not re.fullmatch(r'[a-z0-9-]{1,60}',bill_id):return self.reject('Choose a bill from the calendar.',400)
                try:
                    with bills_lock:
                        book=bills.load(directory)
                        if not secrets.compare_digest(bills.fingerprint(book).encode(),fingerprint.encode('utf-8')):
                            return self.reject('The bill draft changed in another window. Reopen the bill calendar.',409)
                        try:updated=bills.change(book,bill_id,values)
                        except (ValueError,ArithmeticError):return self.send_html(bills.form(book,bill_id,token,values,'Use a whole-cent amount, a valid date if supplied, and one of the listed choices. Included bills need a date and funding source.'),422)
                        bills.save(directory,updated)
                    self.send_response(303);self.send_header('Location','/bills');self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers();return
                except FileNotFoundError:return self.reject('No bill draft was found.',404)
                except KeyError:return self.reject('This bill was not found.',404)
                except (ValueError,ArithmeticError):return self.reject('The bill draft could not be validated. Nothing was replaced.',422)
                except OSError:return self.reject('Could not save the bill draft. Check the local data folder.',500)
            if self.path=='/my-money/save':
                fingerprint=values.pop('fingerprint','')
                try:
                    with money_lock:
                        original=my_money.load(directory)
                        if not secrets.compare_digest(my_money.fingerprint(original).encode(),fingerprint.encode('utf-8')):
                            return self.reject('These figures changed in another window. Reopen My Money before updating.',409)
                        try:updated=my_money.change(original,values)
                        except (ValueError,ArithmeticError):return self.send_html(my_money.form(original,token,values,'Use valid dates and whole-cent amounts; cushion, card and paycheck amounts cannot be negative.'),422)
                        my_money.save(directory,updated)
                    self.send_response(303);self.send_header('Location','/my-money');self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers()
                    return
                except FileNotFoundError:return self.reject('No starting picture was found. Nothing was saved.',404)
                except (ValueError,OSError,ArithmeticError):return self.reject('Could not update your starting picture. Check the local data folder.',422)
            if self.path=='/personal-forecast-preview':
                source=values.pop('source','');fingerprint=values.pop('fingerprint','')
                if not re.fullmatch(r'[0-9a-f]{32}',source):return self.reject('Choose a saved plan first.',400)
                try:
                    original=load_scenario(directory/(source+'.json'))
                    if not secrets.compare_digest(strategy_fingerprint(original).encode(),fingerprint.encode('utf-8')):
                        return self.reject('The original changed. Reopen the form.',409)
                    try:return self.send_html(personal_forecast_preview(original,source,values))
                    except (ValueError,ArithmeticError) as exc:
                        return self.send_html(personal_forecast_form(original,source,token,values,str(exc)),422)
                except FileNotFoundError:return self.reject('The saved plan was not found.',404)
                except (ValueError,ArithmeticError) as exc:return self.reject(str(exc),422)
                except OSError:return self.reject('Could not read the saved plan.',500)
            if self.path=='/forecast-terms-preview':
                source=values.pop('source','');fingerprint=values.pop('fingerprint','')
                if not re.fullmatch(r'[0-9a-f]{32}',source):return self.reject('Choose a saved plan first.',400)
                try:
                    original=load_scenario(directory/(source+'.json'))
                    if not secrets.compare_digest(strategy_fingerprint(original).encode(),fingerprint.encode('utf-8')):
                        return self.reject('The original changed. Reopen the form.',409)
                    candidate=change_terms(original,values)
                    return self.send_html(terms_preview(original,candidate,token))
                except FileNotFoundError:return self.reject('The saved plan was not found.',404)
                except (ValueError,ArithmeticError):return self.reject('Check all values, source choices and dates. Nothing was saved. Use Back to correct the form.',422)
                except OSError:return self.reject('Could not read the saved plan.',500)
            if self.path=='/payment-preview':
                source=values.pop('source','');fingerprint=values.pop('fingerprint','')
                if not re.fullmatch(r'[0-9a-f]{32}',source):return self.reject('Choose a saved scenario first.',400)
                try:
                    original=load_scenario(directory/(source+'.json'))
                    if not secrets.compare_digest(strategy_fingerprint(original).encode(),fingerprint.encode('utf-8')):
                        return self.reject('The original changed. Reopen it before editing.',409)
                    try:
                        candidate=change_payments(original,values)
                        return self.send_html(payment_preview(candidate,original,source,token))
                    except (ValueError,ArithmeticError):
                        return self.send_html(payment_form(original,source,token,values,'Enter a name and positive whole-cent amounts. Nothing was saved.'),422)
                except FileNotFoundError:return self.reject('The original was not found.',404)
                except (ValueError,ArithmeticError):return self.reject('The saved plan could not be validated. Its file has been kept.',422)
                except OSError:return self.reject('Could not open the original scenario.',500)
            if self.path in ('/restore-preview','/restore-save','/payment-save'):
                saving=self.path in ('/restore-save','/payment-save')
                if set(values)!=({'payload','signature'} if saving else {'payload'}):
                    return self.reject('Use the backup restore form.',400)
                payload=values['payload']
                if len(payload.encode('utf-8'))>MAX_BYTES:
                    return self.send_html(restore_form(token,'This backup exceeds the 4 MiB limit.'),413)
                if saving and not secrets.compare_digest(review_signature(payload,token).encode('ascii'),values['signature'].encode('utf-8')):
                    return self.reject('The reviewed backup changed. Preview it again before saving.',409)
                try:
                    restored=parse_scenario(payload.encode('utf-8'))
                    if not saving:return self.send_html(restore_preview(restored,token))
                    id_=uuid4().hex
                    save_scenario(restored,directory/(id_+'.json'))
                except (ValueError,ArithmeticError,RecursionError):
                    return self.send_html(restore_form(token,'This file is not a supported, valid Debt Shredder scenario backup. Nothing was saved. Choose the original downloaded JSON file.'),422)
                except OSError:return self.reject('Could not save locally. Check disk space and folder permissions.',500)
                return self.redirect_saved(id_, simple=self.path=='/payment-save')
            if self.path=='/save-strategy':
                if set(values)!={'source','choice','fingerprint'} or not re.fullmatch(r'example|[0-9a-f]{32}',values.get('source','')):
                    return self.reject('Use the alternative review page to save.',400)
                try:
                    original=strategy_example() if values['source']=='example' else load_scenario(directory/(values['source']+'.json'))
                    candidate=selected_strategy(original,values['choice'])
                    if not secrets.compare_digest(strategy_fingerprint(candidate).encode('ascii'), values['fingerprint'].encode('utf-8')):
                        return self.reject('The scenario changed since review. Reopen the comparison and review it again before saving.',409)
                    id_=uuid4().hex
                    save_scenario(candidate,directory/(id_+'.json'))
                except FileNotFoundError:return self.reject('The source scenario was not found. Nothing was saved.',404)
                except (ValueError,ArithmeticError):return self.reject('This alternative could not be validated. Nothing was saved.',422)
                except OSError:return self.reject('Could not save locally. Check disk space and folder permissions.',500)
                return self.redirect_saved(id_)
            sample=self.path.endswith('-example')
            if self.path in ('/revise','/revise-example'):
                return self.send_html(manual_form(token,values,sample=sample))
            try:
                scenario=ManualScenario.model_validate(values).scenario()
                if sample:scenario=reconstruct(scenario,origin='synthetic_demo')
                if self.path in ('/preview','/preview-example'):
                    return self.send_html(render_preview(scenario,values,token,sample=sample))
                id_=uuid4().hex
                save_scenario(scenario,directory/(id_+'.json'))
            except ValidationError as exc:
                errors=validation_messages(exc.errors(include_input=False))
                return self.send_html(manual_form(token,values,errors,sample=sample),422)
            except (ValueError,ArithmeticError) as exc:
                return self.send_html(manual_form(token,values,[str(exc)],sample=sample),422)
            except OSError:
                return self.send_html(manual_form(token,values,['Could not save locally. Check available disk space and folder permissions.'],sample=sample),500)
            self.redirect_saved(id_)

        def redirect_saved(self, id_, *, simple=False):
            self.send_response(303)
            self.send_header('Location',('/plan/' if simple else '/scenario/')+id_)
            self.send_header('Content-Length','0')
            self.send_header('Cache-Control','no-store')
            self.end_headers()

    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.timeout=1
    return server


def main():
    parser=argparse.ArgumentParser(description='Debt Shredder local dashboard')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--data-dir',type=Path,default=Path('local_scenarios'))
    args=parser.parse_args()
    server=make_server(args.data_dir,args.port)
    print(f'Debt Shredder: http://127.0.0.1:{server.server_port}',flush=True)
    print(f'Scenarios stay in {args.data_dir.resolve()}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
