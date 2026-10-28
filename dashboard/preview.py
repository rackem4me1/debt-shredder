"""Stateless preview; saving revalidates the exact submitted inputs."""
from html import escape
from dashboard.report import render
from dashboard.cash_review import cash_review


def render_preview(scenario, values, token, *, sample=False):
    hidden = ''.join(f'<input type="hidden" name="{escape(key,quote=True)}" value="{escape(str(value),quote=True)}">'
                     for key,value in (values | {'token':token}).items())
    save = '/create-example' if sample else '/create'
    revise = '/revise-example' if sample else '/revise'
    controls = f'<form method="post" action="{save}">{hidden}<button type="submit">Save this scenario</button> <button type="submit" formaction="{revise}">Change inputs</button></form>'
    intro = '<h1>Preview — nothing saved yet</h1><p>Review every cash date and the payment estimate below. Saving records a local what-if; it does not move money.</p>'
    return render(scenario).replace('<main>','<main>'+intro+cash_review(scenario),1).replace('</main>',controls+'</main>',1).replace('</style>', 'button{font:inherit;padding:.7rem 1rem;border:1px solid #154d80;border-radius:4px;background:#154d80;color:white;cursor:pointer;margin:.5rem .5rem .5rem 0}button:focus-visible{outline:3px solid #c47700;outline-offset:3px}</style>',1)
