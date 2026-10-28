"""Exact dated payment CSV, shared by the headless command and local app."""
import csv
from io import StringIO


def _cell(value):
    # User-entered identifiers must remain text when opened in a spreadsheet.
    value=str(value)
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')) else value


def payment_csv(plan,label=None):
    stream=StringIO(newline='');writer=csv.writer(stream)
    writer.writerow(('slot','account','initiate','credit','debit','settle','minimum_required','minimum_paid','extra_paid','total_paid','funding_account'))
    for payment in plan.payments:
        if not payment.total_paid and not payment.minimum_required:continue
        account=label(payment.account_id) if label else payment.account_id
        writer.writerow((_cell(payment.slot_id),_cell(account),payment.initiated_at.isoformat(),payment.credited_at.isoformat(),
            payment.debited_at.isoformat(),payment.settled_at.isoformat(),str(payment.minimum_required),str(payment.minimum_paid),
            str(payment.extra_paid),str(payment.total_paid),_cell(payment.source_account_id or '')))
    return stream.getvalue()


def loan_payment_csv(plan):
    stream=StringIO(newline='');writer=csv.writer(stream)
    fields=('slot_id','source_account_id','initiated_at','credited_at','debited_at','settled_at',
        'minimum_required','minimum_paid','total_paid','fees_paid','interest_paid','principal_paid',
        'principal_remaining','interest_remaining','fees_remaining','interest_posting_adjustment')
    writer.writerow(fields)
    for p in plan.payments:
        row=[]
        for field in fields:
            value=getattr(p,field)
            row.append(_cell(value) if field in ('slot_id','source_account_id') else value.isoformat() if hasattr(value,'isoformat') else str(value))
        writer.writerow(row)
    return stream.getvalue()
