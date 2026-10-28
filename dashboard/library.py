"""Read-only scenario library with explicit local search and origin filtering."""
from urllib.parse import parse_qs
from dashboard.forms import shell
from dashboard.report import text
from dashboard.simple_view import page


def library_filters(query):
    if len(query)>2048:raise ValueError('Search is too long.')
    params=parse_qs(query,keep_blank_values=True,strict_parsing=True,max_num_fields=2)
    if set(params)-{'q','kind'} or any(len(v)!=1 for v in params.values()):
        raise ValueError('Use the saved-scenario search form.')
    q=params.get('q',[''])[0].strip()
    kind=params.get('kind',['all'])[0]
    if len(q)>120 or kind not in ('all','manual','synthetic_demo'):
        raise ValueError('Use a search of 120 characters or less and one of the listed filters.')
    return q,kind


def render_library(entries,query='',*,has_money=False,setup_resume=None,has_weekly_check=False):
    q,kind=library_filters(query)
    choices=''.join('<option value="'+value+'"'+(' selected' if kind==value else '')+'>'+label+'</option>' for value,label in [('all','All scenarios'),('manual','My manual estimates'),('synthetic_demo','Practice examples')])
    controls='<form method="get" action="/"><div class="grid"><label>Search by scenario or card name<input type="search" name="q" maxlength="120" value="'+text(q)+'"></label><label>Show<select name="kind">'+choices+'</select></label></div><button type="submit">Find scenarios</button> <a href="/">Clear search</a></form>'
    rows=[]
    for id_,saved in entries:
        if saved is None:
            if not q and kind=='all':rows.append('<li>Saved scenario '+text(id_[:8])+' could not be opened. Its file has been kept.</li>')
            continue
        if kind!='all' and saved.origin!=kind:continue
        if q.casefold() not in (' '.join((saved.name,*saved.card_names))).casefold():continue
        label='Practice example' if saved.origin=='synthetic_demo' else 'Manual estimates'
        rows.append('<li><a href="/plan/'+id_+'">'+text(saved.name)+'</a><small>'+label+' · '+str(len(saved.debts))+' card account(s) · Forecast '+text(saved.start.date())+' through '+text(saved.end.date())+'</small></li>')
    empty='No scenarios match this search.' if entries else 'No saved scenarios yet. Start with a practice example or restore a backup.'
    listing='<ul class="plan-list">'+''.join(rows)+'</ul>' if rows else '<p>'+empty+'</p>'
    money_link='<div class="banner"><strong>Your numbers are saved.</strong><p>See your reported checking, Bills Box, Quicksilver and next paycheck together.</p><a class="action" href="/my-money">Open My Money</a></div>' if has_money else ''
    if has_money and has_weekly_check:
        money_link='<details><summary>Earlier My Money snapshot</summary><p>These entries retain their original dates and may describe your earlier financial setup. The weekly system check uses a separate updated planning reference.</p><a href="/my-money">Open earlier My Money entries</a></details>'
    setup_actions=('<a class="action" href="/setup/'+setup_resume+'/plan">Continue my payoff plan</a><a class="action secondary" href="/setup/'+setup_resume+'">Review my saved accounts</a>' if setup_resume else '<a class="action" href="/setup">Set up my accounts</a><a class="action secondary" href="/setup/drafts">Continue account setup</a>')
    weekly_link='<section><h2>Your automated system</h2><p>Compare lower-pay weeks and flexible savings contributions using your updated planning reference.</p><a class="action" href="/weekly-check">Open weekly system check</a> · <a href="/weekly-checks">Saved weekly comparisons</a><p>This separate report does not update earlier money snapshots.</p></section>' if has_weekly_check else ''
    return page('Home', weekly_link+money_link+'<div class="hero"><span class="eyebrow">Debt Shredder</span><h1>Make your next payment clearer.</h1><p>See which payments fit, keep money for bills, and understand what happens next.</p><div class="actions">'+setup_actions+'<a class="action secondary" href="/walkthrough">Show me how it works</a><a class="action secondary" href="#saved-plans">Open my saved plans</a></div><p class="muted">The walkthrough uses sample money. You don’t need to fill out a form.</p></div><div class="cards"><div class="tile"><h2>1 · See the plan</h2><p>Start with a working example of two cards sharing one checking account.</p></div><div class="tile"><h2>2 · Check your money</h2><p>Your own plan shows the bills, cash cushion and payments you entered.</p></div><div class="tile"><h2>3 · Compare before paying</h2><p>Adjust payments and review the result. You stay in control of moving money.</p></div></div><section id="saved-plans"><h2>Your saved plans</h2><p>Choose a plan to see its plain-language summary. Practice examples are labeled below.</p>'+listing+'<details><summary>Find a saved plan</summary>'+controls+'</details><div class="actions"><a class="action secondary" href="/new">Enter my numbers</a><a href="/payoff-runs">Saved card payoff runs</a><a href="/mixed-payoff-runs">Saved cards-and-loan runs</a><a href="/restore">Restore a backup</a></div></section><details><summary>More examples and planning tools</summary><p><a href="/practice">Practice with sample numbers</a></p><p><a href="/demo">View the shared-cash example</a></p><p><a href="/compare">Compare saved scenarios</a></p><p><a href="/strategies-example">Try payment priorities</a></p><p><a href="/multimonth-example">See a three-statement forecast</a></p><p><a href="/mixed-payoff-example">Compare cards and a loan sharing one budget</a></p><p><a href="/loan-payoff-example">See a simple-interest loan payoff</a></p><p><a href="/portfolio-forecast-example">See a multi-card forecast</a></p></details><p class="muted">A local planning app in development. Estimates depend on the information entered. No bank connection or automatic payments.</p>')
