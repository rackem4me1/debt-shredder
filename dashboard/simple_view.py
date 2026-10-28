"""Plain-language front door and result screens over existing calculations."""
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo
from dashboard.forms import shell
from dashboard.report import text, money, summary, card_label
from engine.common import decimal_context

STYLE='''<style>
main{max-width:1140px}header{background:#102f36;padding:1.2rem max(1.5rem,calc((100vw - 1092px)/2))}body{background:#f2f5f3;color:#183b40}h1{font-size:clamp(2rem,5vw,3.3rem);line-height:1.12;letter-spacing:-.045em;margin:.6rem 0 1rem}h2{letter-spacing:-.025em}.eyebrow{font-size:.8rem;font-weight:750;letter-spacing:.1em;text-transform:uppercase;color:#46645e}.hero{padding:1.5rem 0 1rem}.hero p{max-width:660px;font-size:1.1rem;color:#48615f}.actions{display:flex;gap:.8rem;flex-wrap:wrap;margin:1.5rem 0}.action{display:inline-block;padding:.8rem 1.15rem;background:#146457;color:#fff;text-decoration:none;border-radius:9px;font-weight:650}.secondary{background:#e0ebe6;color:#174f44}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(230px,100%),1fr));gap:1rem;margin:1.2rem 0}.tile{background:white;border:1px solid #d5e1da;border-radius:14px;padding:1.4rem}.tile h2,.tile h3{font-size:1rem;margin:0 0 .7rem}.value{font-size:2rem;letter-spacing:-.04em;font-weight:720;display:block}.tile p,.muted{color:#506965;font-size:.95rem}.banner{padding:1rem 1.2rem;border-radius:10px;background:#dceee6;color:#174c3b}.warning{background:#fff0dc;color:#70410d}.sample{display:inline-block;padding:.35rem .7rem;background:#e4e9f7;color:#374775;border-radius:25px;font-size:.85rem}.steps{padding-left:1.3rem}section{border-color:#d5e1da;border-radius:14px}details{margin:1.2rem 0;padding:1.2rem;background:white;border:1px solid #d5e1da;border-radius:12px}summary{cursor:pointer;font-weight:650}.payment-list{list-style:none;padding:0}.payment-list li{display:flex;justify-content:space-between;gap:1rem;border-bottom:1px solid #e0e8e2;padding:1rem 0;margin:0}.payment-list strong{display:block}.payment-list span{display:block}.payment-list .number{font-size:1.15rem;white-space:nowrap}.plan-list{list-style:none;padding:0}.plan-list li{padding:1rem 0;border-bottom:1px solid #e0e8e2}.plan-list a{font-weight:650;font-size:1.1rem}.bar{height:10px;background:#e4eae7;border-radius:8px;overflow:hidden;margin:.6rem 0}.bar div{height:100%;background:#26836e}a{color:#165e52}.action{color:white}.secondary{color:#174f44}@media(max-width:600px){main{padding:1rem}section{padding:1rem}.payment-list li{flex-wrap:wrap}}
</style>'''


def page(title,content):
    return shell(title,STYLE+content).replace(' · Local scenarios',' · Your debt planner')


def tile(label,value,detail):
    return '<div class="tile"><h2>'+text(label)+'</h2><strong class="value">'+text(value)+'</strong><p>'+text(detail)+'</p></div>'


@decimal_context
def saved_plan(scenario,id_,payoff_section='',*,payoff_preview=False):
    data=summary(scenario)
    accepted=sum((Decimal(d['accepted']) for d in data['decisions']),Decimal(0))
    requested=sum((Decimal(d['requested']) for d in data['decisions']),Decimal(0))
    debt=sum((Decimal(d['posted_balance']) for d in data['debts']),Decimal(0))
    unposted=sum((Decimal(d['unposted_interest']) for d in data['debts']),Decimal(0))
    missed=data['missed_minimum_account_ids']
    warning=bool(missed) or accepted<requested or data['cash_status']!='healthy' or not data['decisions']
    alerts=[]
    if missed:alerts.append('At least one card misses a minimum-payment due date in this forecast.')
    if accepted<requested:alerts.append(money(requested-accepted)+' of requested payments cannot be applied.')
    if data['cash_status']!='healthy':alerts.append('Cash falls short somewhere in the forecast. Check the timeline before relying on the ending balance.')
    if not data['decisions']:alerts.append('This plan has no payment requests yet.')
    dates={r.request_id:r for r in scenario.requests}
    zone=ZoneInfo(data['time_zone'])
    def date_label(iso):return datetime.fromisoformat(iso).astimezone(zone).strftime('%b %d, %Y')
    rows=[]
    for d in data['decisions']:
        request=dates[d['request_id']]
        rows.append('<li><div><strong>'+text(card_label(scenario,d['debt_account_id']))+'</strong><span>Submit '+text(request.initiated_at.astimezone(zone).strftime('%b %d'))+' · card credited '+text(request.credited_at.astimezone(zone).strftime('%b %d'))+'</span><small>'+text(d['kind'].title())+' portion · requested '+money(Decimal(d['requested']))+'</small></div><div class="number"><strong>'+money(Decimal(d['accepted']))+'</strong><small>fits this forecast</small></div></li>')
    cash=''.join(tile(r['account_id'],money(Decimal(r['cleared'])),'Cash floor setting: '+money(Decimal(r['floor']))+'. Reserved: '+money(Decimal(r['reserved']))+'. Check alerts above; these settings do not prove the cash is fully funded.') for r in data['cash'])
    return page(scenario.name,'<div class="hero"><span class="sample">'+('Practice numbers' if scenario.origin=='synthetic_demo' else 'Your saved estimates')+'</span><h1>'+text(scenario.name)+'</h1><p>'+('Compare the two payoff strategies below. Your original saved payments remain available in the closed section.' if payoff_preview else 'Here is what this plan would do with the payments and bills you entered.')+'</p></div>'+
        payoff_section+('<details><summary>Original saved payment plan</summary>' if payoff_preview else '')+'<div class="banner '+('warning' if warning else '')+'"><strong>'+('This plan needs a closer look.' if warning else 'The entered payments fit this forecast.')+'</strong><p>'+text(' '.join(alerts) if alerts else 'No missed minimums or cash shortages were found within the supplied dates.')+'</p></div>'+
        '<div class="cards">'+tile('Payments that fit',money(accepted),'Out of '+money(requested)+' requested. No money has moved.')+tile('Debt at the end',money(debt),'Plus '+money(unposted)+' in interest not yet posted.')+'</div>'+
        '<section><h2>Your payment plan</h2><p>Forecast from '+date_label(data['debt_start'])+' through '+date_label(data['debt_end'])+'. Dates shown in '+text(data['time_zone'])+'.</p><ul class="payment-list">'+(''.join(rows) or '<li>No payments entered.</li>')+'</ul><p class="muted">Minimum and extra portions may appear separately. They are parts of the requested payments, not additional bills.</p></section>'+
        '<h2>Money left in your accounts</h2><p class="muted">After the supplied cash activity through '+date_label(data['cash_end'])+'. Cash stays attached to each account.</p><div class="cards">'+cash+'</div>'+
        '<section><h2>What to do here</h2><p>Review the dates and amounts above. If they do not match what you intended, adjust the plan before using it.</p><div class="actions">'+('<a class="action" href="/payment-edit/'+id_+'">Adjust payment amounts</a>' if 1<=len(scenario.requests)<=100 else '')+'<a class="action secondary" href="/timeline/'+id_+'">See money coming and going</a></div><p class="muted">Only entered bills and payments are included. This is a planning estimate, not a bank balance or a full payoff recommendation.</p></section>'+
        '<details><summary>More details and planning tools</summary><p><a href="/scenario/'+id_+'">Full report and editing tools</a></p><p><a href="/forecast-terms/'+id_+'">Review future minimum terms</a></p><p><a href="/personal-forecast/'+id_+'">Build a longer minimum-payment forecast</a></p><p><a href="/backup/'+id_+'">Download a backup</a></p></details><p><a href="/">Back home</a></p>'+('</details><p><a href="/plan/'+id_+'">Return to saved plan</a> · <a href="/">Back home</a></p>' if payoff_preview else ''))


@decimal_context
def walkthrough(shortage=False):
    from dashboard.portfolio_forecast import practice_forecast
    schedules,opening,result=practice_forecast(shortage)
    paid=sum((d.accepted for d in result.decisions),Decimal(0))
    ending=result.liquidity.points[-1].positions[0].cleared
    posted=sum((d.account.total_balance() for d in result.debts),Decimal(0))
    months=[]
    for month,name in ((1,'January'),(2,'February'),(3,'March')):
        ids={r.request_id for r in result.requests if r.credited_at.month==month}
        decisions=[d for d in result.decisions if d.request_id in ids]
        total=sum((d.accepted for d in decisions),Decimal(0));wanted=sum((d.requested for d in decisions),Decimal(0))
        percent=total/wanted*100 if wanted else Decimal(0)
        months.append('<li><div><strong>'+name+' 20</strong><span>Two card minimums: '+money(wanted)+' requested</span><div class="bar"><div style="width:'+str(percent)+'%"></div></div><small>'+('Minimums fit' if total==wanted else 'Not enough cash for all minimums')+'</small></div><strong class="number">'+money(total)+' applied</strong></li>')
    return page('See how your plan works','<div class="hero"><span class="sample">Sample money · Nothing to enter</span><h1>Two cards. One clear plan.</h1><p>Imagine you have '+money(opening.cleared)+' in checking and two cards owing $1,000 each. Here is how the app plans their minimum payments.</p></div>'+
        '<div class="actions"><a class="action '+('secondary' if shortage else '')+'" href="/walkthrough">With $400 in checking</a><a class="action '+('' if shortage else 'secondary')+'" href="/walkthrough-shortage">What if I only had $200?</a></div>'+
        '<div class="banner '+('warning' if shortage else '')+'"><strong>'+('The bill and cushion leave only $30 for card payments.' if shortage else 'Both cards’ minimum payments fit.')+'</strong><p>'+('Some minimum due dates will be missed. The app shows the shortage instead of treating protected money as available.' if shortage else 'The app sets aside the bill and protected cash before allocating money to the cards.')+'</p></div>'+
        '<div class="cards">'+tile('Keep protected','$120.00','$100 cushion plus $20 reserved for another purpose.')+tile('Bill to cover','$50.00','Due January 25, paid from the same checking account.')+tile('Card payments',money(paid),'Total applied across January, February and March.')+'</div>'+
        '<section><h2>Your next three months</h2><ul class="payment-list">'+''.join(months)+'</ul><p class="muted">Dates are supplied in this example. Payments are forecasts, not scheduled bank transactions.</p></section>'+
        '<div class="cards">'+tile('Checking at the end',money(ending),'Includes the $120 protected above. No new income is assumed.')+tile('Combined card debt',money(posted),'Interest is included. This is minimum-only planning, not a full payoff strategy.')+'</div>'+
        '<section><h2>That’s the idea.</h2><p>See what fits, keep bill money protected, and spot problems before making a payment. Your own saved plan uses your entered numbers.</p><div class="actions"><a class="action" href="/#saved-plans">Open my saved plans</a><a class="action secondary" href="/new">Enter my numbers</a></div></section>'+
        '<details><summary>How this example was calculated</summary><p>Practice data only: January–March 2026; cash checks through June 18. Two $1,000 cards, 36.5% APR, daily interest /365, no grace, fees or purchases. Minimum is the smaller of debt and the greater of $25 or 1% of posted balance plus billed interest. Card 1 has the supplied priority. Payment stages coincide on each month’s20th in UTC. No April payment is included.</p><p><a href="/portfolio-forecast-example">See every calculation and missed due date</a></p></details><p><a href="/">Back home</a></p>')
