"""Run with --demo or --input FILE; outputs exact decimal strings and dated CSVs."""
import argparse
import json
from pathlib import Path
from engine.payoff import PayoffInputs,compare_payoff
from payoff_exports import payment_csv


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON key')
        result[key]=value
    return result


def _parse_json(raw):
    if len(raw)>4*1024*1024:raise ValueError('Input exceeds 4 MiB')
    def reject(value):raise ValueError('Use decimal strings for money/rates; floats and nonfinite values are rejected')
    try:data=json.loads(raw,object_pairs_hook=_unique,parse_float=reject,parse_constant=reject)
    except RecursionError as exc:raise ValueError('Input nesting is too deep') from exc
    if not isinstance(data,dict) or type(data.get('version')) is not int or data['version']!=1:
        raise ValueError('Input requires integer version 1')
    return data


def parse_input(raw):return PayoffInputs.model_validate(_parse_json(raw))


def parse_template(raw):
    from engine.payoff_calendar import PayoffTemplate
    return PayoffTemplate.model_validate(_parse_json(raw))


def parse_loan_input(raw):
    from engine.loan_payoff import LoanPayoffInputs
    return LoanPayoffInputs.model_validate(_parse_json(raw))


def parse_mixed_input(raw):
    from engine.mixed_payoff import MixedPayoffInputs
    return MixedPayoffInputs.model_validate(_parse_json(raw))


def mixed_summary(comparison):
    return {'label':'Supplied-input estimate; one shared cash ledger; no bank actions',
        'comparison_note':comparison.comparison_note,'lowest_interest_strategy':comparison.lowest_interest_strategy,
        'results':[r.model_dump(mode='json',exclude={'cards','loans','liquidity'})|{
            'loans':[{'account_id':l.account_id,'projection':l.projection.model_dump(mode='json',exclude={'liquidity'})} for l in r.loans],
            'missed_card_due_dates':{c.account.account_id:[d.isoformat() for d in c.missed_due_dates] for c in r.cards},
            'ending_cash_accounts':{p.account_id:{'balance':str(p.cleared),'reserved':str(p.reserved),'above_floor':str(p.above_floor)} for p in r.liquidity.points[-1].positions},
            'cash_status':r.liquidity.status.value,'cash_horizon_end':r.liquidity.end.isoformat()} for r in comparison.results]}


def summary(comparison):
    return {'label':'Synthetic example or supplied-input estimate; no bank actions',
        'comparison_note':comparison.comparison_note,'lowest_interest_strategy':comparison.lowest_interest_strategy,
        'results':[r.model_dump(mode='json',exclude={'debts','liquidity'})|{
            'ending_checking':next((str(p.cleared) for p in r.liquidity.points[-1].positions if p.account_id=='checking'),None),
            'ending_cash_accounts':{p.account_id:{'balance':str(p.cleared),'reserved':str(p.reserved),'above_floor':str(p.above_floor)} for p in r.liquidity.points[-1].positions},
            'cash_horizon_end':r.liquidity.end.isoformat(),
            'cash_status':r.liquidity.status.value,
            'missed_due_dates':{d.account.account_id:[v.isoformat() for v in d.missed_due_dates] for d in r.debts}}
            for r in comparison.results]}


def run(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--demo',action='store_true');source.add_argument('--input',type=Path)
    source.add_argument('--template',type=Path,help='Explicit repeating payment, statement and cash rules')
    source.add_argument('--mixed-input',type=Path,help='Cards and supported loans under one shared target')
    source.add_argument('--mixed-demo',action='store_true',help='Two synthetic cards plus one loan sharing $300')
    source.add_argument('--loan-input',type=Path,help='Explicit simple-interest loan and due calendar')
    source.add_argument('--loan-demo',action='store_true',help='Synthetic principal-curtailment loan')
    parser.add_argument('--output-dir',type=Path,help='New directory for summary JSON and dated payment CSVs')
    parser.add_argument('--example-input',type=Path,help='Write the demo input to a new file (requires --demo)')
    args=parser.parse_args(argv)
    try:
        if args.mixed_input or args.mixed_demo:
            if args.example_input:raise ValueError('Use --output-dir to export mixed inputs')
            from engine.mixed_payoff import compare_mixed_payoff
            if args.mixed_demo:
                from demo_payoff import mixed_example
                value=mixed_example()
            else:
                with args.mixed_input.open('rb') as stream:value=parse_mixed_input(stream.read(4*1024*1024+1))
            result=compare_mixed_payoff(value);encoded=json.dumps(mixed_summary(result),indent=2)+'\n'
            if args.output_dir:
                args.output_dir.mkdir(parents=True,exist_ok=False)
                (args.output_dir/'inputs.json').write_text(value.model_dump_json(indent=2)+'\n')
                (args.output_dir/'summary.json').write_text(encoded)
                for plan in result.results:
                    (args.output_dir/(plan.strategy+'.csv')).write_text(payment_csv(plan))
            else:print(encoded,end='')
            return
        if args.loan_input or args.loan_demo:
            if args.example_input:raise ValueError('Use --output-dir to export the loan input')
            from engine.loan_payoff import plan_loan_payoff
            from payoff_exports import loan_payment_csv
            if args.loan_demo:
                from demo_payoff import loan_example
                value=loan_example()
            else:
                with args.loan_input.open('rb') as stream:value=parse_loan_input(stream.read(4*1024*1024+1))
            result=plan_loan_payoff(value)
            report=result.model_dump(mode='json',exclude={'liquidity'})
            report['cash_status']=result.liquidity.status.value
            report['ending_cash_accounts']={p.account_id:str(p.cleared) for p in result.liquidity.points[-1].positions}
            encoded=json.dumps(report,indent=2)+'\n'
            if args.output_dir:
                args.output_dir.mkdir(parents=True,exist_ok=False)
                (args.output_dir/'inputs.json').write_text(value.model_dump_json(indent=2)+'\n')
                (args.output_dir/'summary.json').write_text(encoded)
                (args.output_dir/'loan-payments.csv').write_text(loan_payment_csv(result))
                print('Saved loan payoff inputs and schedule to '+str(args.output_dir))
            else:print(encoded,end='')
            return
        expanded=None
        if args.example_input and not args.demo:raise ValueError('--example-input requires --demo')
        if args.demo:
            from demo_payoff import example
            value=example()
        elif args.template:
            from engine.payoff_calendar import expand_payoff_template
            with args.template.open('rb') as stream:template=parse_template(stream.read(4*1024*1024+1))
            expanded=expand_payoff_template(template);value=expanded.inputs
        else:
            with args.input.open('rb') as stream:value=parse_input(stream.read(4*1024*1024+1))
        result=compare_payoff(value)
        report=summary(result)
        if expanded is not None:
            report['calendar_assumption_note']=expanded.assumption_note
            report['generated_cycle_ids']=expanded.generated_cycle_ids
            report['excluded_payment_dates']=[d.isoformat() for d in expanded.excluded_payment_dates]
            report['pending_transfer_ids']=list(expanded.pending_transfer_ids)
        encoded=json.dumps(report,indent=2)+'\n'
        if args.example_input:
            with args.example_input.open('x') as stream:stream.write(value.model_dump_json(indent=2)+'\n')
        if args.output_dir:
            args.output_dir.mkdir(parents=True,exist_ok=False)
            (args.output_dir/'inputs.json').write_text(value.model_dump_json(indent=2)+'\n')
            if expanded is not None:(args.output_dir/'template.json').write_text(expanded.template.model_dump_json(indent=2)+'\n')
            (args.output_dir/'summary.json').write_text(encoded)
            for plan in result.results:
                (args.output_dir/(plan.strategy+'.csv')).write_text(payment_csv(plan))
            print('Saved payoff comparison and schedules to '+str(args.output_dir))
        else:print(encoded,end='')
    except (ValueError,OSError,ArithmeticError) as exc:parser.exit(2,'Payoff calculation not completed: '+str(exc)+'\n')


if __name__=='__main__':run()
